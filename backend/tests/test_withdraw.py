"""集思录撤回测试：仅 accepted 可撤回；状态回 draft、最近 completed 会话重开、
该会话的采纳决策行作废删除；草稿观点重新出现在他山坊队列。

不起 HTTP 层（测试环境无 httpx），直接调用路由函数与领域函数。
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.review import apply_review_decision, open_review_session
from app.models import Base, ReviewDecision, ReviewMessage, ReviewSession, Viewpoint
from app.routers import viewpoints as viewpoints_route
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


def _accepted_with_session(db, content="打磨完成的观点"):
    """构造一条经采纳入库的观点：completed 会话（polish 阶段、含分析与消息、含决策行）。"""
    viewpoint = Viewpoint(content=content, status="draft")
    db.add(viewpoint)
    db.commit()
    session = open_review_session(db, viewpoint)
    session.phase = "polish"
    session.analysis_json = '{"adoption_reason": "值得采纳"}'
    session.analysis_json_en = '{"adoption_reason": "Worth adopting"}'
    db.add_all(
        [
            ReviewMessage(session_id=session.id, role="user", content="提炼讨论", phase="distill"),
            ReviewMessage(session_id=session.id, role="user", content="打磨讨论", phase="polish"),
            ReviewMessage(session_id=session.id, role="assistant", content="打磨回复", phase="polish"),
        ]
    )
    db.commit()
    apply_review_decision(
        db, session, decision_type="accept", final_content=content,
        title_zh="标题", title_en="Title",
    )
    return viewpoint, session


class TestWithdraw:
    def test_撤回全链路(self, db_session):
        viewpoint, session = _accepted_with_session(db_session)
        assert viewpoint.status == "accepted"
        assert session.status == "completed"

        out = viewpoints_route.withdraw(viewpoint.id, db_session)

        # 状态回 draft，重新出现在他山坊队列
        assert out.status == "draft"
        db_session.refresh(viewpoint)
        assert viewpoint.status == "draft"
        queue = review_route.get_review_queue(db_session)
        assert [item.id for item in queue] == [viewpoint.id]

        # 最近一条 completed 会话重开：phase 保持 polish，分析与消息原样保留
        db_session.refresh(session)
        assert session.status == "active"
        assert session.phase == "polish"
        assert session.analysis_json == '{"adoption_reason": "值得采纳"}'
        assert session.analysis_json_en == '{"adoption_reason": "Worth adopting"}'
        assert session.ended_at is None
        messages = db_session.scalars(
            select(ReviewMessage).where(ReviewMessage.session_id == session.id)
        ).all()
        assert len(messages) == 3

        # 采纳决策行随撤回作废删除
        decisions = db_session.scalars(select(ReviewDecision)).all()
        assert decisions == []

        # 重开的会话可直接续聊（get_active_session 恢复）
        active = review_route.get_active_session(db_session)
        assert active.id == session.id
        assert active.viewpoint.id == viewpoint.id

    def test_草稿观点不可撤回(self, db_session):
        viewpoint = Viewpoint(content="草稿", status="draft")
        db_session.add(viewpoint)
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            viewpoints_route.withdraw(viewpoint.id, db_session)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "withdraw_conflict"
        assert viewpoint.status == "draft"

    def test_无completed会话时只回退状态(self, db_session):
        viewpoint = Viewpoint(content="无会话观点", status="accepted")
        db_session.add(viewpoint)
        db_session.commit()

        out = viewpoints_route.withdraw(viewpoint.id, db_session)

        assert out.status == "draft"
        assert db_session.scalars(select(ReviewSession)).all() == []

    def test_撤回重开会话时其他active会话被挂起(self, db_session):
        viewpoint, session = _accepted_with_session(db_session)
        other = Viewpoint(content="他山坊另一草稿", status="draft")
        db_session.add(other)
        db_session.commit()
        other_session = open_review_session(db_session, other)
        assert other_session.status == "active"

        viewpoints_route.withdraw(viewpoint.id, db_session)

        db_session.refresh(session)
        db_session.refresh(other_session)
        assert session.status == "active"
        assert other_session.status == "paused"
