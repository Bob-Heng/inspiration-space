"""内容翻译 Prompt：中英互译（展示层，不动原文）。"""

PROMPT_VERSION = "translate.v2"

_SYSTEM = {
    "en": "You are a translator. Translate the user's Chinese text into idiomatic, accurate English. Preserve the argument structure and nuance. Do not add, remove, or comment on anything. Output only the translation.",
    "zh": "你是翻译器。把用户给出的英文内容翻译成地道、准确的中文，保持论证结构与分寸感，不增删内容，不做评论，只输出译文本身。",
}


def build_translate_messages(content: str, target_lang: str) -> list[dict]:
    return [
        {"role": "system", "content": _SYSTEM[target_lang]},
        {"role": "user", "content": content},
    ]
