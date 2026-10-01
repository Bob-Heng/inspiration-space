"""请求/响应模型。"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from .ai.schemas import AnalysisRelation, AnalysisResult, AnalysisTags

SourceType = Literal["manual", "docx_import", "migration"]
InspirationStatus = Literal["pending", "in_review", "reviewed", "rejected"]


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
    status: str
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
    inspiration_id: int


class ReviewMessageOut(BaseModel):
    id: int
    role: str
    content: str
    content_zh: str | None = None
    content_en: str | None = None
    original_lang: str = 'zh'
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewSessionOut(BaseModel):
    id: int
    inspiration_id: int
    viewpoint_id: int | None
    status: str
    started_at: datetime
    ended_at: datetime | None
    inspiration: InspirationOut
    messages: list[ReviewMessageOut] = []
    analysis: dict | None = None
    analysis_en: dict | None = None

    model_config = {"from_attributes": True}


class ReviewMessageCreate(BaseModel):
    """用户发言。analysis 为前端持有的该灵感最近一次审议分析结果（若有），仅作讨论上下文。"""

    content: str = Field(min_length=1)
    analysis: AnalysisResult | None = None


class ReviewMessagePair(BaseModel):
    user_message: ReviewMessageOut
    assistant_message: ReviewMessageOut


DecisionType = Literal["accept", "accept_modified", "reject", "defer"]


class DecisionRequest(BaseModel):
    """审议决策。正文/分层/四标签取用户确认值；layer 接受 dao/fa/shu 或 道/法/术。"""

    decision_type: DecisionType
    final_content: str | None = None
    reason: str | None = None
    layer: str | None = None
    tags: AnalysisTags | None = None
    relations: list[AnalysisRelation] = []
    regenerate_title: bool = False  # 采纳后用最终正文重新生成双语标题


class DecisionOut(BaseModel):
    decision_id: int | None
    decision_type: str
    viewpoint_id: int | None
    display_id: int | None = None  # 统一显示编号（来源灵感 id）
    session_status: str
    inspiration_status: str


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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


LayerCode = Literal["dao", "fa", "shu"]
ViewpointStatus = Literal["accepted", "suspended", "rejected"]
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


class MergeRequest(BaseModel):
    """合并：merged_content 为空时自动无损接续双方正文。"""

    absorbed_id: int
    merged_content: str | None = None
    reason: str = Field(min_length=1)


class MergeOut(BaseModel):
    survivor: ViewpointOut
    absorbed: ViewpointOut


class SplitRequest(BaseModel):
    parts: list[str] = Field(min_length=2)
    reason: str = Field(min_length=1)


class SplitOut(BaseModel):
    original: ViewpointOut
    new_viewpoints: list[ViewpointOut]


class StatusChangeRequest(BaseModel):
    """显式状态变更：悬置/恢复/否定。否定必须填写理由。"""

    to_status: ViewpointStatus
    reason: str | None = None


class ViewpointEventOut(BaseModel):
    id: int
    viewpoint_id: int
    event_type: str
    from_status: str | None
    to_status: str | None
    reason: str | None
    detail: dict | None
    created_at: datetime


class ClassifiedOut(BaseModel):
    """分类观点视图：道/法/术三组，已否定不列入，悬置保留标记。"""

    dao: list[ViewpointOut]
    fa: list[ViewpointOut]
    shu: list[ViewpointOut]


class RenameTitleRequest(BaseModel):
    title: str
    lang: str  # zh | en
