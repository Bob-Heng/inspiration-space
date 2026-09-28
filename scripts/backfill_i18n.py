"""存量数据双语回填：把既有中文内容翻译出英文版本（幂等，可重复运行）。

用法（网关在线时）：
  backend/venv/Scripts/python scripts/backfill_i18n.py [数据库路径]
缺省作用于开发库；安装版数据库传入 %LOCALAPPDATA%\\InspirationSpace\\data\\inspiration.db。
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

if len(sys.argv) > 1:
    os.environ["INSPIRATION_DATABASE_PATH"] = sys.argv[1]

from sqlalchemy import select  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.domain.translation import bilingual_analysis, detect_lang, make_bilingual  # noqa: E402
from app.models import Inspiration, ReviewMessage, ReviewSession, Viewpoint  # noqa: E402


async def main() -> None:
    Base.metadata.create_all(engine)
    from app.db import ensure_schema_upgrades

    ensure_schema_upgrades()
    db = SessionLocal()
    done = skipped = failed = 0
    try:
        for model in (Inspiration, Viewpoint, ReviewMessage):
            for row in db.scalars(select(model)).all():
                # 已回填过（两版本不同）则跳过
                if row.content_en and row.content_en != row.content:
                    skipped += 1
                    continue
                lang = detect_lang(row.content)
                try:
                    bilingual = await make_bilingual(db, row.content, lang)
                    row.content_zh = bilingual["content_zh"]
                    row.content_en = bilingual["content_en"]
                    row.original_lang = bilingual["original_lang"]
                    db.commit()
                    done += 1
                    print(f"[{model.__tablename__}#{row.id}] ok ({lang})")
                except Exception as exc:
                    db.rollback()
                    failed += 1
                    print(f"[{model.__tablename__}#{row.id}] FAIL: {exc}")
        for session in db.scalars(select(ReviewSession)).all():
            if session.analysis_json and not session.analysis_json_en:
                session.analysis_json_en = await bilingual_analysis(
                    db, session.analysis_json
                )
                db.commit()
                print(f"[review_sessions#{session.id}] analysis_en ok")
    finally:
        db.close()
    print(f"\n完成：翻译 {done}，跳过 {skipped}，失败 {failed}")


if __name__ == "__main__":
    asyncio.run(main())
