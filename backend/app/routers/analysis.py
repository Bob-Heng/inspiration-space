"""打磨分析接口：AI 对指定观点输出三项分析与第一轮疑问。

AI 只返回建议；除写 ai_calls 留痕外，本接口把分析结果（含英文版）持久化到
该观点的 active 会话（关窗重开随会话恢复）。分析对象为观点正文：草稿观点
正文即提炼产物。reset=1 时先删除该会话全部打磨（polish）阶段消息再生成
（前端"重新生成"已弹窗确认，提炼阶段对话保留）。
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import (
    LLMConfigError,
    LLMOutputError,
    LLMProvider,
    LLMUnavailableError,
    llm_provider_dependency,
    run_structured_call,
)
from ..ai.prompts.analysis import PROMPT_VERSION, build_analysis_messages
from ..ai.schemas import AnalysisResult
from ..auth import require_user
from ..db import get_db
from ..errors import biz_error
from ..domain.analysis import validate_analysis_result
from ..domain.translation import bilingual_analysis
from ..models import ReviewMessage, ReviewSession, Viewpoint

router = APIRouter(
    prefix="/api/viewpoints",
    tags=["analysis"],
    dependencies=[Depends(require_user)],
)


@router.post("/{viewpoint_id}/analysis", response_model=AnalysisResult)
async def analyze_viewpoint(
    viewpoint_id: int,
    reset: bool = False,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(llm_provider_dependency),
) -> AnalysisResult:
    viewpoint = db.get(Viewpoint, viewpoint_id)
    if viewpoint is None:
        raise biz_error(404, "viewpoint_not_found", "观点不存在", "Viewpoint not found")
    # 观点库快照只收已采纳：draft 打磨中对集思录（及 AI 上下文）隐藏
    viewpoints = list(
        db.scalars(
            select(Viewpoint)
            .where(Viewpoint.status == "accepted")
            .order_by(Viewpoint.id)
        )
    )
    existing_ids = {vp.id for vp in viewpoints}
    # 分析结果持久化到该观点的 active 会话，关窗重开后随会话恢复
    active_session = db.scalar(
        select(ReviewSession).where(
            ReviewSession.viewpoint_id == viewpoint.id,
            ReviewSession.status == "active",
        )
    )
    if reset and active_session is not None:
        # 重新生成：先清空打磨阶段对话（提炼对话保留），再生成新分析
        db.query(ReviewMessage).where(
            ReviewMessage.session_id == active_session.id,
            ReviewMessage.phase == "polish",
        ).delete(synchronize_session=False)
        db.commit()
    # 分析对象为观点正文（草稿观点正文即提炼产物，docs/04 D9）
    messages = build_analysis_messages(viewpoint, viewpoints)
    try:
        result = await run_structured_call(
            db,
            provider,
            prompt_version=PROMPT_VERSION,
            schema=AnalysisResult,
            messages=messages,
            validate_business=lambda r: validate_analysis_result(r, existing_ids),
        )
    except (LLMUnavailableError, LLMConfigError) as exc:
        raise biz_error(
            503, "ai_unavailable", str(exc),
            "AI service is unavailable. Please check the AI service settings.",
        ) from exc
    except LLMOutputError as exc:
        raise biz_error(
            502, "ai_bad_output", str(exc),
            "The AI returned output that failed validation. Please retry.",
        ) from exc
    if active_session is not None:
        active_session.analysis_json = result.model_dump_json()
        active_session.analysis_json_en = await bilingual_analysis(
            db, active_session.analysis_json
        )
        db.commit()
    return result
