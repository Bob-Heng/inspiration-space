# 灵感空间 InspirationSpace

以"观点"为本体的个人知识整理与认知构建系统。

灵感空间不是笔记软件，也不是 AI 聊天机器人。它的核心对象是**观点**：

> 灵感录入 → AI 审议分析 → 人机讨论 → 用户决策 → 观点库 → 相近/冲突关系 → 道/法/术分类视图

AI 只负责分析、提问、提出候选——**任何正式知识的变更都由你确认后落库**。AI 是协作者，不是数据库管理员。

## 功能特性

- **灵感录入**：界面直接输入为主，外部 docx 文档导入（AI 拆解归纳）为辅
- **审议工作台**：三栏布局（待审队列 / 灵感+AI 分析+讨论 / 关联观点与标签建议），底部决策栏（采纳 / 修改后采纳 / 否定 / 暂缓），审议现场持久化，关窗重开不丢
- **AI 审议分析**：采纳理由与最强反对理由（必须同时给出）、道/法/术分层建议、四标签族建议（领域/圈层/学科/场景）、与已有观点的相近/冲突关系、第一轮疑问
- **观点库**：多维筛选（分层/状态/标签/日期）、相近/冲突关系（冲突双方自动悬置并互记编号）、无损合并与拆分、来源灵感反查、道/法/术分类观点视图
- **观点状态机**：采纳 / 悬置 / 否定；AI 无权替你裁决
- **Docx 导出**：原始观点与分类观点一键导出
- **AI 服务可配置**：OpenAI / DeepSeek / Kimi / 智谱 / 自定义 OpenAI 兼容网关，界面化设置，密钥只回显末 4 位
- **桌面应用形态**：单机运行，数据全部本地（SQLite），无云端依赖
- **可追溯**：观点 → 来源灵感 → 审议会话 → 你的最终决定，全链留痕

## 安装（Windows）

1. 下载 [Releases](../../releases) 页面的 `InspirationSpace-Setup-x.x.x.exe`
2. 双击安装（未签名，SmartScreen 提示时选择"仍要运行"）
3. 桌面双击"灵感空间"，首次使用设置你的账号即可

系统要求：Windows 10/11（自带 WebView2 运行时）。

数据存放在 `%LOCALAPPDATA%\InspirationSpace\data`（灵感、观点、审议记录、设置），卸载不会删除。

## 使用要点

- **AI 服务**：首次使用 AI 功能前，在"审议工作台 → 右侧 AI 服务设置"选择服务商并填入 API Key（点"测试连接"拉取模型列表后选择）。也支持本地 New API 等 OpenAI 兼容网关（选"自定义"）
- **修改后采纳**：面板停靠右侧，可直接拖选 AI 回复的段落复制到修改框
- **密码**：单机应用没有找回密码功能，初始化时请妥善保管

## 从源码运行

要求：Python 3.13+、Node.js 20+。

```bash
# 后端
cd backend
python -m venv venv
venv/Scripts/pip install -r requirements.txt   # Windows
venv/Scripts/uvicorn app.main:app --reload --port 8000

# 前端（另开终端）
cd frontend
npm install
npm run dev    # http://localhost:5173
```

桌面模式（内嵌后端 + WebView2 窗口）：`backend/venv/Scripts/pythonw backend/desktop.py`

测试：`cd backend && venv/Scripts/python -m pytest`

打包：`backend` 目录下运行 PyInstaller（见 `installer/setup.iss` 对应产物路径），再用 Inno Setup 编译安装包。

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python · FastAPI · SQLAlchemy · SQLite |
| 前端 | Vite · React · Tailwind CSS |
| 桌面外壳 | pywebview（系统 WebView2） |
| AI 接入 | OpenAI 兼容协议（可替换 Provider） |
| 打包 | PyInstaller + Inno Setup |

## 隐私

全部数据（灵感、观点、讨论记录、账号、AI 配置）仅存于你本机的 SQLite 文件，不经过任何第三方服务器——除了你主动配置的 AI 服务商（调用内容仅限审议所需的上下文）。

## License

[MIT](LICENSE)
