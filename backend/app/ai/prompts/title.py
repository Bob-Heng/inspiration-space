"""标题 Prompt：为内容生成中英双语标题；用户以一种语言重命名时补齐另一种。"""

from pydantic import BaseModel, Field

PROMPT_VERSION = "title.v2"


class TitleResult(BaseModel):
    title_zh: str = Field(min_length=1, max_length=20)
    title_en: str = Field(min_length=1, max_length=80)


GENERATE_SYSTEM = """你为用户的内容生成标题。要求：
- 同时给出中文与英文两个版本；
- 中文标题不超过 20 个汉字，英文标题不超过 60 个字符；
- 概括核心主旨，措辞自然，不加引号；
- 只输出 JSON，键名固定为 title_zh 与 title_en：
{"title_zh": "示例标题", "title_en": "Example Title"}"""

COMPLETE_SYSTEM = {
    "zh": "把用户给出的英文标题改写为对应的中文标题：不超过 20 个汉字，概括准确、措辞自然。只输出中文标题本身，不加引号。",
    "en": "Rewrite the user's Chinese title as the corresponding English title: max 60 characters, faithful and natural. Output only the English title, no quotes.",
}


def build_title_messages(content: str) -> list[dict]:
    return [
        {"role": "system", "content": GENERATE_SYSTEM},
        {"role": "user", "content": content},
    ]


def build_complete_title_messages(title: str, target_lang: str) -> list[dict]:
    return [
        {"role": "system", "content": COMPLETE_SYSTEM[target_lang]},
        {"role": "user", "content": title},
    ]
