"""TASK-018 docx 导入单元测试：文本提取、文件名年份、日期解析、AI 拆解留痕。"""

import asyncio
import json
from datetime import date
from io import BytesIO

import pytest
from docx import Document
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.ai import LLMProvider, Message
from app.domain.docx_import import (
    DocxImportError,
    default_year_from_filename,
    extract_docx_text,
    resolve_date_text,
    split_document,
)
from app.models import AiCall, Base


def _docx_bytes(paragraphs: list[str]) -> bytes:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


class FakeProvider(LLMProvider):
    provider_name = "fake"
    model = "fake-model"

    def __init__(self, reply: str) -> None:
        self.reply = reply

    async def generate(self, messages: list[Message]) -> str:
        return self.reply


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


class TestExtractDocxText:
    def test_提取段落并跳过空段(self):
        data = _docx_bytes(["第一段", "", "第二段"])
        assert extract_docx_text(data) == "第一段\n第二段"

    def test_非docx报错(self):
        with pytest.raises(DocxImportError, match="有效的 docx"):
            extract_docx_text(b"not a docx")

    def test_空文档报错(self):
        with pytest.raises(DocxImportError, match="没有可拆解的正文"):
            extract_docx_text(_docx_bytes(["", "  "]))


class TestDefaultYearFromFilename:
    @pytest.mark.parametrize(
        "filename, expected",
        [
            ("灵感记录26.5.docx", 2026),
            ("灵感记录26.12.docx", 2026),
            ("2025年随笔.docx", 2025),
            ("随便起的名字.docx", None),
        ],
    )
    def test_文件名年份推断(self, filename, expected):
        assert default_year_from_filename(filename) == expected


class TestResolveDateText:
    @pytest.mark.parametrize(
        "date_text, default_year, expected",
        [
            ("5.2", 2026, date(2026, 5, 2)),
            ("9.08", 2026, date(2026, 9, 8)),
            ("5.2", None, None),
            ("2026-05-02", None, date(2026, 5, 2)),
            ("2026年5月2日", None, date(2026, 5, 2)),
            ("2026/5/2", 2020, date(2026, 5, 2)),
            (None, 2026, None),
            ("", 2026, None),
            ("乱七八糟", 2026, None),
            ("13.40", 2026, None),
        ],
    )
    def test_日期解析(self, date_text, default_year, expected):
        assert resolve_date_text(date_text, default_year) == expected


class TestSplitDocument:
    def test_拆解结果解析日期并留痕(self, db_session):
        reply = json.dumps(
            {
                "items": [
                    {"content": "条目一", "date_text": "5.2"},
                    {"content": "条目二", "date_text": None},
                    {"content": "条目三", "date_text": "无法解析"},
                ]
            },
            ensure_ascii=False,
        )
        items = asyncio.run(
            split_document(
                db_session,
                FakeProvider(reply),
                document_text="5.2\n条目一\n条目二\n条目三",
                filename="灵感记录26.5.docx",
            )
        )
        assert [item.content for item in items] == ["条目一", "条目二", "条目三"]
        assert items[0].source_date == date(2026, 5, 2)
        assert items[1].source_date is None
        assert items[2].source_date is None
        calls = list(db_session.scalars(select(AiCall)))
        assert len(calls) == 1
        assert calls[0].prompt_version == "docx_split.v1"
        assert calls[0].provider == "fake"

    def test_正文过长被拒绝(self, db_session):
        with pytest.raises(DocxImportError, match="过长"):
            asyncio.run(
                split_document(
                    db_session,
                    FakeProvider("{}"),
                    document_text="字" * 20001,
                    filename="x.docx",
                )
            )
