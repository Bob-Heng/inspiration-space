"""审议分析 Prompt：对一条待审灵感输出结构化分析建议。

AI 只输出建议，裁决权在人类；分析结果只是建议，正式落库由决策接口完成。
"""

import json

from ...domain.tags import LAYER_LABELS, TAG_VOCABULARIES
from ...models import Inspiration, Viewpoint
from ..base import Message

PROMPT_VERSION = "analysis.v3"

FAMILY_NAMES = {"domain": "领域", "circle": "圈层", "discipline": "学科", "scene": "场景"}

TAG_VOCABULARY_TEXT = "\n".join(
    f"- {FAMILY_NAMES[family]}（{family}）：{' / '.join(sorted(vocab))}"
    for family, vocab in TAG_VOCABULARIES.items()
)

SYSTEM_PROMPT = f"""你是"灵感空间"系统中的审议分析器。对一条待审灵感给出分析建议，由人类做最终裁决。你只输出建议，不裁决、不落库。

必须完整输出以下三项分析，缺一不可：

1. 采纳理由与反对采纳的最强理由。两者必须同时给出；反对理由要取"最强"形态——即使你不认同，也要把它论证到最有说服力的程度。
2. 分层与四标签族建议。
   - 分层三选一：道=元假设（对世界/人性的根本设定，暂不求证）；法=机制规律（世界如何运转的可检验判断）；术=方法策略（面对某类问题该怎么做的操作原则）。判不准时问：这句话在说"世界是什么/怎么运转"（道/法），还是"该怎么做"（术）。
   - 四个标签族，每族最多选一个，拿不准就留空（null），宁缺毋滥；取值必须来自下列词表：
{TAG_VOCABULARY_TEXT}
3. 与观点库中已有观点的相近/冲突关系。只能引用快照中真实存在的观点 id；确实没有就返回空数组，不得编造。

输出要求：只输出一个 JSON 对象，不得输出任何其他文字、解释或 Markdown 围栏。JSON 结构严格如下（键名与层级不得改动）：
{{
  "adoption_reason": "采纳理由",
  "strongest_counterargument": "反对采纳的最强理由",
  "layer": "道 或 法 或 术",
  "tags": {{"domain": null, "circle": null, "discipline": null, "scene": null}},
  "relations": [{{"viewpoint_id": 0, "type": "similar 或 conflict"}}]
}}
"""


def _viewpoint_snapshot(viewpoints: list[Viewpoint]) -> str:
    if not viewpoints:
        return "观点库当前为空，没有任何已有观点。"
    snapshot = [
        {
            "id": vp.id,
            "layer": LAYER_LABELS.get(vp.layer) if vp.layer else None,
            "tags": {
                "domain": vp.domain,
                "circle": vp.circle,
                "discipline": vp.discipline,
                "scene": vp.scene,
            },
            "content": vp.content,
        }
        for vp in viewpoints
    ]
    return "以下是观点库快照（已有观点全量）：\n" + json.dumps(
        snapshot, ensure_ascii=False, indent=2
    )


def build_analysis_messages(
    inspiration: Inspiration, viewpoints: list[Viewpoint]
) -> list[Message]:
    user_prompt = f"""请审议以下灵感。

灵感（待审条目）：
{inspiration.content}

{_viewpoint_snapshot(viewpoints)}
"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
