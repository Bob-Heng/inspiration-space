import logging
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .ai.newapi import probe_gateway
from .auth import ensure_admin_user
from .db import Base, SessionLocal, engine, ensure_schema_upgrades
from .routers import ai_status as ai_status_router
from .routers import analysis as analysis_router
from .routers import auth as auth_router
from .routers import export as export_router
from .routers import inspirations as inspirations_router
from .routers import review as review_router
from .routers import settings as settings_router
from .routers import viewpoints as viewpoints_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    ensure_schema_upgrades()
    db = SessionLocal()
    try:
        ensure_admin_user(db)
    finally:
        db.close()
    await probe_gateway()
    # 启动对账：AI 可用时后台补齐缺失的译文/标题（不阻塞启动）
    import asyncio

    from .domain.reconcile import reconcile_i18n

    asyncio.create_task(reconcile_i18n())
    yield


app = FastAPI(title="灵感空间", lifespan=lifespan)

# Session 签名密钥缺失时每次启动随机生成，重启后所有会话失效
secret_key = config.SECRET_KEY
if not secret_key:
    secret_key = secrets.token_hex(32)
    logger.warning("未设置 INSPIRATION_SECRET_KEY，已随机生成临时密钥，重启后需重新登录")
app.add_middleware(SessionMiddleware, secret_key=secret_key, https_only=False)

# 开发环境：允许 Vite dev server 跨端口访问（携带 Cookie）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(inspirations_router.router)
app.include_router(ai_status_router.router)
app.include_router(analysis_router.router)
app.include_router(review_router.router)
app.include_router(settings_router.router)
app.include_router(viewpoints_router.router)
app.include_router(export_router.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# 桌面外壳模式：托管前端构建产物，非 /api 路径回退到 index.html（SPA 路由）
if getattr(sys, "frozen", False):
    # PyInstaller 打包模式：前端产物随包内嵌
    DIST_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "frontend_dist"
else:
    DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if DIST_DIR.exists():

    class SpaStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):  # type: ignore[override]
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                # Windows 下 path 已按 OS 分隔符归一化（api\xxx），统一再判断
                first_segment = path.replace("\\", "/").split("/", 1)[0]
                if exc.status_code == 404 and first_segment != "api":
                    # 前端路由（如 /login、/viewpoints）回退到 SPA 入口；API 404 保持 JSON
                    return await super().get_response("index.html", scope)
                raise

    app.mount("/", SpaStaticFiles(directory=DIST_DIR, html=True), name="spa")
