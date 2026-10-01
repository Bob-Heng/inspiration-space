"""审议分析业务校验与输出 Schema 的单元测试（docs/02 §5：三项分析缺一不可）。"""

import pytest
from pydantic import ValidationError

from app.ai.errors import BusinessValidationError
from app.ai.schemas import AnalysisRelation, AnalysisResult, AnalysisTags
from app.domain.analysis import validate_analysis_result


def _valid_result(**overrides) -> AnalysisResult:
    data = {
        "adoption_reason": "值得采纳",
        "strongest_counterargument": "最强反对理由",
        "layer": "法",
        "tags": {"domain": "文化", "circle": None, "discipline": "经济学", "scene": None},
        "relations": [],
    }
    data.update(overrides)
    return AnalysisResult(**data)


class TestAnalysisSchema:
    def test_合法输出通过(self):
        result = _valid_result()
        assert result.layer == "法"
        assert result.tags.domain == "文化"

    @pytest.mark.parametrize(
        "missing_field",
        ["adoption_reason", "strongest_counterargument", "layer", "tags", "relations"],
    )
    def test_三项分析及相关字段缺一即失败(self, missing_field):
        data = _valid_result().model_dump()
        del data[missing_field]
        with pytest.raises(ValidationError):
            AnalysisResult(**data)

    def test_空白理由被拒绝(self):
        with pytest.raises(ValidationError):
            _valid_result(adoption_reason="   ")


class TestAnalysisBusinessValidation:
    def test_合法结果原样通过(self):
        result = _valid_result(
            relations=[AnalysisRelation(viewpoint_id=1, type="similar")]
        )
        validated = validate_analysis_result(result, {1, 2})
        assert len(validated.relations) == 1

    def test_分层必须是道法术(self):
        with pytest.raises(BusinessValidationError, match="分层建议不合法"):
            validate_analysis_result(_valid_result(layer="器"), set())

    def test_标签必须在词表内(self):
        result = _valid_result()
        result.tags.circle = "网友"
        with pytest.raises(BusinessValidationError, match="不在词表内"):
            validate_analysis_result(result, set())

    def test_标签留空合法(self):
        result = _valid_result(tags=AnalysisTags())
        validate_analysis_result(result, set())

    def test_引用不存在的观点被剔除(self):
        result = _valid_result(
            relations=[
                AnalysisRelation(viewpoint_id=1, type="similar"),
                AnalysisRelation(viewpoint_id=999, type="conflict"),
            ]
        )
        validated = validate_analysis_result(result, {1})
        assert [r.viewpoint_id for r in validated.relations] == [1]

    def test_非法关系类型被剔除(self):
        result = _valid_result(
            relations=[AnalysisRelation(viewpoint_id=1, type="related")]
        )
        validated = validate_analysis_result(result, {1})
        assert validated.relations == []

    def test_观点库为空时空关系合法(self):
        validate_analysis_result(_valid_result(), set())
