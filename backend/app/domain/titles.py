"""标题：内容接收时生成中英双语标题；用户重命名时按一种语言补齐另一种。"""

import logging

from sqlalchemy.orm import Session

from ..ai.errors import LLMError
from ..ai.pipeline import record_ai_call
from ..ai.prompts.title import (
    PROMPT_VERSION,
    TitleResult,
    build_complete_title_messages,
    build_title_messages,
)
from ..ai.provider_config import resolve_llm_provider
from ..ai.base import extract_json

logger = logging.getLogger(__name__)


async def make_titles(db: Session, content: str) -> dict:
    """生成 {title_zh, title_en}；LLM 失败时置 None（不写正文截断冒充标题），
    由启动对账补齐，前端显示「标题待生成，等待大模型接入……」。"""
    try:
        provider = resolve_llm_provider(db)
        raw = await provider.generate(build_title_messages(content))
        record_ai_call(
            db,
            provider=provider.provider_name,
            model=provider.model,
            prompt_version=PROMPT_VERSION,
            input_snapshot=content,
            output=raw,
        )
        data = extract_json(raw)
        # 模型偶用 zh/en 键名，归一化到 title_zh/title_en；超长则截断而非失败
        if "title_zh" not in data and "zh" in data:
            data = {"title_zh": data.get("zh"), "title_en": data.get("en")}
        result = TitleResult.model_validate(data)
        return {
            "title_zh": result.title_zh[:20],
            "title_en": result.title_en[:60],
        }
    except Exception as exc:
        logger.warning("标题生成失败（置空待对账）：%s", exc)
        return {"title_zh": None, "title_en": None}


async def complete_title(db: Session, title: str, given_lang: str) -> dict:
    """用户以一种语言重命名后，补齐另一种语言。返回 {title_zh, title_en}。

    补齐失败时另一语言置 None（不把用户输入复制过去冒充译文）。
    """
    other = "en" if given_lang == "zh" else "zh"
    result = {
        "title_zh": title if given_lang == "zh" else None,
        "title_en": title if given_lang == "en" else None,
    }
    try:
        provider = resolve_llm_provider(db)
        completed = (
            await provider.generate(build_complete_title_messages(title, other))
        ).strip().strip('"').strip("'")
        record_ai_call(
            db,
            provider=provider.provider_name,
            model=provider.model,
            prompt_version="title.complete.v1",
            input_snapshot=title,
            output=completed,
        )
        result[f"title_{other}"] = completed
    except Exception as exc:
        logger.warning("标题补齐失败（另一语言置空待对账）：%s", exc)
    return result
