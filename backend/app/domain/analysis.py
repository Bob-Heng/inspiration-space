"""审议分析的业务校验：Schema 合法之后再过业务规则（docs/02 §2/§3/§5）。

- 分层建议必须是 道/法/术 之一；
- 四标签族取值必须在词表内或留空；
- 相近/冲突关系引用的 viewpoint_id 必须真实存在，不存在（或类型非法）则该条剔除并记录。
"""

import logging

from ..ai.errors import BusinessValidationError
from ..ai.schemas import AnalysisResult
from .tags import InvalidTagError, LAYER_CODES, TAG_VOCABULARIES, validate_tag

logger = logging.getLogger(__name__)

RELATION_TYPES = {"similar", "conflict"}


def validate_analysis_result(
    result: AnalysisResult, existing_viewpoint_ids: set[int]
) -> AnalysisResult:
    if result.layer not in LAYER_CODES:
        raise BusinessValidationError(
            f"分层建议不合法：{result.layer}（须为 道/法/术 之一）"
        )
    for family in TAG_VOCABULARIES:
        value = getattr(result.tags, family)
        try:
            validate_tag(family, value)
        except InvalidTagError as exc:
            raise BusinessValidationError(str(exc)) from exc

    kept, dropped = [], []
    for relation in result.relations:
        if relation.type in RELATION_TYPES and relation.viewpoint_id in existing_viewpoint_ids:
            kept.append(relation)
        else:
            dropped.append(relation)
    if dropped:
        logger.warning(
            "AI 建议的关系含无效条目，已剔除：%s",
            [
                {"viewpoint_id": r.viewpoint_id, "type": r.type}
                for r in dropped
            ],
        )
    result.relations = kept
    return result
