"""打磨会话与打磨决策的领域逻辑。

打磨分两个阶段（docs/04 D9）：提炼（distill）→ 打磨（polish）。
新建会话默认进入提炼阶段（phase="distill"），帮用户把现象/素材/疑问收敛为
可裁决的观点；观点草稿即会话关联的 draft 观点本身（录入灵感时已复制创建，
存量数据由 ensure_schema_upgrades 补建），采纳后转为 accepted 对集思录可见。

开会话规则：
- 只有 draft 观点可以开会话：已入库（accepted）的观点不得再开会话；
- 全站同时只允许一个 active 会话：开启/恢复某观点的会话时，其他观点的 active 会话自动挂起（paused），
  再次进入对应观点时恢复（关窗重开据此恢复最近操作的会话）；
- 同一观点重复开会话返回进行中的会话（断点续聊）；
- 存在已挂起（paused）会话时，开会话即恢复该会话。

撤销规则：
- 消息级撤销（undo_last_message）只删不回、不跨阶段：删当前 phase 的最后一条消息；
  删掉的是 assistant 且新的同 phase 末条是 user 时再删该 user 条
  （一次撤销 = 一轮对话或一条落单消息）；无同 phase 消息时不动；
- 阶段级回退（undo_phase）：polish → distill 清空分析（含英文版）并删除全部
  打磨消息，观点正文不动；distill → 重置删除全部消息，观点正文与双语版本
  恢复为关联灵感原文。

决策规则（TASK-011、设计说明书 §6.2 事务节）：只有"采纳"一种决策——
在一个事务内把会话关联的草稿观点转为 accepted（写入最终正文/双语/标题/分层/
标签）、建相近/冲突关系（只建行，不联动任何状态）、记决策、关闭会话；
任一步失败整体回滚。

撤回规则：集思录撤回（withdraw_viewpoint）把 accepted 观点退回 draft，
重开其最近一条 completed 会话（completed → active，阶段与分析消息原样保留），
并作废该会话的采纳决策行；草稿观点重新出现在他山坊队列。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.schemas import AnalysisRelation, AnalysisTags
from ..models import (
    Inspiration,
    ReviewDecision,
    ReviewMessage,
    ReviewSession,
    Viewpoint,
    ViewpointRelation,
)
from ..timeutils import utcnow
from .tags import InvalidTagError, LAYER_CODES, validate_layer, validate_tags
from .viewpoint_state import (
    InvalidTransitionError,
    check_session_transition,
    check_viewpoint_transition,
)


class ReviewError(ValueError):
    """打磨业务规则冲突（如会话状态不允许操作）。"""


class UndoFloorError(ReviewError):
    """撤销地板：观点跳过提炼（录入即为观点且无 distill 消息），
    polish → distill 无更早阶段可回退。"""


def latest_phase_map(db: Session, viewpoint_ids: set[int]) -> dict[int, str]:
    """viewpoint_id → 该观点最近一条非 completed 会话（active/paused）的 phase。

    无进行中/挂起会话的观点不在映射中（调用方兜底 'distill'）；
    同一观点多条会话按会话 id 取最近一条。
    """
    if not viewpoint_ids:
        return {}
    result: dict[int, str] = {}
    for session in db.scalars(
        select(ReviewSession)
        .where(
            ReviewSession.viewpoint_id.in_(viewpoint_ids),
            ReviewSession.status.in_(["active", "paused"]),
        )
        .order_by(ReviewSession.id)
    ):
        result[session.viewpoint_id] = session.phase or "polish"
    return result


def open_review_session(db: Session, viewpoint: Viewpoint) -> ReviewSession:
    """对一条观点开启（或恢复）打磨会话。

    新建会话默认进入提炼阶段（phase="distill"，docs/04 D9）；恢复的会话保留
    其原有阶段。全站同时只允许一个 active 会话：开启/恢复本观点的会话前，
    其他观点的 active 会话一律挂起（paused），再次进入对应观点时恢复。
    已入库（accepted）的观点不得再开会话。
    """
    if viewpoint.status == "accepted":
        raise ReviewError("已入库的观点不得再开会话")

    others = db.scalars(
        select(ReviewSession).where(
            ReviewSession.viewpoint_id != viewpoint.id,
            ReviewSession.status == "active",
        )
    ).all()
    for other in others:
        check_session_transition(other.status, "paused")
        other.status = "paused"

    active = db.scalars(
        select(ReviewSession).where(
            ReviewSession.viewpoint_id == viewpoint.id,
            ReviewSession.status == "active",
        )
    ).first()
    if active is not None:
        if others:
            db.commit()
        return active

    paused = db.scalars(
        select(ReviewSession)
        .where(
            ReviewSession.viewpoint_id == viewpoint.id,
            ReviewSession.status == "paused",
        )
        .order_by(ReviewSession.id.desc())
    ).first()
    if paused is not None:
        check_session_transition(paused.status, "active")
        paused.status = "active"
        db.commit()
        return paused

    # started_at 显式赋值：迁移重建的表缺 server_default（db.py 整表重建手写 DDL
    # 不含 DEFAULT CURRENT_TIMESTAMP），不能依赖数据库默认值
    session = ReviewSession(
        viewpoint_id=viewpoint.id, status="active", phase="distill",
        started_at=utcnow(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _require_active(session: ReviewSession, action: str) -> None:
    if session.status != "active":
        raise ReviewError(f"会话不在进行中（当前状态：{session.status}），无法{action}")


def undo_last_message(db: Session, session: ReviewSession) -> ReviewSession:
    """消息级撤销：只删当前 phase 的最后一条消息（只删不回、不跨阶段）。

    删掉的是 assistant 且新的同 phase 末条是 user 时，再删该 user 条
    （一次撤销 = 一轮对话或一条落单消息）；无同 phase 消息时不动。
    不产生 AI 调用，ai_calls 不留痕。
    """
    _require_active(session, "撤销")
    phase = session.phase or "polish"
    last = db.scalars(
        select(ReviewMessage)
        .where(ReviewMessage.session_id == session.id, ReviewMessage.phase == phase)
        .order_by(ReviewMessage.id.desc())
        .limit(1)
    ).first()
    if last is None:
        return session
    deleted_role = last.role
    db.delete(last)
    db.flush()
    if deleted_role == "assistant":
        new_last = db.scalars(
            select(ReviewMessage)
            .where(ReviewMessage.session_id == session.id, ReviewMessage.phase == phase)
            .order_by(ReviewMessage.id.desc())
            .limit(1)
        ).first()
        if new_last is not None and new_last.role == "user":
            db.delete(new_last)
    db.commit()
    return session


def undo_phase(db: Session, session: ReviewSession) -> ReviewSession:
    """阶段级回退：polish → distill；distill → 重置到提炼最开始。

    polish → distill：分析（含英文版）置空，删除全部 phase='polish' 消息，观点正文不动；
    distill → 重置：删除全部消息，观点正文与双语版本恢复为关联灵感原文
    （无关联灵感时正文不动）。

    撤销地板：观点 is_viewpoint 为 true（录入即判定为观点、跳过了提炼环节）
    且会话无任何 distill 消息时，polish → distill 回退抛 UndoFloorError；
    is_viewpoint 为 NULL/False（旧数据或未判定为观点）不受影响。
    """
    _require_active(session, "阶段回退")
    viewpoint = db.get(Viewpoint, session.viewpoint_id)
    if session.phase == "polish":
        if viewpoint is not None and viewpoint.is_viewpoint:
            has_distill = db.scalar(
                select(ReviewMessage.id)
                .where(
                    ReviewMessage.session_id == session.id,
                    ReviewMessage.phase == "distill",
                )
                .limit(1)
            )
            if has_distill is None:
                raise UndoFloorError("该观点跳过了提炼环节，撤销到打磨开始为止")
        session.phase = "distill"
        session.analysis_json = None
        session.analysis_json_en = None
        db.query(ReviewMessage).where(
            ReviewMessage.session_id == session.id,
            ReviewMessage.phase == "polish",
        ).delete(synchronize_session=False)
    else:
        # distill → 重置：清空全部消息，观点正文恢复为关联灵感原文
        db.query(ReviewMessage).where(
            ReviewMessage.session_id == session.id
        ).delete(synchronize_session=False)
        if viewpoint is not None and viewpoint.source_inspiration_id is not None:
            inspiration = db.get(Inspiration, viewpoint.source_inspiration_id)
            if inspiration is not None:
                viewpoint.content = inspiration.content
                viewpoint.content_zh = inspiration.content_zh
                viewpoint.content_en = inspiration.content_en
                viewpoint.original_lang = inspiration.original_lang
    db.commit()
    return session


DECISION_TYPES = {"accept"}

RELATION_TYPES = {"similar", "conflict"}


@dataclass
class DecisionOutcome:
    """决策落库结果。"""

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
    bilingual: dict | None = None,
    decision_type: str,
    final_content: str | None = None,
    title_zh: str | None = None,
    title_en: str | None = None,
    reason: str | None = None,
    layer: str | None = None,
    tags: AnalysisTags | None = None,
    relations: list[AnalysisRelation] | None = None,
) -> DecisionOutcome:
    """落实打磨决策（仅采纳）：一个事务内完成，任一步失败整体回滚。

    bilingual 为正文变化时由路由层重新双语化的结果（含 original_lang）；
    标题由路由层在请求缺省时用 make_titles 生成后传入。
    业务规则冲突抛出 ReviewError；其余异常回滚后原样抛出。
    """
    if decision_type not in DECISION_TYPES:
        raise ReviewError(f"非法决策类型：{decision_type}")
    _require_active(session, "提交决策")
    viewpoint = db.get(Viewpoint, session.viewpoint_id)
    if viewpoint is None:
        raise ReviewError(f"会话关联的观点不存在：#{session.viewpoint_id}")
    content = final_content.strip() if final_content else ""
    if not content:
        raise ReviewError("采纳必须给出最终正文")
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

    try:
        check_viewpoint_transition(viewpoint.status, "accepted")
        viewpoint.content = content
        if bilingual:
            viewpoint.content_zh = bilingual.get("content_zh")
            viewpoint.content_en = bilingual.get("content_en")
            viewpoint.original_lang = bilingual.get("original_lang") or viewpoint.original_lang
        viewpoint.title_zh = title_zh
        viewpoint.title_en = title_en
        viewpoint.layer = layer_code
        viewpoint.domain = tags.domain
        viewpoint.circle = tags.circle
        viewpoint.discipline = tags.discipline
        viewpoint.scene = tags.scene
        viewpoint.status = "accepted"
        db.flush()

        for relation in relations or []:
            if relation.type not in RELATION_TYPES:
                raise ReviewError(f"非法关系类型：{relation.type}")
            if relation.viewpoint_id == viewpoint.id:
                raise ReviewError("观点不得与自身建立关系")
            target = db.get(Viewpoint, relation.viewpoint_id)
            if target is None:
                raise ReviewError(f"关系目标观点不存在：#{relation.viewpoint_id}")
            # 只建行：冲突/相近均不联动双方状态
            db.add(
                ViewpointRelation(
                    from_viewpoint_id=viewpoint.id,
                    to_viewpoint_id=target.id,
                    relation_type=relation.type,
                )
            )

        decision = ReviewDecision(
            session_id=session.id,
            decision_type=decision_type,
            final_content=viewpoint.content,
            reason=reason.strip() if reason else None,
        )
        db.add(decision)
        check_session_transition(session.status, "completed")
        session.status = "completed"
        session.ended_at = utcnow()
        db.commit()
        db.refresh(decision)
        db.refresh(viewpoint)
        return DecisionOutcome(decision=decision, viewpoint=viewpoint)
    except Exception:
        db.rollback()
        raise


def withdraw_viewpoint(db: Session, viewpoint: Viewpoint) -> Viewpoint:
    """集思录撤回：accepted → draft，重开该观点最近一条 completed 会话。

    重开的会话阶段与分析、消息原样保留（completed → active）；该会话的采纳
    决策行随撤回作废删除。无 completed 会话则不处理会话。
    全站单 active 不变式与开会话一致：重开前其他观点的 active 会话挂起。
    仅 accepted 可撤回，否则抛 InvalidTransitionError。
    """
    if viewpoint.status != "accepted":
        raise InvalidTransitionError(f"仅已入库的观点可撤回（当前状态：{viewpoint.status}）")
    check_viewpoint_transition(viewpoint.status, "draft")
    viewpoint.status = "draft"

    session = db.scalars(
        select(ReviewSession)
        .where(
            ReviewSession.viewpoint_id == viewpoint.id,
            ReviewSession.status == "completed",
        )
        .order_by(ReviewSession.id.desc())
        .limit(1)
    ).first()
    if session is not None:
        others = db.scalars(
            select(ReviewSession).where(
                ReviewSession.viewpoint_id != viewpoint.id,
                ReviewSession.status == "active",
            )
        ).all()
        for other in others:
            check_session_transition(other.status, "paused")
            other.status = "paused"
        check_session_transition(session.status, "active")
        session.status = "active"
        session.ended_at = None
        # 采纳决策随撤回作废
        db.query(ReviewDecision).where(
            ReviewDecision.session_id == session.id,
            ReviewDecision.decision_type == "accept",
        ).delete(synchronize_session=False)
    db.commit()
    db.refresh(viewpoint)
    return viewpoint
