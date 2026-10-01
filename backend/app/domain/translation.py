"""内容双语化：内容被系统接收的那一刻同步翻译，中英两个版本随实体存储与流转。

- 存储按语言分字段（content_zh / content_en），original_lang 标记原文语言；
- 派生（灵感→观点等）直接携带双语版本，不再重复翻译；
- 展示层零翻译调用。
"""

import json
import logging
import re

from sqlalchemy.orm import Session

from ..ai.errors import LLMError
from ..ai.prompts.translate import build_translate_messages
from ..ai.provider_config import resolve_llm_provider

logger = logging.getLogger(__name__)

_CJK = re.compile(r"[一-鿿]")


def detect_lang(text: str) -> str:
    """含汉字即视为中文原文，否则视为英文原文。"""
    return "zh" if _CJK.search(text) else "en"


async def make_bilingual(
    db: Session, text: str, original_lang: str | None = None
) -> dict:
    """接收内容时生成 {content_zh, content_en, original_lang}。

    LLM 不可用时不镜像原文冒充译文：缺失版本置 None，由启动对账或重试补齐，
    前端显示「暂无法翻译，等待大模型接入……」。
    """
    lang = original_lang or detect_lang(text)
    other = "en" if lang == "zh" else "zh"
    result = {
        "content_zh": text if lang == "zh" else None,
        "content_en": text if lang == "en" else None,
        "original_lang": lang,
    }
    try:
        provider = resolve_llm_provider(db)
        translated = (
            await provider.generate(build_translate_messages(text, other))
        ).strip()
        result[f"content_{other}"] = translated
    except LLMError as exc:
        logger.warning("写入时翻译失败（缺失版本置空，待对账补齐）：%s", exc)
    return result


async def bilingual_analysis(db: Session, analysis_json: str) -> str | None:
    """把审议分析 JSON 的文本字段翻译成英文，返回英文版 JSON 字符串。"""
    data = json.loads(analysis_json)
    out = dict(data)
    try:
        for field in ("adoption_reason", "strongest_counterargument"):
            if data.get(field):
                out[field] = (await make_bilingual(db, data[field], "zh"))[
                    "content_en"
                ]
    except Exception:
        logger.exception("分析英译失败")
        return None
    return json.dumps(out, ensure_ascii=False)
