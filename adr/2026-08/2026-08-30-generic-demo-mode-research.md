# 通用演示模式 Research

## 当前需求和范围

用户希望 `choice-agent-v2` 的 demo 不只是饮食场景，而是像旧版 `choice-agent` 一样可以展示通用 Choice Agent 能力：从开放式选择题进入通用决策展示，覆盖旅行、Offer、学习、购物等非饮食场景，并清楚标注演示数据来源。

本轮研究范围：

- 新版 `choice-agent-v2` 当前首页、聊天页、配置、Schema、决策引擎和测试结构。
- 旧版 `choice-agent` 的 Demo Mode、fixture、通用 DecisionState 和工作台展示方式。
- 在不破坏当前饮食闭环的前提下，判断新增通用 demo 能力的可行路径。

本轮不直接修改产品代码。

## ADR / 历史方案检索

已检索 `adr/`、`docs/`、`README.md`、`src/` 和 `tests/` 中的 `demo`、`演示`、`fixture`、`统一入口`、`饮食`、`seed` 等关键词。

相关记录：

- `adr/2026-08/2026-08-29-choice-agent-v1-borrowed-ideas-todo.md`
  - 与本需求高度相关。该文件已明确提出“保持无模型密钥时可用规则/fixture 模式完整演示”和“明确 demo / rule / LLM 状态提示”。
  - 但该文件是长期架构 Todo，不是本次可执行 Plan；其中包含通用 Orchestrator、Domain Plugin、Search Provider、通用 API 等大范围重构。
- `adr/2026-08/2026-08-30-unified-choice-entry-research.md`
  - 与首页统一入口相关。当前首页已经把饮食作为被识别后的场景下沉，而不是一级产品模式。
  - 该记录明确指出非饮食问题当前没有完整后端链路，不能伪装成已可完整处理。
- `adr/2026-08/2026-08-30-unified-choice-entry-plan.md`
  - 已完成统一首页、饮食类问题自动进入聊天、非饮食诚实降级。
  - 本需求是在其基础上要求非饮食 demo 也能展示通用能力。
- `adr/2026-08/2026-08-29-diet-agent-python-migration-research.md` 和 `plan.md`
  - 约束 V2 当前第一个完整领域是饮食，现有 `/api/v1/diet/*` 行为不能被破坏。
- `adr/2026-08/2026-08-29-eat-what-selector-integration-research.md` 和 `plan.md`
  - 已把候选选择策略沉淀为 `decision` 层能力，但目前仍只接入饮食候选。

判断：本次应新建独立 Research / Plan。直接追加到长期 Todo 会混淆“架构最终方向”和“当前可交付 demo 能力”的边界。

## 旧版 Demo Mode 行为

旧版 `choice-agent` 具备显式演示模式：

- `.env.example` 包含 `NEXT_PUBLIC_DEMO_MODE=true`。
- 首页根据浏览器 API Key 状态显示 `在线模式` 或 `演示模式`。
- 无 API Key 时使用 fixture，本地可完整演示，不依赖网络。
- `src/domain/decision/fixtures.ts` 包含多个通用场景：
  - `demo-shanghai-weekend`：旅行；
  - `demo-career-offers`：职业 Offer；
  - `demo-learning-ai`：学习路径；
  - `demo-shopping-laptop`：消费购物；
  - generic fixture：当无法识别场景时仍能用候选名生成粗略比较。
- 旧版 `DecisionState` 面向通用展示，包含：`domain`、`goal`、`constraints`、`criteria`、`unansweredQuestions`、`candidates`、`recommendation`、`trace` 和 `revision`。
- 旧版工作台支持展示演示数据标识、目标、约束、开放问题、候选比较、权重调整、排除候选、fixture 刷新候选和生成结论。

旧版核心价值不是固定页面技术栈，而是“通用 DecisionState + fixture provider + 可交互工作台”。

## 新版当前实现

### 配置

`src/choice_agent/config.py` 当前配置包括 `CHOICE_AGENT_ENABLE_LLM`、模型 API Key、模型 URL、模型名、超时和 debug。不存在 `CHOICE_AGENT_DEMO_MODE` 或类似 demo 开关。

`.env.example` 默认 `CHOICE_AGENT_ENABLE_LLM=false`。

### 启动与数据

`src/choice_agent/main.py` 在应用 lifespan 中创建数据库表，调用 `seed_legacy_data(db)` 幂等导入旧饮食数据，注入 settings、database、OpenAI-compatible provider，并挂载静态 Web UI。

这保证新版无需模型 Key 也能运行饮食流程，但这不是通用 demo fixture。

### 后端 API

`src/choice_agent/api/routes.py` 目前主要是饮食 API：`/api/v1/diet/*`、debug、evaluations，以及 `/api/v1/decisions/{decision_id}`。没有通用“创建决策 / 推进决策 / 刷新候选 / 推荐结论” API。

### 通用 Schema

`src/choice_agent/schemas.py` 已有通用倾向的 `DecisionState`，包括 `domain`、`user_goal`、`constraints`、`criteria`、`candidates`、`candidate_state`、`evidence`、`unanswered_questions`、`assumptions`、`recommendation`、`next_action`、`trace_refs`、`revision`、`status` 和 `domain_state`。

这些字段足够承载通用 demo，但当前候选评分、推荐解释和展示逻辑仍围绕饮食流程。

### 决策引擎

`src/choice_agent/decision/engine.py` 当前是饮食排序引擎：`SLOT_FIELDS` 固定为餐次、心情、场景、健康目标、菜系、口味和便利程度；`rank()` 输入是 `MealRecord` 和 `SlotBundle`；`candidate()` 将餐食转为通用 `Candidate`。

因此它不能直接用于旅行、职业、学习或购物 demo 的通用属性评分。

### 前端

`src/choice_agent/static/assets/js/app.js` 当前包含统一首页、饮食聊天页、餐食库、Trace、评估、首页饮食关键词识别和饮食问题自动发送。非饮食问题目前只显示“这个场景还在接入中”的诚实降级提示。

当前没有通用 demo 路由、通用 demo 工作台、fixture 数据、权重调整或通用候选比较视图。

## 可复用能力

新版可直接复用：

- 首页开放式输入和示例按钮。
- `DecisionState` 中已有的大部分通用字段。
- 静态 Web UI 的 hash 路由和状态管理方式。
- `Candidate`、`Criterion`、`Constraint`、`Evidence`、`Recommendation` 等 Pydantic 模型。
- 当前测试框架和 `pytest`。
- README 中“无需 API Key 也能运行”的定位。
- 旧版 fixture 内容和演示场景设计。

需要新增或改造：

- 通用 demo fixture 数据。
- 通用 demo 状态存取或 API。
- 通用 demo 排序函数。
- 通用 demo 推荐解释函数。
- 通用 demo 工作台 UI。
- 首页非饮食示例进入 demo 工作台，而不是只提示接入中。
- 演示模式标识和数据来源说明。

## 关键调用链

### 当前饮食问题

首页输入饮食问题 → `submitGeneralDecision()` → `isDietPrompt()` → `prepareChatFromHome(prompt)` → `#/diet/chat` → `triggerPendingPrompt()` → `sendChatMessage(prompt)` → `DietApi.createSession()` → `DietApi.chat()` → `DietOrchestrator.chat()` → 饮食 Agent 流程 → 返回 `ChatResponse` 和 `DecisionState` → 前端展示聊天和餐食卡片。

### 当前非饮食问题

首页输入非饮食问题 → `submitGeneralDecision()` → `isDietPrompt()` 为 false → 设置 `state.home.notice` → 停留首页。

### 目标通用 demo 问题

首页输入旅行 / Offer / 学习 / 购物 / 通用比较问题 → `submitGeneralDecision()` → 前端识别为 demo 场景 → 创建通用 demo `DecisionState` → 保存到浏览器本地状态 → 导航到通用 demo 工作台 → 展示目标、约束、权重、候选、证据和推荐 → 支持权重调整、排除候选和查看结论。

## 方案空间

### 方案 A：纯前端通用 Demo 工作台

在静态前端新增 demo fixture、通用排序、解释和工作台渲染；首页非饮食示例进入 `#/demo/decision/:id`；`localStorage` 保存 demo decisions；不新增后端 API，不改数据库；饮食真实流程保持原状。

优点：风险最低，最接近旧版 fixture-first demo，不阻塞后续通用后端架构，无需数据库迁移，可以快速展示通用能力。

缺点：通用 demo 仍是前端 fixture，不是后端真实多 Agent 编排；Trace 和评估无法复用现有后端真实 Trace；后续如果做通用后端 API，需要再迁移。

### 方案 B：后端通用 Demo API

新增 `/api/v1/demo/decisions`、`/api/v1/demo/decisions/{id}`、`/rank`、`/recommend` 等接口，由后端提供 fixture、通用排序和推荐解释，前端工作台通过 API 读取和推进 demo 状态。

优点：数据模型和逻辑更接近未来通用后端，可以用 Python 测试完整覆盖，未来接通用 Orchestrator 更顺。

缺点：API 和状态管理范围更大，需要决定 demo 状态是否持久化，容易提前设计通用 Orchestrator 的边界。

### 方案 C：完整通用 Orchestrator + Domain Plugin

正式推进长期 Todo 中的通用 Orchestrator、Domain Plugin、Search Provider、通用 API 和工作台。

优点：架构最终形态最完整。

缺点：范围过大，会触及核心类型、API、状态流转、前后端多模块；当前需求只是通用 demo 展示，不需要一次性完成完整架构。

## 初步判断

推荐采用方案 A：先做纯前端通用 Demo 工作台。

理由：用户目标是“新版 demo 也可以是通用展示能力”，不是立即要求通用后端真实编排。旧版 demo 的稳定性来自 fixture，不来自在线服务。新版当前真实后端完整能力仍在饮食领域，强行把旅行、职业、学习、购物接入后端会扩大范围。前端 demo 工作台可以复用旧版通用展示模型，快速补上产品表达缺口。饮食场景仍保留真实后端链路，避免退化为全 fixture。

## 约束和风险

- UI 必须清楚标注“演示数据”，避免用户误以为非饮食场景已经接入真实搜索或后端 Agent。
- 首页示例中饮食仍应进入真实饮食链路；旅行、Offer、学习、购物进入 demo 工作台。
- 旧版 `DecisionState` 字段名与新版 Pydantic 字段不完全一致，例如旧版 `id`/`goal`，新版后端 `decision_id`/`user_goal`。纯前端方案可以先保留前端 demo state 的轻量结构，不强行写入后端 `DecisionRecord`。
- 不应在本次把 `DecisionEngine` 泛化，否则会变成核心架构改造。
- 新增 CSS 应复用当前主题变量，避免大范围视觉重构。
- 当前没有前端自动化测试框架，验证主要依赖后端测试和手动页面检查。

## 尚未确定的问题

- 通用 demo 是否只在前端 localStorage 保存，还是需要后端可查询？
- 通用 demo 工作台第一版是否需要支持“刷新候选”，还是只展示固定候选、权重调整和生成结论？
- 首页输入无法识别明确场景时，是进入 generic demo，还是继续提示“接入中”？
- 是否要把 `CHOICE_AGENT_DEMO_MODE` 加到后端配置，还是只根据前端固定 demo 能力展示“演示数据”？
- 是否需要将旧版 demo 数据完全迁移，还是先迁移旅行、职业、学习、购物四套核心 fixture？

## Research 结论

让新版具备通用演示能力是可行的。最小高价值路径是新增一个前端通用 demo 工作台：非饮食 demo 场景使用固定 fixture 和本地排序解释，饮食场景继续走当前真实后端流程。

该方案能恢复旧版“通用 Choice Agent 展示能力”，同时避免提前重构通用后端架构。后续如需把 demo 变成真实通用 Agent，可再基于本轮前端状态模型推进通用 API 和 Domain Plugin。