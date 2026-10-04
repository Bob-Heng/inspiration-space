"""时间戳 UTC 统一单元测试（附带修复）。

覆盖：UtcDateTime 类型读写归一、server_default 读取带时区、
API 输出（Pydantic 序列化）带时区、fix_timestamps 订正脚本。
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import fix_timestamps
from app.models import Base, Inspiration, ReviewSession
from app.schemas import InspirationOut
from app.timeutils import utcnow

CST = timezone(timedelta(hours=8))


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


class TestUtcDateTime:
    def test_aware非UTC写入读取归一到UTC(self, db_session):
        moment = datetime(2026, 9, 27, 10, 30, 0, tzinfo=CST)
        db_session.add(Inspiration(content="测试", created_at=moment))
        db_session.commit()
        row = db_session.scalars(select(Inspiration)).one()
        assert row.created_at == datetime(2026, 9, 27, 2, 30, 0, tzinfo=timezone.utc)
        assert row.created_at.tzinfo is not None

    def test_naive写入按UTC处理(self, db_session):
        naive = datetime(2026, 9, 27, 2, 30, 0)
        db_session.add(Inspiration(content="测试", created_at=naive))
        db_session.commit()
        row = db_session.scalars(select(Inspiration)).one()
        assert row.created_at == naive.replace(tzinfo=timezone.utc)

    def test_存储物理格式为naiveUTC字符串(self, db_session):
        moment = datetime(2026, 9, 27, 10, 30, 0, tzinfo=CST)
        db_session.add(Inspiration(content="测试", created_at=moment))
        db_session.commit()
        value = db_session.execute(text("SELECT created_at FROM inspirations")).scalar()
        assert value == "2026-09-27 02:30:00.000000"

    def test_server_default读取出带UTC时区(self, db_session):
        db_session.add(Inspiration(content="测试"))
        db_session.commit()
        row = db_session.scalars(select(Inspiration)).one()
        assert row.created_at.tzinfo is not None
        assert row.created_at.utcoffset() == timedelta(0)
        assert abs((utcnow() - row.created_at).total_seconds()) < 60

    def test_none字段读写为空(self, db_session):
        db_session.add(ReviewSession(viewpoint_id=1, status="active"))
        db_session.commit()
        row = db_session.scalars(select(ReviewSession)).one()
        assert row.ended_at is None

    def test_utcnow返回awareUTC(self):
        now = utcnow()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)


class TestApiSerialization:
    def test_输出ISO8601带时区(self, db_session):
        db_session.add(Inspiration(content="测试"))
        db_session.commit()
        row = db_session.scalars(select(Inspiration)).one()
        payload = InspirationOut.model_validate(row).model_dump(mode="json")
        assert payload["created_at"].endswith("+00:00") or payload["created_at"].endswith("Z")
        # 前端 new Date() 可解析回同一时刻
        parsed = datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))
        assert parsed == row.created_at


class TestFixTimestamps:
    def test_ended_at本地时间转UTC且幂等防重跑(self, tmp_path, monkeypatch):
        db_path = tmp_path / "inspiration.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE review_sessions (id INTEGER PRIMARY KEY, ended_at TEXT)"
        )
        conn.execute(
            "INSERT INTO review_sessions (id, ended_at) VALUES (1, '2026-09-27 02:16:52.123968')"
        )
        conn.commit()
        conn.close()
        monkeypatch.setattr(fix_timestamps, "DATABASE_PATH", db_path)
        monkeypatch.setattr(
            fix_timestamps, "MARKER_PATH", tmp_path / "inspiration.db.tzfix.done"
        )

        fix_timestamps.main()
        value = sqlite3.connect(db_path).execute(
            "SELECT ended_at FROM review_sessions WHERE id = 1"
        ).fetchone()[0]
        local_offset = datetime.now().astimezone().utcoffset()
        expected = datetime(2026, 9, 27, 2, 16, 52, 123968) - local_offset
        assert value == expected.strftime("%Y-%m-%d %H:%M:%S.%f")
        assert (tmp_path / "inspiration.db.tzfix.done").exists()
        assert list(tmp_path.glob("inspiration.db.bak-*"))  # 已备份

        # 重复运行不再改写
        fix_timestamps.main()
        value2 = sqlite3.connect(db_path).execute(
            "SELECT ended_at FROM review_sessions WHERE id = 1"
        ).fetchone()[0]
        assert value2 == value
