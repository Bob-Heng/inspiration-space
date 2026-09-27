"""分类观点视图单元测试（TASK-016）：道/法/术分组、排除否定、悬置保留、日期排序。"""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.viewpoints import classified_viewpoints
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


def _add(db, content, layer, status="accepted", source_date=None) -> Viewpoint:
    viewpoint = Viewpoint(
        content=content, layer=layer, status=status, source_date=source_date
    )
    db.add(viewpoint)
    db.commit()
    return viewpoint


class TestClassified:
    def test_分组与成员正确(self, db_session):
        a = _add(db_session, "道一", "dao")
        b = _add(db_session, "法一", "fa")
        c = _add(db_session, "术一", "shu")
        groups = classified_viewpoints(db_session)
        assert [v.id for v in groups["dao"]] == [a.id]
        assert [v.id for v in groups["fa"]] == [b.id]
        assert [v.id for v in groups["shu"]] == [c.id]

    def test_否定排除悬置保留(self, db_session):
        accepted = _add(db_session, "采纳", "dao")
        suspended = _add(db_session, "悬置", "dao", status="suspended")
        _add(db_session, "否定", "dao", status="rejected")
        groups = classified_viewpoints(db_session)
        ids = [v.id for v in groups["dao"]]
        assert accepted.id in ids
        assert suspended.id in ids  # 悬置保留，由前端标记
        assert all(v.status != "rejected" for v in groups["dao"])

    def test_组内按来源日期升序无日期排最后(self, db_session):
        late = _add(db_session, "晚", "fa", source_date=date(2026, 6, 1))
        no_date = _add(db_session, "无日期", "fa")
        early = _add(db_session, "早", "fa", source_date=date(2026, 5, 1))
        groups = classified_viewpoints(db_session)
        assert [v.id for v in groups["fa"]] == [early.id, late.id, no_date.id]

    def test_无分层观点不进入任何组(self, db_session):
        _add(db_session, "无分层", None)
        groups = classified_viewpoints(db_session)
        assert groups == {"dao": [], "fa": [], "shu": []}
