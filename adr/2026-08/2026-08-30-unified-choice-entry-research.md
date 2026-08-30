# 统一 Choice Agent 用户入口 Research

## 当前需求和研究范围

本轮目标是把用户侧入口整理成一个 Choice Agent 决策入口，让饮食能力作为被系统识别后的场景自然下沉，而不是作为与 Choice Agent 平级的一级产品模式。

研究范围限定在静态前端：首页定位、示例、统计卡和功能卡；顶部导航；hash 路由；`submitGeneralDecision()` 到饮食聊天页的流转；`/diet` 独立首页的角色；饮食聊天页标题、初始状态和用户可见的模式文案。

本轮不研究或改造后端核心架构、数据库、`DietApi` 命名、通用 Domain Router、通用 `DecisionApi` 或统一后端决策状态。

## ADR / 历史方案检索

已检索 `adr/`，发现以下相关记录：

- `adr/2026-08/2026-08-29-home-general-decision-mode-research.md`：研究了从饮食首页调整为通用首页的第一阶段，与本轮高度相关，但该阶段仍保留“饮食模式”作为用户可见一级入口。
- `adr/2026-08/2026-08-29-home-general-decision-mode-plan.md`：已完成默认 `#/`、通用首页、`#/diet` 饮食模式页和导航收拢。当前反馈正是该阶段之后遗留的体验割裂，因此不应改写历史计划，应新建本轮 ADR。
- `adr/2026-08/2026-08-29-choice-agent-v1-borrowed-ideas-todo.md`：记录了后续 `DecisionApi`、Domain Router、Domain Plugin、通用工作台等长期路线。本轮明确不进入这些后端和核心抽象改造。
- `adr/2026-08/2026-08-29-diet-agent-python-migration-research.md` 和 `plan.md`：记录 V2 以饮食能力为第一个完整领域，同时引入通用决策底座。约束本轮不能破坏既有 `/api/v1/diet/*` 和饮食主流程。

结论：本轮应新建 Research / Plan，主题是 `unified-choice-entry`。

## 核心文件及其职责

### `src/choice_agent/static/index.html`

页面壳层，负责 `<title>`、顶部品牌、顶部主导航、用户 ID 输入，以及加载 CSS、`api.js` 和 `app.js`。

当前状态：title 已是 `Choice Agent V2 · 通用决策`，品牌副标题是 `通用多 Agent 决策`，顶部导航为 `首页 / 饮食模式 / Trace / 评估`。

问题：用户侧仍把“饮食模式”看作与 Choice Agent 平级的一级入口；`Trace / 评估` 是开发者入口，继续保留可以接受，但需要与用户主流程分层表达。

### `src/choice_agent/static/assets/js/app.js`

静态应用主逻辑，负责全局 `state`、hash 路由、首页、饮食页、聊天页、餐食库、Trace、评估渲染，以及表单提交和点击事件。

当前相关状态：`state.home` 保存 `generalPrompt` 和 `notice`；`state.chat` 保存 `sourceMode`、`sessionId`、`sending` 和 `messages`；聊天初始消息是饮食推荐欢迎语。

当前路由：`currentRoute()` 默认返回 `/`；`render()` 支持 `/`、`/diet`、`/diet/chat`、`/diet/meals/personal`、`/diet/meals/public`、`/admin/traces`、`/admin/evaluations`；饮食子路由导航高亮归组到 `/diet`。

当前首页：`renderGeneralHome()` 展示 `通用决策入口`、开放式输入和混合示例；主操作旁仍有并列按钮 `进入饮食模式`；右侧统计卡仍展示 `当前完整模式：饮食决策` 和 `当前用户`；下方 Feature Card 是 `饮食模式 / Trace / 评估`，混合了用户功能和开发功能。

当前 `/diet`：`renderDietModeHome()` 是完整饮食 Hero，包含 `饮食决策模式`、`决定今天吃什么`、聊天、个人餐食、公共餐食三个入口。因为顶部导航也有 `饮食模式`，它在用户感知上仍像第二个产品首页。

当前聊天页：`renderChat()` 标题是 `聊天推荐`；顶部直接展示 `个人库 / 公共库` 切换按钮；使用提示写着 `PERSONAL 模式依赖你的个人餐食库；如果还没有数据，可以先去维护餐食，或切换到 PUBLIC 模式体验。` 这些文案偏系统配置，不像自然决策流程。

当前 `submitGeneralDecision()` 只做前端关键词判断并设置 `state.home.notice`：饮食问题提示“进入饮食模式”，非饮食问题提示“通用决策入口已预留”。它不会导航、不会创建会话，也不会把原始 prompt 交给聊天页。

### `src/choice_agent/static/assets/js/api.js`

前端 API 客户端当前全部饮食请求通过 `API_BASE = "/api/v1/diet"`、`DietApi.createSession()`、`DietApi.chat(payload)` 以及餐食、反馈、Trace、评估接口。本轮可以继续复用 `DietApi`，不抽 `DecisionApi`，避免为了入口体验扩大到 API 命名和后端抽象。

### `src/choice_agent/static/assets/css/app.css`

已有 `.decision-entry-form`、`.example-grid`、`.example-button`、`.mode-notice`、`.general-home`、`.stats`、`.stat-card`、`.chat-layout`、`.chat-window`、`.messages`、`.composer` 等样式。响应式断点已经覆盖顶部导航、首页和聊天布局。本轮可复用大部分样式，只需要新增或调整少量 class 来表达首页唯一入口、决策流程卡、已识别领域标签和数据源提示弱化。

## 关键调用链和数据流

### 当前首页饮食问题流转

用户打开 `/` → 无 hash 时进入 `#/` → `renderGeneralHome()` → 输入 `今晚不知道吃什么` → `submitGeneralDecision()` → 前端关键词判断为饮食 → `state.home.notice` 显示进入饮食模式提示 → 用户点击 `#/diet` → `renderDietModeHome()` → 用户点击 `#/diet/chat` → `renderChat()` → 用户需要再次输入问题 → `submitChat()` → `DietApi.createSession()` → `DietApi.chat()`。

### 目标首页饮食问题流转

用户打开 `/` → `renderGeneralHome()` → 输入 `今晚不知道吃什么` → `submitGeneralDecision()` → 前端识别为饮食场景 → 将原始 prompt 放入一次性待发送状态 → 导航到 `#/diet/chat` → `renderChat()` 展示“已识别：饮食决策” → 自动创建饮食会话并发送第一轮消息 → 返回澄清问题或推荐。

## 当前实现逻辑

- `renderGeneralHome()` 已具备通用首页外观，但仍明确告诉用户“当前完整可用的领域模式是饮食决策”。
- 首页保留 `进入饮食模式` 并列按钮，强化了“通用 / 饮食”双入口。
- `renderDietModeHome()` 仍是完整产品首页。
- `submitGeneralDecision()` 只做提示，不改变路由或创建聊天会话。
- 聊天页内部已能在首次发送时自动创建 session，因此首页只要把 prompt 交给聊天页，就能复用现有 `submitChat()` 的后续逻辑。
- `submitChat()` 当前直接从表单读取消息，不适合被首页自动发送复用；需要抽出共享的 `sendChatMessage(message)`。
- 聊天初始欢迎语在从首页带 prompt 进入时会显得重复，应根据是否有待发送 prompt 决定初始展示。

## 已有可复用能力

- 饮食聊天的 session 创建、请求发送、错误处理、消息渲染和 Trace 展示可直接复用。
- hash 路由已经支持 `/` 和 `/diet/chat`，无需新增后端路由。
- `state.chat` 可扩展少量前端状态，如 `pendingPrompt`、`domain`、`autoSending`。
- `setActiveNav()` 已支持把 `/diet/*` 高亮到 `/diet`，后续可把数据页高亮到“我的数据”。
- 餐食库页面路径已经存在，可作为 `我的数据` 导航入口。

## 潜在问题和隐患

- 如果在 `submitGeneralDecision()` 中直接调用 `submitChat()`，会依赖 DOM 表单，容易和路由切换顺序耦合。
- 如果导航到 `#/diet/chat` 后立即自动发送，每次 `renderChat()` 都可能重复触发，需要用一次性 pending 状态并在发送前清空或标记。
- 如果自动发送失败，需要保留用户原始问题，避免用户丢输入。
- 饮食识别仍是前端关键词判断，不是真正 Domain Router；文案应称为“已识别：饮食决策”，不要暗示后端智能路由已经完成。
- 非饮食问题当前没有完整后端链路，不能伪装成可完成 Offer、学习路线、旅行等通用决策。
- `/diet` 若直接重定向到聊天页，原饮食功能入口会消失；若改为饮食数据页，则需避免第二首页感。
- 去掉顶部“饮食模式”后，个人餐食和公共餐食需要一个用户可理解的入口，如“我的数据”。
- 直接隐藏 `PERSONAL / PUBLIC` 切换后，用户仍需要知道当前使用什么数据源；应改成柔和说明，保留高级切换或侧栏切换。

## 与需求相关的约束

- 不改后端核心架构。
- 不改 `/api/v1/diet/*` 接口。
- 不删除 `/diet/*` 路由，保持兼容。
- 不抽象 `DecisionApi`，暂时继续使用 `DietApi`。
- 本轮优先完成 P0 和部分低风险 P1。
- 首页必须表现为唯一 Choice Agent 入口。
- 饮食问题应从首页自然进入决策对话，并自动发起第一轮。
- 非饮食问题应保持诚实降级，但不再用“通用入口已预留”这类半成品感强的表达作为主体验。

## Plan 阶段需要决策的问题

- `/diet` 是直接重定向到 `#/diet/chat`，还是改成轻量饮食能力说明/数据页。
- 顶部导航移除“饮食模式”后，“我的数据”默认指向个人餐食还是一个新的数据聚合页。
- 自动发送首页 prompt 时，是否继续默认 `PERSONAL` 并在空数据时依赖后端/现有逻辑 fallback，还是前端先检测个人库数量。
- 用户可见的数据源切换是完全隐藏，还是保留为高级控件。
- 非饮食问题提交后的文案和行为如何不承诺未实现能力。