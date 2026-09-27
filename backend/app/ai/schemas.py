"""AI 结构化输出 Schema（设计说明书 §11.2）。"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AnalysisTags(BaseModel):
    """四标签族建议：每族 0~1 个，可留空，取值须在 docs/02 §3 词表内（业务校验把关）。"""

    domain: str | None = None
    circle: str | None = None
    discipline: str | None = None
    scene: str | None = None


class AnalysisRelation(BaseModel):
    """与已有观点的相近/冲突关系建议。"""

    viewpoint_id: int
    type: str  # similar / conflict，业务校验把关


class AnalysisResult(BaseModel):
    """审议分析输出：三项分析（采纳理由+最强反对理由 / 分层+四标签建议 / 相近冲突关系）
    缺一不可，外加第一轮疑问。"""

    adoption_reason: NonEmptyStr
    strongest_counterargument: NonEmptyStr
    layer: str  # 道 / 法 / 术，业务校验把关
    tags: AnalysisTags
    relations: list[AnalysisRelation]
    questions: list[NonEmptyStr] = Field(min_length=1)


class DocxSplitItem(BaseModel):
    """docx 拆解出的单条灵感：只切割不改写；date_text 保留原文日期写法，识别不到为 null。"""

    content: NonEmptyStr
    date_text: str | None = None


class DocxSplitResult(BaseModel):
    """docx 导入的 AI 拆解输出（TASK-018）。"""

    items: list[DocxSplitItem] = Field(min_length=1)
