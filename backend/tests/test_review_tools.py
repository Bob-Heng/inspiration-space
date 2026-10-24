"""讨论按需查询与统一展示编号测试。

覆盖：默认不带全库、连续工具调用、查询结果回喂、SSE 进度事件、
工具记录随消息撤销，以及采纳关系由展示编号解析到内部 id。
"""

import asyncio
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai import LLMProvider, Message
from app.domain.review import apply_review_decision, open_review_session, undo_last_message
from app.models import (
    Base,
    Inspiration,
    ReviewMessage,
    ReviewToolCall,
    Viewpoint,
    ViewpointRelation,
)
from app.routers import review as review_route
from app.routers import viewpoints as viewpoints_route
from app.schemas import ReviewMessageCreate


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
def _no_translation(monkeypatch):
    async def _bilingual_stub(db, text, original_lang=None):
        return {
            "content_zh": None,
            "content_en": None,
            "original_lang": original_lang or "zh",
        }

    monkeypatch.setattr(review_route, "make_bilingual", _bilingual_stub)


class QueryProvider(LLMProvider):
    provider_name = "fake"
    model = "fake-model"

    def __init__(self):
        self.outputs = [
            {"tool": "get_current_viewpoint"},
            {"tool": "get_accepted_viewpoint", "display_id": 33},
            {"reply": "已核实 #33 的正文与来源。", "ready_to_adopt": False},
        ]
        self.calls = []

    async def generate(self, messages: list[Message]) -> str:
        self.calls.append(messages)
        return json.dumps(self.outputs[len(self.calls) - 1], ensure_ascii=False)


def _seed(db):
    current_inspiration = Inspiration(id=42, content="当前灵感", title_zh="当前标题")
    other_inspiration = Inspiration(id=33, content="#33 的来源灵感", title_zh="来源标题")
    db.add_all([current_inspiration, other_inspiration])
    current = Viewpoint(
        id=42,
        content="当前观点正文",
        source_inspiration_id=42,
        status="draft",
        title_zh="当前标题",
    )
    other = Viewpoint(
        id=6,
        content="其他观点正文秘密",
        source_inspiration_id=33,
        status="accepted",
        title_zh="其他观点标题",
        layer="fa",
        domain="文化",
    )
    db.add_all([current, other])
    db.flush()
    db.add(
        ViewpointRelation(
            from_viewpoint_id=current.id,
            to_viewpoint_id=other.id,
            relation_type="similar",
        )
    )
    db.commit()
    session = open_review_session(db, current)
    session.phase = "polish"
    session.distilled_snapshot = "提炼完成的工作稿"
    db.commit()
    return session, current, other


def _send(db, session, provider, emit=None):
    return asyncio.run(
        review_route._post_message_impl(
            session.id,
            ReviewMessageCreate(content="请解释关联观点"),
            db,
            provider,
            None,
            emit,
        )
    )


def test_连续查询_默认无全库_结果回喂与撤销(db_session):
    session, current, other = _seed(db_session)
    provider = QueryProvider()
    events = []
    pair = _send(db_session, session, provider, lambda event, data: events.append((event, data)))

    assert pair.assistant_message.content == "已核实 #33 的正文与来源。"
    assert len(provider.calls) == 3
    first_context = json.dumps(provider.calls[0], ensure_ascii=False)
    assert "其他观点正文秘密" not in first_context
    assert "#42" in first_context
    second_context = provider.calls[1][-1]["content"]
    assert '"number": 33' in second_context
    assert "提炼完成的工作稿" in second_context
    third_context = json.dumps(provider.calls[2], ensure_ascii=False)
    assert "其他观点正文秘密" in third_context
    assert "#33 的来源灵感" in third_context

    calls = list(db_session.scalars(select(ReviewToolCall).order_by(ReviewToolCall.id)))
    assert [c.target for c in calls] == ["current", "33"]
    assert [c.status for c in calls] == ["completed", "completed"]
    assert [e[1]["status"] for e in events] == ["running", "completed", "running", "completed"]

    user_message_id = pair.user_message.id
    assert all(c.turn_id == user_message_id for c in calls)
    undo_last_message(db_session, session)
    assert db_session.query(ReviewToolCall).count() == 0
    assert db_session.query(ReviewMessage).count() == 0


def test_展示编号查询与采纳关系解析(db_session):
    session, current, other = _seed(db_session)
    assert viewpoints_route.get_viewpoint_by_display_id(33, db_session).id == 6
    assert viewpoints_route.get_viewpoint_by_display_id(33, db_session).title_zh == "其他观点标题"

    from app.ai.schemas import AnalysisRelation

    outcome = apply_review_decision(
        db_session,
        session,
        decision_type="accept",
        final_content=current.content,
        title_zh="当前标题",
        title_en="Current",
        layer="fa",
        relations=[AnalysisRelation(display_id=33, type="similar")],
    )
    relations = db_session.query(ViewpointRelation).filter_by(
        from_viewpoint_id=outcome.viewpoint.id
    ).all()
    assert relations[-1].to_viewpoint_id == other.id == 6


def test_SSE包含工具进度与最终会话快照(db_session):
    session, _, _ = _seed(db_session)
    provider = QueryProvider()
    response = review_route._sse_response(
        db_session,
        session,
        lambda emit: review_route._post_message_impl(
            session.id,
            ReviewMessageCreate(content="请解释关联观点"),
            db_session,
            provider,
            None,
            emit,
        ),
        "pair",
    )

    async def collect():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return "".join(chunks)

    body = asyncio.run(collect())
    assert body.count("event: tool") == 4
    assert '"status": "running"' in body
    assert '"target": "current"' in body
    assert '"target": "33"' in body
    assert "event: done" in body
    done = json.loads(body.split("event: done\ndata: ", 1)[1].split("\n\n", 1)[0])
    assert len(done["session"]["tool_calls"]) == 2
    assert done["pair"]["assistant_message"]["content"] == "已核实 #33 的正文与来源。"


def test_旧分析在会话响应中统一为展示编号(db_session):
    session, _, _ = _seed(db_session)
    session.analysis_json = json.dumps(
        {
            "adoption_reason": "值得采纳",
            "strongest_counterargument": "最强反对",
            "layer": "法",
            "tags": {},
            "relations": [
                {"viewpoint_id": 6, "type": "similar"},
                {"viewpoint_id": 42, "type": "conflict"},
            ],
        },
        ensure_ascii=False,
    )
    db_session.commit()
    out = review_route._session_out(db_session, session)
    assert out.analysis["relations"] == [
        {"display_id": 33, "type": "similar"},
        {"display_id": 42, "type": "conflict"},
    ]


def test_首问撤销同时删除turn0工具记录(db_session):
    session, _, _ = _seed(db_session)
    assistant = ReviewMessage(
        session_id=session.id,
        role="assistant",
        content="首问",
        phase="polish",
    )
    db_session.add(assistant)
    db_session.flush()
    db_session.add(
        ReviewToolCall(
            call_id="opening-call",
            session_id=session.id,
            turn_id=0,
            phase="polish",
            tool="get_current_viewpoint",
            target="current",
            status="completed",
            result_json="{}",
        )
    )
    db_session.commit()
    undo_last_message(db_session, session)
    assert db_session.query(ReviewToolCall).count() == 0
    assert db_session.query(ReviewMessage).count() == 0
