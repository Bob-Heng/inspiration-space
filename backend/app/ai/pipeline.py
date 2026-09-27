"""结构化调用管线：LLM → Schema 校验 → 业务校验，每次调用（成功或失败）写入 ai_calls。

任何一段失败都不得把原始输出当成功结果返回（设计说明书 §11.2）。
"""

import json
import logging
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models import AiCall
from .base import LLMProvider, Message
from .errors import BusinessValidationError, LLMError, LLMOutputError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

RAW_EXCERPT_LIMIT = 2000


def record_ai_call(
    db: Session,
    *,
    provider: str,
    model: str,
    prompt_version: str,
    input_snapshot: str,
    output: str | None,
) -> AiCall:
    """AI 调用留痕：成功存原始输出，失败存错误摘要。独立提交，不随业务事务回滚。"""
    call = AiCall(
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        input_snapshot=input_snapshot,
        output=output,
    )
    db.add(call)
    db.commit()
    return call


def _failure_summary(exc: LLMError) -> str:
    if isinstance(exc, LLMOutputError) and exc.raw_output:
        return f"{exc}；原始输出摘录：{exc.raw_output[:RAW_EXCERPT_LIMIT]}"
    return str(exc)


async def run_structured_call(
    db: Session,
    provider: LLMProvider,
    *,
    prompt_version: str,
    schema: type[T],
    messages: list[Message],
    validate_business: Callable[[T], T] | None = None,
) -> T:
    """三段管线：任一失败留痕并抛出 LLMError 子类，由 API 层决定响应码。"""
    input_snapshot = json.dumps(messages, ensure_ascii=False)
    try:
        output = await provider.generate_structured(messages, schema)
    except LLMError as exc:
        record_ai_call(
            db,
            provider=provider.provider_name,
            model=provider.model,
            prompt_version=prompt_version,
            input_snapshot=input_snapshot,
            output=f"调用失败：{_failure_summary(exc)}",
        )
        raise
    try:
        data = validate_business(output.data) if validate_business is not None else output.data
    except BusinessValidationError as exc:
        if not exc.raw_output:
            exc.raw_output = output.raw
        record_ai_call(
            db,
            provider=provider.provider_name,
            model=provider.model,
            prompt_version=prompt_version,
            input_snapshot=input_snapshot,
            output=f"调用失败：{_failure_summary(exc)}",
        )
        raise
    record_ai_call(
        db,
        provider=provider.provider_name,
        model=provider.model,
        prompt_version=prompt_version,
        input_snapshot=input_snapshot,
        output=output.raw,
    )
    return data
