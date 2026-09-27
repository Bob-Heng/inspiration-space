"""时间戳统一约定：存储一律 UTC，ORM 读写均为 timezone-aware datetime。

SQLite 没有时区类型，物理存储为 naive UTC 字符串（与 CURRENT_TIMESTAMP 输出格式一致）；
UtcDateTime 在写入时把任意 aware datetime 归一到 UTC（naive 输入按 UTC 处理），
读取时统一附加 UTC 时区，保证应用层拿到的永远是 aware UTC。
API 输出由 Pydantic 序列化为带时区的 ISO 8601，前端展示时转本地时区。
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    """当前时刻的 aware UTC datetime。"""
    return datetime.now(timezone.utc)


class UtcDateTime(TypeDecorator):
    """存 naive UTC、读 aware UTC 的 DateTime 类型。"""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value  # naive 按 UTC 存储
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc)
        return value.replace(tzinfo=timezone.utc)
