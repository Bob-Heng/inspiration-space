"""观点关系/合并/拆分/状态变更单元测试（TASK-014）。"""

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.viewpoints import (
    ViewpointOpError,
    change_viewpoint_status,
    create_relation,
    delete_relation,
    list_events,
    list_relations,
    merge_viewpoints,
    split_viewpoint,
)
from app.models import Base, Viewpoint, ViewpointEvent, ViewpointRelation


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


def _add(db, content="观点", status="accepted", **kwargs) -> Viewpoint:
    viewpoint = Viewpoint(content=content, status=status, **kwargs)
    db.add(viewpoint)
    db.commit()
    return viewpoint


def _events(db, viewpoint_id, event_type=None):
    events = list_events(db, viewpoint_id)
    if event_type is not None:
        events = [e for e in events if e.event_type == event_type]
    return events


class TestCreateRelation:
    def test_相近关系不影响状态(self, db_session):
        a = _add(db_session, "观点甲")
        b = _add(db_session, "观点乙")
        relation = create_relation(db_session, a, b.id, "similar")
        assert relation.relation_type == "similar"
        assert a.status == "accepted" and b.status == "accepted"
        # 双向可查
        assert [cp.id for _, cp in list_relations(db_session, a.id)] == [b.id]
        assert [cp.id for _, cp in list_relations(db_session, b.id)] == [a.id]

    def test_冲突双方转悬置互记编号并留痕(self, db_session):
        a = _add(db_session, "观点甲")
        b = _add(db_session, "观点乙")
        create_relation(db_session, a, b.id, "conflict")
        assert a.status == "suspended" and b.status == "suspended"
        relations_a = list_relations(db_session, a.id)
        relations_b = list_relations(db_session, b.id)
        assert len(relations_a) == 1 and len(relations_b) == 1
        assert relations_a[0][0].id == relations_b[0][0].id  # 同一关系行互记双方
        for viewpoint, other in ((a, b), (b, a)):
            events = _events(db_session, viewpoint.id, "conflict_suspend")
            assert len(events) == 1
            assert events[0].from_status == "accepted"
            assert events[0].to_status == "suspended"
            assert f'"conflict_with": {other.id}' in events[0].detail

    def test_已悬置方不再重复转移(self, db_session):
        a = _add(db_session, "观点甲", status="suspended")
        b = _add(db_session, "观点乙")
        create_relation(db_session, a, b.id, "conflict")
        assert a.status == "suspended" and b.status == "suspended"
        assert _events(db_session, a.id) == []  # 无状态变化不留痕
        assert len(_events(db_session, b.id, "conflict_suspend")) == 1

    def test_与被否定观点建关系被拒绝(self, db_session):
        a = _add(db_session, "观点甲")
        b = _add(db_session, "观点乙", status="rejected")
        with pytest.raises(ViewpointOpError, match="被否定"):
            create_relation(db_session, a, b.id, "similar")

    def test_与自身建关系被拒绝(self, db_session):
        a = _add(db_session, "观点甲")
        with pytest.raises(ViewpointOpError, match="自身"):
            create_relation(db_session, a, a.id, "similar")

    def test_重复关系被拒绝(self, db_session):
        a = _add(db_session, "观点甲")
        b = _add(db_session, "观点乙")
        create_relation(db_session, a, b.id, "similar")
        with pytest.raises(ViewpointOpError, match="已存在"):
            create_relation(db_session, b, a.id, "similar")  # 反向同样判重

    def test_非法关系类型被拒绝(self, db_session):
        a = _add(db_session, "观点甲")
        b = _add(db_session, "观点乙")
        with pytest.raises(ViewpointOpError, match="非法关系类型"):
            create_relation(db_session, a, b.id, "depends")


class TestDeleteRelation:
    def test_解除冲突不自动恢复状态(self, db_session):
        a = _add(db_session, "观点甲")
        b = _add(db_session, "观点乙")
        relation = create_relation(db_session, a, b.id, "conflict")
        delete_relation(db_session, a.id, relation.id)
        assert db_session.scalars(select(ViewpointRelation)).all() == []
        assert a.status == "suspended" and b.status == "suspended"

    def test_解除不存在的关系报404语义(self, db_session):
        a = _add(db_session, "观点甲")
        with pytest.raises(ViewpointOpError, match="不存在"):
            delete_relation(db_session, a.id, 99999)


class TestChangeStatus:
    def test_悬置与恢复(self, db_session):
        a = _add(db_session, "观点甲")
        change_viewpoint_status(db_session, a, "suspended")
        assert a.status == "suspended"
        change_viewpoint_status(db_session, a, "accepted")
        assert a.status == "accepted"
        events = _events(db_session, a.id, "status_change")
        assert [(e.from_status, e.to_status) for e in events] == [
            ("accepted", "suspended"),
            ("suspended", "accepted"),
        ]

    def test_否定必须填理由(self, db_session):
        a = _add(db_session, "观点甲")
        with pytest.raises(ViewpointOpError, match="理由"):
            change_viewpoint_status(db_session, a, "rejected", reason=" ")
        assert a.status == "accepted"
        change_viewpoint_status(db_session, a, "rejected", reason="已被新观点取代")
        assert a.status == "rejected"
        assert _events(db_session, a.id, "status_change")[0].reason == "已被新观点取代"

    def test_否定为终态(self, db_session):
        a = _add(db_session, "观点甲", status="rejected")
        with pytest.raises(ViewpointOpError, match="非法观点状态转换"):
            change_viewpoint_status(db_session, a, "accepted")

    def test_状态未变化被拒绝(self, db_session):
        a = _add(db_session, "观点甲")
        with pytest.raises(ViewpointOpError, match="状态未变化"):
            change_viewpoint_status(db_session, a, "accepted")


class TestMerge:
    def test_自动合并正文接续无改写(self, db_session):
        a = _add(db_session, "前半部分。")
        b = _add(db_session, "后半部分。")
        survivor, absorbed = merge_viewpoints(
            db_session, a, b.id, reason="两条实为一条"
        )
        assert survivor.content == "前半部分。\n后半部分。"
        assert absorbed.status == "rejected"
        assert absorbed.content == "后半部分。"  # 被合并方原文保留可追溯

    def test_重复内容撇去(self, db_session):
        a = _add(db_session, "完整表述的版本，内容更长。")
        b = _add(db_session, "完整表述")
        survivor, _ = merge_viewpoints(db_session, a, b.id, reason="重复")
        assert survivor.content == "完整表述的版本，内容更长。"

    def test_双方留痕含追溯信息(self, db_session):
        a = _add(db_session, "正文甲")
        b = _add(db_session, "正文乙")
        merge_viewpoints(db_session, a, b.id, reason="合并原因")
        survivor_events = _events(db_session, a.id, "merge")
        absorbed_events = _events(db_session, b.id, "merge")
        assert len(survivor_events) == 1 and len(absorbed_events) == 1
        assert survivor_events[0].reason == "合并原因"
        assert '"absorbed_id": ' in survivor_events[0].detail
        assert '"content_before": "正文甲"' in survivor_events[0].detail
        assert absorbed_events[0].from_status == "accepted"
        assert absorbed_events[0].to_status == "rejected"
        assert f'"merged_into": {a.id}' in absorbed_events[0].detail

    def test_指定合并正文以用户确认值为准(self, db_session):
        a = _add(db_session, "正文甲")
        b = _add(db_session, "正文乙")
        survivor, _ = merge_viewpoints(
            db_session, a, b.id, merged_content="用户确认的合并正文", reason="合并"
        )
        assert survivor.content == "用户确认的合并正文"

    def test_缺原因被拒绝(self, db_session):
        a = _add(db_session, "正文甲")
        b = _add(db_session, "正文乙")
        with pytest.raises(ViewpointOpError, match="原因"):
            merge_viewpoints(db_session, a, b.id)

    def test_被否定观点不得参与合并(self, db_session):
        a = _add(db_session, "正文甲")
        b = _add(db_session, "正文乙", status="rejected")
        with pytest.raises(ViewpointOpError, match="被否定"):
            merge_viewpoints(db_session, a, b.id, reason="合并")


class TestSplit:
    def test_拆分继承与原观点留痕(self, db_session):
        original = _add(
            db_session,
            "复合观点",
            layer="fa",
            domain="社会",
            circle="公众",
            discipline="社会学",
            scene="商业创业",
            source_date=date(2026, 5, 1),
        )
        original, new_viewpoints = split_viewpoint(
            db_session,
            original,
            ["拆分后的第一条", "拆分后的第二条", "拆分后的第三条"],
            reason="一条内含三个独立判断",
        )
        assert original.status == "rejected"
        assert len(new_viewpoints) == 3
        for item, content in zip(
            new_viewpoints, ["拆分后的第一条", "拆分后的第二条", "拆分后的第三条"]
        ):
            assert item.content == content
            assert item.layer == "fa" and item.domain == "社会"
            assert item.circle == "公众" and item.discipline == "社会学"
            assert item.scene == "商业创业"
            assert item.source_date == date(2026, 5, 1)
            assert item.status == "accepted"  # 继承拆分前状态
        original_events = _events(db_session, original.id, "split")
        assert original_events[0].from_status == "accepted"
        assert original_events[0].to_status == "rejected"
        for item in new_viewpoints:
            events = _events(db_session, item.id, "split")
            assert f'"split_from": {original.id}' in events[0].detail

    def test_拆分条目不足或含空条被拒绝(self, db_session):
        original = _add(db_session, "复合观点")
        with pytest.raises(ViewpointOpError, match="至少"):
            split_viewpoint(db_session, original, ["只有一条"], reason="拆分")
        with pytest.raises(ViewpointOpError, match="至少"):
            split_viewpoint(db_session, original, ["有内容", "  "], reason="拆分")
        assert original.status == "accepted"

    def test_被否定观点不得拆分(self, db_session):
        original = _add(db_session, "旧观点", status="rejected")
        with pytest.raises(ViewpointOpError, match="被否定"):
            split_viewpoint(db_session, original, ["甲", "乙"], reason="拆分")


class TestEvents:
    def test_留痕按时间升序且计数正确(self, db_session):
        a = _add(db_session, "观点甲")
        b = _add(db_session, "观点乙")
        create_relation(db_session, a, b.id, "conflict")
        change_viewpoint_status(db_session, a, "accepted")
        merge_viewpoints(db_session, a, b.id, reason="裁决后合并")
        events = _events(db_session, a.id)
        assert [e.event_type for e in events] == [
            "conflict_suspend",
            "status_change",
            "merge",
        ]
        assert all(e.created_at is not None for e in events)
        total = db_session.scalars(select(ViewpointEvent)).all()
        assert len(total) == 2 + 1 + 2  # a/b 冲突 + a 恢复 + a/b 合并
