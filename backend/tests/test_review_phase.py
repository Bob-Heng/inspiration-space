"""提炼/打磨两阶段测试（docs/04 D9）：phase 模型、观点判断与进入打磨端点、
提炼期讨论结构化信号、打磨期分析以关联观点正文为对象；
以及"观点为中心"存量迁移（ensure_schema_upgrades）测试。

不起 HTTP 层（测试环境无 httpx），直接以协程方式调用路由函数。
"""

import asyncio
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db as app_db
from app.ai import LLMProvider, Message
from app.db import ensure_schema_upgrades
from app.domain.review import open_review_session
from app.models import AiCall, Base, ReviewMessage, Viewpoint
from app.routers import analysis as analysis_route
from app.routers import review as review_route
from app.schemas import EnterPolishRequest, ReviewMessageCreate

ANALYSIS_JSON = json.dumps(
    {
        "adoption_reason": "值得采纳",
        "strongest_counterargument": "最强反对理由",
        "layer": "法",
        "tags": {"domain": "文化", "circle": None, "discipline": "经济学", "scene": None},
        "relations": [],
    },
    ensure_ascii=False,
)

DISTILL_JSON = json.dumps(
    {
        "reply": "你觉得这个现象背后是什么在起作用？",
        "ready_to_polish": True,
        "distilled_viewpoint": "提炼出的观点草稿",
    },
    ensure_ascii=False,
)

DISTILL_NOT_READY_JSON = json.dumps(
    {
        "reply": "还在提炼中的回复",
        "ready_to_polish": False,
        "distilled_viewpoint": None,
    },
    ensure_ascii=False,
)


class DistillProvider(LLMProvider):
    provider_name = "fake"
    model = "fake-model"

    async def generate(self, messages: list[Message]) -> str:
        return DISTILL_JSON


class NotReadyDistillProvider(LLMProvider):
    provider_name = "fake"
    model = "fake-model"

    async def generate(self, messages: list[Message]) -> str:
        return DISTILL_NOT_READY_JSON


class ViewpointCheckProvider(LLMProvider):
    provider_name = "fake"
    model = "fake-model"

    async def generate(self, messages: list[Message]) -> str:
        return json.dumps({"is_viewpoint": True})


class PlainTextProvider(LLMProvider):
    provider_name = "fake"
    model = "fake-model"

    async def generate(self, messages: list[Message]) -> str:
        return "打磨阶段的纯文本回复"


class AnalysisProvider(LLMProvider):
    provider_name = "fake"
    model = "fake-model"

    async def generate(self, messages: list[Message]) -> str:
        return ANALYSIS_JSON


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _no_translation(monkeypatch):
    """翻译走真实 Provider 解析，置空以保持测试与网关环境无关。"""

    async def _bilingual_stub(db, text, original_lang=None):
        return {
            "content_zh": None,
            "content_en": None,
            "original_lang": original_lang or "zh",
        }

    async def _analysis_stub(db, analysis_json):
        return None

    async def _titles_stub(db, content):
        return {"title_zh": "生成中文标题", "title_en": "Generated title"}

    monkeypatch.setattr(review_route, "make_bilingual", _bilingual_stub)
    monkeypatch.setattr(review_route, "make_titles", _titles_stub)
    monkeypatch.setattr(analysis_route, "bilingual_analysis", _analysis_stub)


def _add_viewpoint(db, content="测试观点", **kwargs) -> Viewpoint:
    viewpoint = Viewpoint(content=content, status="draft", **kwargs)
    db.add(viewpoint)
    db.commit()
    return viewpoint


def _open_session(db, content="测试观点"):
    return open_review_session(db, _add_viewpoint(db, content))


class TestSessionPhase:
    def test_新会话默认提炼阶段(self, db_session):
        session = _open_session(db_session)
        assert session.phase == "distill"
        # started_at 显式赋值（迁移重建的表缺 server_default，不能依赖数据库默认）
        assert session.started_at is not None

    def test_挂起恢复后阶段保留(self, db_session):
        viewpoint = _add_viewpoint(db_session)
        session = open_review_session(db_session, viewpoint)
        session.phase = "polish"
        session.status = "paused"
        db_session.commit()

        resumed = open_review_session(db_session, viewpoint)
        assert resumed.id == session.id
        assert resumed.status == "active"
        assert resumed.phase == "polish"


def _build_legacy_db(db_path, *, with_phase_columns: bool):
    """构造"观点为中心"重构前的旧结构库：

    inspirations 带 status、review_sessions 带 inspiration_id + distilled_draft、
    review_messages 无 phase、有 viewpoint_events。
    with_phase_columns=False 时 review_sessions 连 phase/distilled_draft 两列也没有
    （更早期的库），用于验证 phase 回填经整表重建后仍为 polish。
    """
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_phase_cols = (
        "phase VARCHAR(10), distilled_draft TEXT," if with_phase_columns else ""
    )
    with engine.begin() as conn:
        for table in ("review_messages", "review_sessions", "inspirations"):
            conn.execute(text(f"DROP TABLE {table}"))
        conn.execute(
            text(
                """
                CREATE TABLE inspirations (
                    id INTEGER PRIMARY KEY,
                    content TEXT,
                    source_date DATE,
                    source_type VARCHAR(20),
                    status VARCHAR(20),
                    content_zh TEXT,
                    content_en TEXT,
                    original_lang VARCHAR(2),
                    title_zh VARCHAR(100),
                    title_en VARCHAR(100),
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TABLE review_sessions (
                    id INTEGER PRIMARY KEY,
                    inspiration_id INTEGER NOT NULL REFERENCES inspirations(id),
                    viewpoint_id INTEGER REFERENCES viewpoints(id),
                    status VARCHAR(20),
                    {session_phase_cols}
                    started_at DATETIME,
                    ended_at DATETIME,
                    analysis_json TEXT,
                    analysis_json_en TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE review_messages (
                    id INTEGER PRIMARY KEY,
                    session_id INTEGER NOT NULL REFERENCES review_sessions(id),
                    role VARCHAR(20),
                    content TEXT,
                    content_zh TEXT,
                    content_en TEXT,
                    original_lang VARCHAR(2),
                    created_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE viewpoint_events (
                    id INTEGER PRIMARY KEY,
                    viewpoint_id INTEGER NOT NULL REFERENCES viewpoints(id),
                    event_type VARCHAR(20),
                    from_status VARCHAR(20),
                    to_status VARCHAR(20),
                    reason TEXT,
                    detail TEXT,
                    created_at DATETIME
                )
                """
            )
        )
    return engine


class TestEnsureSchemaUpgradesPhase:
    def test_存量会话迁移回填为打磨阶段(self, tmp_path, monkeypatch):
        engine = _build_legacy_db(tmp_path / "legacy.db", with_phase_columns=False)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO inspirations (content, source_type, status, original_lang)"
                    " VALUES ('旧灵感', 'manual', 'pending', 'zh')"
                )
            )
            conn.execute(
                text("INSERT INTO review_sessions (inspiration_id, status) VALUES (1, 'active')")
            )
        monkeypatch.setattr(app_db, "engine", engine)
        try:
            ensure_schema_upgrades()
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT phase, viewpoint_id FROM review_sessions WHERE id = 1")
                ).one()
                assert row[0] == "polish"  # 存量会话一律视为打磨阶段
                assert row[1] is not None  # 已映射到补建的草稿观点
            cols = {c["name"] for c in inspect(engine).get_columns("review_sessions")}
            assert "phase" in cols
            assert "inspiration_id" not in cols
            assert "distilled_draft" not in cols
        finally:
            engine.dispose()


class TestEnsureSchemaUpgradesIsViewpoint:
    """viewpoints 补 is_viewpoint 列：幂等 ALTER；存量观点保持 NULL（未判断），
    首次开会话时前端走 live 判断兜底。"""

    def test_补列幂等且存量观点保持NULL(self, tmp_path, monkeypatch):
        engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            # 模拟补列前的存量库：viewpoints 无 is_viewpoint 列
            conn.execute(text("ALTER TABLE viewpoints DROP COLUMN is_viewpoint"))
            conn.execute(
                text(
                    "INSERT INTO viewpoints (type, content, status, original_lang)"
                    " VALUES ('raw', '存量观点', 'draft', 'zh')"
                )
            )
        monkeypatch.setattr(app_db, "engine", engine)
        try:
            ensure_schema_upgrades()
            with engine.connect() as conn:
                cols = {c["name"] for c in inspect(engine).get_columns("viewpoints")}
                assert "is_viewpoint" in cols
                # 存量观点不回填：保持 NULL（未判断）
                assert conn.execute(
                    text("SELECT is_viewpoint FROM viewpoints WHERE content='存量观点'")
                ).scalar() is None
            # 幂等：重复执行不报错、数据不变
            ensure_schema_upgrades()
            with engine.connect() as conn:
                assert conn.execute(
                    text("SELECT COUNT(*) FROM viewpoints")
                ).scalar() == 1
        finally:
            engine.dispose()


class TestEnsureSchemaUpgradesViewpointCentric:
    """观点为中心存量迁移：补建草稿观点、会话整表重建、消息补 phase、
    灵感 status 列下线、viewpoint_events 删表，整体幂等。"""

    @pytest.fixture()
    def legacy_engine(self, tmp_path):
        engine = _build_legacy_db(tmp_path / "legacy.db", with_phase_columns=True)
        with engine.begin() as conn:
            # 灵感一（pending，无观点）；灵感二（历史 rejected，无观点）；
            # 灵感三（已有采纳观点，不得重复补建）
            conn.execute(
                text(
                    "INSERT INTO inspirations"
                    " (id, content, source_date, source_type, status,"
                    "  content_zh, content_en, original_lang) VALUES"
                    " (1, '灵感一', '2026-05-01', 'manual', 'pending', '灵感一', 'idea one', 'zh'),"
                    " (2, '灵感二', NULL, 'manual', 'rejected', '灵感二', 'idea two', 'zh'),"
                    " (3, '灵感三', '2026-06-01', 'manual', 'reviewed', '灵感三', 'idea three', 'zh')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO viewpoints"
                    " (id, type, content, source_inspiration_id, source_date, status,"
                    "  content_zh, content_en, original_lang) VALUES"
                    " (1, 'raw', '已采纳观点', 3, '2026-06-01', 'accepted',"
                    "  '已采纳观点', 'accepted idea', 'zh')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO review_sessions"
                    " (id, inspiration_id, viewpoint_id, status, phase, analysis_json) VALUES"
                    " (1, 1, NULL, 'active', 'polish', '{\"a\": 1}'),"
                    " (2, 2, NULL, 'completed', 'polish', NULL),"
                    " (3, 3, 1, 'completed', 'distill', NULL)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO review_messages (session_id, role, content) VALUES"
                    " (1, 'user', '讨论一'),"
                    " (2, 'assistant', '回答')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO viewpoint_events (viewpoint_id, event_type, to_status)"
                    " VALUES (1, 'status_change', 'accepted')"
                )
            )
        return engine

    def test_迁移结果与幂等(self, legacy_engine, monkeypatch):
        monkeypatch.setattr(app_db, "engine", legacy_engine)
        try:
            ensure_schema_upgrades()
            insp = inspect(legacy_engine)
            with legacy_engine.connect() as conn:
                # 1. 无观点的灵感（含历史 rejected）补建 draft 观点，内容/双语/日期一致
                drafts = conn.execute(
                    text(
                        "SELECT v.content, v.status, v.type, v.source_date,"
                        " v.content_zh, v.content_en, v.original_lang,"
                        " v.source_inspiration_id"
                        " FROM viewpoints v WHERE v.id > 1 ORDER BY v.id"
                    )
                ).all()
                assert len(drafts) == 2
                assert drafts[0] == (
                    "灵感一", "draft", "raw", "2026-05-01", "灵感一", "idea one", "zh", 1,
                )
                assert drafts[1] == (
                    "灵感二", "draft", "raw", None, "灵感二", "idea two", "zh", 2,
                )
                # 灵感三已有采纳观点，不重复补建
                vp_of_3 = conn.execute(
                    text("SELECT COUNT(*) FROM viewpoints WHERE source_inspiration_id = 3")
                ).scalar()
                assert vp_of_3 == 1
                # 每条灵感都有关联观点
                orphans = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM inspirations i"
                        " WHERE NOT EXISTS ("
                        " SELECT 1 FROM viewpoints v WHERE v.source_inspiration_id = i.id)"
                    )
                ).scalar()
                assert orphans == 0

                # 2. review_sessions 整表重建：viewpoint_id 正确映射，旧列下线
                scols = {c["name"] for c in insp.get_columns("review_sessions")}
                assert "inspiration_id" not in scols
                assert "distilled_draft" not in scols
                draft1 = conn.execute(
                    text("SELECT id FROM viewpoints WHERE source_inspiration_id = 1")
                ).scalar()
                draft2 = conn.execute(
                    text("SELECT id FROM viewpoints WHERE source_inspiration_id = 2")
                ).scalar()
                sessions = conn.execute(
                    text(
                        "SELECT id, viewpoint_id, status, phase, analysis_json"
                        " FROM review_sessions ORDER BY id"
                    )
                ).all()
                assert sessions == [
                    (1, draft1, "active", "polish", '{"a": 1}'),
                    (2, draft2, "completed", "polish", None),
                    (3, 1, "completed", "distill", None),  # 已有 viewpoint_id 原样保留
                ]
                # started_at 为 NULL 的会话被回填（重建时期 DDL 丢 DEFAULT 的历史问题）
                null_started = conn.execute(
                    text("SELECT COUNT(*) FROM review_sessions WHERE started_at IS NULL")
                ).scalar()
                assert null_started == 0

                # 3. 存量消息 phase 回填 polish
                phases = conn.execute(
                    text("SELECT phase FROM review_messages ORDER BY id")
                ).all()
                assert phases == [("polish",), ("polish",)]

                # 4. viewpoint_events 表删除；inspirations 无 status 列
                assert "viewpoint_events" not in set(insp.get_table_names())
                icols = {c["name"] for c in insp.get_columns("inspirations")}
                assert "status" not in icols

                counts_before = {
                    table: conn.execute(
                        text(f"SELECT COUNT(*) FROM {table}")
                    ).scalar()
                    for table in ("inspirations", "viewpoints", "review_sessions", "review_messages")
                }
                sessions_before = sessions

            # 幂等：重复执行不报错且结果不变
            ensure_schema_upgrades()
            with legacy_engine.connect() as conn:
                for table, expected in counts_before.items():
                    assert conn.execute(
                        text(f"SELECT COUNT(*) FROM {table}")
                    ).scalar() == expected
                sessions_after = conn.execute(
                    text(
                        "SELECT id, viewpoint_id, status, phase, analysis_json"
                        " FROM review_sessions ORDER BY id"
                    )
                ).all()
                assert sessions_after == sessions_before
            # 结构稳定：第二次执行后旧列不会复活（inspector 只见已提交结构）
            scols_after = {
                c["name"] for c in inspect(legacy_engine).get_columns("review_sessions")
            }
            assert "inspiration_id" not in scols_after
            assert "distilled_draft" not in scols_after
        finally:
            legacy_engine.dispose()


class TestViewpointCheck:
    def test_观点判断返回结构化结果(self, db_session):
        session = _open_session(db_session)

        out = asyncio.run(
            review_route.viewpoint_check(
                session.id, db=db_session, provider=ViewpointCheckProvider()
            )
        )

        assert out.is_viewpoint is True

    def test_非进行中会话观点判断被拒绝(self, db_session):
        session = _open_session(db_session)
        session.status = "paused"
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                review_route.viewpoint_check(
                    session.id, db=db_session, provider=ViewpointCheckProvider()
                )
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "session_not_active"


class TestEnterPolish:
    def test_进入打磨成功且草稿写入观点正文(self, db_session):
        session = _open_session(db_session)

        out = asyncio.run(
            review_route.enter_polish(
                session.id, EnterPolishRequest(draft="  提炼草稿正文  "), db=db_session
            )
        )

        assert out.phase == "polish"
        db_session.refresh(session)
        assert session.phase == "polish"
        viewpoint = db_session.get(Viewpoint, session.viewpoint_id)
        assert viewpoint.content == "提炼草稿正文"  # 去空白后落库

    def test_进入打磨重新生成观点标题(self, db_session):
        viewpoint = _add_viewpoint(db_session, title_zh="旧标题", title_en="Old title")
        session = open_review_session(db_session, viewpoint)

        asyncio.run(
            review_route.enter_polish(
                session.id, EnterPolishRequest(draft="收敛后的观点正文"), db=db_session
            )
        )

        db_session.refresh(viewpoint)
        assert viewpoint.title_zh == "生成中文标题"
        assert viewpoint.title_en == "Generated title"

    def test_草稿与现正文相同则不重新双语化(self, db_session, monkeypatch):
        session = _open_session(db_session, content="已有正文")

        async def _forbidden(db, text, original_lang=None):
            raise AssertionError("正文未变化不应调用双语化")

        monkeypatch.setattr(review_route, "make_bilingual", _forbidden)
        out = asyncio.run(
            review_route.enter_polish(
                session.id, EnterPolishRequest(draft=" 已有正文 "), db=db_session
            )
        )

        assert out.phase == "polish"
        viewpoint = db_session.get(Viewpoint, session.viewpoint_id)
        assert viewpoint.content == "已有正文"

    def test_空草稿进入打磨观点正文不变(self, db_session):
        session = _open_session(db_session)

        out = asyncio.run(
            review_route.enter_polish(
                session.id, EnterPolishRequest(draft="   "), db=db_session
            )
        )

        assert out.phase == "polish"
        viewpoint = db_session.get(Viewpoint, session.viewpoint_id)
        assert viewpoint.content == "测试观点"  # 空草稿不覆盖草稿观点正文

    def test_已在打磨阶段重复进入被拒绝(self, db_session):
        session = _open_session(db_session)
        asyncio.run(
            review_route.enter_polish(session.id, EnterPolishRequest(), db=db_session)
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                review_route.enter_polish(
                    session.id, EnterPolishRequest(), db=db_session
                )
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "phase_conflict"


class TestPostMessageByPhase:
    def test_提炼收敛轮回复不落库(self, db_session):
        session = _open_session(db_session)

        pair = asyncio.run(
            review_route.post_message(
                session.id,
                ReviewMessageCreate(content="我观察到一些现象"),
                db=db_session,
                provider=DistillProvider(),
            )
        )

        # ready_to_polish=true：回复被压下（不落库、不进对话框），正文随信号携带
        assert pair.assistant_message is None
        assert pair.distill_signal is not None
        assert pair.distill_signal.ready_to_polish is True
        assert pair.distill_signal.distilled_viewpoint == "提炼出的观点草稿"
        assert pair.distill_signal.reply == "你觉得这个现象背后是什么在起作用？"
        roles = [m.role for m in db_session.query(ReviewMessage).all()]
        assert roles == ["user"]

    def test_提炼未收敛轮回复照常落库(self, db_session):
        session = _open_session(db_session)

        pair = asyncio.run(
            review_route.post_message(
                session.id,
                ReviewMessageCreate(content="我观察到一些现象"),
                db=db_session,
                provider=NotReadyDistillProvider(),
            )
        )

        assert pair.assistant_message is not None
        assert pair.assistant_message.content == "还在提炼中的回复"
        assert pair.distill_signal is not None
        assert pair.distill_signal.ready_to_polish is False
        assert pair.distill_signal.reply is None
        # 消息写入时记录会话当时阶段
        messages = db_session.query(ReviewMessage).order_by(ReviewMessage.id).all()
        assert [m.phase for m in messages] == ["distill", "distill"]

    def test_打磨阶段发言不附提炼信号(self, db_session):
        session = _open_session(db_session)
        session.phase = "polish"
        db_session.commit()

        pair = asyncio.run(
            review_route.post_message(
                session.id,
                ReviewMessageCreate(content="继续讨论"),
                db=db_session,
                provider=PlainTextProvider(),
            )
        )

        assert pair.assistant_message.content == "打磨阶段的纯文本回复"
        assert pair.distill_signal is None
        messages = db_session.query(ReviewMessage).order_by(ReviewMessage.id).all()
        assert [m.phase for m in messages] == ["polish", "polish"]


class TestPolishEntryOpening:
    def _polish_session_with_analysis(self, db):
        session = _open_session(db)
        session.phase = "polish"
        session.analysis_json = ANALYSIS_JSON
        db.add(ReviewMessage(session_id=session.id, role="user", content="提炼期讨论", phase="distill"))
        db.commit()
        return session

    def test_提炼讨论保留时也能生成打磨首问(self, db_session):
        session = self._polish_session_with_analysis(db_session)

        out = asyncio.run(
            review_route.post_opening(
                session.id, False, True, db=db_session, provider=PlainTextProvider()
            )
        )

        assert out is not None
        assert out.content == "打磨阶段的纯文本回复"
        # 首问落库，原有提炼讨论保留
        roles = [m.role for m in db_session.query(ReviewMessage).order_by(ReviewMessage.id)]
        assert roles == ["user", "assistant"]

    def test_提炼阶段请求打磨首问被拒绝(self, db_session):
        session = _open_session(db_session)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                review_route.post_opening(
                    session.id, False, True, db=db_session, provider=PlainTextProvider()
                )
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "phase_conflict"

    def test_无分析时打磨首问被拒绝(self, db_session):
        session = _open_session(db_session)
        session.phase = "polish"
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                review_route.post_opening(
                    session.id, False, True, db=db_session, provider=PlainTextProvider()
                )
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "analysis_missing"


class TestAnalysisUsesDraft:
    def test_会话观点正文被提炼后分析以其为对象(self, db_session):
        viewpoint = _add_viewpoint(db_session, content="原始灵感文本标记")
        open_review_session(db_session, viewpoint)
        viewpoint.content = "提炼后的观点草稿标记"
        db_session.commit()

        asyncio.run(
            analysis_route.analyze_viewpoint(
                viewpoint.id, db=db_session, provider=AnalysisProvider()
            )
        )

        call = db_session.query(AiCall).order_by(AiCall.id.desc()).first()
        assert call is not None
        assert "提炼后的观点草稿标记" in call.input_snapshot
        assert "原始灵感文本标记" not in call.input_snapshot
