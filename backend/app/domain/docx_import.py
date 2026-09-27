"""docx 导入的领域逻辑（TASK-018）：文本提取、AI 拆解、日期解析。

只切割不改写：content 保持原文；日期从 AI 返回的 date_text 解析为 ISO，
缺年份时取文件名年份（如 灵感记录26.5.docx → 2026），仍无法确定则留空。
"""

import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from sqlalchemy.orm import Session

from ..ai.base import LLMProvider
from ..ai.pipeline import run_structured_call
from ..ai.prompts.docx_split import PROMPT_VERSION, build_split_messages
from ..ai.schemas import DocxSplitResult

# 超出该长度的文档拒绝拆解（单次 LLM 调用的输入预算）
MAX_TEXT_CHARS = 20000


class DocxImportError(ValueError):
    """docx 读取或拆解输入不合法。"""


@dataclass
class SplitPreviewItem:
    content: str
    source_date: date | None


def extract_docx_text(file_bytes: bytes) -> str:
    """提取 docx 正文段落文本（跳过空段），段落间以换行连接。"""
    try:
        doc = Document(BytesIO(file_bytes))
    except (PackageNotFoundError, BadZipFile, KeyError, ValueError) as exc:
        raise DocxImportError("文件不是有效的 docx，请上传 Word 文档") from exc
    texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    if not texts:
        raise DocxImportError("文档没有可拆解的正文内容")
    return "\n".join(texts)


def default_year_from_filename(filename: str) -> int | None:
    """从文件名推断默认年份：优先四位年份（如 2026），其次两位简写（如 灵感记录26.5 → 2026）。"""
    match = re.search(r"(20\d{2})", filename)
    if match:
        return int(match.group(1))
    match = re.search(r"(?<!\d)(\d{2})\s*[.年]", filename)
    if match:
        return 2000 + int(match.group(1))
    return None


_FULL_DATE_RE = re.compile(r"(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*日?")
_SHORT_DATE_RE = re.compile(r"^(\d{1,2})\s*[.月/]\s*(\d{1,2})\s*日?$")


def resolve_date_text(date_text: str | None, default_year: int | None) -> date | None:
    """把 AI 返回的原文日期写法解析为 ISO 日期；无法解析时返回 None（日期留空）。"""
    if not date_text:
        return None
    text = date_text.strip()
    match = _FULL_DATE_RE.search(text)
    if match:
        year, month, day = (int(g) for g in match.groups())
    else:
        match = _SHORT_DATE_RE.match(text)
        if not match or default_year is None:
            return None
        year, month, day = default_year, int(match.group(1)), int(match.group(2))
    try:
        return date(year, month, day)
    except ValueError:
        return None


async def split_document(
    db: Session,
    provider: LLMProvider,
    *,
    document_text: str,
    filename: str,
) -> list[SplitPreviewItem]:
    """AI 拆解 + 日期解析，返回预览条目。拆解调用走结构化管线并留痕 ai_calls。"""
    if len(document_text) > MAX_TEXT_CHARS:
        raise DocxImportError(
            f"文档正文过长（{len(document_text)} 字，上限 {MAX_TEXT_CHARS}），请拆分后分批导入"
        )
    result = await run_structured_call(
        db,
        provider,
        prompt_version=PROMPT_VERSION,
        schema=DocxSplitResult,
        messages=build_split_messages(document_text),
    )
    default_year = default_year_from_filename(filename)
    return [
        SplitPreviewItem(
            content=item.content,
            source_date=resolve_date_text(item.date_text, default_year),
        )
        for item in result.items
    ]
