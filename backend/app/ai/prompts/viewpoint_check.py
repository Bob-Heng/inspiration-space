"""观点判断 Prompt：一次结构化调用判断一条观点正文是否已构成观点（docs/04 D9）。

观点 = 可裁决的命题（可采纳/可反对的判断句）；
不是观点 = 现象描述、素材、片段、疑问。
AI 只输出判断，不落库。
"""

from ...models import Viewpoint
from ..base import Message

PROMPT_VERSION = "viewpoint_check.v1"

SYSTEM_PROMPT = """你是"灵感空间"系统中的观点判断器。判断一条灵感是否已经构成观点。你只输出判断，不落库。

观点 = 一个可裁决的命题：一句可以被采纳也可以被反对的判断，表达了对世界如何运转或该如何行动的主张。
不是观点 = 现象描述（只陈述发生了什么）、素材（引文、事实片段）、片段（不成句的想法残片）、疑问（只提出问题而未给出判断）。

判据：把这句话拿去问"你同意还是反对"，若这个问题有意义，它就是观点；若只能说"所以呢"或"这是什么意思"，它还不是观点。

输出要求：只输出一个 JSON 对象，不得输出任何其他文字、解释或 Markdown 围栏。JSON 结构严格如下：
{"is_viewpoint": true 或 false}
"""


def build_viewpoint_check_messages(viewpoint: Viewpoint) -> list[Message]:
    """判断输入为观点正文（duck-type .content）。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"请判断以下灵感是否已构成观点。\n\n灵感：\n{viewpoint.content}"},
    ]
