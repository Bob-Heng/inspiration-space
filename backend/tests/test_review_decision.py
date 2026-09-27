"""审议决策事务单元测试（TASK-011）：采纳/修改后采纳/否定/暂缓与整体回滚。"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.schemas import AnalysisRelation, AnalysisTags
from app.domain.review import (
    ReviewError,
    apply_review_decision,
    open_review_session,
)
from app.models import (
    Base,
    Inspiration,
    ReviewDecision,
    ReviewSession,
    Viewpoint,
    ViewpointRelation,
)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


def _open(db, content="测试灵感") -> tuple[Inspiration, ReviewSession]:
    inspiration = Inspiration(content=content, status="pending")
    db.add(inspiration)
    db.commit()
    return inspiration, open_review_session(db, inspiration)


def _counts(db):
    return {
        "viewpoints": len(db.scalars(select(Viewpoint)).all()),
        "relations": len(db.scalars(select(ViewpointRelation)).all()),
        "decisions": len(db.scalars(select(ReviewDecision)).all()),
    }


class TestAccept:
    def test_采纳建观点记决策关会话灵感出队(self, db_session):
        inspiration, session = _open(db_session)
        outcome = apply_review_decision(
            db_session,
            session,
            decision_type="accept",
            layer="法",
            tags=AnalysisTags(domain="文化", discipline="经济学"),
            reason="分析充分",
        )
        viewpoint = outcome.viewpoint
        assert viewpoint.content == inspiration.content  # 未改正文取灵感原文
        assert viewpoint.layer == "fa"  # 中文标签归一为代码
        assert viewpoint.domain == "文化"
        assert viewpoint.discipline == "经济学"
        assert viewpoint.status == "accepted"
        assert viewpoint.source_inspiration_id == inspiration.id

        decision = outcome.decision
        assert decision.decision_type == "accept"
        assert decision.final_content == inspiration.content
        assert decision.reason == "分析充分"

        assert session.status == "completed"
        assert session.viewpoint_id == viewpoint.id
        assert session.ended_at is not None
        assert inspiration.status == "reviewed"

    def test_修改后采纳取用户确认正文(self, db_session):
        inspiration, session = _open(db_session)
        outcome = apply_review_decision(
            db_session,
            session,
            decision_type="accept_modified",
            final_content="  修改后的最终正文  ",
        )
        assert outcome.viewpoint.content == "修改后的最终正文"
        assert outcome.decision.final_content == "修改后的最终正文"
        assert inspiration.content == "测试灵感"  # 灵感原文留档不改

    def test_修改后采纳缺正文被拒绝(self, db_session):
        _, session = _open(db_session)
        with pytest.raises(ReviewError, match="最终正文"):
            apply_review_decision(db_session, session, decision_type="accept_modified")
        assert _counts(db_session) == {"viewpoints": 0, "relations": 0, "decisions": 0}

    def test_非法标签被拒绝且不落库(self, db_session):
        _, session = _open(db_session)
        with pytest.raises(ReviewError, match="不在词表内"):
            apply_review_decision(
                db_session,
                session,
                decision_type="accept",
                tags=AnalysisTags(domain="军事"),
            )
        assert _counts(db_session)["viewpoints"] == 0


class TestConflictRelation:
    def test_冲突双方悬置并互记编号(self, db_session):
        existing = Viewpoint(content="已有观点", status="accepted")
        db_session.add(existing)
        db_session.commit()
        _, session = _open(db_session)

        outcome = apply_review_decision(
            db_session,
            session,
            decision_type="accept",
            relations=[AnalysisRelation(viewpoint_id=existing.id, type="conflict")],
        )
        assert outcome.viewpoint.status == "suspended"
        assert existing.status == "suspended"
        relations = db_session.scalars(select(ViewpointRelation)).all()
        assert len(relations) == 1
        assert relations[0].from_viewpoint_id == outcome.viewpoint.id
        assert relations[0].to_viewpoint_id == existing.id
        assert relations[0].relation_type == "conflict"

    def test_相近关系不触发悬置(self, db_session):
        existing = Viewpoint(content="已有观点", status="accepted")
        db_session.add(existing)
        db_session.commit()
        _, session = _open(db_session)

        outcome = apply_review_decision(
            db_session,
            session,
            decision_type="accept",
            relations=[AnalysisRelation(viewpoint_id=existing.id, type="similar")],
        )
        assert outcome.viewpoint.status == "accepted"
        assert existing.status == "accepted"

    def test_与被否定观点建关系被拒绝(self, db_session):
        existing = Viewpoint(content="已否定观点", status="rejected")
        db_session.add(existing)
        db_session.commit()
        _, session = _open(db_session)
        with pytest.raises(ReviewError, match="被否定"):
            apply_review_decision(
                db_session,
                session,
                decision_type="accept",
                relations=[AnalysisRelation(viewpoint_id=existing.id, type="similar")],
            )


class TestRejectAndDefer:
    def test_否定记决策灵感出队不建观点(self, db_session):
        inspiration, session = _open(db_session)
        outcome = apply_review_decision(
            db_session, session, decision_type="reject", reason="与既有认知矛盾"
        )
        assert outcome.viewpoint is None
        assert outcome.decision.decision_type == "reject"
        assert outcome.decision.reason == "与既有认知矛盾"
        assert session.status == "completed"
        assert inspiration.status == "rejected"
        assert _counts(db_session)["viewpoints"] == 0

    def test_否定缺理由被拒绝(self, db_session):
        _, session = _open(db_session)
        with pytest.raises(ReviewError, match="理由"):
            apply_review_decision(db_session, session, decision_type="reject", reason="  ")

    def test_暂缓不产生任何终态(self, db_session):
        inspiration, session = _open(db_session)
        outcome = apply_review_decision(db_session, session, decision_type="defer")
        assert outcome.decision is None
        assert outcome.viewpoint is None
        assert session.status == "paused"
        assert inspiration.status == "pending"
        assert _counts(db_session) == {"viewpoints": 0, "relations": 0, "decisions": 0}

    def test_已完结会话不能重复决策(self, db_session):
        _, session = _open(db_session)
        apply_review_decision(db_session, session, decision_type="defer")
        with pytest.raises(ReviewError, match="不在进行中"):
            apply_review_decision(db_session, session, decision_type="accept")


class TestTransactionRollback:
    def test_关系目标不存在则整体回滚(self, db_session):
        inspiration, session = _open(db_session)
        with pytest.raises(ReviewError, match="不存在"):
            apply_review_decision(
                db_session,
                session,
                decision_type="accept",
                relations=[AnalysisRelation(viewpoint_id=99999, type="similar")],
            )
        # 无部分写入：观点、关系、决策都不落库，会话与灵感保持原状态
        assert _counts(db_session) == {"viewpoints": 0, "relations": 0, "decisions": 0}
        assert session.status == "active"
        assert inspiration.status == "in_review"

    def test_提交中途失败则整体回滚(self, db_session, monkeypatch):
        inspiration, session = _open(db_session)

        def _broken_commit(self):
            raise RuntimeError("模拟提交时数据库故障")

        monkeypatch.setattr(type(db_session), "commit", _broken_commit)
        with pytest.raises(RuntimeError, match="数据库故障"):
            apply_review_decision(
                db_session,
                session,
                decision_type="accept",
                layer="dao",
                relations=[],
            )
        monkeypatch.undo()

        assert _counts(db_session) == {"viewpoints": 0, "relations": 0, "decisions": 0}
        assert session.status == "active"
        assert inspiration.status == "in_review"
        # 回滚后同一会话可重新决策
        outcome = apply_review_decision(db_session, session, decision_type="accept")
        assert outcome.viewpoint.id is not None
        assert _counts(db_session)["viewpoints"] == 1
