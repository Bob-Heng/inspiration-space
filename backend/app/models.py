from datetime import datetime, date

from sqlalchemy import Boolean, Date, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .timeutils import UtcDateTime


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    # 找回密码用（可选，仅本地保存）
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())


class Inspiration(Base):
    """灵感：原始录入条目。灵感自身无状态机，首页状态由关联观点推导。"""

    __tablename__ = "inspirations"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    source_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="manual")
    # 原生双语：content 为原文镜像；content_zh/content_en 为两个语言版本
    content_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_lang: Mapped[str] = mapped_column(String(2), default="zh")
    title_zh: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now()
    )


class Viewpoint(Base):
    """观点：系统核心条目。status: draft（他山坊打磨中，集思录隐藏）/ accepted（已采纳入库）"""

    __tablename__ = "viewpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(20), default="raw")
    content: Mapped[str] = mapped_column(Text)
    source_inspiration_id: Mapped[int | None] = mapped_column(
        ForeignKey("inspirations.id"), nullable=True
    )
    source_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    layer: Mapped[str | None] = mapped_column(String(10), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(20), nullable=True)
    circle: Mapped[str | None] = mapped_column(String(20), nullable=True)
    discipline: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scene: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # 观点判断结果（录入/编辑时 AI 前置判断）：NULL=未判断或判断失败，开会话时前端走 live 判断兜底
    is_viewpoint: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    content_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_lang: Mapped[str] = mapped_column(String(2), default="zh")
    title_zh: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now()
    )


class ViewpointRelation(Base):
    """观点关系。relation_type: similar / conflict / related"""

    __tablename__ = "viewpoint_relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_viewpoint_id: Mapped[int] = mapped_column(ForeignKey("viewpoints.id"))
    to_viewpoint_id: Mapped[int] = mapped_column(ForeignKey("viewpoints.id"))
    relation_type: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())


class ReviewSession(Base):
    """打磨会话：围绕一条观点的打磨过程。status: active / paused / completed，
    允许 completed -> active（集思录撤回重开）；phase: distill 提炼 / polish 打磨"""

    __tablename__ = "review_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 本会话打磨的观点（主关联）
    viewpoint_id: Mapped[int] = mapped_column(ForeignKey("viewpoints.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")
    # 两阶段：distill=提炼（现象收敛为观点）/ polish=打磨（分析+决策）
    phase: Mapped[str] = mapped_column(String(10), default="distill")
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    # 最近一次 AI 审议分析结果（JSON），随会话持久化，关窗重开后恢复
    analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 分析结果的英文版（JSON），生成时同步翻译
    analysis_json_en: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReviewMessage(Base):
    """打磨对话消息。role: user / assistant / system；phase 为写入时会话所处阶段"""

    __tablename__ = "review_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("review_sessions.id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(String(10), default="polish")
    content_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_lang: Mapped[str] = mapped_column(String(2), default="zh")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())


class ReviewDecision(Base):
    """打磨决策。decision_type 今后只有 accept（历史行可能还有 accept_modified / reject / defer）"""

    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("review_sessions.id"))
    decision_type: Mapped[str] = mapped_column(String(20))
    final_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())


class LlmSetting(Base):
    """AI 服务设置（单行，id 固定为 1）。界面配置优先于环境变量（docs/04 D7 的扩展）。"""

    __tablename__ = "llm_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(50))
    base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())


class AiCall(Base):
    """AI 调用留痕：每次调用（成功或失败）记录 provider/model/prompt 版本/输入输出快照。"""

    __tablename__ = "ai_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    input_snapshot: Mapped[str] = mapped_column(Text)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
