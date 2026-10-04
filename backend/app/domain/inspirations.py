"""灵感领域逻辑：级联删除、编号分配、关联草稿观点与观点判断。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import LLMError, LLMProvider, run_structured_call
from ..ai.prompts.viewpoint_check import (
    PROMPT_VERSION as VIEWPOINT_CHECK_PROMPT_VERSION,
    build_viewpoint_check_messages,
)
from ..ai.schemas import ViewpointCheck
from ..models import (
    Inspiration,
    ReviewDecision,
    ReviewMessage,
    ReviewSession,
    Viewpoint,
    ViewpointRelation,
)


def next_inspiration_id(db: Session) -> int:
    """最小未占用正整数编号：删号可复用，但不向前递补已有编号。"""
    ids = sorted(db.scalars(select(Inspiration.id)).all())
    candidate = 1
    for existing in ids:
        if existing == candidate:
            candidate += 1
        elif existing > candidate:
            break
    return candidate


def create_draft_viewpoint(db: Session, inspiration: Inspiration) -> Viewpoint:
    """为灵感创建关联草稿观点：复制正文/双语/原文语言/来源日期/标题。

    标题在采纳前沿用灵感标题（灵感标题本身不改动，docs/04 D10）；
    进入打磨与采纳时再按观点正文重新生成。
    与灵感录入在同一事务内完成（调用方负责 flush/commit）。
    """
    viewpoint = Viewpoint(
        type="raw",
        content=inspiration.content,
        source_inspiration_id=inspiration.id,
        source_date=inspiration.source_date,
        status="draft",
        content_zh=inspiration.content_zh,
        content_en=inspiration.content_en,
        original_lang=inspiration.original_lang,
        title_zh=inspiration.title_zh,
        title_en=inspiration.title_en,
    )
    db.add(viewpoint)
    db.flush()
    return viewpoint


def linked_viewpoint(db: Session, inspiration_id: int) -> Viewpoint | None:
    """灵感的关联观点（每条灵感至多一条，取最早建的一条）。"""
    return db.scalars(
        select(Viewpoint)
        .where(Viewpoint.source_inspiration_id == inspiration_id)
        .order_by(Viewpoint.id)
        .limit(1)
    ).first()


async def judge_viewpoint(
    db: Session, provider: LLMProvider | None, viewpoint: Viewpoint
) -> None:
    """观点判断前置：以观点正文为输入判断是否已构成可裁决的观点，写入 is_viewpoint。

    AI 未配置/不可用/输出非法时置 NULL（未判断），不阻断业务流程；
    调用留痕（成功或失败）由 run_structured_call 完成。
    provider 为 None 时跳过判断（配置缺失无留痕对象），直接置 NULL。
    调用方负责 commit。
    """
    if provider is None:
        viewpoint.is_viewpoint = None
        return
    try:
        result = await run_structured_call(
            db,
            provider,
            prompt_version=VIEWPOINT_CHECK_PROMPT_VERSION,
            schema=ViewpointCheck,
            messages=build_viewpoint_check_messages(viewpoint),
        )
    except LLMError:
        viewpoint.is_viewpoint = None
    else:
        viewpoint.is_viewpoint = result.is_viewpoint


def reset_sessions_for_edit(db: Session, viewpoint: Viewpoint) -> None:
    """灵感被编辑后，重置该观点的 active/paused 会话到提炼最开始：

    phase='distill'、分析（含英文版）置空、删除全部消息（调用方负责 commit）。
    """
    sessions = db.scalars(
        select(ReviewSession).where(
            ReviewSession.viewpoint_id == viewpoint.id,
            ReviewSession.status.in_(["active", "paused"]),
        )
    ).all()
    for session in sessions:
        session.phase = "distill"
        session.analysis_json = None
        session.analysis_json_en = None
        db.query(ReviewMessage).where(
            ReviewMessage.session_id == session.id
        ).delete(synchronize_session=False)


def cascade_delete_inspiration(db: Session, inspiration: Inspiration) -> dict:
    """删除一条灵感及其全部关联数据（单事务，无残留）。"""
    iid = inspiration.id
    derived_vp_ids = [
        v.id
        for v in db.scalars(
            select(Viewpoint).where(Viewpoint.source_inspiration_id == iid)
        )
    ]
    guard_vp = derived_vp_ids or [0]

    session_ids = [
        s.id
        for s in db.scalars(
            select(ReviewSession).where(ReviewSession.viewpoint_id.in_(guard_vp))
        )
    ]
    guard_s = session_ids or [0]

    n_messages = db.query(ReviewMessage).where(
        ReviewMessage.session_id.in_(guard_s)
    ).delete(synchronize_session=False)
    n_decisions = db.query(ReviewDecision).where(
        ReviewDecision.session_id.in_(guard_s)
    ).delete(synchronize_session=False)
    n_sessions = db.query(ReviewSession).where(
        ReviewSession.id.in_(guard_s)
    ).delete(synchronize_session=False)

    n_relations = db.query(ViewpointRelation).where(
        (ViewpointRelation.from_viewpoint_id.in_(guard_vp))
        | (ViewpointRelation.to_viewpoint_id.in_(guard_vp))
    ).delete(synchronize_session=False)
    n_viewpoints = db.query(Viewpoint).where(
        Viewpoint.id.in_(guard_vp)
    ).delete(synchronize_session=False)

    db.delete(inspiration)
    db.commit()
    return {
        "deleted_id": iid,
        "sessions": n_sessions,
        "messages": n_messages,
        "decisions": n_decisions,
        "viewpoints": n_viewpoints,
        "relations": n_relations,
    }
