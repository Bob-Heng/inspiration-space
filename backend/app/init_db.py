"""建库脚本：创建全部表。可重复执行（已存在的表不受影响）。

用法：在 backend/ 下执行 `venv/Scripts/python -m app.init_db`
"""

from .db import Base, engine
from . import models  # noqa: F401  确保模型已注册


def main() -> None:
    Base.metadata.create_all(engine)
    tables = sorted(Base.metadata.tables)
    print(f"建库完成，共 {len(tables)} 张表：{', '.join(tables)}")


if __name__ == "__main__":
    main()
