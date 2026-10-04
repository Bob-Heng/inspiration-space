"""AI 服务状态：供前端 30s 轮询；恢复时可直接触发对账补全。附 AI 标题建议。"""

import asyncio
import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..ai.errors import LLMConfigError
from ..ai.provider_config import resolve_llm_config
from ..auth import require_user
from ..db import get_db
from ..errors import biz_error
from ..domain.reconcile import reconcile_i18n
from ..domain.titles import make_titles
from ..schemas import TitleSuggestionOut, TitleSuggestionRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(require_user)])

_reconcile_lock = asyncio.Lock()


@router.get("/status")
async def ai_status(db: Session = Depends(get_db)) -> dict:
    """AI 服务当前是否可达（真实探测，5s 超时）。"""
    from openai import AsyncOpenAI

    import httpx2

    resolved = resolve_llm_config(db)
    if resolved is None:
        return {"available": False, "reason": "not_configured"}
    client = AsyncOpenAI(
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        timeout=5.0,
        max_retries=0,
        http_client=httpx2.AsyncClient(trust_env=False),
    )
    try:
        await client.models.list()
        return {"available": True}
    except Exception:
        return {"available": False, "reason": "unreachable"}


@router.post("/reconcile", status_code=status.HTTP_202_ACCEPTED)
async def reconcile() -> dict:
    """触发对账补全（AI 恢复后由前端调用）。已在跑则直接返回。"""
    if _reconcile_lock.locked():
        return {"started": False, "already_running": True}

    async def _run():
        async with _reconcile_lock:
            await reconcile_i18n()

    asyncio.create_task(_run())
    return {"started": True}


@router.post("/title-suggestion", response_model=TitleSuggestionOut)
async def title_suggestion(
    payload: TitleSuggestionRequest, db: Session = Depends(get_db)
) -> TitleSuggestionOut:
    """AI 标题建议：以正文生成双语标题（不落库）；AI 不可用时报 503 双语错误。"""
    titles = await make_titles(db, payload.content)
    if titles["title_zh"] is None:
        raise biz_error(
            503, "ai_unavailable",
            "标题生成失败：大模型未接入，请检查 AI 服务设置。",
            "Title suggestion failed: AI service is unavailable. Please check the AI service settings.",
        )
    return TitleSuggestionOut(
        title_zh=titles["title_zh"], title_en=titles["title_en"]
    )
