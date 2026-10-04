# Design — 灵感空间

A locked design system for this app. Every page redesign reads this file before
emitting code. Do not regenerate per page — extend or amend this file when the
system needs to grow.

<!-- Hallmark · genre: playful · macrostructure: Workbench (app) · design-system: design.md · designed-as-app -->

## Genre

playful（post-Linear soft school），以 editorial 的克制约束排版。
产品本体是文字与观点：活泼只落在动效与点缀色上，不落在排版噪音上。

## Macrostructure family

- App pages: **Workbench**——页头（灵感空间 + 副标题）+ 功能主区；审议工作台为三栏独立滚动。
- Auth pages: 居中单卡 + 全屏开场动效（登录序列）。
- Content pages: 观点详情等，排版优先。

## Theme

白底为纸，深靛为墨，星空蓝为主点缀，流星金只做高光（呼应 logo：深蓝星空 + 金色流星）。

- `--color-paper`    oklch(98.8% 0.004 95)    暖白纸面
- `--color-paper-2`  oklch(96.8% 0.008 255)   微蓝面板
- `--color-ink`      oklch(34% 0.035 275)     深靛墨
- `--color-ink-2`    oklch(52% 0.028 275)     次级墨
- `--color-rule`     oklch(90.5% 0.01 265)    分隔线/边框
- `--color-accent`   oklch(58% 0.16 258)      星空蓝（主点缀）
- `--color-accent-2` oklch(82% 0.15 88)       流星金（仅高光：光束、粒子、焦点）
- `--color-accent-ink` oklch(99% 0.003 95)    accent 上的文字
- `--color-focus`    = accent
- `--color-danger`   oklch(58% 0.19 28)       错误/危险（柔和红，不刺眼）

Accent 纪律：每屏蓝色 ≤ 10% 面积；金色 ≤ 3%。

**按钮颜色语义（全站统一）**：
- **蓝 = 执行**：登录、生成分析、发送、保存、测试、建立关系、恢复采纳等动作性操作（`ui-btn-primary`）
- **金 = 创造**：采纳/修改后采纳、合并、拆分、录入、入库、创建账号等产生新对象的操作（`ui-btn-gold`）
- **红 = 推翻**：否定、删除、解除关系等推翻性操作（`ui-btn-danger` / `ui-link-danger`）
- **白 = 其他**：取消、暂缓、重置、编辑、导出等（`ui-btn-ghost` / `ui-link`）

## Typography

离线单机应用，不加载网络字体。中文系统字体栈，靠字重/字距分层。

- Display: `--font-display`（系统中文栈），weight 650，tracking -0.01em
- Body:    `--font-body`（同栈），weight 400
- Mono:    `--font-mono`（编号 `#6`、`#8128` 等），weight 500
- Type scale anchor: `--text-display` = clamp(2rem, 1.4rem + 2.4vw, 3rem)

## Spacing

4pt 命名标尺，见 `src/tokens.css`（`--space-3xs` … `--space-3xl`）。
页面与组件必须用命名 token，禁止内联色值与裸尺寸。

## Motion

- Easings: `--ease-out` cubic-bezier(0.22, 1, 0.36, 1)（苹果式回稳）；
  `--ease-in-out` cubic-bezier(0.65, 0, 0.35, 1)；`--ease-spring` cubic-bezier(0.34, 1.4, 0.64, 1)（轻回弹，仅用于入场）
- UI 交互时长 160–320ms；叙事动效（登录序列）另计
- Reveal pattern: fade + 轻微上浮（translateY 8px 内）
- 只动 transform / opacity
- **始终播放**：单用户个人应用，叙事动效是产品核心价值；机主明确不跟随系统
  prefers-reduced-motion 降级（本机系统级"窗口内动画"处于关闭状态）。
  同时不得写全局 `* { transition/animation … !important }` 覆盖——它会把任意
  偶发样式变化变成幻影动画。

## Microinteractions stance

- silent success（操作成功不弹庆祝 toast）
- hover 反馈：轻微上浮（-1px）+ 阴影加深；tooltip hover 延迟 800ms、focus 0ms
- 错误反馈：弹簧抖动（输入框），不用红屏闪烁
- 危险操作保留二次确认（现有行为，不改）

## CTA voice

- Primary CTA: 胶囊形（pill）实底星空蓝，白字，hover 上浮
- Secondary CTA: 描边胶囊，墨字，hover 底色微染
- 危险 CTA: 描边柔和红

## Per-page allowances

- Auth pages MAY use 叙事动效（卡墙/粒子/星空穿梭）——登录序列是产品的"开门仪式"。
- App pages MUST 保持功能优先：仅微交互与轻揭示，不用叙事动效。

## What pages MUST share

- "灵感空间" 字标（PageHeader 统一结构：灵感空间 + 副标题）
- accent 双色与其位置纪律
- 字体栈、按钮语言、圆角语言（卡 20px / 输入 12px / 按钮 pill）
- i18n：所有面向用户的文案走 `src/i18n.jsx` STRINGS，双语齐全

## What pages MAY differ on

- 各页在主区内的布局组织（列表/表格/三栏）
- 组件 archetype 选择
