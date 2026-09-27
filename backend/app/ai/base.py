"""LLMProvider 抽象层（设计说明书 §11.3）：Provider 可替换，业务层不感知具体实现。"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import LLMOutputError

T = TypeVar("T", bound=BaseModel)

Message = dict[str, str]


@dataclass
class StructuredOutput(Generic[T]):
    """结构化调用结果：解析后的数据与原始文本（供留痕）。"""

    data: T
    raw: str


def extract_json(text: str) -> dict:
    """从模型输出中提取 JSON 对象，容忍 Markdown 代码围栏与前后杂文本。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMOutputError(
                "AI 输出不是合法 JSON，无法解析", raw_output=text
            ) from None
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            raise LLMOutputError(
                "AI 输出不是合法 JSON，无法解析", raw_output=text
            ) from None


class LLMProvider(ABC):
    """统一模型接口：业务层只依赖本抽象，Provider 可替换。"""

    provider_name: str
    model: str

    @abstractmethod
    async def generate(self, messages: list[Message]) -> str:
        """自由文本生成。失败抛出 LLMError 子类。"""

    async def generate_structured(
        self, messages: list[Message], schema: type[T]
    ) -> StructuredOutput[T]:
        """结构化生成：LLM → JSON 解析 → Schema 校验。任一失败抛 LLMOutputError。"""
        raw = await self.generate(messages)
        data = extract_json(raw)
        try:
            return StructuredOutput(data=schema.model_validate(data), raw=raw)
        except ValidationError as exc:
            raise LLMOutputError(
                f"AI 输出未通过 Schema 校验：{exc.error_count()} 个字段不合法",
                raw_output=raw,
            ) from exc
