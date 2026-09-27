"""标签族词表与校验（docs/02 §3）。

四个标签族，每族 0~1 个，组内互斥，可留空，宁缺毋滥。
词表可随用随扩："其他"聚集满 3 个同类即升格为新标签。
"""


class InvalidTagError(ValueError):
    """标签值不在词表内。"""


LAYERS = {"dao", "fa", "shu"}

LAYER_CODES = {"道": "dao", "法": "fa", "术": "shu"}
LAYER_LABELS = {code: label for label, code in LAYER_CODES.items()}

TAG_VOCABULARIES: dict[str, set[str]] = {
    "domain": {"政治", "经济", "文化", "社会", "科技", "其他"},
    "circle": {"个人", "家庭", "朋友", "同事同窗", "公众", "其他"},
    "discipline": {"哲学", "心理学", "经济学", "社会学", "历史", "自然科学", "计算机", "文学艺术", "其他"},
    "scene": {"自我管理", "商业创业", "投资", "社交沟通", "学习认知", "文旅消费", "其他"},
}


def validate_layer(layer: str | None) -> None:
    if layer is not None and layer not in LAYERS:
        raise InvalidTagError(f"非法分层：{layer}（合法值：dao/fa/shu）")


def validate_tag(family: str, value: str | None) -> None:
    if family not in TAG_VOCABULARIES:
        raise InvalidTagError(f"未知标签族：{family}")
    if value is not None and value not in TAG_VOCABULARIES[family]:
        raise InvalidTagError(f"标签值不在词表内：{family}={value}")


def validate_tags(
    domain: str | None = None,
    circle: str | None = None,
    discipline: str | None = None,
    scene: str | None = None,
) -> None:
    validate_tag("domain", domain)
    validate_tag("circle", circle)
    validate_tag("discipline", discipline)
    validate_tag("scene", scene)
