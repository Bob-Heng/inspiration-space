"""AI 服务配置解析：界面配置（llm_settings 表）优先，环境变量兜底。

服务商预设均为 OpenAI 兼容协议；custom 预设要求用户自填 Base URL。
"""

from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..models import LlmSetting
from .base import LLMProvider
from .errors import LLMConfigError
from .newapi import NewAPIProvider

SETTINGS_ROW_ID = 1

PRESETS: dict[str, dict[str, str | None]] = {
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1"},
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com/v1"},
    "moonshot": {"label": "Kimi（月之暗面）", "base_url": "https://api.moonshot.cn/v1"},
    "zhipu": {"label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4"},
    "custom": {"label": "自定义（OpenAI 兼容）", "base_url": None},
}


@dataclass
class ResolvedLlmConfig:
    provider_key: str
    label: str
    base_url: str
    api_key: str
    model: str | None
    source: str  # "ui" | "env"


def resolve_llm_config(db: Session) -> ResolvedLlmConfig | None:
    """生效配置：界面已保存且含 API Key 时用界面配置，否则回退环境变量。"""
    row = db.get(LlmSetting, SETTINGS_ROW_ID)
    if row and row.api_key:
        # 兼容早期版本的 "newapi" 预设：并入 custom
        if row.provider_key == "newapi":
            row.provider_key = "custom"
            if not row.base_url:
                row.base_url = "http://localhost:3000/v1"
        preset = PRESETS.get(row.provider_key)
        label = preset["label"] if preset else row.provider_key
        base_url = row.base_url or (preset["base_url"] if preset else None)
        if not base_url:
            raise LLMConfigError(
                "「AI 服务设置」中的自定义服务商缺少 Base URL，请补全后保存"
            )
        return ResolvedLlmConfig(
            provider_key=row.provider_key,
            label=label,
            base_url=base_url,
            api_key=row.api_key,
            model=row.model,
            source="ui",
        )
    if config.NEWAPI_BASE_URL and config.NEWAPI_API_KEY:
        return ResolvedLlmConfig(
            provider_key="env",
            label="环境变量配置",
            base_url=config.NEWAPI_BASE_URL,
            api_key=config.NEWAPI_API_KEY,
            model=config.NEWAPI_MODEL,
            source="env",
        )
    return None


def resolve_llm_provider(db: Session) -> LLMProvider:
    """按生效配置构造 Provider。"""
    resolved = resolve_llm_config(db)
    if resolved is None:
        raise LLMConfigError(
            "未配置 AI 服务，请在审议工作台右侧「AI 服务设置」中选择服务商并填写 API Key"
        )
    return NewAPIProvider(
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        model=resolved.model,
        label=resolved.label,
        name=resolved.provider_key,
    )


def llm_provider_dependency(db: Session = Depends(get_db)) -> LLMProvider:
    """FastAPI 依赖：按生效配置构造 Provider。"""
    return resolve_llm_provider(db)


def mask_api_key(api_key: str | None) -> str | None:
    """密钥只回显末 4 位，完整值不出库。"""
    if not api_key:
        return None
    tail = api_key[-4:] if len(api_key) > 4 else api_key
    return f"****{tail}"
