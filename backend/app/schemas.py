"""请求/响应模型。"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .ai.schemas import AnalysisRelation, AnalysisResult, AnalysisTags

SourceType = Literal["manual", "docx_import", "migration"]


class InspirationCreate(BaseModel):
    content: str = Field(min_length=1)
    source_date: date | None = None
    source_type: SourceType = "manual"


class InspirationUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    source_date: date | None = None


class InspirationOut(BaseModel):
    id: int
    content: str
    content_zh: str | None = None
    content_en: str | None = None
    original_lang: str = 'zh'
    title_zh: str | None = None
    title_en: str | None = None
    source_date: date | None
    source_type: str
    # 关联观点（录入时同事务创建的草稿观点）；首页状态由观点状态推导
    viewpoint_id: int | None = None
    viewpoint_status: str | None = None
    # 关联观点为 draft 时取其最近一条非 completed 会话的阶段（无会话为 distill）；
    # accepted 或无观点时为 None
    viewpoint_phase: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InspirationDeleted(BaseModel):
    deleted_id: int


class ImportPreviewItem(BaseModel):
    """docx 拆解预览条目：content 原文，source_date 可空（识别不到日期留空）。"""

    content: str = Field(min_length=1)
    source_date: date | None = None


class ImportPreviewOut(BaseModel):
    """上传 docx 的拆解预览：不入库，用户确认后才批量写入。"""

    filename: str
    default_year: int | None
    items: list[ImportPreviewItem]


class ImportConfirmRequest(BaseModel):
    """用户确认（可勾选/编辑后）的批量入库请求。"""

    items: list[ImportPreviewItem] = Field(min_length=1)


class ReviewSessionCreate(BaseModel):
    viewpoint_id: int


class ReviewMessageOut(BaseModel):
    id: int
    role: str
    content: str
    phase: str = "polish"  # 写入时会话所处阶段；存量消息迁移回填 polish
    content_zh: str | None = None
    content_en: str | None = None
    original_lang: str = 'zh'
    created_at: datetime

    model_config = {"from_attributes": True}


class ViewpointOut(BaseModel):
    id: int
    type: str
    content: str
    content_zh: str | None = None
    content_en: str | None = None
    original_lang: str = 'zh'
    title_zh: str | None = None
    title_en: str | None = None
    source_inspiration_id: int | None
    source_date: date | None
    layer: str | None
    domain: str | None
    circle: str | None
    discipline: str | None
    scene: str | None
    status: str
    # 观点判断结果：NULL=未判断/判断失败（存量观点或 AI 不可用），前端走 live 判断兜底
    is_viewpoint: bool | None = None
    # 冲突对方的展示编号（来源灵感编号，无来源兜底观点编号），排序去重；
    # 仅集思录列表/分类视图组装，其他场景保持 None
    conflict_with: list[int] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewQueueItem(BaseModel):
    """他山坊待打磨队列条目：draft 观点；标题取关联灵感的工作名（可空）。"""

    id: int
    content: str
    content_zh: str | None = None
    content_en: str | None = None
    original_lang: str = 'zh'
    source_date: date | None
    inspiration_id: int | None
    title_zh: str | None = None
    title_en: str | None = None
    # 该观点最近一条非 completed 会话（active/paused）的阶段；无会话为 distill
    phase: str = "distill"


class ReviewSessionOut(BaseModel):
    id: int
    viewpoint_id: int
    status: str
    phase: str = "polish"  # 兜底默认：正常从模型读到；旧式会话视为打磨
    started_at: datetime
    ended_at: datetime | None
    viewpoint: ViewpointOut  # 本会话打磨的观点（主关联，必然存在）
    messages: list[ReviewMessageOut] = []
    analysis: dict | None = None
    analysis_en: dict | None = None

    model_config = {"from_attributes": True}


class ReviewMessageCreate(BaseModel):
    """用户发言。analysis 为前端持有的该灵感最近一次审议分析结果（若有），仅作讨论上下文。"""

    content: str = Field(min_length=1)
    analysis: AnalysisResult | None = None


class DistillSignal(BaseModel):
    """提炼阶段 AI 回复附带的收敛信号（docs/04 D9），仅提炼期讨论返回。

    ready_to_polish=true 时该轮回复不落库、不进对话框（前端弹窗接管），
    reply 携带被压下的回复正文，供用户取消弹窗时临时展示。"""

    ready_to_polish: bool
    distilled_viewpoint: str | None = None
    reply: str | None = None


class ReviewMessagePair(BaseModel):
    user_message: ReviewMessageOut
    # 提炼收敛轮回复不落库，此时为 None
    assistant_message: ReviewMessageOut | None = None
    distill_signal: DistillSignal | None = None


class ViewpointCheckOut(BaseModel):
    """观点判断结果：该会话的观点正文是否已构成可裁决的观点。"""

    is_viewpoint: bool


class EnterPolishRequest(BaseModel):
    """进入打磨阶段：draft 为提炼收敛出的观点草稿（空串视为无草稿）。"""

    draft: str | None = None


DecisionType = Literal["accept"]


class DecisionRequest(BaseModel):
    """打磨决策：仅采纳。正文必填；标题缺省时由 AI 生成；layer 接受 dao/fa/shu 或 道/法/术。"""

    decision_type: DecisionType
    final_content: str = Field(min_length=1)
    title_zh: str | None = None
    title_en: str | None = None
    reason: str | None = None
    layer: str | None = None
    tags: AnalysisTags | None = None
    relations: list[AnalysisRelation] = []


class DecisionOut(BaseModel):
    decision_id: int | None
    decision_type: str
    viewpoint_id: int | None
    display_id: int | None = None  # 统一显示编号（来源灵感编号，无来源时兜底观点编号）
    session_status: str


LayerCode = Literal["dao", "fa", "shu"]
RelationType = Literal["similar", "conflict", "related"]


class RelationCreate(BaseModel):
    to_viewpoint_id: int
    relation_type: RelationType


class RelationOut(BaseModel):
    """一条关系及其对方观点。"""

    id: int
    relation_type: str
    created_at: datetime
    viewpoint: ViewpointOut


class ViewpointTitleUpdate(BaseModel):
    """观点标题更新：两字段独立可空更新（None = 不动），全空 422。"""

    title_zh: str | None = None
    title_en: str | None = None

    @model_validator(mode="after")
    def _at_least_one(self):
        if self.title_zh is None and self.title_en is None:
            raise ValueError("title_zh 与 title_en 至少提供其一")
        return self


class ClassifiedOut(BaseModel):
    """分类观点视图：道/法/术三组，只收已采纳观点。"""

    dao: list[ViewpointOut]
    fa: list[ViewpointOut]
    shu: list[ViewpointOut]


class RenameTitleRequest(BaseModel):
    title: str
    lang: str  # zh | en


class TitleSuggestionRequest(BaseModel):
    """AI 标题建议：以正文为输入，返回双语标题建议（不落库）。"""

    content: str = Field(min_length=1)


class TitleSuggestionOut(BaseModel):
    title_zh: str | None = None
    title_en: str | None = None
