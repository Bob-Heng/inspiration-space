"""启动对账：大模型可用时，补齐所有缺失的译文与标题（后台任务，不阻塞启动）。

缺失判定统一为"字段为 NULL"：写入路径在 LLM 失败时置空而非写兜底内容，
因此对账只需扫 NULL 即可，无需区分"未翻译"与"兜底"。
"""

import logging

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Inspiration, ReviewMessage, ReviewSession, Viewpoint
from .titles import make_titles
from .translation import bilingual_analysis, make_bilingual

logger = logging.getLogger(__name__)


async def reconcile_i18n() -> None:
    """补齐缺失的双语版本。任一失败只记日志，下次启动再试。"""
    db = SessionLocal()
    fixed = 0
    try:
        for model in (Inspiration, Viewpoint, ReviewMessage):
            for row in db.scalars(select(model)).all():
                lang = row.original_lang or "zh"
                missing = [
                    f"content_{x}"
                    for x in ("zh", "en")
                    if getattr(row, f"content_{x}") is None
                ]
                if not missing:
                    continue
                bilingual = await make_bilingual(db, row.content, lang)
                for field in missing:
                    setattr(row, field, bilingual[field])
                db.commit()
                fixed += 1
        for model in (Inspiration, Viewpoint):
            for row in db.scalars(select(model)).all():
                if row.title_zh and row.title_en:
                    continue
                titles = await make_titles(db, row.content)
                if titles["title_zh"] is None:
                    continue  # LLM 仍不可用，保持 NULL 等下次
                row.title_zh = row.title_zh or titles["title_zh"]
                row.title_en = row.title_en or titles["title_en"]
                db.commit()
                fixed += 1
        for session in db.scalars(select(ReviewSession)).all():
            if session.analysis_json and not session.analysis_json_en:
                session.analysis_json_en = await bilingual_analysis(
                    db, session.analysis_json
                )
                db.commit()
                fixed += 1
    except Exception:
        logger.exception("启动对账异常")
    finally:
        db.close()
    if fixed:
        logger.info("启动对账完成：补齐 %d 项", fixed)
