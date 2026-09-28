"""审议分析接口：AI 对指定灵感输出三项分析与第一轮疑问。

AI 只返回建议；本接口除写 ai_calls 外不改动任何业务表。
"""

from fastapi import APIRouter, Depends, HTTPException, status
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
from ..domain.analysis import validate_analysis_result
from ..domain.translation import bilingual_analysis
from ..models import Inspiration, ReviewSession, Viewpoint

router = APIRouter(
    prefix="/api/inspirations",
    tags=["analysis"],
    dependencies=[Depends(require_user)],
)


@router.post("/{inspiration_id}/analysis", response_model=AnalysisResult)
async def analyze_inspiration(
    inspiration_id: int,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(llm_provider_dependency),
) -> AnalysisResult:
    inspiration = db.get(Inspiration, inspiration_id)
    if inspiration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="灵感不存在")
    viewpoints = list(db.scalars(select(Viewpoint).order_by(Viewpoint.id)))
    existing_ids = {vp.id for vp in viewpoints}
    messages = build_analysis_messages(inspiration, viewpoints)
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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except LLMOutputError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    # 分析结果持久化到该灵感的 active 会话，关窗重开后随会话恢复
    active_session = db.scalar(
        select(ReviewSession).where(
            ReviewSession.inspiration_id == inspiration_id,
            ReviewSession.status == "active",
        )
    )
    if active_session is not None:
        active_session.analysis_json = result.model_dump_json()
        active_session.analysis_json_en = await bilingual_analysis(
            db, active_session.analysis_json
        )
        db.commit()
    return result
