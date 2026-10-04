"""观点库接口：组合筛选列表（TASK-013，只收已采纳）、关系、撤回与标题更新。

合并/拆分/操作留痕已删除；显式状态变更端点已删除——状态只由打磨决策
（draft → accepted）与撤回（accepted → draft）改变。建立关系只记关系行，
不联动任何状态（含冲突）。
"""

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_user
from ..db import get_db
from ..errors import biz_error
from ..domain.review import withdraw_viewpoint
from ..domain.tags import InvalidTagError, validate_tag
from ..domain.viewpoint_state import InvalidTransitionError
from ..domain.viewpoints import (
    ViewpointOpError,
    classified_viewpoints,
    conflict_display_map,
    create_relation,
    delete_relation,
    list_relations,
    query_viewpoints,
)
from ..models import (
    ReviewDecision,
    ReviewMessage,
    ReviewSession,
    Viewpoint,
)
from ..schemas import (
    ClassifiedOut,
    LayerCode,
    RelationCreate,
    RelationOut,
    ViewpointOut,
    ViewpointTitleUpdate,
)

router = APIRouter(
    prefix="/api/viewpoints",
    tags=["viewpoints"],
    dependencies=[Depends(require_user)],
)


def _validate_tag_filter(family: str, value: str | None) -> None:
    try:
        validate_tag(family, value)
    except InvalidTagError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


def _get_or_404(viewpoint_id: int, db: Session) -> Viewpoint:
    viewpoint = db.get(Viewpoint, viewpoint_id)
    if viewpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="观点不存在")
    return viewpoint


def _conflict_409(exc: ViewpointOpError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def _with_conflicts(db: Session, viewpoints: list[Viewpoint]) -> list[ViewpointOut]:
    """批量组装 ViewpointOut 并附上 conflict_with（冲突对方展示编号，无冲突为 []）。

    仅集思录列表/分类视图使用；其他场景不调用，conflict_with 保持默认 None。
    """
    conflicts = conflict_display_map(db, {v.id for v in viewpoints})
    result = []
    for viewpoint in viewpoints:
        out = ViewpointOut.model_validate(viewpoint)
        out.conflict_with = conflicts.get(viewpoint.id, [])
        result.append(out)
    return result


@router.get("", response_model=list[ViewpointOut])
def list_viewpoints(
    layer: LayerCode | None = Query(default=None),
    domain: str | None = Query(default=None),
    circle: str | None = Query(default=None),
    discipline: str | None = Query(default=None),
    scene: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ViewpointOut]:
    """观点列表（集思录）：只收已采纳；分层/四标签族/来源日期区间/关键词组合筛选。
    每项附 conflict_with（冲突对方展示编号，供冲突标记渲染）。"""
    for family, value in (
        ("domain", domain),
        ("circle", circle),
        ("discipline", discipline),
        ("scene", scene),
    ):
        _validate_tag_filter(family, value)
    viewpoints = query_viewpoints(
        db,
        layer=layer,
        status="accepted",
        domain=domain,
        circle=circle,
        discipline=discipline,
        scene=scene,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
    )
    return _with_conflicts(db, viewpoints)


@router.get("/classified", response_model=ClassifiedOut)
def get_classified(db: Session = Depends(get_db)) -> ClassifiedOut:
    """分类观点视图：道/法/术三组，只收已采纳，组内按来源日期排序。
    每项附 conflict_with（冲突对方展示编号，供冲突标记渲染）。"""
    groups = classified_viewpoints(db)
    conflicts = conflict_display_map(
        db, {v.id for group in groups.values() for v in group}
    )
    result = {}
    for layer, group in groups.items():
        items = []
        for viewpoint in group:
            out = ViewpointOut.model_validate(viewpoint)
            out.conflict_with = conflicts.get(viewpoint.id, [])
            items.append(out)
        result[layer] = items
    return ClassifiedOut(**result)


@router.get("/{viewpoint_id}", response_model=ViewpointOut)
def get_viewpoint(viewpoint_id: int, db: Session = Depends(get_db)) -> Viewpoint:
    return _get_or_404(viewpoint_id, db)


@router.get("/{viewpoint_id}/review-history")
def get_review_history(viewpoint_id: int, db: Session = Depends(get_db)) -> dict:
    """观点的审议历史（只读）：会话 + 讨论消息 + 决策 + 当时的 AI 分析。"""
    _get_or_404(viewpoint_id, db)
    session = db.scalar(
        select(ReviewSession)
        .where(ReviewSession.viewpoint_id == viewpoint_id)
        .order_by(ReviewSession.id.desc())
    )
    if session is None:
        return {"exists": False}
    messages = list(
        db.scalars(
            select(ReviewMessage)
            .where(ReviewMessage.session_id == session.id)
            .order_by(ReviewMessage.id)
        )
    )
    decision = db.scalar(
        select(ReviewDecision)
        .where(ReviewDecision.session_id == session.id)
        .order_by(ReviewDecision.id.desc())
    )
    return {
        "exists": True,
        "session": {
            "id": session.id,
            "status": session.status,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
        },
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "content_zh": m.content_zh,
                "content_en": m.content_en,
                "original_lang": m.original_lang,
                "created_at": m.created_at,
            }
            for m in messages
        ],
        "decision": (
            {
                "decision_type": decision.decision_type,
                "final_content": decision.final_content,
                "reason": decision.reason,
                "created_at": decision.created_at,
            }
            if decision
            else None
        ),
        "analysis": json.loads(session.analysis_json) if session.analysis_json else None,
        "analysis_en": (
            json.loads(session.analysis_json_en) if session.analysis_json_en else None
        ),
    }


@router.get("/{viewpoint_id}/relations", response_model=list[RelationOut])
def get_relations(viewpoint_id: int, db: Session = Depends(get_db)) -> list[RelationOut]:
    """某观点的全部相近/冲突/相关关系（双向），每项含对方观点完整字段。"""
    _get_or_404(viewpoint_id, db)
    return [
        RelationOut(
            id=relation.id,
            relation_type=relation.relation_type,
            created_at=relation.created_at,
            viewpoint=ViewpointOut.model_validate(counterpart),
        )
        for relation, counterpart in list_relations(db, viewpoint_id)
    ]


@router.post(
    "/{viewpoint_id}/relations",
    response_model=RelationOut,
    status_code=status.HTTP_201_CREATED,
)
def post_relation(
    viewpoint_id: int, payload: RelationCreate, db: Session = Depends(get_db)
) -> RelationOut:
    """建立关系。只记关系行，不联动变更任何状态。"""
    viewpoint = _get_or_404(viewpoint_id, db)
    try:
        relation = create_relation(
            db, viewpoint, payload.to_viewpoint_id, payload.relation_type
        )
    except ViewpointOpError as exc:
        raise _conflict_409(exc) from exc
    counterpart = db.get(Viewpoint, payload.to_viewpoint_id)
    return RelationOut(
        id=relation.id,
        relation_type=relation.relation_type,
        created_at=relation.created_at,
        viewpoint=ViewpointOut.model_validate(counterpart),
    )


@router.delete("/{viewpoint_id}/relations/{relation_id}")
def remove_relation(
    viewpoint_id: int, relation_id: int, db: Session = Depends(get_db)
) -> dict:
    """解除关系。不自动恢复任何状态。"""
    _get_or_404(viewpoint_id, db)
    try:
        delete_relation(db, viewpoint_id, relation_id)
    except ViewpointOpError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return {"deleted_id": relation_id}


@router.post("/{viewpoint_id}/withdraw", response_model=ViewpointOut)
def withdraw(viewpoint_id: int, db: Session = Depends(get_db)) -> Viewpoint:
    """集思录撤回：accepted → draft；重开该观点最近一条 completed 会话
    （阶段/分析/消息原样保留），该会话的采纳决策行随撤回作废删除。
    草稿观点重新出现在他山坊队列。仅 accepted 可撤回。"""
    viewpoint = _get_or_404(viewpoint_id, db)
    try:
        return withdraw_viewpoint(db, viewpoint)
    except InvalidTransitionError as exc:
        raise biz_error(
            409, "withdraw_conflict", str(exc),
            "Only an accepted viewpoint can be withdrawn",
        ) from exc


@router.patch("/{viewpoint_id}/title", response_model=ViewpointOut)
def patch_title(
    viewpoint_id: int, payload: ViewpointTitleUpdate, db: Session = Depends(get_db)
) -> Viewpoint:
    """观点标题更新：两字段独立可空更新（缺省语种不动），全空 422。"""
    viewpoint = _get_or_404(viewpoint_id, db)
    if payload.title_zh is not None:
        viewpoint.title_zh = payload.title_zh.strip() or None
    if payload.title_en is not None:
        viewpoint.title_en = payload.title_en.strip() or None
    db.commit()
    db.refresh(viewpoint)
    return viewpoint
