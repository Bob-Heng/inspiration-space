"""灵感 CRUD：录入即存档并生成关联草稿观点，id 即编号；docx 导入（TASK-018）。

编辑/删除守卫：关联观点已入库（accepted）的灵感不可编辑/删除（409 adopted_locked），
需先在集思录撤回。编辑灵感会同步关联观点（正文/双语/来源日期），且正文变化时
重置其进行中/挂起的会话到提炼最开始。

观点判断前置：录入（含 docx 导入确认）建观点后、编辑正文实际变化后，用 AI 判断
观点正文是否已构成可裁决的观点并写入 viewpoints.is_viewpoint；AI 未配置/不可用/
输出非法时置 NULL（未判断），不阻断录入与编辑，开会话时前端走 live 判断兜底。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import (
    LLMConfigError,
    LLMOutputError,
    LLMProvider,
    LLMUnavailableError,
    llm_provider_dependency,
    resolve_llm_provider,
)
from ..auth import require_user
from ..db import get_db
from ..errors import biz_error
from ..domain.translation import make_bilingual
from ..domain.inspirations import (
    cascade_delete_inspiration,
    create_draft_viewpoint,
    judge_viewpoint,
    linked_viewpoint,
    next_inspiration_id,
    reset_sessions_for_edit,
)
from ..domain.review import latest_phase_map
from ..domain.titles import complete_title, make_titles
from ..domain.docx_import import (
    DocxImportError,
    default_year_from_filename,
    extract_docx_text,
    split_document,
)
from ..models import Inspiration, User, Viewpoint
from ..schemas import (
    ImportConfirmRequest,
    ImportPreviewItem,
    ImportPreviewOut,
    InspirationCreate,
    InspirationDeleted,
    InspirationOut,
    InspirationUpdate,
    RenameTitleRequest,
)

# 上传 docx 大小上限
MAX_DOCX_BYTES = 5 * 1024 * 1024

router = APIRouter(
    prefix="/api/inspirations",
    tags=["inspirations"],
    dependencies=[Depends(require_user)],
)


def _optional_llm_provider(db: Session = Depends(get_db)) -> LLMProvider | None:
    """可选 AI Provider：未配置时返回 None——观点判断跳过（is_viewpoint 置 NULL），
    不阻断录入/编辑（直接注入 llm_provider_dependency 会在配置缺失时 500）。"""
    try:
        return resolve_llm_provider(db)
    except LLMConfigError:
        return None


def _viewpoint_map(db: Session, inspiration_ids: set[int]) -> dict[int, Viewpoint]:
    """inspiration_id → 关联观点（每条灵感至多一条；异常多条时取最早建的）。"""
    if not inspiration_ids:
        return {}
    result: dict[int, Viewpoint] = {}
    for vp in db.scalars(
        select(Viewpoint)
        .where(Viewpoint.source_inspiration_id.in_(inspiration_ids))
        .order_by(Viewpoint.id)
    ):
        result.setdefault(vp.source_inspiration_id, vp)
    return result


def _phase_of(db: Session, viewpoint: Viewpoint | None) -> str | None:
    """单条场景的阶段查询：draft 观点取最近一条非 completed 会话的 phase（无会话为 distill）。"""
    if viewpoint is None or viewpoint.status != "draft":
        return None
    return latest_phase_map(db, {viewpoint.id}).get(viewpoint.id, "distill")


def _inspiration_out(
    inspiration: Inspiration,
    viewpoint: Viewpoint | None,
    viewpoint_phase: str | None = None,
) -> InspirationOut:
    out = InspirationOut.model_validate(inspiration)
    out.viewpoint_id = viewpoint.id if viewpoint else None
    out.viewpoint_status = viewpoint.status if viewpoint else None
    out.viewpoint_phase = (
        (viewpoint_phase or "distill")
        if viewpoint is not None and viewpoint.status == "draft"
        else None
    )
    return out


@router.get("", response_model=list[InspirationOut])
def list_inspirations(
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[InspirationOut]:
    stmt = select(Inspiration).order_by(Inspiration.id)
    if keyword:
        stmt = stmt.where(Inspiration.content.contains(keyword))
    inspirations = list(db.scalars(stmt))
    viewpoints = _viewpoint_map(db, {i.id for i in inspirations})
    phases = latest_phase_map(db, {v.id for v in viewpoints.values()})
    return [
        _inspiration_out(
            i,
            viewpoints.get(i.id),
            phases.get(viewpoints[i.id].id) if i.id in viewpoints else None,
        )
        for i in inspirations
    ]


@router.post("", response_model=InspirationOut, status_code=status.HTTP_201_CREATED)
async def create_inspiration(
    payload: InspirationCreate,
    db: Session = Depends(get_db),
    provider: LLMProvider | None = Depends(_optional_llm_provider),
) -> InspirationOut:
    bilingual = await make_bilingual(db, payload.content)
    titles = await make_titles(db, payload.content)
    inspiration = Inspiration(
        id=next_inspiration_id(db),
        content=payload.content,
        source_date=payload.source_date,
        source_type=payload.source_type,
        **bilingual,
        **titles,
    )
    db.add(inspiration)
    db.flush()
    # 同一事务内创建关联草稿观点（他山坊队列的打磨对象）
    viewpoint = create_draft_viewpoint(db, inspiration)
    db.commit()
    # 观点判断前置：AI 不可用/输出非法时置 NULL（未判断），不阻断录入
    await judge_viewpoint(db, provider, viewpoint)
    db.commit()
    db.refresh(inspiration)
    return _inspiration_out(inspiration, viewpoint, _phase_of(db, viewpoint))


def _get_or_404(inspiration_id: int, db: Session) -> Inspiration:
    inspiration = db.get(Inspiration, inspiration_id)
    if inspiration is None:
        raise biz_error(404, "inspiration_not_found", "灵感不存在", "Inspiration not found")
    return inspiration


@router.get("/{inspiration_id}", response_model=InspirationOut)
def get_inspiration(inspiration_id: int, db: Session = Depends(get_db)) -> InspirationOut:
    inspiration = _get_or_404(inspiration_id, db)
    viewpoint = linked_viewpoint(db, inspiration_id)
    return _inspiration_out(inspiration, viewpoint, _phase_of(db, viewpoint))


@router.put("/{inspiration_id}", response_model=InspirationOut)
async def update_inspiration(
    inspiration_id: int,
    payload: InspirationUpdate,
    db: Session = Depends(get_db),
    provider: LLMProvider | None = Depends(_optional_llm_provider),
) -> InspirationOut:
    inspiration = _get_or_404(inspiration_id, db)
    viewpoint = linked_viewpoint(db, inspiration_id)
    if viewpoint is not None and viewpoint.status == "accepted":
        raise biz_error(
            409, "adopted_locked",
            "已纳入集思录的灵感不可编辑；如需修改，先在集思录中撤回",
            "This inspiration has been adopted into the collection and cannot be edited; withdraw it in the collection first.",
        )
    content_changed = False
    if payload.content is not None and payload.content != inspiration.content:
        content_changed = True
        bilingual = await make_bilingual(db, payload.content)
        inspiration.content = payload.content
        inspiration.content_zh = bilingual["content_zh"]
        inspiration.content_en = bilingual["content_en"]
        inspiration.original_lang = bilingual["original_lang"]
    if payload.source_date is not None:
        inspiration.source_date = payload.source_date
    if viewpoint is not None:
        if content_changed:
            viewpoint.content = inspiration.content
            viewpoint.content_zh = inspiration.content_zh
            viewpoint.content_en = inspiration.content_en
            viewpoint.original_lang = inspiration.original_lang
            # 正文已变，进行中的讨论与分析作废：会话回退到提炼最开始
            reset_sessions_for_edit(db, viewpoint)
        if payload.source_date is not None:
            viewpoint.source_date = inspiration.source_date
    db.commit()
    if viewpoint is not None and content_changed:
        # 正文已变：重新判断观点（失败置 NULL，不阻断编辑；仅改日期不判断）
        await judge_viewpoint(db, provider, viewpoint)
        db.commit()
    db.refresh(inspiration)
    return _inspiration_out(inspiration, viewpoint, _phase_of(db, viewpoint))


@router.delete("/{inspiration_id}")
def delete_inspiration(inspiration_id: int, db: Session = Depends(get_db)) -> dict:
    inspiration = _get_or_404(inspiration_id, db)
    viewpoint = linked_viewpoint(db, inspiration_id)
    if viewpoint is not None and viewpoint.status == "accepted":
        raise biz_error(
            409, "adopted_locked",
            "已纳入集思录的灵感不可删除；先在集思录中撤回",
            "This inspiration has been adopted into the collection and cannot be deleted; withdraw it in the collection first.",
        )
    return cascade_delete_inspiration(db, inspiration)


@router.post("/import", response_model=ImportPreviewOut)
async def import_docx_preview(
    file: UploadFile,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(llm_provider_dependency),
) -> ImportPreviewOut:
    """上传 docx → AI 拆解归纳（只切割不改写、保留日期标记）→ 逐条预览，不入库。"""
    filename = file.filename or ""
    # multipart 规范中文件名按 latin-1 解码，中文文件名需还原为 UTF-8
    try:
        filename = filename.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    if not filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "docx_only", "zh": "仅支持 .docx 文件", "en": "Only .docx files are supported"},
        )
    data = await file.read()
    if not data or len(data) > MAX_DOCX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"文件为空或超过大小上限（{MAX_DOCX_BYTES // (1024 * 1024)}MB）",
        )
    try:
        text = extract_docx_text(data)
        items = await split_document(db, provider, document_text=text, filename=filename)
    except DocxImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except (LLMUnavailableError, LLMConfigError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except LLMOutputError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return ImportPreviewOut(
        filename=filename,
        default_year=default_year_from_filename(filename),
        items=[
            ImportPreviewItem(content=item.content, source_date=item.source_date)
            for item in items
        ],
    )


@router.post(
    "/import/confirm",
    response_model=list[InspirationOut],
    status_code=status.HTTP_201_CREATED,
)
async def confirm_import(
    payload: ImportConfirmRequest,
    db: Session = Depends(get_db),
    provider: LLMProvider | None = Depends(_optional_llm_provider),
) -> list[InspirationOut]:
    """用户确认预览后批量入库：source_type=docx_import，单事务；
    每条灵感同事务创建关联草稿观点。入库后逐条前置观点判断
    （AI 不可用/输出非法置 NULL，不阻断导入）。"""
    inspirations = []
    viewpoints = []
    for item in payload.items:
        bilingual = await make_bilingual(db, item.content)
        titles = await make_titles(db, item.content)
        inspiration = Inspiration(
            id=next_inspiration_id(db),
            content=item.content,
            source_date=item.source_date,
            source_type="docx_import",
            **bilingual,
            **titles,
        )
        db.add(inspiration)
        db.flush()
        inspirations.append(inspiration)
        viewpoints.append(create_draft_viewpoint(db, inspiration))
    db.commit()
    for viewpoint in viewpoints:
        await judge_viewpoint(db, provider, viewpoint)
    db.commit()
    for inspiration in inspirations:
        db.refresh(inspiration)
    return [
        _inspiration_out(inspiration, viewpoint, _phase_of(db, viewpoint))
        for inspiration, viewpoint in zip(inspirations, viewpoints)
    ]


@router.post("/{inspiration_id}/rename-title", response_model=InspirationOut)
async def rename_title(
    inspiration_id: int, payload: RenameTitleRequest, db: Session = Depends(get_db)
) -> InspirationOut:
    """用户以一种语言重命名标题，另一种语言由大模型补齐；派生观点的标题同步更新。"""
    inspiration = db.get(Inspiration, inspiration_id)
    if inspiration is None:
        raise biz_error(404, "inspiration_not_found", "灵感不存在", "Inspiration not found")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="标题不能为空")
    if payload.lang not in ("zh", "en"):
        raise HTTPException(status_code=422, detail="lang 必须是 zh 或 en")
    # 只写用户指定的语种；另一语种仅当为空时才由 AI 补齐，不覆盖已有标题
    existing_other = (
        inspiration.title_en if payload.lang == "zh" else inspiration.title_zh
    )
    if existing_other:
        titles = {
            "title_zh": title if payload.lang == "zh" else existing_other,
            "title_en": title if payload.lang == "en" else existing_other,
        }
    else:
        titles = await complete_title(db, title, payload.lang)
    inspiration.title_zh = titles["title_zh"]
    inspiration.title_en = titles["title_en"]
    # 派生观点同步：同样只写用户语种，另一语种仅补空
    for vp in db.scalars(
        select(Viewpoint).where(Viewpoint.source_inspiration_id == inspiration.id)
    ):
        vp_existing_other = (
            vp.title_en if payload.lang == "zh" else vp.title_zh
        )
        vp.title_zh = titles["title_zh"] if payload.lang == "zh" else (vp_existing_other or titles["title_zh"])
        vp.title_en = titles["title_en"] if payload.lang == "en" else (vp_existing_other or titles["title_en"])
    db.commit()
    db.refresh(inspiration)
    viewpoint = linked_viewpoint(db, inspiration.id)
    return _inspiration_out(inspiration, viewpoint, _phase_of(db, viewpoint))
