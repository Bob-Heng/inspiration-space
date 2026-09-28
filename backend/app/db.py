from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATA_DIR, DATABASE_PATH


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
    """
    from sqlalchemy import inspect, text

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
        tables = set(insp.get_table_names())
        for legacy in ("content_translations", "viewpoint_translations", "content_i18n"):
            if legacy in tables:
                conn.execute(text(f"DROP TABLE {legacy}"))
