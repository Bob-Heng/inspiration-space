"""打磨会话领域逻辑单元测试：开会话（观点驱动）、已入库拒开、断点续聊、会话状态机。"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.review import ReviewError, open_review_session
from app.domain.viewpoint_state import (
    InvalidTransitionError,
    check_session_transition,
)
from app.models import Base, ReviewSession, Viewpoint


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


def _add_viewpoint(db, content="测试观点", status="draft", **kwargs) -> Viewpoint:
    viewpoint = Viewpoint(content=content, status=status, **kwargs)
    db.add(viewpoint)
    db.commit()
    return viewpoint


class TestOpenReviewSession:
    def test_开会话默认提炼阶段(self, db_session):
        viewpoint = _add_viewpoint(db_session)
        session = open_review_session(db_session, viewpoint)
        assert session.status == "active"
        assert session.phase == "distill"
        assert session.viewpoint_id == viewpoint.id

    def test_已入库观点不得再开会话(self, db_session):
        viewpoint = _add_viewpoint(db_session, status="accepted")
        with pytest.raises(ReviewError, match="已入库的观点不得再开会话"):
            open_review_session(db_session, viewpoint)
        assert db_session.query(ReviewSession).all() == []

    def test_同一观点重复开返回进行中的会话(self, db_session):
        viewpoint = _add_viewpoint(db_session)
        first = open_review_session(db_session, viewpoint)
        second = open_review_session(db_session, viewpoint)
        assert second.id == first.id
        sessions = db_session.query(ReviewSession).all()
        assert len(sessions) == 1

    def test_挂起会话被恢复而非新建(self, db_session):
        viewpoint = _add_viewpoint(db_session)
        session = open_review_session(db_session, viewpoint)
        session.status = "paused"
        db_session.commit()

        resumed = open_review_session(db_session, viewpoint)
        assert resumed.id == session.id
        assert resumed.status == "active"

    def test_开新会话时其他观点的active会话被挂起(self, db_session):
        first_viewpoint = _add_viewpoint(db_session, "观点一")
        second_viewpoint = _add_viewpoint(db_session, "观点二")
        first = open_review_session(db_session, first_viewpoint)

        second = open_review_session(db_session, second_viewpoint)

        assert first.status == "paused"
        assert second.status == "active"
        active = db_session.query(ReviewSession).filter_by(status="active").all()
        assert [s.id for s in active] == [second.id]

    def test_切回旧观点恢复其会话并挂起当前会话(self, db_session):
        first_viewpoint = _add_viewpoint(db_session, "观点一")
        second_viewpoint = _add_viewpoint(db_session, "观点二")
        first = open_review_session(db_session, first_viewpoint)
        second = open_review_session(db_session, second_viewpoint)

        resumed = open_review_session(db_session, first_viewpoint)

        assert resumed.id == first.id
        assert resumed.status == "active"
        assert second.status == "paused"


class TestSessionStateMachine:
    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            ("active", "paused"),
            ("active", "completed"),
            ("paused", "active"),
            ("completed", "active"),  # 集思录撤回后重开会话
        ],
    )
    def test_合法转换通过(self, from_status, to_status):
        check_session_transition(from_status, to_status)

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            ("completed", "paused"),
            ("paused", "completed"),
            ("active", "active"),
            ("pending", "active"),
        ],
    )
    def test_非法转换被拒绝(self, from_status, to_status):
        with pytest.raises(InvalidTransitionError):
            check_session_transition(from_status, to_status)
