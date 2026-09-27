"""审议会话领域逻辑单元测试（TASK-010）：开会话、断点续聊、完结拒绝。"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.review import ReviewError, open_review_session
from app.domain.viewpoint_state import (
    InvalidTransitionError,
    check_session_transition,
)
from app.models import Base, Inspiration, ReviewSession


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


def _add_inspiration(db, status="pending") -> Inspiration:
    inspiration = Inspiration(content="测试灵感", status=status)
    db.add(inspiration)
    db.commit()
    return inspiration


class TestOpenReviewSession:
    def test_对待审灵感开会话(self, db_session):
        inspiration = _add_inspiration(db_session)
        session = open_review_session(db_session, inspiration)
        assert session.status == "active"
        assert session.inspiration_id == inspiration.id
        assert inspiration.status == "in_review"

    def test_同一灵感重复开返回进行中的会话(self, db_session):
        inspiration = _add_inspiration(db_session)
        first = open_review_session(db_session, inspiration)
        second = open_review_session(db_session, inspiration)
        assert second.id == first.id
        sessions = db_session.query(ReviewSession).all()
        assert len(sessions) == 1

    def test_挂起会话被恢复而非新建(self, db_session):
        inspiration = _add_inspiration(db_session)
        session = open_review_session(db_session, inspiration)
        session.status = "paused"
        inspiration.status = "pending"
        db_session.commit()

        resumed = open_review_session(db_session, inspiration)
        assert resumed.id == session.id
        assert resumed.status == "active"
        assert inspiration.status == "in_review"

    @pytest.mark.parametrize("final_status", ["reviewed", "rejected"])
    def test_已完结灵感拒绝再开会话(self, db_session, final_status):
        inspiration = _add_inspiration(db_session, status=final_status)
        with pytest.raises(ReviewError, match="已审议完结"):
            open_review_session(db_session, inspiration)


class TestSessionStateMachine:
    @pytest.mark.parametrize(
        "from_status,to_status",
        [("active", "paused"), ("active", "completed"), ("paused", "active")],
    )
    def test_合法转换通过(self, from_status, to_status):
        check_session_transition(from_status, to_status)

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            ("completed", "active"),
            ("completed", "paused"),
            ("paused", "completed"),
            ("active", "active"),
            ("pending", "active"),
        ],
    )
    def test_非法转换被拒绝(self, from_status, to_status):
        with pytest.raises(InvalidTransitionError):
            check_session_transition(from_status, to_status)
