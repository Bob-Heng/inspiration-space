"""观点关系单元测试。

观点为中心重构后：观点状态只有 draft / accepted；建立关系只记关系行、
不联动状态；合并/拆分/操作留痕（viewpoint_events）已删除；显式状态变更
端点已删除（状态只由采纳决策与集思录撤回改变，分别见决策/撤回测试）。
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.viewpoints import (
    ViewpointOpError,
    create_relation,
    delete_relation,
    list_relations,
)
from app.models import Base, Viewpoint, ViewpointRelation


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

    def test_冲突关系只记关系行不联动状态(self, db_session):
        a = _add(db_session, "观点甲")
        b = _add(db_session, "观点乙")
        create_relation(db_session, a, b.id, "conflict")
        # 悬置已删除：冲突不再联动双方状态
        assert a.status == "accepted" and b.status == "accepted"
        relations_a = list_relations(db_session, a.id)
        relations_b = list_relations(db_session, b.id)
        assert len(relations_a) == 1 and len(relations_b) == 1
        assert relations_a[0][0].id == relations_b[0][0].id  # 同一关系行互记双方

    def test_与自身建关系被拒绝(self, db_session):
        a = _add(db_session, "观点甲")
        with pytest.raises(ViewpointOpError, match="自身"):
            create_relation(db_session, a, a.id, "similar")

    def test_与不存在的观点建关系被拒绝(self, db_session):
        a = _add(db_session, "观点甲")
        with pytest.raises(ViewpointOpError, match="不存在"):
            create_relation(db_session, a, 99999, "similar")

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
    def test_解除关系不自动恢复状态(self, db_session):
        a = _add(db_session, "观点甲")
        b = _add(db_session, "观点乙")
        relation = create_relation(db_session, a, b.id, "conflict")
        delete_relation(db_session, a.id, relation.id)
        assert db_session.scalars(select(ViewpointRelation)).all() == []
        assert a.status == "accepted" and b.status == "accepted"

    def test_解除不存在的关系报404语义(self, db_session):
        a = _add(db_session, "观点甲")
        with pytest.raises(ViewpointOpError, match="不存在"):
            delete_relation(db_session, a.id, 99999)
