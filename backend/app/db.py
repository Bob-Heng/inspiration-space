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
    """轻量结构升级：为存量库补充后加的列（幂等）。

    create_all 不会修改已有表；一阶段不引入 Alembic，逐条手写。
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("review_sessions")}
    if "analysis_json" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE review_sessions ADD COLUMN analysis_json TEXT")
            )
