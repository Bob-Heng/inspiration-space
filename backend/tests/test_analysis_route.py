"""打磨分析路由测试：分析对象为观点正文，结果持久化到该观点的 active 会话；
reset=1 先清空打磨阶段消息（提炼消息保留）。

不起 HTTP 层（测试环境无 httpx），直接以协程方式调用路由函数。
"""

import asyncio
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai import LLMProvider, Message
from app.domain.review import open_review_session
from app.models import Base, ReviewMessage, Viewpoint
from app.routers import analysis as analysis_route

ANALYSIS_JSON = json.dumps(
    {
        "adoption_reason": "值得采纳",
        "strongest_counterargument": "最强反对理由",
        "layer": "法",
        "tags": {"domain": "文化", "circle": None, "discipline": "经济学", "scene": None},
        "relations": [],
    },
    ensure_ascii=False,
)


class FakeProvider(LLMProvider):
    provider_name = "fake"
    model = "fake-model"

    async def generate(self, messages: list[Message]) -> str:
        return ANALYSIS_JSON


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
    """英译走真实 Provider 解析，置空以保持测试与网关环境无关。"""
    async def _stub(db, analysis_json):
        return None

    monkeypatch.setattr(analysis_route, "bilingual_analysis", _stub)


def _analyze(db, viewpoint_id: int, reset: bool = False):
    return asyncio.run(
        analysis_route.analyze_viewpoint(
            viewpoint_id, reset=reset, db=db, provider=FakeProvider()
        )
    )


def _add_viewpoint(db, content="测试观点", status="draft", **kwargs) -> Viewpoint:
    viewpoint = Viewpoint(content=content, status=status, **kwargs)
    db.add(viewpoint)
    db.commit()
    return viewpoint


class TestAnalyzeViewpoint:
    def test_分析落库到关联观点的会话(self, db_session):
        viewpoint = _add_viewpoint(db_session)
        session = open_review_session(db_session, viewpoint)

        result = _analyze(db_session, viewpoint.id)

        assert result.adoption_reason == "值得采纳"
        assert session.analysis_json is not None

    def test_重新生成分析覆盖会话分析(self, db_session):
        viewpoint = _add_viewpoint(db_session)
        session = open_review_session(db_session, viewpoint)

        _analyze(db_session, viewpoint.id)
        first = session.analysis_json
        _analyze(db_session, viewpoint.id)

        assert session.analysis_json == first  # 同一 fake 输出，重复生成不报错

    def test_无活动会话时分析不落库(self, db_session):
        viewpoint = _add_viewpoint(db_session)

        result = _analyze(db_session, viewpoint.id)

        assert result.adoption_reason == "值得采纳"

    def test_观点不存在返回404(self, db_session):
        with pytest.raises(HTTPException) as exc_info:
            _analyze(db_session, 99999)
        assert exc_info.value.status_code == 404

    def test_reset先清空打磨消息再生成(self, db_session):
        viewpoint = _add_viewpoint(db_session)
        session = open_review_session(db_session, viewpoint)
        session.phase = "polish"
        db_session.add_all(
            [
                ReviewMessage(
                    session_id=session.id, role="user", content="提炼讨论", phase="distill"
                ),
                ReviewMessage(
                    session_id=session.id, role="assistant", content="提炼回复", phase="distill"
                ),
                ReviewMessage(
                    session_id=session.id, role="user", content="打磨讨论", phase="polish"
                ),
                ReviewMessage(
                    session_id=session.id, role="assistant", content="打磨回复", phase="polish"
                ),
            ]
        )
        db_session.commit()

        _analyze(db_session, viewpoint.id, reset=True)

        remaining = [
            (m.role, m.phase)
            for m in db_session.query(ReviewMessage).order_by(ReviewMessage.id)
        ]
        # 打磨阶段消息清空，提炼消息保留
        assert remaining == [("user", "distill"), ("assistant", "distill")]
        assert session.analysis_json is not None

    def test_不带reset保留打磨消息(self, db_session):
        viewpoint = _add_viewpoint(db_session)
        session = open_review_session(db_session, viewpoint)
        session.phase = "polish"
        db_session.add(
            ReviewMessage(
                session_id=session.id, role="user", content="打磨讨论", phase="polish"
            )
        )
        db_session.commit()

        _analyze(db_session, viewpoint.id)

        assert db_session.query(ReviewMessage).count() == 1

    def test_观点库快照只收已采纳(self, db_session):
        _add_viewpoint(db_session, "已采纳观点标记", status="accepted")
        _add_viewpoint(db_session, "他人草稿标记")  # draft 不进快照
        viewpoint = _add_viewpoint(db_session, "待分析观点")
        open_review_session(db_session, viewpoint)

        _analyze(db_session, viewpoint.id)

        from app.models import AiCall

        call = db_session.query(AiCall).order_by(AiCall.id.desc()).first()
        assert "已采纳观点标记" in call.input_snapshot
        assert "他人草稿标记" not in call.input_snapshot
