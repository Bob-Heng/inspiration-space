"""观点库 Docx 导出（TASK-019）：原始观点与分类观点，沿用原系统条目格式（docs/02 §6）。

条目行格式：`序号.[日期][分层][领域/圈层/学科/场景]正文`，纯文字编号，不用 markdown。
- 序号为观点库内编号（id），保证导出件可回溯；
- 日期为原系统简写 M.D；无日期/无分层/空标签位均留空位（与空标签位约定一致）；
- 正文跨段落在 docx 中还原为多个段落；
- 非采纳状态在条目末尾保留标记：【悬置】/【已否定】（原始观点文档三种状态均列入）；
- 分类视图：道/法/术三节，已否定不列入，悬置保留标记，组内按来源日期排序。
"""

from datetime import date
from io import BytesIO

from docx import Document

from ..models import Viewpoint
from .tags import LAYER_LABELS

STATUS_MARKERS = {"suspended": "【悬置】", "rejected": "【已否定】"}

RAW_VIEWPOINTS_HEADER = "（经审议采纳/悬置/否定的本人原创观点，按序列入库。格式：序号.[日期][分层][标签]正文）"
CLASSIFIED_HEADER = "（分类观点视图：道/法/术三节，已否定不列入，悬置保留标记，组内按来源日期排序。）"


def _format_date(source_date: date | None) -> str:
    if source_date is None:
        return ""
    return f"{source_date.month}.{source_date.day}"


def _format_tags(viewpoint: Viewpoint) -> str:
    return "/".join(
        slot or ""
        for slot in (
            viewpoint.domain,
            viewpoint.circle,
            viewpoint.discipline,
            viewpoint.scene,
        )
    )


def format_viewpoint_line(viewpoint: Viewpoint) -> str:
    """单条观点的首行（序号+日期+分层+标签+首段正文）。"""
    layer = LAYER_LABELS.get(viewpoint.layer, "") if viewpoint.layer else ""
    head = (
        f"{viewpoint.id}.[{_format_date(viewpoint.source_date)}]"
        f"[{layer}][{_format_tags(viewpoint)}]"
    )
    first_paragraph = viewpoint.content.split("\n", 1)[0]
    marker = STATUS_MARKERS.get(viewpoint.status, "")
    return f"{head}{first_paragraph}{marker}"


def _add_viewpoint(doc: Document, viewpoint: Viewpoint) -> None:
    """写入一条观点：首行带序号/日期/标签，续段单独成段。"""
    doc.add_paragraph(format_viewpoint_line(viewpoint))
    paragraphs = viewpoint.content.split("\n")
    for continuation in paragraphs[1:]:
        doc.add_paragraph(continuation)


def _save(doc: Document) -> bytes:
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def build_viewpoints_docx(viewpoints: list[Viewpoint]) -> bytes:
    """原始观点.docx：全部观点按库内编号排序。"""
    doc = Document()
    doc.add_heading("原始观点", level=0)
    doc.add_paragraph(RAW_VIEWPOINTS_HEADER)
    for viewpoint in viewpoints:
        _add_viewpoint(doc, viewpoint)
    return _save(doc)


def build_classified_docx(groups: dict[str, list[Viewpoint]]) -> bytes:
    """分类观点.docx：单个文档三节（道/法/术）。"""
    doc = Document()
    doc.add_heading("分类观点", level=0)
    doc.add_paragraph(CLASSIFIED_HEADER)
    for layer_code in ("dao", "fa", "shu"):
        doc.add_heading(LAYER_LABELS[layer_code], level=1)
        for viewpoint in groups.get(layer_code, []):
            _add_viewpoint(doc, viewpoint)
    return _save(doc)
