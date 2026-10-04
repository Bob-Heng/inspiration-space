"""灵感守卫测试：录入联动建草稿观点；编辑/删除对已入库灵感拒 409（adopted_locked）；
编辑同步关联观点并把其进行中/挂起会话重置到提炼最开始；删除级联无残留。
观点判断前置：录入（含 docx 导入确认）与编辑正文变化时写入 is_viewpoint，
AI 未配置/不可用/输出非法置 NULL 不阻断；灵感输出携带 viewpoint_phase。

不起 HTTP 层（测试环境无 httpx），直接以协程方式调用路由函数。
"""

import asyncio
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai import LLMProvider, LLMUnavailableError, Message
from app.domain.review import open_review_session
from app.models import (
    AiCall,
    Base,
    Inspiration,
    ReviewDecision,
    ReviewMessage,
    ReviewSession,
    Viewpoint,
    ViewpointRelation,
)
from app.routers import inspirations as inspirations_route
from app.schemas import InspirationCreate, InspirationUpdate


class CheckProvider(LLMProvider):
    """观点判断 fake：固定返回 {"is_viewpoint": ...}。"""

    provider_name = "fake"
    model = "fake-model"

    def __init__(self, is_viewpoint: bool) -> None:
        self.is_viewpoint = is_viewpoint

    async def generate(self, messages: list[Message]) -> str:
        return json.dumps({"is_viewpoint": self.is_viewpoint})


class UnavailableProvider(LLMProvider):
    """AI 不可达 fake。"""

    provider_name = "fake"
    model = "fake-model"

    async def generate(self, messages: list[Message]) -> str:
        raise LLMUnavailableError("AI 网关未启动")


class BadOutputProvider(LLMProvider):
    """输出非法 fake：返回非 JSON 文本。"""

    provider_name = "fake"
    model = "fake-model"

    async def generate(self, messages: list[Message]) -> str:
        return "这不是 JSON"


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _stub_ai(monkeypatch):
    async def _bilingual_stub(db, text, original_lang=None):
        return {
            "content_zh": text,
            "content_en": f"EN: {text}",
            "original_lang": "zh",
        }

    async def _titles_stub(db, content):
        return {"title_zh": "标题", "title_en": "Title"}

    monkeypatch.setattr(inspirations_route, "make_bilingual", _bilingual_stub)
    monkeypatch.setattr(inspirations_route, "make_titles", _titles_stub)


def _create(db, content="测试灵感", source_date=None, provider=None):
    return asyncio.run(
        inspirations_route.create_inspiration(
            InspirationCreate(content=content, source_date=source_date),
            db,
            provider=provider,
        )
    )


def _accepted_viewpoint(db, inspiration_id: int) -> Viewpoint:
    viewpoint = db.scalars(
        select(Viewpoint).where(Viewpoint.source_inspiration_id == inspiration_id)
    ).one()
    viewpoint.status = "accepted"
    db.commit()
    return viewpoint


class TestCreateLink:
    def test_录入灵感同事务建草稿观点(self, db_session):
        from datetime import date

        out = _create(db_session, "新灵感", source_date=date(2026, 5, 2))

        assert out.viewpoint_id is not None
        assert out.viewpoint_status == "draft"
        viewpoint = db_session.get(Viewpoint, out.viewpoint_id)
        assert viewpoint.source_inspiration_id == out.id
        assert viewpoint.content == "新灵感"
        assert viewpoint.content_zh == "新灵感"
        assert viewpoint.content_en == "EN: 新灵感"
        assert viewpoint.original_lang == "zh"
        assert viewpoint.source_date == date(2026, 5, 2)
        # 采纳前沿用灵感标题（灵感标题本身不改动）
        assert viewpoint.title_zh == "标题"
        assert viewpoint.title_en == "Title"

    def test_列表与单条响应携带关联观点(self, db_session):
        created = _create(db_session)

        listed = inspirations_route.list_inspirations(keyword=None, db=db_session)
        assert [i.id for i in listed] == [created.id]
        assert listed[0].viewpoint_id == created.viewpoint_id
        assert listed[0].viewpoint_status == "draft"

        single = inspirations_route.get_inspiration(created.id, db_session)
        assert single.viewpoint_id == created.viewpoint_id
        assert single.viewpoint_status == "draft"


class TestUpdateGuard:
    def test_已入库灵感编辑被拒(self, db_session):
        created = _create(db_session)
        _accepted_viewpoint(db_session, created.id)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                inspirations_route.update_inspiration(
                    created.id, InspirationUpdate(content="改内容"), db_session,
                    provider=None,
                )
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "adopted_locked"
        assert "先在集思录中撤回" in exc_info.value.detail["zh"]
        assert exc_info.value.detail["en"]
        # 内容未被改动
        assert db_session.get(Inspiration, created.id).content == "测试灵感"

    def test_编辑同步观点并重置会话(self, db_session):
        from datetime import date

        created = _create(db_session)
        viewpoint = db_session.get(Viewpoint, created.viewpoint_id)
        session = open_review_session(db_session, viewpoint)
        session.phase = "polish"
        session.analysis_json = '{"adoption_reason": "值得采纳"}'
        session.analysis_json_en = '{"adoption_reason": "Worth"}'
        db_session.add_all(
            [
                ReviewMessage(session_id=session.id, role="user", content="提炼讨论", phase="distill"),
                ReviewMessage(session_id=session.id, role="assistant", content="打磨回复", phase="polish"),
            ]
        )
        db_session.commit()

        out = asyncio.run(
            inspirations_route.update_inspiration(
                created.id,
                InspirationUpdate(content="改后的灵感", source_date=date(2026, 6, 1)),
                db_session,
                provider=None,
            )
        )

        assert out.content == "改后的灵感"
        assert out.source_date == date(2026, 6, 1)
        db_session.refresh(viewpoint)
        assert viewpoint.content == "改后的灵感"
        assert viewpoint.content_zh == "改后的灵感"
        assert viewpoint.content_en == "EN: 改后的灵感"
        assert viewpoint.original_lang == "zh"
        assert viewpoint.source_date == date(2026, 6, 1)
        # 会话重置到提炼最开始：distill、分析清空、消息全删
        db_session.refresh(session)
        assert session.phase == "distill"
        assert session.analysis_json is None
        assert session.analysis_json_en is None
        assert db_session.scalars(select(ReviewMessage)).all() == []

    def test_内容未变时不重置会话(self, db_session):
        from datetime import date

        created = _create(db_session)
        viewpoint = db_session.get(Viewpoint, created.viewpoint_id)
        session = open_review_session(db_session, viewpoint)
        session.phase = "polish"
        session.analysis_json = '{"a": 1}'
        db_session.add(
            ReviewMessage(session_id=session.id, role="user", content="讨论", phase="polish")
        )
        db_session.commit()

        asyncio.run(
            inspirations_route.update_inspiration(
                created.id,
                InspirationUpdate(source_date=date(2026, 6, 1)),
                db_session,
                provider=None,
            )
        )

        db_session.refresh(viewpoint)
        assert viewpoint.source_date == date(2026, 6, 1)
        db_session.refresh(session)
        assert session.phase == "polish"
        assert session.analysis_json == '{"a": 1}'
        assert db_session.scalars(select(ReviewMessage)).all() != []


class TestDeleteGuard:
    def test_已入库灵感删除被拒(self, db_session):
        created = _create(db_session)
        _accepted_viewpoint(db_session, created.id)

        with pytest.raises(HTTPException) as exc_info:
            inspirations_route.delete_inspiration(created.id, db_session)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "adopted_locked"
        assert "不可删除" in exc_info.value.detail["zh"]
        assert db_session.get(Inspiration, created.id) is not None

    def test_删除级联无残留(self, db_session):
        created = _create(db_session)
        viewpoint = db_session.get(Viewpoint, created.viewpoint_id)
        session = open_review_session(db_session, viewpoint)
        db_session.add(
            ReviewMessage(session_id=session.id, role="user", content="讨论", phase="distill")
        )
        other = Viewpoint(content="其他观点", status="accepted")
        db_session.add(other)
        db_session.commit()
        db_session.add(
            ViewpointRelation(
                from_viewpoint_id=viewpoint.id,
                to_viewpoint_id=other.id,
                relation_type="similar",
            )
        )
        db_session.commit()

        result = inspirations_route.delete_inspiration(created.id, db_session)

        assert result["deleted_id"] == created.id
        assert db_session.scalars(select(Inspiration)).all() == []
        # 关联观点、会话、消息、关系行全部级联删除；其他观点不受影响
        remaining_viewpoints = db_session.scalars(select(Viewpoint)).all()
        assert [v.id for v in remaining_viewpoints] == [other.id]
        assert db_session.scalars(select(ReviewSession)).all() == []
        assert db_session.scalars(select(ReviewMessage)).all() == []
        assert db_session.scalars(select(ReviewDecision)).all() == []
        assert db_session.scalars(select(ViewpointRelation)).all() == []


class TestImportConfirmLink:
    def test_docx导入确认每条建草稿观点(self, db_session):
        from app.schemas import ImportConfirmRequest, ImportPreviewItem

        out = asyncio.run(
            inspirations_route.confirm_import(
                ImportConfirmRequest(
                    items=[
                        ImportPreviewItem(content="导入条目一"),
                        ImportPreviewItem(content="导入条目二"),
                    ]
                ),
                db_session,
                provider=None,
            )
        )

        assert len(out) == 2
        for item in out:
            assert item.viewpoint_id is not None
            assert item.viewpoint_status == "draft"
            viewpoint = db_session.get(Viewpoint, item.viewpoint_id)
            assert viewpoint.content == item.content
            assert viewpoint.source_inspiration_id == item.id


class TestViewpointJudgement:
    """观点判断前置：录入（含 docx 导入确认）与编辑正文变化时写入 is_viewpoint。"""

    def test_录入时判断为观点(self, db_session):
        out = _create(db_session, "明确的判断句", provider=CheckProvider(True))

        assert db_session.get(Viewpoint, out.viewpoint_id).is_viewpoint is True
        # 结构化调用留痕
        call = db_session.query(AiCall).order_by(AiCall.id.desc()).first()
        assert call.prompt_version == "viewpoint_check.v1"

    def test_录入时判断为非观点(self, db_session):
        out = _create(db_session, "一段现象描述", provider=CheckProvider(False))

        assert db_session.get(Viewpoint, out.viewpoint_id).is_viewpoint is False

    def test_AI不可用置NULL不阻断录入(self, db_session):
        out = _create(db_session, "任何内容", provider=UnavailableProvider())

        viewpoint = db_session.get(Viewpoint, out.viewpoint_id)
        assert viewpoint.is_viewpoint is None
        # 失败也留痕（run_structured_call 完成）
        call = db_session.query(AiCall).order_by(AiCall.id.desc()).first()
        assert call.prompt_version == "viewpoint_check.v1"
        assert "调用失败" in call.output

    def test_AI输出非法置NULL不阻断录入(self, db_session):
        out = _create(db_session, "任何内容", provider=BadOutputProvider())

        assert db_session.get(Viewpoint, out.viewpoint_id).is_viewpoint is None

    def test_未配置AI置NULL不阻断录入(self, db_session):
        out = _create(db_session, "任何内容", provider=None)

        assert out.viewpoint_id is not None
        assert db_session.get(Viewpoint, out.viewpoint_id).is_viewpoint is None

    def test_docx导入确认逐条判断(self, db_session):
        from app.schemas import ImportConfirmRequest, ImportPreviewItem

        out = asyncio.run(
            inspirations_route.confirm_import(
                ImportConfirmRequest(
                    items=[
                        ImportPreviewItem(content="导入条目一"),
                        ImportPreviewItem(content="导入条目二"),
                    ]
                ),
                db_session,
                provider=CheckProvider(True),
            )
        )

        assert len(out) == 2
        for item in out:
            assert db_session.get(Viewpoint, item.viewpoint_id).is_viewpoint is True

    def test_docx导入确认AI失败置NULL不阻断(self, db_session):
        from app.schemas import ImportConfirmRequest, ImportPreviewItem

        out = asyncio.run(
            inspirations_route.confirm_import(
                ImportConfirmRequest(items=[ImportPreviewItem(content="导入条目")]),
                db_session,
                provider=UnavailableProvider(),
            )
        )

        assert len(out) == 1
        assert db_session.get(Viewpoint, out[0].viewpoint_id).is_viewpoint is None

    def test_编辑正文变化重新判断(self, db_session):
        created = _create(db_session, provider=CheckProvider(True))
        viewpoint = db_session.get(Viewpoint, created.viewpoint_id)
        assert viewpoint.is_viewpoint is True

        asyncio.run(
            inspirations_route.update_inspiration(
                created.id,
                InspirationUpdate(content="改后的灵感"),
                db_session,
                provider=CheckProvider(False),
            )
        )

        db_session.refresh(viewpoint)
        assert viewpoint.is_viewpoint is False

    def test_编辑正文变化但判断失败置NULL(self, db_session):
        created = _create(db_session, provider=CheckProvider(True))
        viewpoint = db_session.get(Viewpoint, created.viewpoint_id)

        asyncio.run(
            inspirations_route.update_inspiration(
                created.id,
                InspirationUpdate(content="改后的灵感"),
                db_session,
                provider=UnavailableProvider(),
            )
        )

        db_session.refresh(viewpoint)
        assert viewpoint.is_viewpoint is None

    def test_仅改日期不重新判断(self, db_session):
        from datetime import date

        created = _create(db_session, provider=CheckProvider(True))
        viewpoint = db_session.get(Viewpoint, created.viewpoint_id)
        calls_before = db_session.query(AiCall).count()

        class _ForbiddenProvider(LLMProvider):
            provider_name = "fake"
            model = "fake-model"

            async def generate(self, messages: list[Message]) -> str:
                raise AssertionError("仅改日期不应触发观点判断")

        asyncio.run(
            inspirations_route.update_inspiration(
                created.id,
                InspirationUpdate(source_date=date(2026, 6, 1)),
                db_session,
                provider=_ForbiddenProvider(),
            )
        )

        db_session.refresh(viewpoint)
        assert viewpoint.is_viewpoint is True  # 保持原判断结果
        assert db_session.query(AiCall).count() == calls_before


class TestViewpointPhase:
    """InspirationOut.viewpoint_phase：draft 观点取最近非 completed 会话阶段。"""

    def test_draft无会话为distill(self, db_session):
        created = _create(db_session)

        assert created.viewpoint_phase == "distill"
        single = inspirations_route.get_inspiration(created.id, db_session)
        assert single.viewpoint_phase == "distill"
        listed = inspirations_route.list_inspirations(keyword=None, db=db_session)
        assert listed[0].viewpoint_phase == "distill"

    def test_draft取会话阶段(self, db_session):
        created = _create(db_session)
        viewpoint = db_session.get(Viewpoint, created.viewpoint_id)
        session = open_review_session(db_session, viewpoint)
        session.phase = "polish"
        db_session.commit()

        single = inspirations_route.get_inspiration(created.id, db_session)
        assert single.viewpoint_phase == "polish"
        listed = inspirations_route.list_inspirations(keyword=None, db=db_session)
        assert listed[0].viewpoint_phase == "polish"

    def test_completed会话忽略回退distill(self, db_session):
        created = _create(db_session)
        viewpoint = db_session.get(Viewpoint, created.viewpoint_id)
        session = open_review_session(db_session, viewpoint)
        session.phase = "polish"
        session.status = "completed"
        db_session.commit()

        single = inspirations_route.get_inspiration(created.id, db_session)
        assert single.viewpoint_phase == "distill"

    def test_已入库观点为None(self, db_session):
        created = _create(db_session)
        _accepted_viewpoint(db_session, created.id)

        single = inspirations_route.get_inspiration(created.id, db_session)
        assert single.viewpoint_phase is None
        listed = inspirations_route.list_inspirations(keyword=None, db=db_session)
        assert listed[0].viewpoint_phase is None
