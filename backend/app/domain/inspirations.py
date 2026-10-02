"""灵感领域逻辑：级联删除与编号分配。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Inspiration,
    ReviewDecision,
    ReviewMessage,
    ReviewSession,
    Viewpoint,
    ViewpointEvent,
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
            select(ReviewSession).where(
                (ReviewSession.inspiration_id == iid)
                | (ReviewSession.viewpoint_id.in_(guard_vp))
            )
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
    n_events = db.query(ViewpointEvent).where(
        ViewpointEvent.viewpoint_id.in_(guard_vp)
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
        "events": n_events,
    }
