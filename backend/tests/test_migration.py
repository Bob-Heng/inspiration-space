"""TASK-017 迁移脚本单元测试：解析规则、日期转换、空标签位、幂等。"""

import sys
from datetime import date
from pathlib import Path

import pytest
from docx import Document
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from app.db import Base  # noqa: E402
from app import models  # noqa: E402,F401  # 确保表注册到 metadata
import import_docx  # noqa: E402

REAL_SOURCE_DIR = Path(__file__).resolve().parents[3] / "原系统" / "观点库"


def _make_docx(path: Path, paragraphs: list[tuple[str, str]]) -> Path:
    """按 (样式, 文本) 列表生成测试 docx。"""
    doc = Document()
    for style, text in paragraphs:
        doc.add_paragraph(text, style=style)
    doc.save(str(path))
    return path


@pytest.fixture
def pending_docx(tmp_path) -> Path:
    return _make_docx(
        tmp_path / "待审观点.docx",
        [
            ("Title", "待审观点（审议队列）"),
            ("Normal", "上次摄取位置：灵感记录26.9.docx，最后一条日期：9.8"),
            ("Normal", "（本文件为审议队列：未经审议，不含分层分类。）"),
            ("Normal", "游离文本段落，独立于编号条目。"),
            ("Normal", "1.[5.2]第一条正文。"),
            ("Normal", "第一条的续段。"),
            ("Normal", "2.[9.8]第二条正文。"),
            ("Normal", "上次摄取执行：2026-09-12"),
        ],
    )


@pytest.fixture
def viewpoints_docx(tmp_path) -> Path:
    return _make_docx(
        tmp_path / "原始观点.docx",
        [
            ("Title", "原始观点"),
            ("Normal", "（经审议采纳/悬置/否定的本人原创观点，按序列入库。）"),
            ("Normal", "1.[2.2][法][经济//经济学/文旅消费]第一段。"),
            ("Normal", "条目一的第二段。"),
            ("Normal", "条目一的第三段。"),
            ("Normal", "2.[4.21][术][//哲学/自我管理]另一条。"),
        ],
    )


class TestParsePendingQueue:
    def test_条数与游离文本独立成条(self, pending_docx):
        items = import_docx.parse_pending_queue(pending_docx)
        assert len(items) == 3
        floating = items[0]
        assert floating.source_label == "游离文本"
        assert floating.source_date == date(2026, 4, 21)
        assert floating.content == "游离文本段落，独立于编号条目。"

    def test_日期转换_简写加默认年份(self, pending_docx):
        items = import_docx.parse_pending_queue(pending_docx)
        assert items[1].source_date == date(2026, 5, 2)
        assert items[2].source_date == date(2026, 9, 8)

    def test_跨段并入上一条(self, pending_docx):
        items = import_docx.parse_pending_queue(pending_docx)
        assert items[1].content == "第一条正文。\n第一条的续段。"
        assert items[2].content == "第二条正文。"

    def test_头部与摄取记录行不入库(self, pending_docx):
        items = import_docx.parse_pending_queue(pending_docx)
        for item in items:
            assert "上次摄取" not in item.content
            assert "本文件为审议队列" not in item.content
            assert "待审观点（审议队列）" not in item.content


class TestParseRawViewpoints:
    def test_跨段条目按序号边界切割(self, viewpoints_docx):
        items = import_docx.parse_raw_viewpoints(viewpoints_docx)
        assert len(items) == 2
        assert items[0].content == "第一段。\n条目一的第二段。\n条目一的第三段。"
        assert items[1].content == "另一条。"

    def test_分层与日期(self, viewpoints_docx):
        items = import_docx.parse_raw_viewpoints(viewpoints_docx)
        assert items[0].layer == "fa"
        assert items[0].source_date == date(2026, 2, 2)
        assert items[1].layer == "shu"
        assert items[1].source_date == date(2026, 4, 21)

    def test_空标签位为None(self, viewpoints_docx):
        items = import_docx.parse_raw_viewpoints(viewpoints_docx)
        first = items[0]
        assert (first.domain, first.circle, first.discipline, first.scene) == (
            "经济",
            None,
            "经济学",
            "文旅消费",
        )
        second = items[1]
        assert (second.domain, second.circle) == (None, None)
        assert (second.discipline, second.scene) == ("哲学", "自我管理")

    def test_非法标签值报错(self, tmp_path):
        path = _make_docx(
            tmp_path / "原始观点.docx",
            [("Normal", "1.[2.2][法][不存在的领域//经济学/文旅消费]正文。")],
        )
        with pytest.raises(ValueError, match="标签值不在词表内"):
            import_docx.parse_raw_viewpoints(path)


@pytest.fixture
def migrated_db(tmp_path, pending_docx, viewpoints_docx, monkeypatch):
    """在临时数据库上执行两次迁移，返回 (db_path, source_dir)。"""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    source_dir = tmp_path
    reports_1 = import_docx.run_migration(db_path, source_dir)
    reports_2 = import_docx.run_migration(db_path, source_dir)
    return db_path, reports_1, reports_2


class TestMigrationIdempotency:
    def test_首次入库条数(self, migrated_db):
        _, reports_1, _ = migrated_db
        pending_report, viewpoint_report = reports_1
        assert (pending_report.parsed, pending_report.inserted, pending_report.skipped) == (3, 3, 0)
        assert (viewpoint_report.parsed, viewpoint_report.inserted, viewpoint_report.skipped) == (2, 2, 0)

    def test_重复运行不产生重复数据(self, migrated_db):
        _, _, reports_2 = migrated_db
        for report in reports_2:
            assert report.inserted == 0
            assert report.skipped == report.parsed

    def test_入库字段正确(self, migrated_db):
        db_path, _, _ = migrated_db
        engine = create_engine(f"sqlite:///{db_path}")
        session_factory = sessionmaker(bind=engine)
        with session_factory() as db:
            inspirations = list(db.scalars(select(models.Inspiration).order_by(models.Inspiration.id)))
            assert len(inspirations) == 3
            assert all(i.source_type == "migration" and i.status == "pending" for i in inspirations)
            assert inspirations[0].source_date == date(2026, 4, 21)

            viewpoints = list(db.scalars(select(models.Viewpoint).order_by(models.Viewpoint.id)))
            assert len(viewpoints) == 2
            assert all(v.type == "raw" and v.status == "accepted" for v in viewpoints)
            assert viewpoints[0].layer == "fa"
            assert viewpoints[0].circle is None
            assert viewpoints[0].source_inspiration_id is None


@pytest.mark.skipif(
    not (REAL_SOURCE_DIR / "待审观点.docx").exists(), reason="原系统文件不在本机"
)
class TestRealSourceParse:
    """对真实原系统文件的解析对照（docs/03 盘点条数）。"""

    def test_待审观点28条(self):
        items = import_docx.parse_pending_queue(REAL_SOURCE_DIR / "待审观点.docx")
        assert len(items) == 28
        assert items[0].source_label == "游离文本"
        assert items[0].source_date == date(2026, 4, 21)
        assert items[0].content.startswith("化势是灵活的")
        assert items[1].source_date == date(2026, 5, 2)
        assert items[-1].source_date == date(2026, 9, 8)

    def test_原始观点5条(self):
        items = import_docx.parse_raw_viewpoints(REAL_SOURCE_DIR / "原始观点.docx")
        assert len(items) == 5
        化势 = items[2]
        assert 化势.layer == "shu"
        assert 化势.domain is None and 化势.circle is None
        assert 化势.discipline == "经济学" and 化势.scene == "商业创业"
        assert 化势.source_date == date(2026, 4, 21)
        assert 化势.content.count("\n") == 2  # 跨三段
