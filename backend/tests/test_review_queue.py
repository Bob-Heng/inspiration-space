"""他山坊队列与开会话端点测试：队列形状/排序、viewpoint_id 开会话、
已入库观点拒开（409）、会话输出携带关联观点（不再有 inspiration 字段）。

不起 HTTP 层（测试环境无 httpx），直接调用路由函数。
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Inspiration, Viewpoint
from app.routers import review as review_route
from app.schemas import ReviewSessionCreate


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


class TestReviewQueue:
    def test_队列只收草稿按编号升序(self, db_session):
        first = _add_viewpoint(db_session, "草稿一")
        _add_viewpoint(db_session, "已采纳", status="accepted")
        second = _add_viewpoint(db_session, "草稿二")

        queue = review_route.get_review_queue(db_session)

        assert [item.id for item in queue] == [first.id, second.id]

    def test_队列条目形状与标题取观点自身标题(self, db_session):
        inspiration = Inspiration(
            content="灵感原文",
            title_zh="工作名",
            title_en="Working Title",
            source_date=None,
        )
        db_session.add(inspiration)
        db_session.commit()
        viewpoint = _add_viewpoint(
            db_session,
            "草稿观点",
            source_inspiration_id=inspiration.id,
            content_zh="草稿观点",
            content_en="Draft viewpoint",
            original_lang="zh",
            title_zh="观点标题",
            title_en="Viewpoint title",
        )
        orphan = _add_viewpoint(db_session, "无来源观点")  # 无标题：可空

        queue = review_route.get_review_queue(db_session)
        by_id = {item.id: item for item in queue}

        item = by_id[viewpoint.id]
        assert item.content == "草稿观点"
        assert item.content_zh == "草稿观点"
        assert item.content_en == "Draft viewpoint"
        assert item.original_lang == "zh"
        assert item.inspiration_id == inspiration.id
        assert item.title_zh == "观点标题"
        assert item.title_en == "Viewpoint title"
        assert item.source_date is None

        orphan_item = by_id[orphan.id]
        assert orphan_item.inspiration_id is None
        assert orphan_item.title_zh is None
        assert orphan_item.title_en is None

    def test_空队列(self, db_session):
        assert review_route.get_review_queue(db_session) == []


class TestReviewQueuePhase:
    """队列条目的 phase：该观点最近一条非 completed 会话（active/paused）的阶段。"""

    def _open_session(self, db, viewpoint, phase="distill", status="active"):
        from app.models import ReviewSession

        session = ReviewSession(
            viewpoint_id=viewpoint.id, status=status, phase=phase
        )
        db.add(session)
        db.commit()
        return session

    def test_无会话为distill(self, db_session):
        viewpoint = _add_viewpoint(db_session, "无会话草稿")

        queue = review_route.get_review_queue(db_session)

        assert queue[0].phase == "distill"

    def test_distill会话(self, db_session):
        viewpoint = _add_viewpoint(db_session, "提炼中草稿")
        self._open_session(db_session, viewpoint, phase="distill")

        queue = review_route.get_review_queue(db_session)

        assert queue[0].phase == "distill"

    def test_polish会话(self, db_session):
        viewpoint = _add_viewpoint(db_session, "打磨中草稿")
        self._open_session(db_session, viewpoint, phase="polish")

        queue = review_route.get_review_queue(db_session)

        assert queue[0].phase == "polish"

    def test_挂起会话同样计入(self, db_session):
        viewpoint = _add_viewpoint(db_session, "挂起草稿")
        self._open_session(db_session, viewpoint, phase="polish", status="paused")

        queue = review_route.get_review_queue(db_session)

        assert queue[0].phase == "polish"

    def test_completed会话忽略(self, db_session):
        viewpoint = _add_viewpoint(db_session, "已完成草稿")
        self._open_session(db_session, viewpoint, phase="polish", status="completed")

        queue = review_route.get_review_queue(db_session)

        assert queue[0].phase == "distill"

    def test_多条会话取最近一条(self, db_session):
        viewpoint = _add_viewpoint(db_session, "多会话草稿")
        self._open_session(db_session, viewpoint, phase="polish", status="paused")
        self._open_session(db_session, viewpoint, phase="distill", status="active")

        queue = review_route.get_review_queue(db_session)

        assert queue[0].phase == "distill"


class TestCreateSession:
    def test_按观点开会话且输出携带观点(self, db_session):
        viewpoint = _add_viewpoint(db_session, "草稿观点")

        out = review_route.create_session(
            ReviewSessionCreate(viewpoint_id=viewpoint.id), db_session
        )

        assert out.viewpoint_id == viewpoint.id
        assert out.status == "active"
        assert out.phase == "distill"
        assert out.viewpoint.id == viewpoint.id
        assert out.viewpoint.content == "草稿观点"
        assert out.viewpoint.status == "draft"
        assert out.messages == []
        assert out.analysis is None
        assert not hasattr(out, "inspiration")  # 会话输出不再携带灵感字段

    def test_观点不存在返回404(self, db_session):
        with pytest.raises(HTTPException) as exc_info:
            review_route.create_session(
                ReviewSessionCreate(viewpoint_id=99999), db_session
            )
        assert exc_info.value.status_code == 404

    def test_已入库观点拒开(self, db_session):
        viewpoint = _add_viewpoint(db_session, status="accepted")

        with pytest.raises(HTTPException) as exc_info:
            review_route.create_session(
                ReviewSessionCreate(viewpoint_id=viewpoint.id), db_session
            )
        assert exc_info.value.status_code == 409
        assert "已入库的观点不得再开会话" in exc_info.value.detail["zh"]

    def test_重复开返回进行中会话(self, db_session):
        viewpoint = _add_viewpoint(db_session)
        first = review_route.create_session(
            ReviewSessionCreate(viewpoint_id=viewpoint.id), db_session
        )
        second = review_route.create_session(
            ReviewSessionCreate(viewpoint_id=viewpoint.id), db_session
        )
        assert second.id == first.id
