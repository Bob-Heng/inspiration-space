import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATA_DIR, DATABASE_PATH

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


DATA_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema_upgrades() -> None:
    """轻量结构升级：为存量库补充后加的列/表（幂等）。

    create_all 不会修改已有表；一阶段不引入 Alembic，逐条手写。
    content_translations / viewpoint_translations 是纯缓存，直接废弃重建。
    末尾为"观点为中心"重构迁移：灵感补建草稿观点、会话改关联观点、
    消息补 phase、灵感状态列与操作留痕表下线。
    """
    from datetime import datetime, timezone

    from sqlalchemy import inspect, text
    from sqlalchemy.exc import OperationalError

    insp = inspect(engine)
    with engine.begin() as conn:
        cols = {c["name"] for c in insp.get_columns("review_sessions")}
        if "analysis_json" not in cols:
            conn.execute(
                text("ALTER TABLE review_sessions ADD COLUMN analysis_json TEXT")
            )
        if "analysis_json_en" not in cols:
            conn.execute(
                text("ALTER TABLE review_sessions ADD COLUMN analysis_json_en TEXT")
            )
        if "phase" not in cols:
            conn.execute(
                text("ALTER TABLE review_sessions ADD COLUMN phase VARCHAR(10)")
            )
            # 存量会话皆为旧式审议（无提炼环节），一律视为打磨阶段
            conn.execute(
                text("UPDATE review_sessions SET phase='polish' WHERE phase IS NULL")
            )
        # 原生双语列：先镜像原文，原文语言标记 zh，英文版由补译脚本回填
        for table in ("inspirations", "viewpoints", "review_messages"):
            tcols = {c["name"] for c in insp.get_columns(table)}
            if "content_zh" not in tcols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN content_zh TEXT"))
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN content_en TEXT"))
                conn.execute(
                    text(
                        f"ALTER TABLE {table} ADD COLUMN original_lang VARCHAR(2) DEFAULT 'zh'"
                    )
                )
                conn.execute(
                    text(
                        f"UPDATE {table} SET content_zh=content, content_en=content, original_lang='zh'"
                    )
                )
            if "title_zh" not in tcols and table in ("inspirations", "viewpoints"):
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN title_zh VARCHAR(100)")
                )
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN title_en VARCHAR(100)")
                )
        ucols = {c["name"] for c in insp.get_columns("users")}
        if "phone" not in ucols:
            conn.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(30)"))
            conn.execute(text("ALTER TABLE users ADD COLUMN birthday DATE"))
        tables = set(insp.get_table_names())
        for legacy in ("content_translations", "viewpoint_translations", "content_i18n"):
            if legacy in tables:
                conn.execute(text(f"DROP TABLE {legacy}"))

        # ---- 观点为中心重构：以下为一次性存量迁移，全部幂等 ----

        # 1. review_messages 补 phase 列：存量消息一律视为打磨阶段
        mcols = {c["name"] for c in insp.get_columns("review_messages")}
        if "phase" not in mcols:
            conn.execute(
                text("ALTER TABLE review_messages ADD COLUMN phase VARCHAR(10)")
            )
            conn.execute(
                text("UPDATE review_messages SET phase='polish' WHERE phase IS NULL")
            )

        # 2. 补建草稿观点：每条没有关联观点的灵感（含历史 rejected 灵感）
        #    复制内容建一条 draft 观点；NOT EXISTS 保证重复执行无副作用
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        conn.execute(
            text(
                """
                INSERT INTO viewpoints (
                    type, content, source_inspiration_id, source_date, status,
                    content_zh, content_en, original_lang, title_zh, title_en,
                    created_at, updated_at
                )
                SELECT 'raw', i.content, i.id, i.source_date, 'draft',
                       i.content_zh, i.content_en, i.original_lang,
                       i.title_zh, i.title_en, :now, :now
                FROM inspirations i
                WHERE NOT EXISTS (
                    SELECT 1 FROM viewpoints v WHERE v.source_inspiration_id = i.id
                )
                """
            ),
            {"now": now},
        )

        # 3. review_sessions 整表重建：inspiration_id / distilled_draft 下线，
        #    viewpoint_id 成为 NOT NULL 主关联；已是新结构则整步跳过
        scols = {c["name"] for c in insp.get_columns("review_sessions")}
        if (
            "inspiration_id" in scols
            or "distilled_draft" in scols
            or "viewpoint_id" not in scols
        ):
            conn.execute(
                text(
                    """
                    CREATE TABLE review_sessions_new (
                        id INTEGER PRIMARY KEY,
                        viewpoint_id INTEGER NOT NULL REFERENCES viewpoints(id),
                        status VARCHAR(20),
                        phase VARCHAR(10),
                        started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        ended_at DATETIME,
                        analysis_json TEXT,
                        analysis_json_en TEXT
                    )
                    """
                )
            )
            old_rows = conn.execute(
                text(
                    "SELECT id, inspiration_id, viewpoint_id, status, phase,"
                    " started_at, ended_at, analysis_json, analysis_json_en"
                    " FROM review_sessions"
                )
            ).mappings().all()
            for row in old_rows:
                viewpoint_id = row["viewpoint_id"]
                if viewpoint_id is None:
                    # 第 2 步已保证每条灵感都有草稿观点，按来源灵感回填
                    viewpoint_id = conn.execute(
                        text(
                            "SELECT id FROM viewpoints"
                            " WHERE source_inspiration_id = :iid ORDER BY id LIMIT 1"
                        ),
                        {"iid": row["inspiration_id"]},
                    ).scalar()
                if viewpoint_id is None:
                    logger.warning(
                        "会话 #%s 找不到可关联的观点（灵感 #%s），迁移时跳过该行",
                        row["id"],
                        row["inspiration_id"],
                    )
                    continue
                conn.execute(
                    text(
                        "INSERT INTO review_sessions_new ("
                        " id, viewpoint_id, status, phase,"
                        " started_at, ended_at, analysis_json, analysis_json_en)"
                        " VALUES (:id, :viewpoint_id, :status, :phase,"
                        " :started_at, :ended_at, :analysis_json, :analysis_json_en)"
                    ),
                    {
                        "id": row["id"],
                        "viewpoint_id": viewpoint_id,
                        "status": row["status"],
                        "phase": row["phase"] or "polish",
                        "started_at": row["started_at"],
                        "ended_at": row["ended_at"],
                        "analysis_json": row["analysis_json"],
                        "analysis_json_en": row["analysis_json_en"],
                    },
                )
            conn.execute(text("DROP TABLE review_sessions"))
            conn.execute(
                text("ALTER TABLE review_sessions_new RENAME TO review_sessions")
            )

        # 4. inspirations 下线 status 列（灵感无状态机）
        icols = {c["name"] for c in insp.get_columns("inspirations")}
        if "status" in icols:
            try:
                conn.execute(text("ALTER TABLE inspirations DROP COLUMN status"))
            except OperationalError:
                # 旧版 SQLite 不支持 DROP COLUMN：整表重建去掉该列
                conn.execute(
                    text(
                        """
                        CREATE TABLE inspirations_new (
                            id INTEGER PRIMARY KEY,
                            content TEXT,
                            source_date DATE,
                            source_type VARCHAR(20),
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
                        "INSERT INTO inspirations_new ("
                        " id, content, source_date, source_type,"
                        " content_zh, content_en, original_lang,"
                        " title_zh, title_en, created_at, updated_at)"
                        " SELECT id, content, source_date, source_type,"
                        " content_zh, content_en, original_lang,"
                        " title_zh, title_en, created_at, updated_at"
                        " FROM inspirations"
                    )
                )
                conn.execute(text("DROP TABLE inspirations"))
                conn.execute(
                    text("ALTER TABLE inspirations_new RENAME TO inspirations")
                )

        # 5. 观点操作留痕表下线
        if "viewpoint_events" in set(insp.get_table_names()):
            conn.execute(text("DROP TABLE viewpoint_events"))

        # 6. viewpoints 补 is_viewpoint 列（观点判断前置到录入/编辑；
        #    存量观点保持 NULL=未判断，开会话时前端走 live 判断兜底）
        vcols = {c["name"] for c in insp.get_columns("viewpoints")}
        if "is_viewpoint" not in vcols:
            conn.execute(
                text("ALTER TABLE viewpoints ADD COLUMN is_viewpoint BOOLEAN")
            )

        # 7. 整表重建时期手写 DDL 丢了 started_at 的 DEFAULT CURRENT_TIMESTAMP，
        #    该时期新开的会话 started_at 为 NULL（ReviewSessionOut 序列化 500）。
        #    回填存量 NULL；新会话由 open_review_session 显式赋值兜底。
        conn.execute(
            text(
                "UPDATE review_sessions SET started_at=CURRENT_TIMESTAMP"
                " WHERE started_at IS NULL"
            )
        )
