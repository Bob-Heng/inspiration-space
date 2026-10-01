"""AI 服务状态：供前端 30s 轮询；恢复时可直接触发对账补全。"""

import asyncio
import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..ai.errors import LLMConfigError
from ..ai.provider_config import resolve_llm_config
from ..auth import require_user
from ..db import get_db
from ..domain.reconcile import reconcile_i18n

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
