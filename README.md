# 灵感空间 v2（InspirationSpace）

以"观点"为本体的个人知识整理与认知构建系统 —— v2 单机 Web 应用。技术栈：FastAPI + SQLite（后端），Vite + React + Tailwind CSS（前端）。

项目背景、术语定义与任务拆解见上级目录的 `README.md` 与 `docs/`。

## 目录结构

- `backend/`：FastAPI 后端（Python 虚拟环境在 `backend/venv/`）
- `frontend/`：Vite + React + Tailwind 前端
- `scripts/`：运维与数据脚本（后续任务使用）

## 快速启动（推荐）

**桌面模式**：双击根目录 `灵感空间.vbs`——无控制台窗口，自动内嵌启动后端并打开应用窗口（使用系统 WebView2）。若 8000 端口已有后端在运行，窗口会直接附着到它。

**开发模式**：双击 `启动.bat`，自动各开一个窗口分别启动后端与前端（前端改动即时生效）。打开 <http://localhost:5173> 使用。

注意：两种模式都是前台进程——桌面模式关闭应用窗口即停止，开发模式关闭对应命令行窗口即停止。

## 启动后端

前提：系统 Python 3.13（anaconda）可用；首次启动前在 `backend/` 下创建 `.env`（模板见 `backend/.env.example`），至少配置 `INSPIRATION_ADMIN_PASSWORD`（首次启动时以此创建管理员 admin，密码哈希入库，之后该变量不再生效）与 `INSPIRATION_SECRET_KEY`（Session 签名密钥，缺省时每次启动随机生成、重启后需重新登录）。

双击 `backend/run.bat`，或手动执行：

```bash
cd backend
python -m venv venv                # 仅首次
venv/Scripts/pip install -r requirements.txt   # 仅首次或依赖变更后
venv/Scripts/uvicorn app.main:app --reload --port 8000
```

启动时自动建表（SQLite，数据文件 `backend/data/inspiration.db`）。健康检查：<http://localhost:8000/api/health>，接口文档：<http://localhost:8000/docs>。除 `/api/health` 与 `/api/auth/login` 外，所有接口需登录。

数据库 schema 变更（开发期）：删除 `backend/data/inspiration.db` 后重启即可重建；也可手动执行 `venv/Scripts/python -m app.init_db`（幂等）。

## 启动前端

前提：Node.js 已安装（本机位于 `C:\Program Files\nodejs`，Git Bash 中需先 `export PATH="/c/Program Files/nodejs:$PATH"`）。

双击 `frontend/run.bat`，或手动执行：

```bash
cd frontend
npm install    # 仅首次或依赖变更后
npm run dev
```

开发服务器：<http://localhost:5173>。需后端同时运行：未登录自动跳转登录页，登录后首页为"灵感录入与队列"（录入、关键词搜索、状态过滤、编辑、删除）。

## 开发

```bash
cd backend && venv/Scripts/python -m pytest   # 后端单元测试（领域状态机、标签校验）
```
