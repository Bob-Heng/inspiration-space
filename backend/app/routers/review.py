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
from ..domain.review import ReviewError, apply_review_decision, open_review_session
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
    )


def _get_session_or_404(session_id: int, db: Session) -> ReviewSession:
    session = db.get(ReviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审议会话不存在")
    return session


@router.post("/sessions", response_model=ReviewSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(payload: ReviewSessionCreate, db: Session = Depends(get_db)) -> ReviewSessionOut:
    """对某灵感开启审议会话。

    同一灵感已有 active 会话时直接返回该会话（断点续聊）；
    有 paused 会话时恢复它；已完结的灵感返回 409。
    """
    inspiration = db.get(Inspiration, payload.inspiration_id)
    if inspiration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="灵感不存在")
    try:
        session = open_review_session(db, inspiration)
    except ReviewError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"会话不在进行中（当前状态：{session.status}），无法发言",
        )
    inspiration = db.get(Inspiration, session.inspiration_id)

    user_message = ReviewMessage(
        session_id=session.id, role="user", content=payload.content
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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
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
        session_id=session.id, role="assistant", content=reply
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return ReviewMessagePair(
        user_message=ReviewMessageOut.model_validate(user_message),
        assistant_message=ReviewMessageOut.model_validate(assistant_message),
    )


@router.post("/sessions/{session_id}/decision", response_model=DecisionOut)
def post_decision(
    session_id: int, payload: DecisionRequest, db: Session = Depends(get_db)
) -> DecisionOut:
    """审议决策：采纳/修改后采纳/否定在一个事务内落库，任一步失败整体回滚；
    暂缓只挂起会话、灵感回到待审队列，不产生终态。"""
    session = _get_session_or_404(session_id, db)
    try:
        outcome = apply_review_decision(
            db,
            session,
            decision_type=payload.decision_type,
            final_content=payload.final_content,
            reason=payload.reason,
            layer=payload.layer,
            tags=payload.tags,
            relations=payload.relations,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return DecisionOut(
        decision_id=outcome.decision.id if outcome.decision else None,
        decision_type=payload.decision_type,
        viewpoint_id=outcome.viewpoint.id if outcome.viewpoint else None,
        session_status=session.status,
        inspiration_status=db.get(Inspiration, session.inspiration_id).status,
    )
