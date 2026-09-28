"""观点库接口：组合筛选列表（TASK-013）、关系/合并/拆分/状态变更与留痕（TASK-014）。"""

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_user
from ..db import get_db
from ..domain.tags import InvalidTagError, validate_tag
from ..domain.viewpoints import (
    ViewpointOpError,
    change_viewpoint_status,
    classified_viewpoints,
    create_relation,
    delete_relation,
    list_events,
    list_relations,
    merge_viewpoints,
    query_viewpoints,
    split_viewpoint,
)
from ..models import (
    ReviewDecision,
    ReviewMessage,
    ReviewSession,
    Viewpoint,
    ViewpointEvent,
)
from ..schemas import (
    ClassifiedOut,
    LayerCode,
    MergeOut,
    MergeRequest,
    RelationCreate,
    RelationOut,
    SplitOut,
    SplitRequest,
    StatusChangeRequest,
    ViewpointEventOut,
    ViewpointOut,
    ViewpointStatus,
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


def _event_out(event: ViewpointEvent) -> ViewpointEventOut:
    return ViewpointEventOut(
        id=event.id,
        viewpoint_id=event.viewpoint_id,
        event_type=event.event_type,
        from_status=event.from_status,
        to_status=event.to_status,
        reason=event.reason,
        detail=json.loads(event.detail) if event.detail else None,
        created_at=event.created_at,
    )


@router.get("", response_model=list[ViewpointOut])
def list_viewpoints(
    layer: LayerCode | None = Query(default=None),
    status_filter: ViewpointStatus | None = Query(default=None, alias="status"),
    domain: str | None = Query(default=None),
    circle: str | None = Query(default=None),
    discipline: str | None = Query(default=None),
    scene: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Viewpoint]:
    """观点列表：分层/状态/四标签族/来源日期区间/关键词组合筛选。"""
    for family, value in (
        ("domain", domain),
        ("circle", circle),
        ("discipline", discipline),
        ("scene", scene),
    ):
        _validate_tag_filter(family, value)
    return query_viewpoints(
        db,
        layer=layer,
        status=status_filter,
        domain=domain,
        circle=circle,
        discipline=discipline,
        scene=scene,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
    )


@router.get("/classified", response_model=ClassifiedOut)
def get_classified(db: Session = Depends(get_db)) -> dict[str, list[Viewpoint]]:
    """分类观点视图：道/法/术三组，排除已否定，悬置保留，组内按来源日期排序。"""
    return classified_viewpoints(db)


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
    """建立关系。建立冲突时双方自动转悬置并互记编号。"""
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
    """解除关系。解除冲突不自动恢复状态，悬置的解除需显式状态操作。"""
    _get_or_404(viewpoint_id, db)
    try:
        delete_relation(db, viewpoint_id, relation_id)
    except ViewpointOpError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return {"deleted_id": relation_id}


@router.post("/{viewpoint_id}/merge", response_model=MergeOut)
def post_merge(
    viewpoint_id: int, payload: MergeRequest, db: Session = Depends(get_db)
) -> MergeOut:
    """把另一条观点合并进本观点：正文无损接续，被合并方转否定留档。"""
    survivor = _get_or_404(viewpoint_id, db)
    try:
        survivor, absorbed = merge_viewpoints(
            db,
            survivor,
            payload.absorbed_id,
            merged_content=payload.merged_content,
            reason=payload.reason,
        )
    except ViewpointOpError as exc:
        raise _conflict_409(exc) from exc
    return MergeOut(
        survivor=ViewpointOut.model_validate(survivor),
        absorbed=ViewpointOut.model_validate(absorbed),
    )


@router.post("/{viewpoint_id}/split", response_model=SplitOut)
def post_split(
    viewpoint_id: int, payload: SplitRequest, db: Session = Depends(get_db)
) -> SplitOut:
    """把本观点拆为多条：原观点转否定记原因，新观点继承分层/标签/来源。"""
    viewpoint = _get_or_404(viewpoint_id, db)
    try:
        original, new_viewpoints = split_viewpoint(
            db, viewpoint, payload.parts, reason=payload.reason
        )
    except ViewpointOpError as exc:
        raise _conflict_409(exc) from exc
    return SplitOut(
        original=ViewpointOut.model_validate(original),
        new_viewpoints=[ViewpointOut.model_validate(v) for v in new_viewpoints],
    )


@router.patch("/{viewpoint_id}/status", response_model=ViewpointOut)
def patch_status(
    viewpoint_id: int, payload: StatusChangeRequest, db: Session = Depends(get_db)
) -> Viewpoint:
    """显式状态变更：悬置/恢复/否定（否定必须填写理由），写留痕。"""
    viewpoint = _get_or_404(viewpoint_id, db)
    try:
        return change_viewpoint_status(
            db, viewpoint, payload.to_status, reason=payload.reason
        )
    except ViewpointOpError as exc:
        raise _conflict_409(exc) from exc


@router.get("/{viewpoint_id}/history", response_model=list[ViewpointEventOut])
def get_history(
    viewpoint_id: int, db: Session = Depends(get_db)
) -> list[ViewpointEventOut]:
    """某观点的写操作留痕（合并/拆分/状态变更/冲突联动），按时间升序。"""
    _get_or_404(viewpoint_id, db)
    return [_event_out(event) for event in list_events(db, viewpoint_id)]
