"""AI 标题建议端点测试：以正文生成双语标题；AI 不可用时 503 双语错误。

不起 HTTP 层（测试环境无 httpx），直接以协程方式调用路由函数。
"""

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.routers import ai_status as ai_status_route
from app.schemas import TitleSuggestionRequest


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


class TestTitleSuggestion:
    def test_返回双语标题(self, db_session, monkeypatch):
        async def _titles_stub(db, content):
            assert content == "观点正文"
            return {"title_zh": "建议标题", "title_en": "Suggested Title"}

        monkeypatch.setattr(ai_status_route, "make_titles", _titles_stub)

        out = asyncio.run(
            ai_status_route.title_suggestion(
                TitleSuggestionRequest(content="观点正文"), db_session
            )
        )

        assert out.title_zh == "建议标题"
        assert out.title_en == "Suggested Title"

    def test_AI不可用时503双语错误(self, db_session, monkeypatch):
        async def _titles_fail(db, content):
            return {"title_zh": None, "title_en": None}

        monkeypatch.setattr(ai_status_route, "make_titles", _titles_fail)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                ai_status_route.title_suggestion(
                    TitleSuggestionRequest(content="观点正文"), db_session
                )
            )
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["code"] == "ai_unavailable"
        assert "大模型未接入" in exc_info.value.detail["zh"]
        assert exc_info.value.detail["en"]
