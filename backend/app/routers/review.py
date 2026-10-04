"""打磨会话与讨论接口（TASK-010，docs/04 D9 两阶段）。

AI 在讨论中只输出观点与提问，不落库任何业务数据；
正式落库只由决策接口（TASK-011，仅采纳）完成。

两阶段：提炼（distill）→ 打磨（polish）。提炼期讨论走结构化 DistillReply
（回复 + 收敛信号），观点判断与进入打磨由本模块的专用端点完成。
撤销分两档：消息级撤销（/undo，只删当前阶段末轮）与阶段级回退
（/undo-phase，polish→distill 清分析与打磨消息；distill→重置恢复观点原文）。
待打磨队列（/queue）为全站 draft 观点。
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import (
    LLMConfigError,
    LLMError,
    LLMOutputError,
    LLMProvider,
    LLMUnavailableError,
    llm_provider_dependency,
    record_ai_call,
    run_structured_call,
)
from ..ai.prompts.discussion import PROMPT_VERSION, build_discussion_messages
from ..ai.prompts.distill import (
    PROMPT_VERSION as DISTILL_PROMPT_VERSION,
    build_distill_messages,
)
from ..ai.prompts.viewpoint_check import (
    PROMPT_VERSION as VIEWPOINT_CHECK_PROMPT_VERSION,
    build_viewpoint_check_messages,
)
from ..ai.schemas import DistillReply, ViewpointCheck
from ..auth import require_user
from ..db import get_db
from ..errors import biz_error
from ..domain.review import (
    ReviewError,
    UndoFloorError,
    apply_review_decision,
    latest_phase_map,
    open_review_session,
    undo_last_message,
    undo_phase,
)
from ..domain.titles import make_titles
from ..domain.translation import make_bilingual
from ..models import Inspiration, ReviewMessage, ReviewSession, Viewpoint
from ..schemas import (
    DecisionOut,
    DecisionRequest,
    DistillSignal,
    EnterPolishRequest,
    ReviewMessageCreate,
    ReviewMessageOut,
    ReviewMessagePair,
    ReviewQueueItem,
    ReviewSessionCreate,
    ReviewSessionOut,
    ViewpointCheckOut,
    ViewpointOut,
)

logger = logging.getLogger(__name__)


async def _run_distill_call(
    db: Session, provider: LLMProvider, messages: list
) -> DistillReply:
    """提炼期结构化调用：长对话中模型偶发忘记 JSON 约定，解析失败自动重试一次。"""
    try:
        return await run_structured_call(
            db,
            provider,
            prompt_version=DISTILL_PROMPT_VERSION,
            schema=DistillReply,
            messages=messages,
        )
    except LLMOutputError:
        return await run_structured_call(
            db,
            provider,
            prompt_version=DISTILL_PROMPT_VERSION,
            schema=DistillReply,
            messages=messages,
        )

router = APIRouter(
    prefix="/api/review",
    tags=["review"],
    dependencies=[Depends(require_user)],
)


def _session_viewpoint(db: Session, session: ReviewSession) -> Viewpoint:
    """会话打磨的观点（会话的主关联，必然存在）。"""
    return db.get(Viewpoint, session.viewpoint_id)


def _session_out(db: Session, session: ReviewSession) -> ReviewSessionOut:
    messages = list(
        db.scalars(
            select(ReviewMessage)
            .where(ReviewMessage.session_id == session.id)
            .order_by(ReviewMessage.id)
        )
    )
    viewpoint = _session_viewpoint(db, session)
    return ReviewSessionOut(
        id=session.id,
        viewpoint_id=session.viewpoint_id,
        status=session.status,
        phase=session.phase or "polish",  # 兜底：极早期行可能无 phase
        started_at=session.started_at,
        ended_at=session.ended_at,
        viewpoint=ViewpointOut.model_validate(viewpoint),
        messages=[ReviewMessageOut.model_validate(m) for m in messages],
        analysis=json.loads(session.analysis_json) if session.analysis_json else None,
        analysis_en=(
            json.loads(session.analysis_json_en) if session.analysis_json_en else None
        ),
    )


def _get_session_or_404(session_id: int, db: Session) -> ReviewSession:
    session = db.get(ReviewSession, session_id)
    if session is None:
        raise biz_error(404, "session_not_found", "审议会话不存在", "Review session not found")
    return session


@router.get("/queue", response_model=list[ReviewQueueItem])
def get_review_queue(db: Session = Depends(get_db)) -> list[ReviewQueueItem]:
    """他山坊待打磨队列：draft 观点按 id 升序；标题为观点自身标题（采纳前沿用灵感标题）。

    phase 为该观点最近一条非 completed 会话（active/paused）的阶段；无会话为 distill。
    """
    viewpoints = list(
        db.scalars(
            select(Viewpoint).where(Viewpoint.status == "draft").order_by(Viewpoint.id)
        )
    )
    phases = latest_phase_map(db, {vp.id for vp in viewpoints})
    return [
        ReviewQueueItem(
            id=vp.id,
            content=vp.content,
            content_zh=vp.content_zh,
            content_en=vp.content_en,
            original_lang=vp.original_lang,
            source_date=vp.source_date,
            inspiration_id=vp.source_inspiration_id,
            title_zh=vp.title_zh,
            title_en=vp.title_en,
            phase=phases.get(vp.id, "distill"),
        )
        for vp in viewpoints
    ]


@router.post("/sessions", response_model=ReviewSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(payload: ReviewSessionCreate, db: Session = Depends(get_db)) -> ReviewSessionOut:
    """对某观点开启打磨会话。

    同一观点已有 active 会话时直接返回该会话（断点续聊）；
    有 paused 会话时恢复它。已入库（accepted）的观点不得再开会话。
    """
    viewpoint = db.get(Viewpoint, payload.viewpoint_id)
    if viewpoint is None:
        raise biz_error(404, "viewpoint_not_found", "观点不存在", "Viewpoint not found")
    try:
        session = open_review_session(db, viewpoint)
    except ReviewError as exc:
        raise biz_error(409, "review_conflict", str(exc)) from exc
    return _session_out(db, session)


@router.get("/sessions/active", response_model=ReviewSessionOut | None)
def get_active_session(db: Session = Depends(get_db)):
    """当前唯一的 active 审议会话（用于关窗重开后自动恢复），无则返回 null。

    历史数据可能残留多个 active 会话（旧版开会话不挂起其他会话），取最近创建的一个。
    """
    session = db.scalar(
        select(ReviewSession)
        .where(ReviewSession.status == "active")
        .order_by(ReviewSession.id.desc())
        .limit(1)
    )
    if session is None:
        return None
    return _session_out(db, session)


@router.get("/sessions/{session_id}", response_model=ReviewSessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)) -> ReviewSessionOut:
    return _session_out(db, _get_session_or_404(session_id, db))


@router.post("/sessions/{session_id}/viewpoint-check", response_model=ViewpointCheckOut)
async def viewpoint_check(
    session_id: int,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(llm_provider_dependency),
) -> ViewpointCheckOut:
    """观点判断（docs/04 D9）：一次结构化调用判断该会话的观点正文是否已构成可裁决的观点。"""
    session = _get_session_or_404(session_id, db)
    if session.status != "active":
        raise biz_error(
            409, "session_not_active",
            "会话不在进行中，无法进行观点判断",
            "Session is not active",
        )
    viewpoint = _session_viewpoint(db, session)
    messages = build_viewpoint_check_messages(viewpoint)
    try:
        result = await run_structured_call(
            db,
            provider,
            prompt_version=VIEWPOINT_CHECK_PROMPT_VERSION,
            schema=ViewpointCheck,
            messages=messages,
        )
    except (LLMUnavailableError, LLMConfigError) as exc:
        raise biz_error(
            503, "ai_unavailable", str(exc),
            "AI service is unavailable. Please check the AI service settings.",
        ) from exc
    except LLMOutputError as exc:
        raise biz_error(
            502, "ai_bad_output", str(exc),
            "The AI returned output that failed validation. Please retry.",
        ) from exc
    return ViewpointCheckOut(is_viewpoint=result.is_viewpoint)


@router.post("/sessions/{session_id}/enter-polish", response_model=ReviewSessionOut)
async def enter_polish(
    session_id: int,
    payload: EnterPolishRequest,
    db: Session = Depends(get_db),
) -> ReviewSessionOut:
    """进入打磨阶段（docs/04 D9）：提炼收敛出的观点草稿写入关联观点正文（可空）。

    草稿非空且与现正文不同时，重新双语化观点的 content_zh/content_en。
    """
    session = _get_session_or_404(session_id, db)
    if session.status != "active":
        raise biz_error(
            409, "session_not_active",
            "会话不在进行中，无法进入打磨阶段",
            "Session is not active",
        )
    if session.phase == "polish":
        raise biz_error(
            409, "phase_conflict",
            "会话已处于打磨阶段",
            "Session is already in the polish phase",
        )
    draft = (payload.draft or "").strip() or None
    session.phase = "polish"
    viewpoint = _session_viewpoint(db, session)
    if draft:
        if draft != (viewpoint.content or "").strip():
            bilingual = await make_bilingual(db, draft)
            viewpoint.content = draft
            viewpoint.content_zh = bilingual["content_zh"]
            viewpoint.content_en = bilingual["content_en"]
            viewpoint.original_lang = bilingual["original_lang"]
        else:
            viewpoint.content = draft
    # 进入打磨时按观点正文重新生成标题（失败保留旧标题，不阻断流程）
    titles = await make_titles(db, viewpoint.content)
    if titles["title_zh"] is not None:
        viewpoint.title_zh = titles["title_zh"]
        viewpoint.title_en = titles["title_en"]
    db.commit()
    db.refresh(session)
    return _session_out(db, session)


@router.post("/sessions/{session_id}/undo", response_model=ReviewSessionOut)
def undo_message(session_id: int, db: Session = Depends(get_db)) -> ReviewSessionOut:
    """消息级撤销：只删当前阶段最后一条消息（assistant 连同其用户提问）。

    只删不回、不跨阶段；无同阶段消息时不动。无 AI 调用，ai_calls 不留痕。
    """
    session = _get_session_or_404(session_id, db)
    try:
        undo_last_message(db, session)
    except ReviewError as exc:
        raise biz_error(409, "session_not_active", str(exc)) from exc
    db.refresh(session)
    return _session_out(db, session)


@router.post("/sessions/{session_id}/undo-phase", response_model=ReviewSessionOut)
def undo_session_phase(session_id: int, db: Session = Depends(get_db)) -> ReviewSessionOut:
    """阶段级回退：polish → distill（清分析与打磨消息）；distill → 重置（清消息、观点正文恢复灵感原文）。

    撤销地板：观点 is_viewpoint 为 true（录入即判定为观点、跳过提炼）且会话无
    distill 消息时，polish → distill 回退拒绝（409 undo_floor）。
    """
    session = _get_session_or_404(session_id, db)
    try:
        undo_phase(db, session)
    except UndoFloorError as exc:
        raise biz_error(
            409, "undo_floor", str(exc),
            "This viewpoint skipped distilling; nothing earlier to undo.",
        ) from exc
    except ReviewError as exc:
        raise biz_error(409, "session_not_active", str(exc)) from exc
    db.refresh(session)
    return _session_out(db, session)

@router.post("/sessions/{session_id}/opening", response_model=ReviewMessageOut | None)
async def post_opening(
    session_id: int,
    regenerate: bool = False,
    polish_entry: bool = False,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(llm_provider_dependency),
):
    """AI 首问：AI 在讨论区主动提出它认为当前最重要的一个问题。

    提炼阶段（distill）走结构化 DistillReply（只取回复正文，信号不随首问外露）；
    打磨阶段（polish）沿用讨论 prompt 的自由文本。
    会话已有消息时返回 None（不重复提问）。regenerate=True 时：
    若用户尚未发言（讨论区只有 AI 首问），删除旧首问并按最新分析重新生成。
    polish_entry=True 时不受"已有消息"限制：用于提炼→打磨转换后，
    在保留的提炼讨论之后生成"进入打磨"的衔接首问（须已有分析）。
    失败抛 503/502 双语错误。
    """
    session = _get_session_or_404(session_id, db)
    if session.status != "active":
        raise biz_error(
            409, "session_not_active",
            "会话不在进行中，无法生成首问",
            "Session is not active",
        )
    if polish_entry:
        return await _polish_entry_opening(session, db, provider)
    existing = db.scalar(
        select(ReviewMessage.id).where(ReviewMessage.session_id == session.id).limit(1)
    )
    if existing is not None:
        if not regenerate:
            return None
        has_user_msg = db.scalar(
            select(ReviewMessage.id)
            .where(ReviewMessage.session_id == session.id, ReviewMessage.role == "user")
            .limit(1)
        )
        if has_user_msg is not None:
            return None  # 用户已发言，历史不动
        db.query(ReviewMessage).where(
            ReviewMessage.session_id == session.id,
            ReviewMessage.role == "assistant",
        ).delete()
        db.commit()
    subject = _session_viewpoint(db, session)
    viewpoints = list(
        db.scalars(
            select(Viewpoint)
            .where(Viewpoint.status == "accepted")
            .order_by(Viewpoint.id)
        )
    )
    opening_instruction = {
        "role": "user",
        "content": "（系统指令）请提出你判断在当前语境下最重要的一个问题，开启讨论。",
    }
    if session.phase == "distill":
        messages = build_distill_messages(subject, viewpoints, [])
        messages.append(opening_instruction)
        try:
            result = await _run_distill_call(db, provider, messages)
        except (LLMUnavailableError, LLMConfigError) as exc:
            raise biz_error(
                503, "ai_unavailable", str(exc),
                "AI service is unavailable. Please check the AI service settings.",
            ) from exc
        except LLMOutputError as exc:
            raise biz_error(
                502, "ai_bad_output", str(exc),
                "The AI returned output that failed validation. Please retry.",
            ) from exc
        reply = result.reply
    else:
        from ..ai.schemas import AnalysisResult

        analysis = (
            AnalysisResult.model_validate_json(session.analysis_json)
            if session.analysis_json
            else None
        )
        messages = build_discussion_messages(subject, viewpoints, analysis, [])
        messages.append(opening_instruction)
        try:
            reply = await provider.generate(messages)
        except LLMUnavailableError as exc:
            raise biz_error(
                503, "ai_unavailable", str(exc),
                "AI service is unavailable. Please check the AI service settings.",
            ) from exc
        except (LLMConfigError, LLMError) as exc:
            raise biz_error(
                502, "ai_bad_output", str(exc),
                "The AI returned output that failed validation. Please retry.",
            ) from exc
        record_ai_call(
            db,
            provider=provider.provider_name,
            model=provider.model,
            prompt_version=PROMPT_VERSION,
            input_snapshot=json.dumps(messages, ensure_ascii=False),
            output=reply,
        )
    assistant_message = ReviewMessage(
        session_id=session.id,
        role="assistant",
        content=reply,
        phase=session.phase,
        **await make_bilingual(db, reply, original_lang="zh"),
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return ReviewMessageOut.model_validate(assistant_message)


async def _polish_entry_opening(
    session: ReviewSession, db: Session, provider: LLMProvider
) -> ReviewMessageOut:
    """提炼→打磨转换后的首问：基于已定草稿的分析，在保留的提炼讨论之后，
    用一句话衔接"已进入打磨"，再提出当前最重要的一个问题，保证对话连贯。"""
    if session.phase != "polish":
        raise biz_error(
            409, "phase_conflict",
            "会话不在打磨阶段，无法生成打磨首问",
            "Session is not in the polish phase",
        )
    if not session.analysis_json:
        raise biz_error(
            409, "analysis_missing",
            "尚未生成分析，无法生成打磨首问",
            "Analysis is not available yet",
        )
    subject = _session_viewpoint(db, session)
    viewpoints = list(
        db.scalars(
            select(Viewpoint)
            .where(Viewpoint.status == "accepted")
            .order_by(Viewpoint.id)
        )
    )
    history = list(
        db.scalars(
            select(ReviewMessage)
            .where(ReviewMessage.session_id == session.id)
            .order_by(ReviewMessage.id)
        )
    )
    from ..ai.schemas import AnalysisResult

    analysis = AnalysisResult.model_validate_json(session.analysis_json)
    messages = build_discussion_messages(subject, viewpoints, analysis, history)
    messages.append(
        {
            "role": "user",
            "content": "（系统指令）讨论刚结束提炼、进入打磨阶段，观点草稿已经确定。请先用一句话自然衔接这个节点（可以点明已进入打磨），再提出你判断在当前语境下最重要的一个问题。",
        }
    )
    try:
        reply = await provider.generate(messages)
    except LLMUnavailableError as exc:
        raise biz_error(
            503, "ai_unavailable", str(exc),
            "AI service is unavailable. Please check the AI service settings.",
        ) from exc
    except (LLMConfigError, LLMError) as exc:
        raise biz_error(
            502, "ai_bad_output", str(exc),
            "The AI returned output that failed validation. Please retry.",
        ) from exc
    record_ai_call(
        db,
        provider=provider.provider_name,
        model=provider.model,
        prompt_version=PROMPT_VERSION,
        input_snapshot=json.dumps(messages, ensure_ascii=False),
        output=reply,
    )
    assistant_message = ReviewMessage(
        session_id=session.id,
        role="assistant",
        content=reply,
        phase=session.phase,
        **await make_bilingual(db, reply, original_lang="zh"),
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return ReviewMessageOut.model_validate(assistant_message)


@router.post("/sessions/{session_id}/messages", response_model=ReviewMessagePair)
async def post_message(
    session_id: int,
    payload: ReviewMessageCreate,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(llm_provider_dependency),
) -> ReviewMessagePair:
    """用户发言：落库后调 LLM 生成回复，双方消息均落库，调用留痕 ai_calls。

    提炼阶段（distill）走结构化 DistillReply，返回的 pair 附 distill_signal
    （收敛信号，含 ready_to_polish 与观点草稿）；打磨阶段（polish）走讨论 prompt，
    distill_signal 为 None。
    """
    session = _get_session_or_404(session_id, db)
    if session.status != "active":
        raise biz_error(
            409,
            "session_not_active",
            f"会话不在进行中（当前状态：{session.status}），无法发言",
            f"Session is not active ({session.status}); cannot post",
        )
    subject = _session_viewpoint(db, session)

    user_message = ReviewMessage(
        session_id=session.id,
        role="user",
        content=payload.content,
        phase=session.phase,
        **await make_bilingual(db, payload.content),
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    viewpoints = list(
        db.scalars(
            select(Viewpoint)
            .where(Viewpoint.status == "accepted")
            .order_by(Viewpoint.id)
        )
    )
    history = list(
        db.scalars(
            select(ReviewMessage)
            .where(ReviewMessage.session_id == session.id)
            .order_by(ReviewMessage.id)
        )
    )
    distill_signal = None
    if session.phase == "distill":
        # 提炼阶段：结构化回复（reply + 收敛信号），留痕由 run_structured_call 完成
        messages = build_distill_messages(subject, viewpoints, history)
        try:
            result = await _run_distill_call(db, provider, messages)
        except (LLMUnavailableError, LLMConfigError) as exc:
            raise biz_error(
                503, "ai_unavailable", str(exc),
                "AI service is unavailable. Please check the AI service settings.",
            ) from exc
        except LLMOutputError as exc:
            raise biz_error(
                502, "ai_bad_output", str(exc),
                "The AI returned output that failed validation. Please retry.",
            ) from exc
        reply = result.reply
        if result.ready_to_polish:
            # 收敛轮：回复不落库、不进对话框——前端弹窗接管；用户取消弹窗时
            # 用 distill_signal.reply 临时展示该回复（刷新后不再出现）
            return ReviewMessagePair(
                user_message=ReviewMessageOut.model_validate(user_message),
                assistant_message=None,
                distill_signal=DistillSignal(
                    ready_to_polish=True,
                    distilled_viewpoint=result.distilled_viewpoint,
                    reply=reply,
                ),
            )
        distill_signal = DistillSignal(
            ready_to_polish=False,
            distilled_viewpoint=result.distilled_viewpoint,
        )
    else:
        messages = build_discussion_messages(subject, viewpoints, payload.analysis, history)
        try:
            reply = await provider.generate(messages)
        except LLMUnavailableError as exc:
            record_ai_call(
                db,
                provider=provider.provider_name,
                model=provider.model,
                prompt_version=PROMPT_VERSION,
                input_snapshot=json.dumps(messages, ensure_ascii=False),
                output=f"调用失败：{exc}",
            )
            raise biz_error(
                503, "ai_unavailable", str(exc),
                "AI service is unavailable. Please check the AI service settings.",
            ) from exc
        except (LLMConfigError, LLMError) as exc:
            record_ai_call(
                db,
                provider=provider.provider_name,
                model=provider.model,
                prompt_version=PROMPT_VERSION,
                input_snapshot=json.dumps(messages, ensure_ascii=False),
                output=f"调用失败：{exc}",
            )
            raise biz_error(
                502, "ai_bad_output", str(exc),
                "The AI returned output that failed validation. Please retry.",
            ) from exc

        record_ai_call(
            db,
            provider=provider.provider_name,
            model=provider.model,
            prompt_version=PROMPT_VERSION,
            input_snapshot=json.dumps(messages, ensure_ascii=False),
            output=reply,
        )
    assistant_message = ReviewMessage(
        session_id=session.id,
        role="assistant",
        content=reply,
        phase=session.phase,
        **await make_bilingual(db, reply, original_lang="zh"),
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return ReviewMessagePair(
        user_message=ReviewMessageOut.model_validate(user_message),
        assistant_message=ReviewMessageOut.model_validate(assistant_message),
        distill_signal=distill_signal,
    )


@router.post("/sessions/{session_id}/decision", response_model=DecisionOut)
async def post_decision(
    session_id: int, payload: DecisionRequest, db: Session = Depends(get_db)
) -> DecisionOut:
    """打磨决策（仅采纳）：在一个事务内把会话关联的草稿观点转为 accepted——
    写入最终正文（变化则重新双语化）/双语标题（缺省时 AI 生成）/分层/标签，
    建相近/冲突关系（只建行，不联动任何状态），记决策，关闭会话；
    任一步失败整体回滚。"""
    session = _get_session_or_404(session_id, db)
    viewpoint = _session_viewpoint(db, session)
    final_text = (payload.final_content or "").strip()
    bilingual = None
    if final_text and viewpoint is not None:
        if final_text == (viewpoint.content or "").strip():
            # 未修改：直接携带观点的双语版本
            bilingual = {
                "content_zh": viewpoint.content_zh,
                "content_en": viewpoint.content_en,
                "original_lang": viewpoint.original_lang,
            }
        else:
            bilingual = await make_bilingual(db, final_text)
    title_zh = (payload.title_zh or "").strip() or None
    title_en = (payload.title_en or "").strip() or None
    if (title_zh is None or title_en is None) and final_text:
        # 请求缺省时用最终正文生成双语标题（AI 不可用则置空，待对账补齐）
        generated = await make_titles(db, final_text)
        title_zh = title_zh or generated["title_zh"]
        title_en = title_en or generated["title_en"]
    try:
        outcome = apply_review_decision(
            db,
            session,
            bilingual=bilingual,
            decision_type=payload.decision_type,
            final_content=payload.final_content,
            title_zh=title_zh,
            title_en=title_en,
            reason=payload.reason,
            layer=payload.layer,
            tags=payload.tags,
            relations=payload.relations,
        )
    except ReviewError as exc:
        raise biz_error(409, "review_conflict", str(exc)) from exc
    return DecisionOut(
        decision_id=outcome.decision.id if outcome.decision else None,
        decision_type=payload.decision_type,
        viewpoint_id=outcome.viewpoint.id if outcome.viewpoint else None,
        display_id=(
            (outcome.viewpoint.source_inspiration_id or outcome.viewpoint.id)
            if outcome.viewpoint
            else None
        ),
        session_status=session.status,
    )
