"""采纳决策路由测试：全事务（正文/双语/标题/分层/标签/关系/决策行/关会话）、
标题缺省时 AI 生成、DecisionOut 形状（display_id = 统一显示编号）。

不起 HTTP 层（测试环境无 httpx），直接以协程方式调用路由函数。
"""

import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.schemas import AnalysisRelation, AnalysisTags
from app.domain.review import open_review_session
from app.models import Base, ReviewDecision, Viewpoint, ViewpointRelation
from app.routers import review as review_route
from app.schemas import DecisionRequest


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
    """双语化与标题生成走真实 Provider 解析，替换为可控桩。"""
    calls = {"bilingual": 0, "titles": 0}

    async def _bilingual_stub(db, text, original_lang=None):
        calls["bilingual"] += 1
        return {
            "content_zh": text,
            "content_en": f"EN: {text}",
            "original_lang": "zh",
        }

    async def _titles_stub(db, content):
        calls["titles"] += 1
        return {"title_zh": "生成标题", "title_en": "Generated Title"}

    monkeypatch.setattr(review_route, "make_bilingual", _bilingual_stub)
    monkeypatch.setattr(review_route, "make_titles", _titles_stub)
    return calls


def _open(db, content="测试观点"):
    viewpoint = Viewpoint(content=content, status="draft")
    db.add(viewpoint)
    db.commit()
    return viewpoint, open_review_session(db, viewpoint)


def _decide(db, session, payload: DecisionRequest):
    return asyncio.run(review_route.post_decision(session.id, payload, db))


class TestDecisionSchema:
    def test_仅接受accept决策类型(self):
        with pytest.raises(ValidationError):
            DecisionRequest(decision_type="reject", final_content="正文")
        with pytest.raises(ValidationError):
            DecisionRequest(decision_type="defer", final_content="正文")
        with pytest.raises(ValidationError):
            DecisionRequest(decision_type="accept_modified", final_content="正文")

    def test_最终正文必填(self):
        with pytest.raises(ValidationError):
            DecisionRequest(decision_type="accept")


class TestAcceptRoute:
    def test_采纳全事务(self, db_session, _stub_ai):
        existing = Viewpoint(content="已有观点", status="accepted")
        db_session.add(existing)
        db_session.commit()
        viewpoint, session = _open(db_session)

        out = _decide(
            db_session,
            session,
            DecisionRequest(
                decision_type="accept",
                final_content="  最终正文  ",
                title_zh="用户标题",
                title_en="User Title",
                layer="道",
                tags=AnalysisTags(domain="文化", discipline="哲学"),
                relations=[AnalysisRelation(viewpoint_id=existing.id, type="conflict")],
            ),
        )

        # DecisionOut 形状：display_id = 统一显示编号（来源灵感编号，无来源兜底观点编号）
        assert out.decision_type == "accept"
        assert out.viewpoint_id == viewpoint.id
        assert out.display_id == viewpoint.id
        assert out.session_status == "completed"
        assert out.decision_id is not None

        db_session.refresh(viewpoint)
        assert viewpoint.status == "accepted"
        assert viewpoint.content == "最终正文"
        # 正文变化：重新双语化
        assert viewpoint.content_zh == "最终正文"
        assert viewpoint.content_en == "EN: 最终正文"
        assert viewpoint.title_zh == "用户标题"
        assert viewpoint.title_en == "User Title"
        assert viewpoint.layer == "dao"
        assert viewpoint.domain == "文化"
        assert viewpoint.discipline == "哲学"

        # 冲突关系只建行，双方状态不联动
        assert existing.status == "accepted"
        relations = db_session.scalars(select(ViewpointRelation)).all()
        assert len(relations) == 1
        assert relations[0].relation_type == "conflict"

        # 决策行落库，会话完结
        decisions = db_session.scalars(select(ReviewDecision)).all()
        assert len(decisions) == 1
        assert decisions[0].decision_type == "accept"
        assert decisions[0].final_content == "最终正文"
        assert session.status == "completed"
        assert session.ended_at is not None
        # 请求已带双语标题：不再调用标题生成
        assert _stub_ai["titles"] == 0

    def test_标题缺省时由AI生成(self, db_session, _stub_ai):
        viewpoint, session = _open(db_session)

        _decide(
            db_session,
            session,
            DecisionRequest(decision_type="accept", final_content="最终正文"),
        )

        db_session.refresh(viewpoint)
        assert viewpoint.title_zh == "生成标题"
        assert viewpoint.title_en == "Generated Title"
        assert _stub_ai["titles"] == 1

    def test_有来源灵感时display_id为灵感编号(self, db_session, _stub_ai):
        from app.models import Inspiration

        inspiration = Inspiration(content="灵感原文")
        db_session.add(inspiration)
        db_session.commit()
        viewpoint = Viewpoint(
            content="测试观点", status="draft", source_inspiration_id=inspiration.id
        )
        db_session.add(viewpoint)
        db_session.commit()
        session = open_review_session(db_session, viewpoint)

        out = _decide(
            db_session,
            session,
            DecisionRequest(decision_type="accept", final_content="最终正文"),
        )

        assert out.viewpoint_id == viewpoint.id
        assert out.display_id == inspiration.id

    def test_正文未变化时不重新双语化(self, db_session, monkeypatch, _stub_ai):
        viewpoint, session = _open(db_session, content="原样正文")
        viewpoint.content_zh = "原样正文"
        viewpoint.content_en = "Original content"
        db_session.commit()

        _decide(
            db_session,
            session,
            DecisionRequest(decision_type="accept", final_content=" 原样正文 "),
        )

        db_session.refresh(viewpoint)
        assert viewpoint.content_zh == "原样正文"
        assert viewpoint.content_en == "Original content"
        assert _stub_ai["bilingual"] == 0

    def test_空正文被拒409(self, db_session):
        from fastapi import HTTPException

        _, session = _open(db_session)
        with pytest.raises(HTTPException) as exc_info:
            _decide(
                db_session,
                session,
                DecisionRequest(decision_type="accept", final_content="   "),
            )
        assert exc_info.value.status_code == 409
