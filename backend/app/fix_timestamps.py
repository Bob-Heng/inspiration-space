"""既有数据时间戳订正脚本（一次性）。

背景：修复前 ended_at 由应用层 datetime.now() 写入（本地时间，naive），
其余时间字段由数据库 func.now()（CURRENT_TIMESTAMP）写入（UTC，naive），两者混用。
修复后统一为 UTC（见 app/timeutils.py）。本脚本只处理存量数据：

- review_sessions.ended_at：本地时间 naive → 减去本机时区偏移转为 UTC naive；
- 其余时间字段本就是 UTC naive，按"naive 视为 UTC"无需改写，仅统计输出。

运行前自动备份数据库文件；运行后写标记文件防止重复执行。
用法：在 backend/ 下执行 `venv/Scripts/python -m app.fix_timestamps`
"""

import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import DATABASE_PATH

MARKER_PATH = DATABASE_PATH.with_suffix(DATABASE_PATH.suffix + ".tzfix.done")

TABLES_WITH_TIME = {
    "users": ["created_at"],
    "inspirations": ["created_at", "updated_at"],
    "viewpoints": ["created_at", "updated_at"],
    "viewpoint_relations": ["created_at"],
    "review_sessions": ["started_at", "ended_at"],
    "review_messages": ["created_at"],
    "review_decisions": ["created_at"],
    "ai_calls": ["created_at"],
}


def _parse(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析的时间值：{value!r}")


def main() -> None:
    if not DATABASE_PATH.exists():
        print(f"数据库不存在：{DATABASE_PATH}", file=sys.stderr)
        sys.exit(1)
    if MARKER_PATH.exists():
        print(f"已执行过订正（标记文件 {MARKER_PATH.name} 存在），不再重复运行。")
        return

    backup = DATABASE_PATH.with_name(
        f"{DATABASE_PATH.name}.bak-{datetime.now():%Y%m%d-%H%M%S}"
    )
    shutil.copy2(DATABASE_PATH, backup)
    print(f"已备份数据库到 {backup.name}")

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, ended_at FROM review_sessions WHERE ended_at IS NOT NULL"
        ).fetchall()
        local_offset = datetime.now().astimezone().utcoffset()
        for session_id, ended_at in rows:
            local_value = _parse(ended_at)
            utc_value = (local_value - local_offset).replace(tzinfo=timezone.utc)
            conn.execute(
                "UPDATE review_sessions SET ended_at = ? WHERE id = ?",
                (utc_value.strftime("%Y-%m-%d %H:%M:%S.%f"), session_id),
            )
            print(f"review_sessions #{session_id} ended_at: {ended_at} (本地) -> {utc_value:%Y-%m-%d %H:%M:%S.%f} (UTC)")
        conn.commit()

        print("各表时间字段行数（其余字段为 UTC naive，无需改写）：")
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        for table, columns in TABLES_WITH_TIME.items():
            if table not in existing:
                continue
            existing_columns = {
                row[1] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            for column in columns:
                if column not in existing_columns:
                    continue
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL"
                ).fetchone()[0]
                print(f"  {table}.{column}: {count} 行")
    finally:
        conn.close()

    MARKER_PATH.write_text(
        f"timestamps fixed at {datetime.now(timezone.utc).isoformat()}\n",
        encoding="utf-8",
    )
    print(f"订正完成，共修正 {len(rows)} 行 ended_at；已写入标记文件 {MARKER_PATH.name}")


if __name__ == "__main__":
    main()
