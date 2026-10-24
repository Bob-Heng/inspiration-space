"""AI 结构化输出 Schema（设计说明书 §11.2）。"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AnalysisTags(BaseModel):
    """四标签族建议：每族 0~1 个，可留空，取值须在 docs/02 §3 词表内（业务校验把关）。"""

    domain: str | None = None
    circle: str | None = None
    discipline: str | None = None
    scene: str | None = None


class AnalysisRelation(BaseModel):
    """与已有观点的相近/冲突关系建议。新分析使用展示编号；旧内部 id 仅作兼容。"""

    viewpoint_id: int | None = None
    display_id: int | None = None
    type: str  # similar / conflict，业务校验把关

    @model_validator(mode="after")
    def _has_number(self):
        if self.display_id is None and self.viewpoint_id is None:
            raise ValueError("关联观点必须包含 display_id")
        return self


class DiscussionTurn(BaseModel):
    """讨论的一轮输出：要么请求查询，要么给出正式回复，二者互斥。"""

    tool: Literal["get_current_viewpoint", "get_accepted_viewpoint"] | None = None
    display_id: int | None = None
    reply: NonEmptyStr | None = None
    ready_to_polish: bool = False
    distilled_viewpoint: str | None = None
    ready_to_adopt: bool = False
    polished_viewpoint: str | None = None

    @model_validator(mode="after")
    def _tool_or_reply(self):
        if self.tool is None and self.reply is None:
            raise ValueError("讨论输出必须包含 reply 或 tool")
        if self.tool is not None:
            if self.reply is not None:
                raise ValueError("查询请求不得同时包含 reply")
            if self.tool == "get_accepted_viewpoint" and self.display_id is None:
                raise ValueError("查询已入库观点必须包含 display_id")
            if self.tool == "get_current_viewpoint":
                self.display_id = None
        return self


class AnalysisResult(BaseModel):
    """审议分析输出：三项分析（采纳理由+最强反对理由 / 分层+四标签建议 / 相近冲突关系）
    缺一不可。疑问不在分析中预设——由讨论中的 AI 现场提问。"""

    adoption_reason: NonEmptyStr
    strongest_counterargument: NonEmptyStr
    layer: str  # 道 / 法 / 术，业务校验把关
    tags: AnalysisTags
    relations: list[AnalysisRelation]


class ViewpointCheck(BaseModel):
    """观点判断输出：一条灵感是否已构成可裁决的观点（docs/04 D9）。"""

    is_viewpoint: bool


class DistillReply(BaseModel):
    """提炼阶段讨论输出：自然回复 + 收敛信号。ready_to_polish 仅在用户已明确说出
    可裁决的命题性判断时为 true，distilled_viewpoint 为可直接入库的观点草稿。"""

    reply: NonEmptyStr
    ready_to_polish: bool
    distilled_viewpoint: str | None = None


class PolishReply(BaseModel):
    """打磨阶段讨论输出：自然回复 + 采纳收敛信号。ready_to_adopt 仅在用户与 AI
    已就观点最终表述形成共识时为 true，polished_viewpoint 为双方认可、
    可直接入库的最终正文。"""

    reply: NonEmptyStr
    ready_to_adopt: bool
    polished_viewpoint: str | None = None


class DocxSplitItem(BaseModel):
    """docx 拆解出的单条灵感：只切割不改写；date_text 保留原文日期写法，识别不到为 null。"""

    content: NonEmptyStr
    date_text: str | None = None


class DocxSplitResult(BaseModel):
    """docx 导入的 AI 拆解输出（TASK-018）。"""

    items: list[DocxSplitItem] = Field(min_length=1)
