import pytest

from app.domain.tags import (
    InvalidTagError,
    TAG_VOCABULARIES,
    validate_layer,
    validate_tag,
    validate_tags,
)
from app.domain.viewpoint_state import (
    InvalidTransitionError,
    check_inspiration_transition,
    check_viewpoint_transition,
    validate_viewpoint_status,
)


class TestViewpointStateMachine:
    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            ("accepted", "suspended"),   # 冲突转悬置
            ("accepted", "rejected"),    # 裁决否定
            ("suspended", "accepted"),   # 裁决采纳
            ("suspended", "rejected"),   # 裁决否定
        ],
    )
    def test_合法转换通过(self, from_status, to_status):
        check_viewpoint_transition(from_status, to_status)

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            ("rejected", "accepted"),    # 否定是终态
            ("rejected", "suspended"),   # 否定是终态
            ("accepted", "accepted"),    # 状态未变化
            ("suspended", "suspended"),
            ("pending", "accepted"),     # 灵感状态不是观点状态
            ("accepted", "pending"),
            ("accepted", "deleted"),     # 不存在的状态
        ],
    )
    def test_非法转换被拒绝(self, from_status, to_status):
        with pytest.raises(InvalidTransitionError):
            check_viewpoint_transition(from_status, to_status)

    def test_合法状态校验(self):
        for status in ("accepted", "suspended", "rejected"):
            validate_viewpoint_status(status)
        with pytest.raises(InvalidTransitionError):
            validate_viewpoint_status("archived")


class TestInspirationStateMachine:
    def test_入队到审议(self):
        check_inspiration_transition("pending", "in_review")

    def test_审议退回队列(self):
        check_inspiration_transition("in_review", "pending")

    @pytest.mark.parametrize("final_status", ["reviewed", "rejected"])
    def test_审议完结出队(self, final_status):
        check_inspiration_transition("in_review", final_status)

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            ("pending", "accepted"),     # 灵感状态不是观点状态
            ("pending", "reviewed"),     # 未经审议不得直接完结
            ("reviewed", "pending"),     # 完结是终态
            ("rejected", "in_review"),
        ],
    )
    def test_非法转换被拒绝(self, from_status, to_status):
        with pytest.raises(InvalidTransitionError):
            check_inspiration_transition(from_status, to_status)


class TestTags:
    def test_词表内合法值通过(self):
        validate_tags(domain="经济", circle="个人", discipline="心理学", scene="投资")

    def test_全部留空通过(self):
        validate_tags()

    def test_部分留空通过(self):
        validate_tags(domain="科技", scene=None)

    @pytest.mark.parametrize(
        "family,value",
        [
            ("domain", "军事"),
            ("circle", "网友"),
            ("discipline", "生物学"),
            ("scene", "运动"),
        ],
    )
    def test_词表外非法值被拒绝(self, family, value):
        with pytest.raises(InvalidTagError):
            validate_tag(family, value)

    def test_未知标签族被拒绝(self):
        with pytest.raises(InvalidTagError):
            validate_tag("emotion", "高兴")

    def test_validate_tags_抛出非法族值(self):
        with pytest.raises(InvalidTagError):
            validate_tags(circle="陌生人")

    def test_分层校验(self):
        for layer in ("dao", "fa", "shu", None):
            validate_layer(layer)
        with pytest.raises(InvalidTagError):
            validate_layer("道")

    def test_词表与docs约定一致(self):
        assert TAG_VOCABULARIES["domain"] == {"政治", "经济", "文化", "社会", "科技", "其他"}
        assert len(TAG_VOCABULARIES) == 4
