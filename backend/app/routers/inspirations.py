"""灵感 CRUD：录入即入队（status=pending），id 即编号；docx 导入（TASK-018）。"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import (
    LLMConfigError,
    LLMOutputError,
    LLMProvider,
    LLMUnavailableError,
    llm_provider_dependency,
)
from ..auth import require_user
from ..db import get_db
from ..domain.translation import make_bilingual
from ..domain.docx_import import (
    DocxImportError,
    default_year_from_filename,
    extract_docx_text,
    split_document,
)
from ..models import Inspiration, User
from ..schemas import (
    ImportConfirmRequest,
    ImportPreviewItem,
    ImportPreviewOut,
    InspirationCreate,
    InspirationDeleted,
    InspirationOut,
    InspirationStatus,
    InspirationUpdate,
)

# 上传 docx 大小上限
MAX_DOCX_BYTES = 5 * 1024 * 1024

router = APIRouter(
    prefix="/api/inspirations",
    tags=["inspirations"],
    dependencies=[Depends(require_user)],
)


@router.get("", response_model=list[InspirationOut])
def list_inspirations(
    status_filter: InspirationStatus | None = Query(default=None, alias="status"),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Inspiration]:
    stmt = select(Inspiration).order_by(Inspiration.id)
    if status_filter is not None:
        stmt = stmt.where(Inspiration.status == status_filter)
    if keyword:
        stmt = stmt.where(Inspiration.content.contains(keyword))
    return list(db.scalars(stmt))


@router.post("", response_model=InspirationOut, status_code=status.HTTP_201_CREATED)
async def create_inspiration(
    payload: InspirationCreate,
    db: Session = Depends(get_db),
) -> Inspiration:
    bilingual = await make_bilingual(db, payload.content)
    inspiration = Inspiration(
        content=payload.content,
        source_date=payload.source_date,
        source_type=payload.source_type,
        status="pending",
        **bilingual,
    )
    db.add(inspiration)
    db.commit()
    db.refresh(inspiration)
    return inspiration


def _get_or_404(inspiration_id: int, db: Session) -> Inspiration:
    inspiration = db.get(Inspiration, inspiration_id)
    if inspiration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="灵感不存在")
    return inspiration


@router.get("/{inspiration_id}", response_model=InspirationOut)
def get_inspiration(inspiration_id: int, db: Session = Depends(get_db)) -> Inspiration:
    return _get_or_404(inspiration_id, db)


@router.put("/{inspiration_id}", response_model=InspirationOut)
def update_inspiration(
    inspiration_id: int, payload: InspirationUpdate, db: Session = Depends(get_db)
) -> Inspiration:
    inspiration = _get_or_404(inspiration_id, db)
    if payload.content is not None:
        inspiration.content = payload.content
    if payload.source_date is not None:
        inspiration.source_date = payload.source_date
    db.commit()
    db.refresh(inspiration)
    return inspiration


@router.delete("/{inspiration_id}", response_model=InspirationDeleted)
def delete_inspiration(inspiration_id: int, db: Session = Depends(get_db)) -> InspirationDeleted:
    inspiration = _get_or_404(inspiration_id, db)
    db.delete(inspiration)
    db.commit()
    return InspirationDeleted(deleted_id=inspiration_id)


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
            detail="仅支持 .docx 文件",
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
    payload: ImportConfirmRequest, db: Session = Depends(get_db)
) -> list[Inspiration]:
    """用户确认预览后批量入库：source_type=docx_import，status=pending，单事务。"""
    inspirations = []
    for item in payload.items:
        bilingual = await make_bilingual(db, item.content)
        inspirations.append(
            Inspiration(
                content=item.content,
                source_date=item.source_date,
                source_type="docx_import",
                status="pending",
                **bilingual,
            )
        )
    db.add_all(inspirations)
    db.commit()
    for inspiration in inspirations:
        db.refresh(inspiration)
    return inspirations
