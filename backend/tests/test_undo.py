"""消息级撤销与阶段级回退测试。

- 消息级撤销（/undo）：只删当前 phase 末条；assistant 连同其 user 提问成对删除；
  落单 user 单删；不跨阶段；无同阶段消息时不动；非 active 409；ai_calls 不留痕。
- 阶段级回退（/undo-phase）：polish→distill 清分析（含英文版）与全部打磨消息、
  提炼消息保留、观点正文不动；distill→重置清全部消息、观点正文与双语恢复灵感原文。

不起 HTTP 层（测试环境无 httpx），直接调用路由函数。
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.review import open_review_session
from app.models import AiCall, Base, Inspiration, ReviewMessage, Viewpoint
from app.routers import review as review_route


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


def _add_viewpoint(db, content="测试观点", **kwargs) -> Viewpoint:
    viewpoint = Viewpoint(content=content, status="draft", **kwargs)
    db.add(viewpoint)
    db.commit()
    return viewpoint


def _open(db, content="测试观点"):
    viewpoint = _add_viewpoint(db, content)
    return viewpoint, open_review_session(db, viewpoint)


def _msg(db, session, role, content, phase):
    message = ReviewMessage(
        session_id=session.id, role=role, content=content, phase=phase
    )
    db.add(message)
    db.commit()
    return message


def _messages(db, session):
    return [
        (m.role, m.content, m.phase)
        for m in db.query(ReviewMessage)
        .where(ReviewMessage.session_id == session.id)
        .order_by(ReviewMessage.id)
    ]


class TestUndoMessage:
    def test_assistant连同其user提问成对删除(self, db_session):
        _, session = _open(db_session)
        _msg(db_session, session, "user", "问一", "distill")
        _msg(db_session, session, "assistant", "答一", "distill")

        out = review_route.undo_message(session.id, db_session)

        assert _messages(db_session, session) == []
        assert out.messages == []

    def test_落单user消息单删(self, db_session):
        _, session = _open(db_session)
        _msg(db_session, session, "assistant", "首问", "distill")
        _msg(db_session, session, "user", "落单发言", "distill")

        review_route.undo_message(session.id, db_session)

        assert _messages(db_session, session) == [("assistant", "首问", "distill")]

    def test_连续撤销逐轮回退(self, db_session):
        _, session = _open(db_session)
        _msg(db_session, session, "user", "问一", "distill")
        _msg(db_session, session, "assistant", "答一", "distill")
        _msg(db_session, session, "user", "问二", "distill")
        _msg(db_session, session, "assistant", "答二", "distill")

        review_route.undo_message(session.id, db_session)
        assert _messages(db_session, session) == [
            ("user", "问一", "distill"),
            ("assistant", "答一", "distill"),
        ]
        review_route.undo_message(session.id, db_session)
        assert _messages(db_session, session) == []

    def test_打磨期撤销不吃提炼消息(self, db_session):
        _, session = _open(db_session)
        _msg(db_session, session, "user", "提炼讨论", "distill")
        _msg(db_session, session, "assistant", "提炼回复", "distill")
        session.phase = "polish"
        db_session.commit()

        # polish 阶段无消息：撤销不动（尤其不跨阶段吃提炼消息）
        out = review_route.undo_message(session.id, db_session)
        assert len(out.messages) == 2

        _msg(db_session, session, "user", "打磨提问", "polish")
        out = review_route.undo_message(session.id, db_session)
        assert [(m.role, m.content) for m in out.messages] == [
            ("user", "提炼讨论"),
            ("assistant", "提炼回复"),
        ]

    def test_无消息时撤销不动(self, db_session):
        _, session = _open(db_session)
        out = review_route.undo_message(session.id, db_session)
        assert out.messages == []

    def test_非进行中会话撤销被拒(self, db_session):
        _, session = _open(db_session)
        _msg(db_session, session, "user", "问", "distill")
        session.status = "paused"
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            review_route.undo_message(session.id, db_session)
        assert exc_info.value.status_code == 409
        # 消息未被删除
        assert len(_messages(db_session, session)) == 1

    def test_撤销不产生AI留痕(self, db_session):
        _, session = _open(db_session)
        _msg(db_session, session, "user", "问", "distill")
        _msg(db_session, session, "assistant", "答", "distill")

        review_route.undo_message(session.id, db_session)

        assert db_session.query(AiCall).count() == 0


class TestUndoPhase:
    def test_打磨回提炼清分析与打磨消息(self, db_session):
        viewpoint, session = _open(db_session)
        _msg(db_session, session, "user", "提炼讨论", "distill")
        _msg(db_session, session, "assistant", "提炼回复", "distill")
        session.phase = "polish"
        session.analysis_json = '{"adoption_reason": "值得采纳"}'
        session.analysis_json_en = '{"adoption_reason": "Worth adopting"}'
        db_session.commit()
        _msg(db_session, session, "user", "打磨提问", "polish")
        _msg(db_session, session, "assistant", "打磨回复", "polish")
        viewpoint.content = "打磨中改过的正文"
        db_session.commit()

        out = review_route.undo_session_phase(session.id, db_session)

        assert out.phase == "distill"
        assert out.analysis is None
        assert out.analysis_en is None
        # 打磨消息清空，提炼消息保留
        assert [(m.role, m.phase) for m in out.messages] == [
            ("user", "distill"),
            ("assistant", "distill"),
        ]
        db_session.refresh(session)
        assert session.analysis_json is None
        assert session.analysis_json_en is None
        # 观点正文不动
        db_session.refresh(viewpoint)
        assert viewpoint.content == "打磨中改过的正文"

    def test_提炼重置清消息并恢复灵感原文(self, db_session):
        inspiration = Inspiration(
            content="灵感原文",
            content_zh="灵感原文",
            content_en="Original inspiration",
            original_lang="zh",
        )
        db_session.add(inspiration)
        db_session.commit()
        viewpoint = _add_viewpoint(
            db_session,
            "被提炼改过的正文",
            source_inspiration_id=inspiration.id,
            content_zh="被提炼改过的正文",
            content_en="Distilled draft",
            original_lang="zh",
        )
        session = open_review_session(db_session, viewpoint)
        _msg(db_session, session, "user", "讨论一", "distill")
        _msg(db_session, session, "assistant", "回复一", "distill")

        out = review_route.undo_session_phase(session.id, db_session)

        assert out.phase == "distill"
        assert out.messages == []
        db_session.refresh(viewpoint)
        assert viewpoint.content == "灵感原文"
        assert viewpoint.content_zh == "灵感原文"
        assert viewpoint.content_en == "Original inspiration"
        assert viewpoint.original_lang == "zh"

    def test_提炼重置无关联灵感时正文不动(self, db_session):
        viewpoint, session = _open(db_session, content="孤儿观点正文")
        _msg(db_session, session, "user", "讨论", "distill")

        review_route.undo_session_phase(session.id, db_session)

        db_session.refresh(viewpoint)
        assert viewpoint.content == "孤儿观点正文"
        assert _messages(db_session, session) == []

    def test_非进行中会话回退被拒(self, db_session):
        _, session = _open(db_session)
        session.status = "paused"
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            review_route.undo_session_phase(session.id, db_session)
        assert exc_info.value.status_code == 409


class TestUndoFloor:
    """撤销地板：观点 is_viewpoint 为 true（录入即判定为观点、跳过提炼）
    且会话无 distill 消息时，polish → distill 回退拒绝（409 undo_floor）。"""

    def _polish_session(self, db, is_viewpoint, with_distill=False):
        viewpoint = _add_viewpoint(db, "测试观点", is_viewpoint=is_viewpoint)
        session = open_review_session(db, viewpoint)
        if with_distill:
            _msg(db, session, "user", "提炼讨论", "distill")
        session.phase = "polish"
        session.analysis_json = '{"adoption_reason": "值得采纳"}'
        db.commit()
        _msg(db, session, "user", "打磨提问", "polish")
        return viewpoint, session

    def test_跳过提炼的观点回退被拒(self, db_session):
        viewpoint, session = self._polish_session(db_session, True)

        with pytest.raises(HTTPException) as exc_info:
            review_route.undo_session_phase(session.id, db_session)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "undo_floor"
        assert exc_info.value.detail["zh"] == "该观点跳过了提炼环节，撤销到打磨开始为止"
        assert exc_info.value.detail["en"] == (
            "This viewpoint skipped distilling; nothing earlier to undo."
        )
        # 会话原样保留：阶段/分析/打磨消息均未动
        db_session.refresh(session)
        assert session.phase == "polish"
        assert session.analysis_json is not None
        assert _messages(db_session, session) == [("user", "打磨提问", "polish")]

    def test_有提炼消息仍可回退(self, db_session):
        viewpoint, session = self._polish_session(
            db_session, True, with_distill=True
        )

        out = review_route.undo_session_phase(session.id, db_session)

        assert out.phase == "distill"
        assert [(m.role, m.phase) for m in out.messages] == [("user", "distill")]

    def test_判定为非观点不受影响(self, db_session):
        viewpoint, session = self._polish_session(db_session, False)

        out = review_route.undo_session_phase(session.id, db_session)

        assert out.phase == "distill"
        assert out.messages == []

    def test_未判断NULL不受影响(self, db_session):
        viewpoint, session = self._polish_session(db_session, None)

        out = review_route.undo_session_phase(session.id, db_session)

        assert out.phase == "distill"
        assert out.messages == []

    def test_distill阶段重置不受地板影响(self, db_session):
        viewpoint = _add_viewpoint(db_session, "测试观点", is_viewpoint=True)
        session = open_review_session(db_session, viewpoint)
        _msg(db_session, session, "user", "提炼讨论", "distill")

        out = review_route.undo_session_phase(session.id, db_session)

        assert out.phase == "distill"
        assert out.messages == []
