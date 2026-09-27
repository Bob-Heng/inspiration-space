"""AI 服务包：Provider 抽象、结构化输出管线、审议分析。"""

from .base import LLMProvider, Message, StructuredOutput
from .errors import (
    BusinessValidationError,
    LLMConfigError,
    LLMError,
    LLMOutputError,
    LLMUnavailableError,
)
from .newapi import NewAPIProvider, get_llm_provider
from .pipeline import record_ai_call, run_structured_call
from .provider_config import (
    PRESETS,
    llm_provider_dependency,
    mask_api_key,
    resolve_llm_config,
    resolve_llm_provider,
)

__all__ = [
    "BusinessValidationError",
    "LLMConfigError",
    "LLMError",
    "LLMOutputError",
    "LLMProvider",
    "LLMUnavailableError",
    "Message",
    "NewAPIProvider",
    "StructuredOutput",
    "get_llm_provider",
    "llm_provider_dependency",
    "mask_api_key",
    "record_ai_call",
    "resolve_llm_config",
    "resolve_llm_provider",
    "run_structured_call",
]
