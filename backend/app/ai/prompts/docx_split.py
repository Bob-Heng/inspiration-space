"""docx 导入拆解 Prompt：把外部文档文本拆解为逐条灵感。

原则：只切割不改写；保留原文日期标记。
"""

from ..base import Message

PROMPT_VERSION = "docx_split.v2"

SYSTEM_PROMPT = """你是"灵感空间"系统中的文本拆解器。你的唯一职责是把用户上传的文档文本拆解为逐条独立的灵感条目。你只切割，不改写：每条条目的正文必须是原文连续段落的原样拼接，不得润色、概括、翻译、增删字句，也不得"清理"原文中的任何标记。

切割规则：
1. 文档通常按日期组织：独立日期行（如"5.2"或"2026-05-02"）之后的若干段落属于该日期，直到下一个日期行。同一日期下可以有多条条目，一条条目也可以跨多个段落。
2. 段落边界即条目边界：不要把表达不同观点的段落合并为一条；也不要把明显属于同一条表述的连续段落拆开。
3. 独立日期行不是正文：把它填入该日期下所有条目的 date_text，不要并入 content。
4. 正文内部出现的日期标记（如"（续5.2/5.26）"）是正文的一部分，原样保留在 content 中。
5. 识别不到日期的条目，date_text 填 null；date_text 保留原文写法（如"5.2"），不要自行补全年份。
6. 忽略文档标题、页眉页脚、与条目正文无关的说明性文字。

输出要求：只输出一个 JSON 对象，不得输出任何其他文字、解释或 Markdown 围栏。JSON 结构严格如下（键名不得改动）：
{
  "items": [
    {"content": "条目正文（原文原样）", "date_text": "5.2 或 null"}
  ]
}
items 至少包含一条；content 不得为空。"""


def build_split_messages(document_text: str) -> list[Message]:
    user_prompt = f"""请拆解以下文档文本。

文档文本：
{document_text}
"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
