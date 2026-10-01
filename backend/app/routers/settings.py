"""AI 服务设置：服务商选择、API Key、Base URL 的界面化配置。"""

from openai import AsyncOpenAI
import httpx2
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai.errors import LLMConfigError
from ..ai.provider_config import (
    PRESETS,
    SETTINGS_ROW_ID,
    mask_api_key,
    resolve_llm_config,
)
from ..auth import require_user
from ..db import get_db
from ..models import LlmSetting

router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    dependencies=[Depends(require_user)],
)

TEST_TIMEOUT = 15.0


class LlmSettingsIn(BaseModel):
    provider_key: str
    base_url: str | None = None
    api_key: str | None = None  # 空字符串/缺省 = 保持已保存的密钥
    model: str | None = None  # 来自下拉选择（测试连接后拉取的可用模型列表）


class LlmTestIn(BaseModel):
    provider_key: str | None = None
    base_url: str | None = None
    api_key: str | None = None


def _saved_view(row: LlmSetting | None) -> dict | None:
    if row is None:
        return None
    return {
        "provider_key": row.provider_key,
        "base_url": row.base_url,
        "model": row.model,
        "has_api_key": bool(row.api_key),
        "api_key_masked": mask_api_key(row.api_key),
    }


def _effective_view(db: Session) -> dict | None:
    resolved = resolve_llm_config(db)
    if resolved is None:
        return None
    return {
        "provider_key": resolved.provider_key,
        "label": resolved.label,
        "base_url": resolved.base_url,
        "model": resolved.model,
        "source": resolved.source,
    }


@router.get("/llm")
def get_llm_settings(db: Session = Depends(get_db)) -> dict:
    return {
        "saved": _saved_view(db.get(LlmSetting, SETTINGS_ROW_ID)),
        "effective": _effective_view(db),
        "presets": [
            {"key": key, "label": p["label"], "base_url": p["base_url"]}
            for key, p in PRESETS.items()
        ],
    }


@router.put("/llm")
def save_llm_settings(payload: LlmSettingsIn, db: Session = Depends(get_db)) -> dict:
    if payload.provider_key not in PRESETS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "unknown_provider", "zh": f"未知的服务商：{payload.provider_key}", "en": f"Unknown provider: {payload.provider_key}"},
        )
    base_url = payload.base_url or PRESETS[payload.provider_key]["base_url"]
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "base_url_required", "zh": "自定义服务商必须填写 Base URL", "en": "Base URL is required for a custom provider"},
        )
    row = db.get(LlmSetting, SETTINGS_ROW_ID)
    if row is None:
        row = LlmSetting(id=SETTINGS_ROW_ID, provider_key=payload.provider_key)
        db.add(row)
    if row.provider_key != payload.provider_key:
        # 切换服务商后旧密钥必然失效，强制重新填写，避免残留他家密钥
        row.api_key = None
    row.provider_key = payload.provider_key
    row.base_url = payload.base_url  # 留空则保存 null，解析时回落预设地址
    row.model = payload.model or None
    if payload.api_key:  # 未填写则保留已保存密钥
        row.api_key = payload.api_key
    db.commit()
    return {"saved": _saved_view(row), "effective": _effective_view(db)}


@router.post("/llm/test")
async def test_llm_settings(payload: LlmTestIn, db: Session = Depends(get_db)) -> dict:
    """用给定参数（缺省回落到已保存/环境变量配置）测试连通性。"""
    resolved = resolve_llm_config(db)
    provider_key = payload.provider_key or (resolved.provider_key if resolved else None)
    base_url = payload.base_url or (
        PRESETS[provider_key]["base_url"] if provider_key in PRESETS else None
    ) or (resolved.base_url if resolved else None)
    api_key = payload.api_key or (resolved.api_key if resolved else None)
    label = PRESETS[provider_key]["label"] if provider_key in PRESETS else "AI 服务"
    if not base_url or not api_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "missing_credentials", "zh": "缺少 Base URL 或 API Key，无法测试", "en": "Base URL or API Key is missing"},
        )
    client = AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=TEST_TIMEOUT,
        max_retries=0,
        http_client=httpx2.AsyncClient(trust_env=False),
    )
    try:
        result = await client.models.list()
        models = [m.id for m in result.data][:10]
    except LLMConfigError:
        raise
    except Exception as exc:
        return {"ok": False, "message": f"{label}连接失败：{type(exc).__name__}，请检查 Base URL 与 API Key"}
    return {"ok": True, "message": f"{label}连接成功", "models": models}
