"""打磨决策事务单元测试：仅采纳——正文/双语/标题/分层/标签/关系/决策/关会话
在一个事务内完成，任一步失败整体回滚；冲突关系不再联动任何状态。
"""

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


def _open(db, content="测试观点") -> tuple[Viewpoint, ReviewSession]:
    viewpoint = Viewpoint(content=content, status="draft")
    db.add(viewpoint)
    db.commit()
    return viewpoint, open_review_session(db, viewpoint)


def _counts(db):
    return {
        "viewpoints": len(db.scalars(select(Viewpoint)).all()),
        "relations": len(db.scalars(select(ViewpointRelation)).all()),
        "decisions": len(db.scalars(select(ReviewDecision)).all()),
    }


class TestAccept:
    def test_采纳使草稿观点入库记决策关会话(self, db_session):
        viewpoint, session = _open(db_session)
        outcome = apply_review_decision(
            db_session,
            session,
            decision_type="accept",
            final_content="  最终正文  ",
            title_zh="最终标题",
            title_en="Final Title",
            layer="法",
            tags=AnalysisTags(domain="文化", discipline="经济学"),
            reason="分析充分",
        )
        accepted = outcome.viewpoint
        assert accepted.id == session.viewpoint_id  # 采纳的是会话打磨的草稿观点
        assert accepted.content == "最终正文"  # 去空白后落库
        assert accepted.title_zh == "最终标题"
        assert accepted.title_en == "Final Title"
        assert accepted.layer == "fa"  # 中文标签归一为代码
        assert accepted.domain == "文化"
        assert accepted.discipline == "经济学"
        assert accepted.status == "accepted"  # draft -> accepted，集思录可见

        decision = outcome.decision
        assert decision.decision_type == "accept"
        assert decision.final_content == "最终正文"
        assert decision.reason == "分析充分"

        assert session.status == "completed"
        assert session.ended_at is not None

    def test_正文变化时写入路由层重新双语化的结果(self, db_session):
        viewpoint, session = _open(db_session)
        outcome = apply_review_decision(
            db_session,
            session,
            bilingual={
                "content_zh": "最终正文",
                "content_en": "Final content",
                "original_lang": "zh",
            },
            decision_type="accept",
            final_content="最终正文",
        )
        assert outcome.viewpoint.content_zh == "最终正文"
        assert outcome.viewpoint.content_en == "Final content"
        assert outcome.viewpoint.original_lang == "zh"

    def test_采纳必须给出最终正文(self, db_session):
        _, session = _open(db_session)
        with pytest.raises(ReviewError, match="最终正文"):
            apply_review_decision(db_session, session, decision_type="accept")
        with pytest.raises(ReviewError, match="最终正文"):
            apply_review_decision(
                db_session, session, decision_type="accept", final_content="   "
            )
        # 草稿观点仍在（保持 draft），无关系与决策落库
        assert _counts(db_session) == {"viewpoints": 1, "relations": 0, "decisions": 0}
        assert db_session.get(Viewpoint, session.viewpoint_id).status == "draft"

    def test_非采纳决策类型被拒绝(self, db_session):
        _, session = _open(db_session)
        for decision_type in ("accept_modified", "reject", "defer"):
            with pytest.raises(ReviewError, match="非法决策类型"):
                apply_review_decision(
                    db_session, session, decision_type=decision_type,
                    final_content="正文",
                )
        assert _counts(db_session)["decisions"] == 0
        assert session.status == "active"

    def test_非法标签被拒绝且不落库(self, db_session):
        _, session = _open(db_session)
        with pytest.raises(ReviewError, match="不在词表内"):
            apply_review_decision(
                db_session,
                session,
                decision_type="accept",
                final_content="正文",
                tags=AnalysisTags(domain="军事"),
            )
        assert db_session.get(Viewpoint, session.viewpoint_id).status == "draft"
        assert _counts(db_session)["decisions"] == 0

    def test_已完结会话不能重复决策(self, db_session):
        _, session = _open(db_session)
        apply_review_decision(
            db_session, session, decision_type="accept", final_content="正文"
        )
        with pytest.raises(ReviewError, match="不在进行中"):
            apply_review_decision(
                db_session, session, decision_type="accept", final_content="正文"
            )


class TestConflictRelation:
    def test_冲突关系只记关系行不联动状态(self, db_session):
        existing = Viewpoint(content="已有观点", status="accepted")
        db_session.add(existing)
        db_session.commit()
        _, session = _open(db_session)

        outcome = apply_review_decision(
            db_session,
            session,
            decision_type="accept",
            final_content="正文",
            relations=[AnalysisRelation(viewpoint_id=existing.id, type="conflict")],
        )
        # 悬置已删除：冲突不再联动双方状态
        assert outcome.viewpoint.status == "accepted"
        assert existing.status == "accepted"
        relations = db_session.scalars(select(ViewpointRelation)).all()
        assert len(relations) == 1
        assert relations[0].from_viewpoint_id == outcome.viewpoint.id
        assert relations[0].to_viewpoint_id == existing.id
        assert relations[0].relation_type == "conflict"

    def test_相近关系不影响状态(self, db_session):
        existing = Viewpoint(content="已有观点", status="accepted")
        db_session.add(existing)
        db_session.commit()
        _, session = _open(db_session)

        outcome = apply_review_decision(
            db_session,
            session,
            decision_type="accept",
            final_content="正文",
            relations=[AnalysisRelation(viewpoint_id=existing.id, type="similar")],
        )
        assert outcome.viewpoint.status == "accepted"
        assert existing.status == "accepted"


class TestTransactionRollback:
    def test_关系目标不存在则整体回滚(self, db_session):
        _, session = _open(db_session)
        with pytest.raises(ReviewError, match="不存在"):
            apply_review_decision(
                db_session,
                session,
                decision_type="accept",
                final_content="正文",
                relations=[AnalysisRelation(viewpoint_id=99999, type="similar")],
            )
        # 无部分写入：关系、决策都不落库，草稿观点保持 draft，会话保持 active
        assert _counts(db_session) == {"viewpoints": 1, "relations": 0, "decisions": 0}
        assert db_session.get(Viewpoint, session.viewpoint_id).status == "draft"
        assert session.status == "active"

    def test_提交中途失败则整体回滚(self, db_session, monkeypatch):
        _, session = _open(db_session)

        def _broken_commit(self):
            raise RuntimeError("模拟提交时数据库故障")

        monkeypatch.setattr(type(db_session), "commit", _broken_commit)
        with pytest.raises(RuntimeError, match="数据库故障"):
            apply_review_decision(
                db_session,
                session,
                decision_type="accept",
                final_content="正文",
                layer="dao",
                relations=[],
            )
        monkeypatch.undo()

        assert _counts(db_session) == {"viewpoints": 1, "relations": 0, "decisions": 0}
        assert session.status == "active"
        assert db_session.get(Viewpoint, session.viewpoint_id).status == "draft"
        # 回滚后同一会话可重新决策
        outcome = apply_review_decision(
            db_session, session, decision_type="accept", final_content="正文"
        )
        assert outcome.viewpoint.status == "accepted"
        assert _counts(db_session)["decisions"] == 1
