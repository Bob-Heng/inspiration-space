"""存量数据标题回填：为已有灵感/观点生成中英双语标题（幂等）。

用法（网关在线时）：
  backend/venv/Scripts/python scripts/backfill_titles.py [数据库路径]
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

if len(sys.argv) > 1:
    os.environ["INSPIRATION_DATABASE_PATH"] = sys.argv[1]

from sqlalchemy import select  # noqa: E402

from app.db import Base, SessionLocal, engine, ensure_schema_upgrades  # noqa: E402
from app.domain.titles import make_titles  # noqa: E402
from app.models import Inspiration, Viewpoint  # noqa: E402


async def main() -> None:
    Base.metadata.create_all(engine)
    ensure_schema_upgrades()
    db = SessionLocal()
    done = skipped = failed = 0
    try:
        for model in (Inspiration, Viewpoint):
            for row in db.scalars(select(model)).all():
                if row.title_zh and row.title_en:
                    skipped += 1
                    continue
                try:
                    titles = await make_titles(db, row.content)
                    row.title_zh = titles["title_zh"]
                    row.title_en = titles["title_en"]
                    db.commit()
                    done += 1
                    print(f"[{model.__tablename__}#{row.id}] {titles['title_zh']}")
                except Exception as exc:
                    db.rollback()
                    failed += 1
                    print(f"[{model.__tablename__}#{row.id}] FAIL: {exc}")
    finally:
        db.close()
    print(f"\n完成：生成 {done}，跳过 {skipped}，失败 {failed}")


if __name__ == "__main__":
    asyncio.run(main())
