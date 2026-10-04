"""观点组合筛选查询单元测试（TASK-013）。"""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.viewpoints import query_viewpoints
from app.models import Base, Viewpoint


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture()
def seeded(db_session):
    rows = [
        Viewpoint(
            content="道层观点：世界是可知的",
            layer="dao",
            domain="文化",
            circle="个人",
            discipline="哲学",
            scene="学习认知",
            status="accepted",
            source_date=date(2026, 5, 1),
        ),
        Viewpoint(
            content="法层观点：结构决定行为",
            layer="fa",
            domain="社会",
            circle="公众",
            discipline="社会学",
            scene="商业创业",
            status="draft",
            source_date=date(2026, 5, 10),
        ),
        Viewpoint(
            content="术层观点：先写草稿再修改",
            layer="shu",
            domain="文化",
            circle="个人",
            discipline="文学艺术",
            scene="自我管理",
            status="accepted",
            source_date=date(2026, 6, 1),
        ),
        Viewpoint(
            content="无分层无标签观点",
            status="draft",
            source_date=None,
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()
    return rows


def _ids(rows):
    return [row.id for row in rows]


class TestSingleFilter:
    def test_按分层筛选(self, db_session, seeded):
        result = query_viewpoints(db_session, layer="fa")
        assert _ids(result) == [seeded[1].id]

    def test_按状态筛选(self, db_session, seeded):
        result = query_viewpoints(db_session, status="accepted")
        assert _ids(result) == [seeded[0].id, seeded[2].id]

    def test_按四标签族各自筛选(self, db_session, seeded):
        assert _ids(query_viewpoints(db_session, domain="文化")) == [
            seeded[0].id,
            seeded[2].id,
        ]
        assert _ids(query_viewpoints(db_session, circle="公众")) == [seeded[1].id]
        assert _ids(query_viewpoints(db_session, discipline="哲学")) == [seeded[0].id]
        assert _ids(query_viewpoints(db_session, scene="自我管理")) == [seeded[2].id]

    def test_按关键词筛选(self, db_session, seeded):
        result = query_viewpoints(db_session, keyword="结构")
        assert _ids(result) == [seeded[1].id]

    def test_按日期区间筛选(self, db_session, seeded):
        result = query_viewpoints(
            db_session, date_from=date(2026, 5, 5), date_to=date(2026, 6, 30)
        )
        assert _ids(result) == [seeded[1].id, seeded[2].id]
        # 无来源日期的观点不落入任何日期区间
        result = query_viewpoints(db_session, date_from=date(2020, 1, 1))
        assert seeded[3].id not in _ids(result)


class TestCombinedFilter:
    def test_分层加标签加关键词(self, db_session, seeded):
        result = query_viewpoints(
            db_session, layer="shu", domain="文化", keyword="草稿"
        )
        assert _ids(result) == [seeded[2].id]

    def test_状态加日期区间(self, db_session, seeded):
        result = query_viewpoints(
            db_session,
            status="accepted",
            date_from=date(2026, 5, 1),
            date_to=date(2026, 5, 31),
        )
        assert _ids(result) == [seeded[0].id]

    def test_组合无命中返回空(self, db_session, seeded):
        result = query_viewpoints(db_session, layer="dao", status="draft")
        assert result == []

    def test_无筛选返回全部按编号升序(self, db_session, seeded):
        result = query_viewpoints(db_session)
        assert _ids(result) == [row.id for row in seeded]
