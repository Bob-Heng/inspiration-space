"""审议会话与讨论接口（TASK-010）。

AI 在讨论中只输出观点与提问，不落库任何业务数据；
正式落库只由决策接口（TASK-011）完成。
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import (
    LLMConfigError,
    LLMError,
    LLMProvider,
    LLMUnavailableError,
    llm_provider_dependency,
    record_ai_call,
)
from ..ai.prompts.discussion import PROMPT_VERSION, build_discussion_messages
from ..auth import require_user
from ..db import get_db
from ..errors import biz_error
from ..domain.review import ReviewError, apply_review_decision, open_review_session
from ..domain.translation import make_bilingual
from ..models import Inspiration, ReviewMessage, ReviewSession, Viewpoint
from ..schemas import (
    DecisionOut,
    DecisionRequest,
    InspirationOut,
    ReviewMessageCreate,
    ReviewMessageOut,
    ReviewMessagePair,
    ReviewSessionCreate,
    ReviewSessionOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/review",
    tags=["review"],
    dependencies=[Depends(require_user)],
)


def _session_out(db: Session, session: ReviewSession) -> ReviewSessionOut:
    messages = list(
        db.scalars(
            select(ReviewMessage)
            .where(ReviewMessage.session_id == session.id)
            .order_by(ReviewMessage.id)
        )
    )
    return ReviewSessionOut(
        id=session.id,
        inspiration_id=session.inspiration_id,
        viewpoint_id=session.viewpoint_id,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        inspiration=InspirationOut.model_validate(
            db.get(Inspiration, session.inspiration_id)
        ),
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


@router.post("/sessions", response_model=ReviewSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(payload: ReviewSessionCreate, db: Session = Depends(get_db)) -> ReviewSessionOut:
    """对某灵感开启审议会话。

    同一灵感已有 active 会话时直接返回该会话（断点续聊）；
    有 paused 会话时恢复它；已完结的灵感返回 409。
    """
    inspiration = db.get(Inspiration, payload.inspiration_id)
    if inspiration is None:
        raise biz_error(404, "inspiration_not_found", "灵感不存在", "Inspiration not found")
    try:
        session = open_review_session(db, inspiration)
    except ReviewError as exc:
        raise biz_error(409, "review_conflict", str(exc)) from exc
    return _session_out(db, session)


@router.get("/sessions/active", response_model=ReviewSessionOut | None)
def get_active_session(db: Session = Depends(get_db)):
    """当前唯一的 active 审议会话（用于关窗重开后自动恢复），无则返回 null。"""
    session = db.scalar(
        select(ReviewSession).where(ReviewSession.status == "active").limit(1)
    )
    if session is None:
        return None
    return _session_out(db, session)


@router.get("/sessions/{session_id}", response_model=ReviewSessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)) -> ReviewSessionOut:
    return _session_out(db, _get_session_or_404(session_id, db))


@router.post("/sessions/{session_id}/opening", response_model=ReviewMessageOut | None)
async def post_opening(
    session_id: int,
    regenerate: bool = False,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(llm_provider_dependency),
):
    """AI 首问：分析生成后，AI 在讨论区主动提出它认为当前最重要的一个问题。

    会话已有消息时返回 None（不重复提问）。regenerate=True 时：
    若用户尚未发言（讨论区只有 AI 首问），删除旧首问并按最新分析重新生成。
    失败抛 503/502 双语错误。
    """
    session = _get_session_or_404(session_id, db)
    if session.status != "active":
        raise biz_error(
            409, "session_not_active",
            "会话不在进行中，无法生成首问",
            "Session is not active",
        )
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
    inspiration = db.get(Inspiration, session.inspiration_id)
    viewpoints = list(db.scalars(select(Viewpoint).order_by(Viewpoint.id)))
    from ..ai.schemas import AnalysisResult

    analysis = (
        AnalysisResult.model_validate_json(session.analysis_json)
        if session.analysis_json
        else None
    )
    messages = build_discussion_messages(inspiration, viewpoints, analysis, [])
    messages.append(
        {
            "role": "user",
            "content": "（系统指令）请提出你判断在当前语境下最重要的一个问题，开启讨论。",
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
    """用户发言：落库后调 LLM 生成回复，双方消息均落库，调用留痕 ai_calls。"""
    session = _get_session_or_404(session_id, db)
    if session.status != "active":
        raise biz_error(
            409,
            "session_not_active",
            f"会话不在进行中（当前状态：{session.status}），无法发言",
            f"Session is not active ({session.status}); cannot post",
        )
    inspiration = db.get(Inspiration, session.inspiration_id)

    user_message = ReviewMessage(
        session_id=session.id,
        role="user",
        content=payload.content,
        **await make_bilingual(db, payload.content),
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    viewpoints = list(db.scalars(select(Viewpoint).order_by(Viewpoint.id)))
    history = list(
        db.scalars(
            select(ReviewMessage)
            .where(ReviewMessage.session_id == session.id)
            .order_by(ReviewMessage.id)
        )
    )
    messages = build_discussion_messages(inspiration, viewpoints, payload.analysis, history)
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
        **await make_bilingual(db, reply, original_lang="zh"),
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return ReviewMessagePair(
        user_message=ReviewMessageOut.model_validate(user_message),
        assistant_message=ReviewMessageOut.model_validate(assistant_message),
    )


@router.post("/sessions/{session_id}/decision", response_model=DecisionOut)
async def post_decision(
    session_id: int, payload: DecisionRequest, db: Session = Depends(get_db)
) -> DecisionOut:
    """审议决策：采纳/修改后采纳/否定在一个事务内落库，任一步失败整体回滚；
    暂缓只挂起会话、灵感回到待审队列，不产生终态。"""
    session = _get_session_or_404(session_id, db)
    bilingual = None
    if payload.decision_type in ("accept", "accept_modified"):
        final_text = (payload.final_content or "").strip()
        inspiration = db.get(Inspiration, session.inspiration_id)
        if final_text and final_text == (inspiration.content or "").strip():
            # 未修改：直接携带灵感的双语版本
            bilingual = {
                "content_zh": inspiration.content_zh,
                "content_en": inspiration.content_en,
                "original_lang": inspiration.original_lang,
            }
        elif final_text:
            bilingual = await make_bilingual(db, final_text)
    try:
        outcome = apply_review_decision(
            db,
            session,
            bilingual=bilingual,
            decision_type=payload.decision_type,
            final_content=payload.final_content,
            reason=payload.reason,
            layer=payload.layer,
            tags=payload.tags,
            relations=payload.relations,
        )
    except ReviewError as exc:
        raise biz_error(409, "review_conflict", str(exc)) from exc
    if (
        payload.regenerate_title
        and payload.decision_type in ("accept", "accept_modified")
        and outcome.viewpoint is not None
    ):
        # 用最终正文重新生成双语标题，并同步到来源灵感（全站一致）
        from ..domain.titles import make_titles

        titles = await make_titles(db, outcome.viewpoint.content)
        if titles["title_zh"] is None:
            raise biz_error(
                503, "ai_unavailable",
                "标题重新生成失败：大模型未接入。决策已生效，标题未变。",
                "Title regeneration failed: AI unavailable. The decision was applied; titles unchanged.",
            )
        outcome.viewpoint.title_zh = titles["title_zh"]
        outcome.viewpoint.title_en = titles["title_en"]
        src = db.get(Inspiration, session.inspiration_id)
        if src is not None:
            src.title_zh = titles["title_zh"]
            src.title_en = titles["title_en"]
        db.commit()
    return DecisionOut(
        decision_id=outcome.decision.id if outcome.decision else None,
        decision_type=payload.decision_type,
        viewpoint_id=outcome.viewpoint.id if outcome.viewpoint else None,
        display_id=session.inspiration_id,
        session_status=session.status,
        inspiration_status=db.get(Inspiration, session.inspiration_id).status,
    )
