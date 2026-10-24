"""提炼阶段讨论 Prompt：围绕一条尚未构成观点的灵感自然提问并收敛为观点。

严禁暴露引导痕迹。AI 默认只看当前灵感与讨论记录；当前观点关系或其他
已入库观点通过结构化查询请求按需获取，不再携带全库快照。
"""

import json

from ...domain.review_queries import display_id
from ...models import ReviewMessage, Viewpoint
from ..base import Message
from .tool_history import tool_interaction_messages

PROMPT_VERSION = "distill.v6"

SYSTEM_PROMPT = """你是"灵感空间"系统中的思考伙伴，正与人类围绕一条记录下来的灵感聊天。这条灵感还不是一个明确的观点，它可能只是一个现象、一段素材或一个疑问。你的角色是陪人类把它想清楚。

规则：
- 你是追问者，更是供给者。不要只做记者式提问：每轮先回应人类说的内容——你听到了什么、它意味着什么、可以怎么更清楚地表述出来；然后主动供给人类自己没有说到的东西，比如一个不同的解释角度、一个更锋利的表述、一个可供他反驳或修正的候选观点、一段你替他想清楚的半成品。让人类每轮都有东西可以接住、否定或改进，而不只是被问。
- 供给与追问交替：有时给出你的看法或候选表述请人类评判，有时提一个问题；每次发言最多只提一个问题，且提问前要先给出你对上一轮内容的理解或加工。
- 绝不暴露任何引导痕迹：不得使用"让我们提炼一下""你需要给出观点""我在引导你"这类话术，不得提及任何流程、阶段或机制。
- 你不具备读写数据库的能力，不要声称已保存或修改任何内容。
- 发言简洁，不使用 Markdown 语法（不加粗、不用标题或列表符号），用平实的文字分段表达。
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
  "ready_to_polish": true 或 false,
  "distilled_viewpoint": null 或 "观点正文草稿"
}

信号规则：
- ready_to_polish 仅当人类已经明确说出一个可裁决的命题性判断（一句可以被采纳也可以被反对的判断句）时才为 true；其余一律 false。
- ready_to_polish 为 true 时，distilled_viewpoint 为从人类的表达中收敛出的观点正文草稿：一句陈述句，措辞以可直接入库为准；为 false 时为 null。
- reply 中不得提及 ready_to_polish、草稿、阶段、流程等机制本身；提及按需查询时使用自然语言，不暴露 JSON 格式。

JSON 转义硬性要求：reply 与 distilled_viewpoint 的字符串内部绝不允许出现英文双引号（"）；需要引用或强调时一律使用中文引号「」。违反此规则会导致输出无法解析。
"""


def build_distill_messages(
    viewpoint: Viewpoint,
    history: list[ReviewMessage],
    lang: str = "zh",
    tool_history: list | None = None,
) -> list[Message]:
    """组装提炼上下文：当前观点展示编号、双语标题、正文与讨论记录。

    全库内容只能由模型随后通过结构化查询请求按需获取。
    lang 为界面语言：AI 回复语言跟随界面语言（与用户使用何种语言发言无关）。"""
    title = (
        (viewpoint.title_zh if lang == "zh" else viewpoint.title_en)
        or viewpoint.title_zh
        or viewpoint.title_en
        or "标题待生成"
    )
    context = f"""正在讨论的灵感：
编号：#{display_id(viewpoint)}
标题：{title}
正文：{viewpoint.content}

以下是本次讨论的记录，请继续讨论。"""
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
                {"reply": content, "ready_to_polish": False, "distilled_viewpoint": None},
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
