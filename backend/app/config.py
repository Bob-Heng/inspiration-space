import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
FROZEN = getattr(sys, "frozen", False)  # PyInstaller 打包后的 exe 运行模式

if FROZEN:
    # 打包模式：数据放用户目录（安装目录通常不可写）
    DATA_DIR = Path(
        os.environ.get(
            "INSPIRATION_DATA_DIR",
            Path(os.environ.get("LOCALAPPDATA", str(BACKEND_DIR))) / "InspirationSpace" / "data",
        )
    )
    ENV_FILE = Path(sys.executable).parent / ".env"  # 可选，供高级用户覆盖配置
else:
    DATA_DIR = BACKEND_DIR / "data"
    ENV_FILE = BACKEND_DIR / ".env"


def load_env_file() -> None:
    """从 .env 读取环境变量（不覆盖已有环境变量）。"""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_env_file()

DATABASE_PATH = Path(os.environ.get("INSPIRATION_DATABASE_PATH", DATA_DIR / "inspiration.db"))
ADMIN_PASSWORD = os.environ.get("INSPIRATION_ADMIN_PASSWORD")
SECRET_KEY = os.environ.get("INSPIRATION_SECRET_KEY")

NEWAPI_BASE_URL = os.environ.get("NEWAPI_BASE_URL")
NEWAPI_API_KEY = os.environ.get("NEWAPI_API_KEY")
NEWAPI_MODEL = os.environ.get("NEWAPI_MODEL")  # 留空则运行时从服务端 /models 自动取第一个
