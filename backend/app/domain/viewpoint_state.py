"""观点状态机。

规则：
- 观点状态合法值：draft（草稿，他山坊打磨流程中，集思录隐藏）/ accepted（已采纳入库）
- draft ↔ accepted 双向可转：采纳使草稿入库，集思录撤回使已采纳观点退回草稿
- 系统不得擅自变更状态，所有转移必须由打磨决策或显式撤回触发
- 打磨会话状态：active（进行中）/ paused（挂起，可恢复）/ completed（已完成）
- completed 允许转回 active：用于集思录撤回后重开该观点的会话
- 灵感无状态机：首页状态由关联观点的状态推导
"""


class InvalidTransitionError(ValueError):
    """非法状态转换。"""


VIEWPOINT_STATUSES = {"draft", "accepted"}

VIEWPOINT_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"accepted"},
    "accepted": {"draft"},
}


def validate_viewpoint_status(status: str) -> None:
    if status not in VIEWPOINT_STATUSES:
        raise InvalidTransitionError(f"非法观点状态：{status}")


def check_viewpoint_transition(from_status: str, to_status: str) -> None:
    """校验观点状态转换是否合法，非法则抛出 InvalidTransitionError。"""
    validate_viewpoint_status(from_status)
    validate_viewpoint_status(to_status)
    if from_status == to_status:
        raise InvalidTransitionError(f"状态未变化：{from_status}")
    if to_status not in VIEWPOINT_TRANSITIONS[from_status]:
        raise InvalidTransitionError(f"非法观点状态转换：{from_status} -> {to_status}")


SESSION_STATUSES = {"active", "paused", "completed"}

SESSION_TRANSITIONS: dict[str, set[str]] = {
    "active": {"paused", "completed"},
    "paused": {"active"},
    # completed -> active：集思录撤回后重开该观点的会话
    "completed": {"active"},
}


def check_session_transition(from_status: str, to_status: str) -> None:
    """校验打磨会话状态转换是否合法。"""
    if from_status not in SESSION_STATUSES:
        raise InvalidTransitionError(f"非法会话状态：{from_status}")
    if to_status not in SESSION_STATUSES:
        raise InvalidTransitionError(f"非法会话状态：{to_status}")
    if to_status not in SESSION_TRANSITIONS[from_status]:
        raise InvalidTransitionError(f"非法会话状态转换：{from_status} -> {to_status}")
