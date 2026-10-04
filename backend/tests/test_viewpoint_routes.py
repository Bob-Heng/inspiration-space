"""集思录列表与观点标题端点测试：列表只收已采纳；PATCH title 两字段独立可空更新、
全空 422。

不起 HTTP 层（测试环境无 httpx），直接调用路由函数。
"""

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Inspiration, Viewpoint, ViewpointRelation
from app.routers import viewpoints as viewpoints_route
from app.schemas import ViewpointOut, ViewpointTitleUpdate


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


def _list(db, **overrides):
    """直接调用路由函数：Query 默认值在直调时不会生效，显式补全 None。"""
    params = dict(
        layer=None, domain=None, circle=None, discipline=None, scene=None,
        date_from=None, date_to=None, keyword=None,
    )
    params.update(overrides)
    return viewpoints_route.list_viewpoints(**params, db=db)


class TestListViewpoints:
    def test_列表只收已采纳(self, db_session):
        accepted = _add(db_session, "已采纳")
        _add(db_session, "草稿", status="draft")

        items = _list(db_session)

        assert [v.id for v in items] == [accepted.id]

    def test_筛选条件仍生效(self, db_session):
        keep = _add(db_session, "法层观点", layer="fa", domain="经济")
        _add(db_session, "道层观点", layer="dao")
        _add(db_session, "草稿法层", layer="fa", status="draft")

        items = _list(db_session, layer="fa", domain="经济")

        assert [v.id for v in items] == [keep.id]


class TestPatchTitle:
    def test_两字段独立更新(self, db_session):
        viewpoint = _add(db_session, title_zh="旧中文", title_en="Old English")

        out = viewpoints_route.patch_title(
            viewpoint.id, ViewpointTitleUpdate(title_zh="新中文"), db_session
        )
        assert out.title_zh == "新中文"
        assert out.title_en == "Old English"  # 未提供的语种不动

        out = viewpoints_route.patch_title(
            viewpoint.id, ViewpointTitleUpdate(title_en="New English"), db_session
        )
        assert out.title_zh == "新中文"
        assert out.title_en == "New English"

    def test_空串清除该语种标题(self, db_session):
        viewpoint = _add(db_session, title_zh="中文", title_en="English")

        out = viewpoints_route.patch_title(
            viewpoint.id, ViewpointTitleUpdate(title_zh="  "), db_session
        )
        assert out.title_zh is None
        assert out.title_en == "English"

    def test_全空请求422(self):
        with pytest.raises(ValidationError):
            ViewpointTitleUpdate()

    def test_观点不存在404(self, db_session):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            viewpoints_route.patch_title(
                99999, ViewpointTitleUpdate(title_zh="标题"), db_session
            )
        assert exc_info.value.status_code == 404


class TestConflictWith:
    """集思录列表/分类视图的 conflict_with：冲突对方的展示编号
    （对方来源灵感编号，无来源兜底对方观点 id），排序去重，一次性组装。"""

    def _inspiration(self, db, content="灵感") -> Inspiration:
        inspiration = Inspiration(content=content)
        db.add(inspiration)
        db.commit()
        return inspiration

    def _conflict(self, db, from_id, to_id):
        db.add(
            ViewpointRelation(
                from_viewpoint_id=from_id, to_viewpoint_id=to_id,
                relation_type="conflict",
            )
        )
        db.commit()

    def test_冲突展示编号用来源灵感编号(self, db_session):
        inspiration = self._inspiration(db_session)
        a = _add(db_session, "观点甲")  # 无来源：展示编号兜底为观点 id
        b = _add(db_session, "观点乙", source_inspiration_id=inspiration.id)
        self._conflict(db_session, a.id, b.id)

        items = {v.id: v for v in _list(db_session)}

        assert items[a.id].conflict_with == [inspiration.id]  # 对方展示编号=灵感编号
        assert items[b.id].conflict_with == [a.id]  # 对方无来源兜底观点 id

    def test_去重排序(self, db_session):
        b_source = self._inspiration(db_session)  # id=1：b 的展示编号
        b = _add(db_session, "观点乙", source_inspiration_id=b_source.id)
        a = _add(db_session, "观点甲")
        c = _add(db_session, "观点丙")
        # 先建小编号在后的关系，验证排序；重复行（双向各一条）验证去重
        self._conflict(db_session, a.id, c.id)
        self._conflict(db_session, c.id, a.id)
        self._conflict(db_session, b.id, a.id)

        items = {v.id: v for v in _list(db_session)}

        assert items[a.id].conflict_with == sorted({b_source.id, c.id})
        assert items[b.id].conflict_with == [a.id]
        assert items[c.id].conflict_with == [a.id]

    def test_非冲突关系不计入且无冲突为空列表(self, db_session):
        a = _add(db_session, "观点甲")
        b = _add(db_session, "观点乙")
        db_session.add(
            ViewpointRelation(
                from_viewpoint_id=a.id, to_viewpoint_id=b.id,
                relation_type="similar",
            )
        )
        db_session.commit()

        items = {v.id: v for v in _list(db_session)}

        assert items[a.id].conflict_with == []
        assert items[b.id].conflict_with == []

    def test_分类视图同样携带(self, db_session):
        a = _add(db_session, "观点甲", layer="dao")
        b = _add(db_session, "观点乙", layer="fa")
        self._conflict(db_session, a.id, b.id)

        out = viewpoints_route.get_classified(db_session)

        assert out.dao[0].conflict_with == [b.id]
        assert out.fa[0].conflict_with == [a.id]
        assert out.shu == []

    def test_其他场景不组装保持None(self, db_session):
        a = _add(db_session, "观点甲")
        b = _add(db_session, "观点乙")
        self._conflict(db_session, a.id, b.id)

        # schema 默认 None：非集思录列表/分类视图的序列化场景不附带
        assert ViewpointOut.model_validate(a).conflict_with is None
