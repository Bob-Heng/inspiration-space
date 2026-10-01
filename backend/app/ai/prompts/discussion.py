"""审议讨论 Prompt：围绕一条待审灵感与人类往复讨论。

AI 只输出观点与提问，不替人类裁决，也不落库任何业务数据；
正式落库只由决策接口完成。疑问由 AI 现场提出，一次一个，不预设清单。
"""

import json

from ...models import Inspiration, ReviewMessage, Viewpoint
from ..base import Message
from ..schemas import AnalysisResult
from .analysis import _viewpoint_snapshot

PROMPT_VERSION = "discussion.v4"

SYSTEM_PROMPT = """你是"灵感空间"系统中的审议讨论助手，正与人类围绕一条待审灵感进行讨论。目标是帮人类把这条灵感想清楚，最终裁决权在人类。

规则：
- 你只输出观点与提问：质疑、反例、边界情况、澄清与追问。采纳与否定都可以论证，但不得替人类宣布结论。
- 每次发言最多只提一个问题：提出你判断在当前语境下最重要、最明显的那个。顺着人类的回答追问，还是从灵感原文另起一问，由你现场判断。不存在预设的问题清单。
- 你不具备读写数据库的能力，不要声称已保存或修改任何内容；正式落库由人类在界面上确认后由系统完成。
- 发言简洁、聚焦当前问题，不使用 Markdown 语法（不加粗、不用标题或列表符号），用平实的文字分段表达。
- 全程使用中文。"""


def _analysis_section(analysis: AnalysisResult | None) -> str:
    if analysis is None:
        return "暂无审议分析结果。"
    return "以下是针对该灵感的审议分析结果（建议，仅供参考）：\n" + json.dumps(
        analysis.model_dump(), ensure_ascii=False, indent=2
    )


def build_discussion_messages(
    inspiration: Inspiration,
    viewpoints: list[Viewpoint],
    analysis: AnalysisResult | None,
    history: list[ReviewMessage],
) -> list[Message]:
    """组装讨论上下文：灵感原文 + 审议分析（若有）+ 观点库快照 + 历史对话。"""
    context = f"""正在审议的灵感（待审条目）：
{inspiration.content}

{_analysis_section(analysis)}

{_viewpoint_snapshot(viewpoints)}

以下是本次审议的讨论记录，请继续讨论。"""
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ]
    for message in history:
        messages.append({"role": message.role, "content": message.content})
    return messages
