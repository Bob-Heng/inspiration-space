"""原系统 Docx 历史数据迁移脚本（TASK-017，规则见 docs/03）。

迁移对象：
- 原系统/观点库/待审观点.docx → inspirations 表
  （28 条 = 27 条编号 + 1 段无编号游离文本；source_type=migration，
  逐条独立编号接在现有数据后；游离文本日期取 2026-04-21）
- 原系统/观点库/原始观点.docx → viewpoints 表
  （5 条；status=accepted，type=raw；解析 [分层][领域/圈层/学科/场景]，
  空标签位为 None；跨段条目按"序号."边界切割）

日期规则：条目内 [M.D] 简写 + 默认年份 2026 → ISO 日期。
幂等：按内容哈希判重，重复运行不产生重复数据。
灵感记录 7 篇 docx 不迁移（docs/03：内容已分布在待审队列与原始观点中）。

用法（用 backend/venv 的 python 运行）：
    python scripts/import_docx.py --parse-only            # 只解析对照，不写库
    python scripts/import_docx.py --db <副本路径>          # 对数据库副本试跑
    python scripts/import_docx.py                          # 对真实库执行
"""

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from docx import Document

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.domain.tags import LAYER_CODES, validate_layer, validate_tags  # noqa: E402
from app.models import Inspiration, Viewpoint  # noqa: E402

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

DEFAULT_YEAR = 2026
DEFAULT_SOURCE_DIR = REPO_ROOT.parent / "原系统" / "观点库"
DEFAULT_DB = REPO_ROOT / "backend" / "data" / "inspiration.db"

PENDING_DOCX = "待审观点.docx"
RAW_VIEWPOINTS_DOCX = "原始观点.docx"

# docs/03：队列第一条编号之前的无编号游离文本，日期取 4.21
FLOATING_TEXT_DATE = date(2026, 4, 21)

# 不入库的行：标题、文件说明、原摄取模块的状态门凭据（docs/03）
PENDING_SKIP_PREFIXES = ("上次摄取位置", "上次摄取执行", "（本文件")
VIEWPOINT_SKIP_PREFIXES = ("（经审议采纳",)

ITEM_HEAD_RE = re.compile(r"^(\d+)\.\[(\d{1,2})\.(\d{1,2})\](.*)$")
VIEWPOINT_HEAD_RE = re.compile(
    r"^(\d+)\.\[(\d{1,2})\.(\d{1,2})\]\[([道法术]?)\]\[([^\]]*)\](.*)$"
)


@dataclass
class ParsedInspiration:
    content: str
    source_date: date
    source_label: str  # 供对照报告：原编号或"游离文本"


@dataclass
class ParsedViewpoint:
    content: str
    source_date: date
    layer: str  # dao / fa / shu
    domain: str | None
    circle: str | None
    discipline: str | None
    scene: str | None
    source_label: str


@dataclass
class _ItemBuffer:
    month: int
    day: int
    label: str
    parts: list[str] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join(self.parts)


def _paragraph_texts(docx_path: Path) -> list[str]:
    """正文段落文本（跳过 Title 标题段与空段）。"""
    doc = Document(str(docx_path))
    return [
        p.text.strip()
        for p in doc.paragraphs
        if p.text.strip() and p.style.name != "Title"
    ]


def _iso_date(year: int, month: int, day: int) -> date:
    return date(year, month, day)


def parse_pending_queue(docx_path: Path, year: int = DEFAULT_YEAR) -> list[ParsedInspiration]:
    """解析待审观点.docx：编号条目 + 游离文本，跨段内容并入上一条。"""
    items: list[_ItemBuffer] = []
    current: _ItemBuffer | None = None
    for text in _paragraph_texts(docx_path):
        if text.startswith(PENDING_SKIP_PREFIXES):
            continue
        match = ITEM_HEAD_RE.match(text)
        if match:
            _, month, day, body = match.groups()
            current = _ItemBuffer(int(month), int(day), label=f"原编号 {match.group(1)}")
            current.parts.append(body.strip())
            items.append(current)
        elif current is None:
            current = _ItemBuffer(
                FLOATING_TEXT_DATE.month, FLOATING_TEXT_DATE.day, label="游离文本"
            )
            current.parts.append(text)
            items.append(current)
        else:
            current.parts.append(text)
    return [
        ParsedInspiration(
            content=item.text(),
            source_date=(
                FLOATING_TEXT_DATE
                if item.label == "游离文本"
                else _iso_date(year, item.month, item.day)
            ),
            source_label=item.label,
        )
        for item in items
    ]


def _parse_tag_slots(raw: str) -> tuple[str | None, str | None, str | None, str | None]:
    """`领域/圈层/学科/场景` 四标签位，空位为 None（如 `经济//经济学/文旅消费`）。"""
    slots = raw.split("/")
    if len(slots) > 4:
        raise ValueError(f"标签位超过 4 个：{raw!r}")
    slots += [""] * (4 - len(slots))
    domain, circle, discipline, scene = (slot.strip() or None for slot in slots)
    validate_tags(domain=domain, circle=circle, discipline=discipline, scene=scene)
    return domain, circle, discipline, scene


@dataclass
class _ViewpointBuffer:
    label: str
    source_date: date
    layer: str
    domain: str | None
    circle: str | None
    discipline: str | None
    scene: str | None
    parts: list[str] = field(default_factory=list)


def parse_raw_viewpoints(docx_path: Path, year: int = DEFAULT_YEAR) -> list[ParsedViewpoint]:
    """解析原始观点.docx：`序号.[日期][分层][标签]正文`，跨段按"序号."边界切割。"""
    items: list[_ViewpointBuffer] = []
    current: _ViewpointBuffer | None = None
    for text in _paragraph_texts(docx_path):
        if text.startswith(VIEWPOINT_SKIP_PREFIXES):
            continue
        match = VIEWPOINT_HEAD_RE.match(text)
        if match:
            number, month, day, layer_label, tags_raw, body = match.groups()
            if layer_label not in LAYER_CODES:
                raise ValueError(f"非法分层标记：{layer_label!r}（原编号 {number}）")
            layer = LAYER_CODES[layer_label]
            validate_layer(layer)
            domain, circle, discipline, scene = _parse_tag_slots(tags_raw)
            current = _ViewpointBuffer(
                label=f"原编号 {number}",
                source_date=_iso_date(year, int(month), int(day)),
                layer=layer,
                domain=domain,
                circle=circle,
                discipline=discipline,
                scene=scene,
                parts=[body.strip()],
            )
            items.append(current)
        elif current is not None:
            current.parts.append(text)
        else:
            raise ValueError(f"编号条目之前出现无法归类的段落：{text[:50]!r}")
    return [
        ParsedViewpoint(
            content="\n".join(item.parts),
            source_date=item.source_date,
            layer=item.layer,
            domain=item.domain,
            circle=item.circle,
            discipline=item.discipline,
            scene=item.scene,
            source_label=item.label,
        )
        for item in items
    ]


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class MigrateReport:
    source: str
    parsed: int
    inserted: int
    skipped: int
    inserted_ids: list[int] = field(default_factory=list)


def migrate_pending(db: Session, items: list[ParsedInspiration]) -> MigrateReport:
    existing = {
        content_hash(row.content)
        for row in db.scalars(
            select(Inspiration).where(Inspiration.source_type == "migration")
        )
    }
    report = MigrateReport(PENDING_DOCX, parsed=len(items), inserted=0, skipped=0)
    for item in items:
        if content_hash(item.content) in existing:
            report.skipped += 1
            continue
        inspiration = Inspiration(
            content=item.content,
            source_date=item.source_date,
            source_type="migration",
        )
        db.add(inspiration)
        db.flush()
        existing.add(content_hash(item.content))
        report.inserted += 1
        report.inserted_ids.append(inspiration.id)
    return report


def migrate_viewpoints(db: Session, items: list[ParsedViewpoint]) -> MigrateReport:
    existing = {content_hash(row.content) for row in db.scalars(select(Viewpoint))}
    report = MigrateReport(RAW_VIEWPOINTS_DOCX, parsed=len(items), inserted=0, skipped=0)
    for item in items:
        if content_hash(item.content) in existing:
            report.skipped += 1
            continue
        viewpoint = Viewpoint(
            type="raw",
            content=item.content,
            source_inspiration_id=None,
            source_date=item.source_date,
            layer=item.layer,
            domain=item.domain,
            circle=item.circle,
            discipline=item.discipline,
            scene=item.scene,
            status="accepted",
        )
        db.add(viewpoint)
        db.flush()
        existing.add(content_hash(item.content))
        report.inserted += 1
        report.inserted_ids.append(viewpoint.id)
    return report


def run_migration(db_path: Path, source_dir: Path) -> list[MigrateReport]:
    pending_items = parse_pending_queue(source_dir / PENDING_DOCX)
    viewpoint_items = parse_raw_viewpoints(source_dir / RAW_VIEWPOINTS_DOCX)
    engine = create_engine(f"sqlite:///{db_path}")
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as db:
        reports = [
            migrate_pending(db, pending_items),
            migrate_viewpoints(db, viewpoint_items),
        ]
        db.commit()
    return reports


def _print_reports(reports: list[MigrateReport]) -> None:
    print("\n迁移对照报告")
    print(f"{'来源':<14}{'源条数':>6}{'入库条数':>8}{'跳过条数':>8}")
    for report in reports:
        print(
            f"{report.source:<14}{report.parsed:>6}{report.inserted:>8}{report.skipped:>8}"
        )
        if report.inserted_ids:
            print(f"  新入库 id：{report.inserted_ids}")


def main() -> None:
    parser = argparse.ArgumentParser(description="原系统 Docx 历史数据迁移（TASK-017）")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="目标数据库路径")
    parser.add_argument(
        "--source-dir", type=Path, default=DEFAULT_SOURCE_DIR, help="原系统观点库目录"
    )
    parser.add_argument("--parse-only", action="store_true", help="只解析对照，不写库")
    args = parser.parse_args()

    pending_path = args.source_dir / PENDING_DOCX
    viewpoints_path = args.source_dir / RAW_VIEWPOINTS_DOCX
    for path in (pending_path, viewpoints_path):
        if not path.exists():
            sys.exit(f"源文件不存在：{path}")

    pending_items = parse_pending_queue(pending_path)
    viewpoint_items = parse_raw_viewpoints(viewpoints_path)
    print(f"解析 {PENDING_DOCX}：{len(pending_items)} 条（含游离文本）")
    for item in pending_items:
        print(f"  [{item.source_label}] {item.source_date} {item.content[:40]}…")
    print(f"解析 {RAW_VIEWPOINTS_DOCX}：{len(viewpoint_items)} 条")
    for item in viewpoint_items:
        tags = "/".join(
            slot or "" for slot in (item.domain, item.circle, item.discipline, item.scene)
        )
        print(
            f"  [{item.source_label}] {item.source_date} [{item.layer}][{tags}] "
            f"{item.content[:40]}…"
        )
    if args.parse_only:
        return

    if not args.db.exists():
        sys.exit(f"目标数据库不存在：{args.db}（严禁清库重建，请先确认路径）")
    print(f"\n目标数据库：{args.db}")
    reports = run_migration(args.db, args.source_dir)
    _print_reports(reports)


if __name__ == "__main__":
    main()
