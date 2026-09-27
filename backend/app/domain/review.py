"""审议会话与审议决策的领域逻辑。

开会话规则（docs/02 §5 审议节、TASK-010）：
- 同一灵感同时只允许一个 active 会话；重复开会话返回进行中的会话；
- 存在已挂起（paused）会话时，开会话即恢复该会话（暂缓不产生新终态，灵感回到 pending 后可再次进入审议）；
- 已完结（reviewed / rejected）的灵感不得再开会话。

决策规则（TASK-011、设计说明书 §6.2 事务节）：
- 采纳 / 修改后采纳：在一个事务内建观点、建相近/冲突关系、记决策、关闭会话、灵感出队留档；任一步失败整体回滚；
- 带冲突关系时新观点与被冲突观点双方转悬置，关系行互记双方编号；
- 否定：记决策（含理由）、关闭会话、灵感出队留档，不建观点；
- 暂缓：不产生任何终态，会话挂起、灵感回到 pending，不写决策记录。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.schemas import AnalysisRelation, AnalysisTags
from ..models import (
    Inspiration,
    ReviewDecision,
    ReviewSession,
    Viewpoint,
    ViewpointRelation,
)
from ..timeutils import utcnow
from .tags import InvalidTagError, LAYER_CODES, validate_layer, validate_tags
from .viewpoint_state import (
    check_inspiration_transition,
    check_session_transition,
    check_viewpoint_transition,
)

INSPIRATION_FINAL_STATUSES = {"reviewed", "rejected"}


class ReviewError(ValueError):
    """审议业务规则冲突（如灵感已完结、会话状态不允许操作）。"""


def open_review_session(db: Session, inspiration: Inspiration) -> ReviewSession:
    """对一条灵感开启（或恢复）审议会话，并把灵感置为 in_review。"""
    if inspiration.status in INSPIRATION_FINAL_STATUSES:
        raise ReviewError(f"灵感 #{inspiration.id} 已审议完结，不得再次审议")

    active = db.scalars(
        select(ReviewSession).where(
            ReviewSession.inspiration_id == inspiration.id,
            ReviewSession.status == "active",
        )
    ).first()
    if active is not None:
        return active

    paused = db.scalars(
        select(ReviewSession)
        .where(
            ReviewSession.inspiration_id == inspiration.id,
            ReviewSession.status == "paused",
        )
        .order_by(ReviewSession.id.desc())
    ).first()
    if paused is not None:
        check_session_transition(paused.status, "active")
        paused.status = "active"
        if inspiration.status == "pending":
            check_inspiration_transition(inspiration.status, "in_review")
            inspiration.status = "in_review"
        db.commit()
        return paused

    if inspiration.status == "pending":
        check_inspiration_transition(inspiration.status, "in_review")
        inspiration.status = "in_review"
    session = ReviewSession(inspiration_id=inspiration.id, status="active")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


DECISION_TYPES = {"accept", "accept_modified", "reject", "defer"}

RELATION_TYPES = {"similar", "conflict"}


@dataclass
class DecisionOutcome:
    """决策落库结果。暂缓不产生决策记录与观点，两字段均为 None。"""

    decision: ReviewDecision | None
    viewpoint: Viewpoint | None


def _normalize_layer(layer: str | None) -> str | None:
    """接受分层代码（dao/fa/shu）或中文标签（道/法/术），统一存代码。"""
    if layer is None:
        return None
    if layer in LAYER_CODES:
        return LAYER_CODES[layer]
    try:
        validate_layer(layer)
    except InvalidTagError as exc:
        raise ReviewError(str(exc)) from exc
    return layer


def apply_review_decision(
    db: Session,
    session: ReviewSession,
    *,
    decision_type: str,
    final_content: str | None = None,
    reason: str | None = None,
    layer: str | None = None,
    tags: AnalysisTags | None = None,
    relations: list[AnalysisRelation] | None = None,
) -> DecisionOutcome:
    """落实审议决策。采纳/否定在一个数据库事务内完成，任一步失败整体回滚。

    业务规则冲突抛出 ReviewError；其余异常回滚后原样抛出。
    """
    if decision_type not in DECISION_TYPES:
        raise ReviewError(f"非法决策类型：{decision_type}")
    if session.status != "active":
        raise ReviewError(f"会话不在进行中（当前状态：{session.status}），无法提交决策")
    inspiration = db.get(Inspiration, session.inspiration_id)

    try:
        if decision_type == "defer":
            check_session_transition(session.status, "paused")
            session.status = "paused"
            check_inspiration_transition(inspiration.status, "pending")
            inspiration.status = "pending"
            db.commit()
            return DecisionOutcome(decision=None, viewpoint=None)

        if decision_type == "reject":
            if reason is None or not reason.strip():
                raise ReviewError("否定必须填写理由")
            decision = ReviewDecision(
                session_id=session.id,
                decision_type=decision_type,
                reason=reason.strip(),
            )
            db.add(decision)
            check_session_transition(session.status, "completed")
            session.status = "completed"
            session.ended_at = utcnow()
            check_inspiration_transition(inspiration.status, "rejected")
            inspiration.status = "rejected"
            db.commit()
            db.refresh(decision)
            return DecisionOutcome(decision=decision, viewpoint=None)

        # accept / accept_modified
        content = final_content.strip() if final_content else None
        if decision_type == "accept_modified" and not content:
            raise ReviewError("修改后采纳必须给出最终正文")
        if not content:
            content = inspiration.content
        layer_code = _normalize_layer(layer)
        tags = tags or AnalysisTags()
        try:
            validate_tags(
                domain=tags.domain,
                circle=tags.circle,
                discipline=tags.discipline,
                scene=tags.scene,
            )
        except InvalidTagError as exc:
            raise ReviewError(str(exc)) from exc

        viewpoint = Viewpoint(
            type="raw",
            content=content,
            source_inspiration_id=inspiration.id,
            source_date=inspiration.source_date,
            layer=layer_code,
            domain=tags.domain,
            circle=tags.circle,
            discipline=tags.discipline,
            scene=tags.scene,
            status="accepted",
        )
        db.add(viewpoint)
        db.flush()

        has_conflict = False
        for relation in relations or []:
            if relation.type not in RELATION_TYPES:
                raise ReviewError(f"非法关系类型：{relation.type}")
            if relation.viewpoint_id == viewpoint.id:
                raise ReviewError("观点不得与自身建立关系")
            target = db.get(Viewpoint, relation.viewpoint_id)
            if target is None:
                raise ReviewError(f"关系目标观点不存在：#{relation.viewpoint_id}")
            if target.status == "rejected":
                raise ReviewError(
                    f"不能与被否定的观点建立关系：#{relation.viewpoint_id}"
                )
            db.add(
                ViewpointRelation(
                    from_viewpoint_id=viewpoint.id,
                    to_viewpoint_id=target.id,
                    relation_type=relation.type,
                )
            )
            if relation.type == "conflict":
                has_conflict = True
                if target.status == "accepted":
                    check_viewpoint_transition(target.status, "suspended")
                    target.status = "suspended"
        if has_conflict:
            check_viewpoint_transition(viewpoint.status, "suspended")
            viewpoint.status = "suspended"

        decision = ReviewDecision(
            session_id=session.id,
            decision_type=decision_type,
            final_content=content,
            reason=reason.strip() if reason else None,
        )
        db.add(decision)
        check_session_transition(session.status, "completed")
        session.status = "completed"
        session.ended_at = utcnow()
        session.viewpoint_id = viewpoint.id
        check_inspiration_transition(inspiration.status, "reviewed")
        inspiration.status = "reviewed"
        db.commit()
        db.refresh(decision)
        db.refresh(viewpoint)
        return DecisionOutcome(decision=decision, viewpoint=viewpoint)
    except Exception:
        db.rollback()
        raise
