"""New API Provider：本地 New API 网关（OpenAI 兼容协议），见 docs/04 D7。"""

import logging

import httpx2
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
)

from .. import config
from .base import LLMProvider, Message
from .errors import LLMConfigError, LLMOutputError, LLMUnavailableError

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 120.0
PROBE_TIMEOUT = 5.0


class NewAPIProvider(LLMProvider):
    """OpenAI 兼容协议的通用 Provider。预设标签用于错误提示（如"New API 网关"）。"""

    provider_name = "newapi"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        label: str = "New API 网关",
        name: str | None = None,
    ) -> None:
        self.base_url = base_url or config.NEWAPI_BASE_URL
        self.api_key = api_key or config.NEWAPI_API_KEY
        self.model = model or config.NEWAPI_MODEL
        self.label = label
        if name:
            self.provider_name = name
        if not self.base_url or not self.api_key:
            raise LLMConfigError(
                "未配置 AI 服务，请在审议工作台右侧「AI 服务设置」中选择服务商并填写 API Key，"
                "或在 backend/.env 中设置 NEWAPI_BASE_URL 与 NEWAPI_API_KEY"
            )
        self._client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=REQUEST_TIMEOUT,
            max_retries=0,
            http_client=httpx2.AsyncClient(trust_env=False),
        )

    async def _resolve_model(self) -> str:
        """模型名不在本软件内配置：缺省时从服务端 /models 取第一个可用模型。"""
        if self.model:
            return self.model
        try:
            result = await self._client.models.list()
        except Exception as exc:
            raise LLMUnavailableError(
                f"{self.label}不可达或令牌无效，无法获取模型列表"
            ) from exc
        if not result.data:
            raise LLMUnavailableError(f"{self.label}没有可用模型，请在其服务端配置")
        self.model = result.data[0].id
        return self.model

    async def generate(self, messages: list[Message]) -> str:
        model = await self._resolve_model()
        try:
            response = await self._client.chat.completions.create(
                model=model, messages=messages
            )
        except APITimeoutError as exc:
            raise LLMUnavailableError(
                f"{self.label}响应超时（>{int(REQUEST_TIMEOUT)} 秒），请稍后重试"
            ) from exc
        except APIConnectionError as exc:
            raise LLMUnavailableError(
                f"{self.label}不可达，请检查服务地址与网络（本地网关请确认已启动）"
            ) from exc
        except AuthenticationError as exc:
            raise LLMUnavailableError(
                f"{self.label}令牌无效，请在「AI 服务设置」中检查 API Key"
            ) from exc
        except APIStatusError as exc:
            raise LLMUnavailableError(
                f"{self.label}返回错误（HTTP {exc.status_code}），请检查服务与渠道状态"
            ) from exc
        if not response.choices or not response.choices[0].message.content:
            raise LLMOutputError("AI 返回内容为空")
        return response.choices[0].message.content


def get_llm_provider() -> LLMProvider:
    """无库上下文时的兜底 Provider（环境变量）。路由里请用 resolve_llm_provider(db)。"""
    return NewAPIProvider()


async def probe_gateway() -> None:
    """启动探活：按生效配置（界面配置优先）探测 AI 服务，失败只记录日志不阻断启动。"""
    from ..db import SessionLocal
    from .provider_config import resolve_llm_config

    db = SessionLocal()
    try:
        resolved = resolve_llm_config(db)
    finally:
        db.close()
    if resolved is None:
        logger.error("未配置 AI 服务（界面或环境变量），AI 功能不可用")
        return
    client = AsyncOpenAI(
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        timeout=PROBE_TIMEOUT,
        max_retries=0,
        http_client=httpx2.AsyncClient(trust_env=False),
    )
    try:
        await client.models.list()
    except Exception:
        logger.error(
            "AI 服务不可达（%s / %s），请在审议工作台「AI 服务设置」中检查配置",
            resolved.label,
            resolved.base_url,
        )
        return
    logger.info("AI 服务已连接（%s，%s，模型 %s）", resolved.label, resolved.base_url, resolved.model)
