"""观点状态机。

规则（docs/02 §4）：
- 观点状态合法值：accepted（采纳）/ suspended（悬置）/ rejected（否定）
- rejected 为终态，不允许转出
- 任何时刻发现冲突：双方均转悬置（accepted -> suspended）
- 系统不得擅自变更状态，所有转移必须由审议决策显式触发
- 审议会话状态：active（进行中）/ paused（暂缓挂起，可恢复）/ completed（已完结，终态）
- 灵感状态：pending（待审）/ in_review（审议中）/ reviewed（已审议，采纳出队留档）/ rejected（否定出队留档），后两者为终态
"""


class InvalidTransitionError(ValueError):
    """非法状态转换。"""


VIEWPOINT_STATUSES = {"accepted", "suspended", "rejected"}

VIEWPOINT_TRANSITIONS: dict[str, set[str]] = {
    "accepted": {"suspended", "rejected"},
    "suspended": {"accepted", "rejected"},
    "rejected": set(),
}

INSPIRATION_STATUSES = {"pending", "in_review", "reviewed", "rejected"}

INSPIRATION_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in_review"},
    "in_review": {"pending", "reviewed", "rejected"},
    "reviewed": set(),
    "rejected": set(),
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


def check_inspiration_transition(from_status: str, to_status: str) -> None:
    """校验灵感（待审队列条目）状态转换是否合法。"""
    if from_status not in INSPIRATION_STATUSES:
        raise InvalidTransitionError(f"非法灵感状态：{from_status}")
    if to_status not in INSPIRATION_STATUSES:
        raise InvalidTransitionError(f"非法灵感状态：{to_status}")
    if to_status not in INSPIRATION_TRANSITIONS[from_status]:
        raise InvalidTransitionError(f"非法灵感状态转换：{from_status} -> {to_status}")


SESSION_STATUSES = {"active", "paused", "completed"}

SESSION_TRANSITIONS: dict[str, set[str]] = {
    "active": {"paused", "completed"},
    "paused": {"active"},
    "completed": set(),
}


def check_session_transition(from_status: str, to_status: str) -> None:
    """校验审议会话状态转换是否合法。completed 为终态。"""
    if from_status not in SESSION_STATUSES:
        raise InvalidTransitionError(f"非法会话状态：{from_status}")
    if to_status not in SESSION_STATUSES:
        raise InvalidTransitionError(f"非法会话状态：{to_status}")
    if to_status not in SESSION_TRANSITIONS[from_status]:
        raise InvalidTransitionError(f"非法会话状态转换：{from_status} -> {to_status}")
