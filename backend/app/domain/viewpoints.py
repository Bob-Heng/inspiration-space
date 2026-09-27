"""观点库领域逻辑：组合筛选查询（TASK-013）、关系/合并/拆分/状态变更（TASK-014）。

规则（docs/02 §4、§5 审议节）：
- 建立冲突关系：双方均转悬置（accepted -> suspended），关系行互记双方编号，不偏向先到者；
- 解除冲突关系不自动恢复状态，悬置的解除由用户显式操作；
- 合并：两条相近观点经确认后无损合并——撇去重复内容直接接续正文，不做改写；
  被合并方标记否定并记录原因，原文保留可追溯；
- 拆分：一条观点拆为多条，原观点标记否定并记录原因，新观点继承分层/标签/来源；
- 合并/拆分/状态变更均写 viewpoint_events 留痕（哪个观点、前后状态、时间）。
"""

import json
from datetime import date

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from ..models import Viewpoint, ViewpointEvent, ViewpointRelation
from .viewpoint_state import InvalidTransitionError, check_viewpoint_transition


class ViewpointOpError(ValueError):
    """观点写操作业务规则冲突。"""


def query_viewpoints(
    db: Session,
    *,
    layer: str | None = None,
    status: str | None = None,
    domain: str | None = None,
    circle: str | None = None,
    discipline: str | None = None,
    scene: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
) -> list[Viewpoint]:
    """按分层/状态/四标签族/来源日期区间/关键词组合筛选观点，按编号升序。"""
    stmt: Select = select(Viewpoint).order_by(Viewpoint.id)
    if layer is not None:
        stmt = stmt.where(Viewpoint.layer == layer)
    if status is not None:
        stmt = stmt.where(Viewpoint.status == status)
    if domain is not None:
        stmt = stmt.where(Viewpoint.domain == domain)
    if circle is not None:
        stmt = stmt.where(Viewpoint.circle == circle)
    if discipline is not None:
        stmt = stmt.where(Viewpoint.discipline == discipline)
    if scene is not None:
        stmt = stmt.where(Viewpoint.scene == scene)
    if date_from is not None:
        stmt = stmt.where(Viewpoint.source_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Viewpoint.source_date <= date_to)
    if keyword:
        stmt = stmt.where(Viewpoint.content.contains(keyword))
    return list(db.scalars(stmt))


RELATION_TYPES = {"similar", "conflict", "related"}


def _transition(viewpoint: Viewpoint, to_status: str) -> None:
    try:
        check_viewpoint_transition(viewpoint.status, to_status)
    except InvalidTransitionError as exc:
        raise ViewpointOpError(str(exc)) from exc


def _record_event(
    db: Session,
    viewpoint: Viewpoint,
    event_type: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str | None = None,
    detail: dict | None = None,
) -> None:
    db.add(
        ViewpointEvent(
            viewpoint_id=viewpoint.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            detail=json.dumps(detail, ensure_ascii=False) if detail else None,
        )
    )


def _get_or_error(db: Session, viewpoint_id: int) -> Viewpoint:
    viewpoint = db.get(Viewpoint, viewpoint_id)
    if viewpoint is None:
        raise ViewpointOpError(f"观点不存在：#{viewpoint_id}")
    return viewpoint


def list_relations(
    db: Session, viewpoint_id: int
) -> list[tuple[ViewpointRelation, Viewpoint]]:
    """某观点的全部关系（双向），按关系编号升序；每项为（关系行，对方观点）。"""
    relations = db.scalars(
        select(ViewpointRelation)
        .where(
            or_(
                ViewpointRelation.from_viewpoint_id == viewpoint_id,
                ViewpointRelation.to_viewpoint_id == viewpoint_id,
            )
        )
        .order_by(ViewpointRelation.id)
    ).all()
    result = []
    for relation in relations:
        counterpart_id = (
            relation.to_viewpoint_id
            if relation.from_viewpoint_id == viewpoint_id
            else relation.from_viewpoint_id
        )
        counterpart = db.get(Viewpoint, counterpart_id)
        if counterpart is not None:
            result.append((relation, counterpart))
    return result


def create_relation(
    db: Session,
    from_viewpoint: Viewpoint,
    to_viewpoint_id: int,
    relation_type: str,
) -> ViewpointRelation:
    """建立相近/冲突/相关关系。冲突时双方转悬置并写留痕。"""
    if relation_type not in RELATION_TYPES:
        raise ViewpointOpError(f"非法关系类型：{relation_type}")
    if to_viewpoint_id == from_viewpoint.id:
        raise ViewpointOpError("观点不得与自身建立关系")
    target = _get_or_error(db, to_viewpoint_id)
    if from_viewpoint.status == "rejected" or target.status == "rejected":
        raise ViewpointOpError("被否定的观点不得建立关系")

    existing = db.scalars(
        select(ViewpointRelation).where(
            ViewpointRelation.relation_type == relation_type,
            or_(
                (ViewpointRelation.from_viewpoint_id == from_viewpoint.id)
                & (ViewpointRelation.to_viewpoint_id == to_viewpoint_id),
                (ViewpointRelation.from_viewpoint_id == to_viewpoint_id)
                & (ViewpointRelation.to_viewpoint_id == from_viewpoint.id),
            ),
        )
    ).first()
    if existing is not None:
        raise ViewpointOpError(
            f"关系已存在：#{from_viewpoint.id} 与 #{to_viewpoint_id}（{relation_type}）"
        )

    relation = ViewpointRelation(
        from_viewpoint_id=from_viewpoint.id,
        to_viewpoint_id=to_viewpoint_id,
        relation_type=relation_type,
    )
    db.add(relation)
    db.flush()

    if relation_type == "conflict":
        for viewpoint, other in ((from_viewpoint, target), (target, from_viewpoint)):
            if viewpoint.status == "accepted":
                _transition(viewpoint, "suspended")
                viewpoint.status = "suspended"
                _record_event(
                    db,
                    viewpoint,
                    "conflict_suspend",
                    from_status="accepted",
                    to_status="suspended",
                    detail={
                        "conflict_with": other.id,
                        "relation_id": relation.id,
                    },
                )
    db.commit()
    db.refresh(relation)
    return relation


def delete_relation(db: Session, viewpoint_id: int, relation_id: int) -> None:
    """解除关系。不自动恢复任何状态（悬置的解除由用户显式操作）。"""
    relation = db.get(ViewpointRelation, relation_id)
    if relation is None or viewpoint_id not in (
        relation.from_viewpoint_id,
        relation.to_viewpoint_id,
    ):
        raise ViewpointOpError(f"关系不存在：#{relation_id}")
    db.delete(relation)
    db.commit()


def change_viewpoint_status(
    db: Session,
    viewpoint: Viewpoint,
    to_status: str,
    reason: str | None = None,
) -> Viewpoint:
    """显式状态变更（悬置/恢复/否定）。否定必须填写理由；写留痕。"""
    _transition(viewpoint, to_status)
    if to_status == "rejected" and (reason is None or not reason.strip()):
        raise ViewpointOpError("否定必须填写理由")
    from_status = viewpoint.status
    viewpoint.status = to_status
    _record_event(
        db,
        viewpoint,
        "status_change",
        from_status=from_status,
        to_status=to_status,
        reason=reason.strip() if reason else None,
    )
    db.commit()
    db.refresh(viewpoint)
    return viewpoint


def _auto_merge_content(survivor_content: str, absorbed_content: str) -> str:
    """无损合并：撇去重复内容直接接续，不做改写。"""
    if absorbed_content in survivor_content:
        return survivor_content
    if survivor_content in absorbed_content:
        return absorbed_content
    return f"{survivor_content}\n{absorbed_content}"


def merge_viewpoints(
    db: Session,
    survivor: Viewpoint,
    absorbed_id: int,
    merged_content: str | None = None,
    reason: str | None = None,
) -> tuple[Viewpoint, Viewpoint]:
    """把 absorbed 合并进 survivor：survivor 正文为双方接续，absorbed 转否定留档。

    merged_content 为空时自动无损接续；双方写 merge 留痕。
    """
    if absorbed_id == survivor.id:
        raise ViewpointOpError("观点不得与自身合并")
    if reason is None or not reason.strip():
        raise ViewpointOpError("合并必须填写原因")
    absorbed = _get_or_error(db, absorbed_id)
    if survivor.status == "rejected" or absorbed.status == "rejected":
        raise ViewpointOpError("被否定的观点不得参与合并")

    survivor_content_before = survivor.content
    final_content = (
        merged_content.strip()
        if merged_content and merged_content.strip()
        else _auto_merge_content(survivor.content, absorbed.content)
    )
    survivor.content = final_content
    _record_event(
        db,
        survivor,
        "merge",
        from_status=survivor.status,
        to_status=survivor.status,
        reason=reason.strip(),
        detail={
            "absorbed_id": absorbed.id,
            "content_before": survivor_content_before,
            "absorbed_content": absorbed.content,
        },
    )

    absorbed_from = absorbed.status
    _transition(absorbed, "rejected")
    absorbed.status = "rejected"
    _record_event(
        db,
        absorbed,
        "merge",
        from_status=absorbed_from,
        to_status="rejected",
        reason=reason.strip(),
        detail={"merged_into": survivor.id},
    )
    db.commit()
    db.refresh(survivor)
    db.refresh(absorbed)
    return survivor, absorbed


def split_viewpoint(
    db: Session,
    viewpoint: Viewpoint,
    parts: list[str],
    reason: str | None = None,
) -> tuple[Viewpoint, list[Viewpoint]]:
    """把一条观点拆为多条：原观点转否定记原因，新观点继承分层/标签/来源/拆分前状态。"""
    if reason is None or not reason.strip():
        raise ViewpointOpError("拆分必须填写原因")
    if viewpoint.status == "rejected":
        raise ViewpointOpError("被否定的观点不得拆分")
    contents = [part.strip() for part in parts]
    if len(contents) < 2 or any(not part for part in contents):
        raise ViewpointOpError("拆分至少需要 2 条非空正文")

    new_viewpoints = []
    for content in contents:
        new_viewpoint = Viewpoint(
            type=viewpoint.type,
            content=content,
            source_inspiration_id=viewpoint.source_inspiration_id,
            source_date=viewpoint.source_date,
            layer=viewpoint.layer,
            domain=viewpoint.domain,
            circle=viewpoint.circle,
            discipline=viewpoint.discipline,
            scene=viewpoint.scene,
            status=viewpoint.status,
        )
        db.add(new_viewpoint)
        new_viewpoints.append(new_viewpoint)
    db.flush()

    from_status = viewpoint.status
    _transition(viewpoint, "rejected")
    viewpoint.status = "rejected"
    _record_event(
        db,
        viewpoint,
        "split",
        from_status=from_status,
        to_status="rejected",
        reason=reason.strip(),
        detail={"new_viewpoint_ids": [v.id for v in new_viewpoints]},
    )
    for new_viewpoint in new_viewpoints:
        _record_event(
            db,
            new_viewpoint,
            "split",
            to_status=new_viewpoint.status,
            detail={"split_from": viewpoint.id},
        )
    db.commit()
    for item in [viewpoint, *new_viewpoints]:
        db.refresh(item)
    return viewpoint, new_viewpoints


def list_events(db: Session, viewpoint_id: int) -> list[ViewpointEvent]:
    """某观点的写操作留痕，按时间升序。"""
    return list(
        db.scalars(
            select(ViewpointEvent)
            .where(ViewpointEvent.viewpoint_id == viewpoint_id)
            .order_by(ViewpointEvent.id)
        )
    )


def classified_viewpoints(db: Session) -> dict[str, list[Viewpoint]]:
    """分类观点视图（docs/02 §5 分类观点生成）：按道/法/术分组，已否定不列入，
    悬置保留（由前端标记），组内按来源日期升序（无日期排最后）。

    设计预留：未来派生观点（type='derived'）与原始观点合并收录于本视图，
    派生观点状态为可重算的缓存字段，失效者届时与已否定一并排除。
    """
    stmt = (
        select(Viewpoint)
        .where(Viewpoint.status != "rejected", Viewpoint.layer.is_not(None))
        .order_by(Viewpoint.source_date.is_(None), Viewpoint.source_date, Viewpoint.id)
    )
    groups: dict[str, list[Viewpoint]] = {"dao": [], "fa": [], "shu": []}
    for viewpoint in db.scalars(stmt):
        if viewpoint.layer in groups:
            groups[viewpoint.layer].append(viewpoint)
    return groups
