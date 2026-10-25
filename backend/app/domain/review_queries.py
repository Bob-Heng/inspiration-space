"""讨论期按需查询：只暴露指定展示编号的已入库观点，不提供其讨论全文。

全站统一展示编号 = 来源灵感 id，无来源时兜底观点 id。AI 分析与工具调用
均以此编号面向用户；内部关系仍使用 viewpoints.id。
"""

import json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..ai.schemas import AnalysisRelation, AnalysisResult
from ..models import (
    Inspiration,
    ReviewDecision,
    ReviewSession,
    Viewpoint,
    ViewpointRelation,
)
from .tags import LAYER_LABELS

ACCEPTED_TOOL = "get_accepted_viewpoint"


def display_id(viewpoint: Viewpoint) -> int:
    return viewpoint.source_inspiration_id or viewpoint.id


def accepted_display_map(db: Session) -> dict[int, Viewpoint]:
    return {
        display_id(vp): vp
        for vp in db.scalars(select(Viewpoint).where(Viewpoint.status == "accepted"))
    }


def get_accepted_by_display_id(db: Session, number: int) -> Viewpoint | None:
    return accepted_display_map(db).get(number)


def relation_display_id(relation: AnalysisRelation) -> int:
    """新分析使用展示编号；viewpoint_id 仅为旧分析的兼容字段。"""
    return relation.display_id if relation.display_id is not None else relation.viewpoint_id


def canonicalize_analysis(db: Session, analysis: AnalysisResult) -> AnalysisResult:
    """旧分析的内部 id 转成展示编号，避免把两套编号同时交给模型。"""
    for relation in analysis.relations:
        if relation.display_id is None and relation.viewpoint_id is not None:
            target = db.get(Viewpoint, relation.viewpoint_id)
            if target is not None:
                relation.display_id = display_id(target)
                relation.viewpoint_id = None
    return analysis


def analysis_for_display(db: Session, raw: str | None) -> dict | None:
    """历史分析在响应层转换为展示编号，不改写数据库原文。

    只处理 relations，允许早期不完整或缺字段的分析继续正常展示。
    """
    if not raw:
        return None
    data = json.loads(raw)
    for relation in data.get("relations", []):
        if relation.get("display_id") is None and relation.get("viewpoint_id") is not None:
            target = db.get(Viewpoint, relation["viewpoint_id"])
            if target is not None:
                relation["display_id"] = display_id(target)
                relation.pop("viewpoint_id", None)
    return data


def _related(db: Session, viewpoint: Viewpoint) -> list[dict]:
    rows = db.scalars(
        select(ViewpointRelation).where(
            or_(
                ViewpointRelation.from_viewpoint_id == viewpoint.id,
                ViewpointRelation.to_viewpoint_id == viewpoint.id,
            )
        )
    )
    result = []
    for row in rows:
        other_id = (
            row.to_viewpoint_id
            if row.from_viewpoint_id == viewpoint.id
            else row.from_viewpoint_id
        )
        other = db.get(Viewpoint, other_id)
        if other is not None:
            result.append({"number": display_id(other), "type": row.relation_type})
    return sorted(result, key=lambda item: (item["number"], item["type"]))


def _tags(viewpoint: Viewpoint) -> dict:
    return {
        "domain": viewpoint.domain,
        "circle": viewpoint.circle,
        "discipline": viewpoint.discipline,
        "scene": viewpoint.scene,
    }


def _accepted_at(db: Session, viewpoint: Viewpoint):
    decision = db.scalars(
        select(ReviewDecision)
        .join(ReviewSession, ReviewDecision.session_id == ReviewSession.id)
        .where(
            ReviewSession.viewpoint_id == viewpoint.id,
            ReviewDecision.decision_type.in_(["accept", "accept_modified"]),
        )
        .order_by(ReviewDecision.id.desc())
        .limit(1)
    ).first()
    # 迁移观点没有决策记录时，以观点创建时间作为可核实的入库时间兜底
    return (decision.created_at if decision else viewpoint.created_at).isoformat()


def query_accepted_viewpoint(db: Session, number: int) -> dict:
    viewpoint = get_accepted_by_display_id(db, number)
    if viewpoint is None:
        return {
            "error": "viewpoint_not_found",
            "message": f"未找到已入库观点 #{number}；编号按界面展示编号。",
        }
    inspiration = (
        db.get(Inspiration, viewpoint.source_inspiration_id)
        if viewpoint.source_inspiration_id is not None
        else None
    )
    return {
        "number": display_id(viewpoint),
        "title_zh": viewpoint.title_zh,
        "title_en": viewpoint.title_en,
        "content": viewpoint.content,
        "source_inspiration": (
            {
                "title_zh": inspiration.title_zh,
                "title_en": inspiration.title_en,
                "content": inspiration.content,
            }
            if inspiration is not None
            else None
        ),
        "layer": LAYER_LABELS.get(viewpoint.layer) if viewpoint.layer else None,
        "tags": _tags(viewpoint),
        "source_date": viewpoint.source_date.isoformat() if viewpoint.source_date else None,
        "accepted_at": _accepted_at(db, viewpoint),
        "related_viewpoints": _related(db, viewpoint),
    }


def execute_review_tool(db: Session, tool: str, target: int | str) -> dict:
    if tool == ACCEPTED_TOOL:
        return query_accepted_viewpoint(db, int(target))
    return {"error": "unknown_tool", "message": f"未知查询工具：{tool}"}
