"""把历史按需查询及其结果回放到讨论上下文，供后续轮次引用。"""

import json


def tool_interaction_messages(call) -> list[dict]:
    request = {"tool": call.tool}
    if call.tool == "get_accepted_viewpoint":
        request["display_id"] = int(call.target)
    try:
        result = json.loads(call.result_json) if call.result_json else {}
    except json.JSONDecodeError:
        result = {"error": "invalid_stored_result"}
    return [
        {"role": "assistant", "content": json.dumps(request, ensure_ascii=False)},
        {
            "role": "user",
            "content": "（系统指令）此前一次按需查询的结果如下，可在后续讨论中引用：\n"
            + json.dumps(result, ensure_ascii=False),
        },
    ]
