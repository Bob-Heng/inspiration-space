"""审议讨论 Prompt：围绕一条待审灵感与人类往复讨论（docs/02 §5 审议节）。

讨论中 AI 只输出观点与提问，不替人类裁决，也不落库任何业务数据；
正式落库只由决策接口完成。
"""

import json

from ...models import Inspiration, ReviewMessage, Viewpoint
from ..base import Message
from ..schemas import AnalysisResult
from .analysis import _viewpoint_snapshot

PROMPT_VERSION = "discussion.v1"

SYSTEM_PROMPT = """你是一台"审议讨论助手"，服务于一个以观点为本体的个人知识系统。\
你正与人类围绕一条待审灵感进行讨论。你的职责是帮助人类把这条灵感想清楚：

- 你只输出观点与提问：质疑、反例、边界情况、澄清与追问；
- 采纳与否定都可以论证，但最终裁决权在人类，你不得替人类宣布结论；
- 你不具备读写数据库的能力，不要声称已保存、已入库或已修改任何内容；\
正式落库由人类在界面上确认后由系统完成；
- 发言简洁、聚焦当前问题，一次不要抛出过多问题；
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
