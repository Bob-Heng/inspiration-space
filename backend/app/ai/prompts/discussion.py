"""打磨讨论 Prompt：围绕一条待打磨观点与人类往复讨论，直至双方形成共识。

AI 默认只看当前观点与讨论记录；需要当前观点的关系或其他已入库观点时，
通过结构化查询请求按需获取，不再携带全库快照。AI 不替人类裁决、不落库。
"""

import json

from ...domain.review_queries import display_id
from ...models import ReviewMessage, Viewpoint
from ..base import Message
from ..schemas import AnalysisResult
from .tool_history import tool_interaction_messages

PROMPT_VERSION = "discussion.v7"

SYSTEM_PROMPT = """你是"灵感空间"系统中的思考伙伴，正与人类围绕一条观点进行打磨讨论。这条观点已有初步表述，你们的目标是一起把它的措辞与边界想清楚，直到双方认可。最终采纳权在人类。

规则：
- 你是追问者，更是供给者。不要只做记者式提问：每轮先回应人类说的内容，再主动供给你认为更有价值的东西——一个反例、一个边界情况、一个更准确的候选表述，供人类评判、否定或改进。
- 每次发言最多只提一个问题：提出你判断在当前语境下最重要、最明显的那个。顺着人类的回答追问，还是回到观点原文另起一问，由你现场判断，不存在预设的问题清单。
- 你不具备读写数据库的能力，不要声称已保存或修改任何内容；正式落库由人类在界面上确认后由系统完成。
- 发言简洁、聚焦当前问题，不使用 Markdown 语法（不加粗、不用标题或列表符号），用平实的文字分段表达。
- 全程使用中文。

编号与按需查询：
- 你看到的观点编号都是界面展示编号，与人类看到的 #n 完全一致，不存在另一套编号。
- 默认上下文没有观点库快照。不要凭记忆或猜测声称了解其他观点；需要时先查询。
- 需要当前观点的分层、标签、关联观点或提炼暂存草稿时，只输出：
  {"tool": "get_current_viewpoint"}
- 需要某条已入库观点的标题、正文、来源灵感、分层、标签、日期或关联编号时，只输出：
  {"tool": "get_accepted_viewpoint", "display_id": 11}
  其中 11 换成人类所说或当前观点关系中出现的展示编号。该接口不返回其他观点的讨论记录。
- 查询请求与正式回复互斥：输出查询请求时不得同时输出 reply。系统执行后会把结果放入对话，你再继续查询或回复。可连续多次查询，不需要的信息不要查。

正式回复输出要求：只输出一个 JSON 对象，不得输出任何其他文字、解释或 Markdown 围栏。JSON 结构严格如下（键名与层级不得改动）：
{
  "reply": "给人类的回复正文",
  "ready_to_adopt": true 或 false,
  "polished_viewpoint": null 或 "观点最终正文"
}

信号规则：
- ready_to_adopt 仅当你与人类已经就观点的最终表述形成共识时才为 true：人类明确表示认可当前表述或接受了你提出的修改，且没有尚未回应的质疑。人类仍在提出新问题、表达犹豫或反驳时一律为 false。
- ready_to_adopt 为 true 时，polished_viewpoint 为双方认可的观点最终正文：完整陈述，综合讨论中已经确认的修改，措辞以可直接入库为准；为 false 时为 null。
- reply 中不得提及 ready_to_adopt、落库、阶段、流程等机制本身；提及按需查询时使用自然语言，不暴露 JSON 格式。

JSON 转义硬性要求：reply 与 polished_viewpoint 的字符串内部绝不允许出现英文双引号（"）；需要引用或强调时一律使用中文引号「」。违反此规则会导致输出无法解析。"""


def _analysis_section(analysis: AnalysisResult | None) -> str:
    if analysis is None:
        return "暂无分析结果。"
    return "以下是针对该观点的 AI 分析结果（建议，仅供参考；关联编号均为界面展示编号）：\n" + json.dumps(
        analysis.model_dump(exclude_none=True), ensure_ascii=False, indent=2
    )


def build_discussion_messages(
    viewpoint: Viewpoint,
    analysis: AnalysisResult | None,
    history: list[ReviewMessage],
    lang: str = "zh",
    tool_history: list | None = None,
) -> list[Message]:
    """组装打磨上下文：当前观点展示编号、双语标题、正文、分析与讨论记录。

    全库内容只能由模型随后通过结构化查询请求按需获取。
    lang 为界面语言：AI 回复语言跟随界面语言（与用户使用何种语言发言无关）。"""
    title = (
        (viewpoint.title_zh if lang == "zh" else viewpoint.title_en)
        or viewpoint.title_zh
        or viewpoint.title_en
        or "标题待生成"
    )
    context = f"""正在打磨的观点（这是用户在提炼阶段最终确认的观点）：
编号：#{display_id(viewpoint)}
标题：{title}
正文：{viewpoint.content}

{_analysis_section(analysis)}

以下是本次打磨的讨论记录，请继续讨论。"""
    system = SYSTEM_PROMPT.replace(
        "全程使用中文。", "全程使用英文。" if lang == "en" else "全程使用中文。"
    )
    messages: list[Message] = [
        {"role": "system", "content": system},
        {"role": "user", "content": context},
    ]
    for message in history:
        content = message.content
        if message.role == "assistant":
            # 库里的历史 AI 发言是解析后的 reply 散文；回传时还原为结构化形态，
            # 防止模型模仿散文先例而丢掉 JSON 约定。
            content = json.dumps(
                {"reply": content, "ready_to_adopt": False, "polished_viewpoint": None},
                ensure_ascii=False,
            )
        messages.append({"role": message.role, "content": content})
        if message.role == "user":
            for call in tool_history or []:
                if call.turn_id == message.id:
                    messages.extend(tool_interaction_messages(call))
    for call in tool_history or []:
        if call.turn_id == 0:
            messages.extend(tool_interaction_messages(call))
    # 格式提醒压在最后：对话变长后模型容易忘记 JSON 约定，回退成纯文本聊天；
    # 英文界面时语言要求一并压在最后（提高遵从度）
    reminder = (
        "（系统指令）无论对话进行到何处，若需查询就只输出指定查询 JSON；否则必须严格只输出一个符合上述结构的回复 JSON 对象，并全程使用英文。"
        if lang == "en"
        else "（系统指令）无论对话进行到何处，若需查询就只输出指定查询 JSON；否则必须严格只输出一个符合上述结构的回复 JSON 对象。"
    )
    messages.append({"role": "user", "content": reminder})
    return messages
