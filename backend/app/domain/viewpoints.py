"""观点库领域逻辑：组合筛选查询（TASK-013）与关系。

规则（观点为中心重构后）：
- 观点状态只有 draft / accepted：draft 为他山坊打磨中、对集思录隐藏，accepted 为已入库；
  状态只由打磨决策（采纳）与集思录撤回改变（见 domain.review），无显式状态端点；
- 建立关系只记关系行（相近/冲突/相关），不再联动变更任何状态；
- 解除关系不自动恢复状态；
- 合并/拆分与操作留痕（viewpoint_events）已从系统删除。
"""

from datetime import date

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from ..models import Viewpoint, ViewpointRelation


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
    """建立相近/冲突/相关关系。只记关系行，不联动变更任何状态。"""
    if relation_type not in RELATION_TYPES:
        raise ViewpointOpError(f"非法关系类型：{relation_type}")
    if to_viewpoint_id == from_viewpoint.id:
        raise ViewpointOpError("观点不得与自身建立关系")
    _get_or_error(db, to_viewpoint_id)

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
    db.commit()
    db.refresh(relation)
    return relation


def delete_relation(db: Session, viewpoint_id: int, relation_id: int) -> None:
    """解除关系。不自动恢复任何状态。"""
    relation = db.get(ViewpointRelation, relation_id)
    if relation is None or viewpoint_id not in (
        relation.from_viewpoint_id,
        relation.to_viewpoint_id,
    ):
        raise ViewpointOpError(f"关系不存在：#{relation_id}")
    db.delete(relation)
    db.commit()


def conflict_display_map(db: Session, viewpoint_ids: set[int]) -> dict[int, list[int]]:
    """viewpoint_id → 冲突对方的展示编号列表（集思录冲突标记用）。

    展示编号 = 对方 source_inspiration_id，无来源兜底对方 id；排序去重。
    两次查询（关系行 + 对方观点）+ 内存映射，避免逐观点 N+1；
    对方观点已不存在的关系行跳过。无冲突的观点不在映射中（调用方兜底 []）。
    """
    if not viewpoint_ids:
        return {}
    relations = list(
        db.scalars(
            select(ViewpointRelation).where(
                ViewpointRelation.relation_type == "conflict",
                or_(
                    ViewpointRelation.from_viewpoint_id.in_(viewpoint_ids),
                    ViewpointRelation.to_viewpoint_id.in_(viewpoint_ids),
                ),
            )
        )
    )
    pairs: list[tuple[int, int]] = []  # (本观点 id, 对方观点 id)
    counterpart_ids: set[int] = set()
    for relation in relations:
        for vid, other_id in (
            (relation.from_viewpoint_id, relation.to_viewpoint_id),
            (relation.to_viewpoint_id, relation.from_viewpoint_id),
        ):
            if vid in viewpoint_ids:
                pairs.append((vid, other_id))
                counterpart_ids.add(other_id)
    if not counterpart_ids:
        return {}
    counterparts = {
        v.id: v
        for v in db.scalars(select(Viewpoint).where(Viewpoint.id.in_(counterpart_ids)))
    }
    displays: dict[int, set[int]] = {}
    for vid, other_id in pairs:
        other = counterparts.get(other_id)
        if other is None:
            continue
        displays.setdefault(vid, set()).add(other.source_inspiration_id or other.id)
    return {vid: sorted(ids) for vid, ids in displays.items()}


def classified_viewpoints(db: Session) -> dict[str, list[Viewpoint]]:
    """分类观点视图（docs/02 §5 分类观点生成）：按道/法/术分组，只收已采纳
    （draft 打磨中对集思录隐藏），组内按来源日期升序（无日期排最后）。

    设计预留：未来派生观点（type='derived'）与原始观点合并收录于本视图，
    派生观点状态为可重算的缓存字段，失效者届时与草稿一并排除。
    """
    stmt = (
        select(Viewpoint)
        .where(Viewpoint.status == "accepted", Viewpoint.layer.is_not(None))
        .order_by(Viewpoint.source_date.is_(None), Viewpoint.source_date, Viewpoint.id)
    )
    groups: dict[str, list[Viewpoint]] = {"dao": [], "fa": [], "shu": []}
    for viewpoint in db.scalars(stmt):
        if viewpoint.layer in groups:
            groups[viewpoint.layer].append(viewpoint)
    return groups
