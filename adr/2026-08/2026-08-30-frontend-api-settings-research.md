# 前端 API 设置 Research

## 当前需求和范围

用户希望在前端页面增加“设置”，可以配置模型 API；如果不配置，则进入演示模式。

本次研究范围包括前端导航、路由、API 客户端、本地存储、通用演示模式入口、后端模型 Provider 配置方式，以及 Trace / AgentRun 对请求和上下文的持久化。该需求涉及模型密钥、运行模式和首页核心入口行为，属于安全边界和核心用户流程改动，应按大改动处理。

## ADR / 历史方案检索

已检索 `adr/`、`README.md`、`src/`、`tests/` 和 `.env.example` 中的 `api key`、`模型密钥`、`CHOICE_AGENT_MODEL`、`ENABLE_LLM`、`demo`、`演示模式`、`settings`、`设置`、`Base URL` 等关键词。

相关记录：

- `adr/2026-08/2026-08-30-generic-demo-mode-research.md`：高度相关，确认当前通用 demo 是纯前端 fixture，覆盖旅行、职业、学习和购物；无 API Key、无网络、无数据库额外配置时可运行。
- `adr/2026-08/2026-08-30-generic-demo-mode-plan.md`：高度相关，已完成首页非饮食问题进入通用 demo 工作台，饮食问题仍走真实饮食链路。
- `adr/2026-08/2026-08-30-demo-formal-input-flow-research.md` / `plan.md`：相关，记录 demo 创建后先经过约束、候选确认阶段，保持纯前端 fixture。
- `adr/2026-08/2026-08-29-diet-agent-python-migration-research.md` / `plan.md`：相关，记录模型供应商通过 OpenAI-compatible Provider 接入，且 Trace 不应记录模型密钥或敏感配置。
- `adr/2026-08/2026-08-29-ui-skins-research.md` / `plan.md`：轻度相关，前端已有皮肤设置通过 `localStorage` 保存，并在顶部入口中暴露。

判断：本次应新建独立 Research / Plan。已有 demo 和迁移文档已完成，直接追加会混淆“通用 demo 能力”与“浏览器侧模型配置入口”的边界。

## 核心文件及职责

### `src/choice_agent/static/index.html`

静态页面壳层。当前顶部导航包括首页、我的数据、Trace、评估。顶部右侧只有皮肤菜单和用户 ID 输入。没有设置页入口，也没有 API Key / Base URL / 模型名称字段。

### `src/choice_agent/static/assets/js/api.js`

前端饮食 API 客户端。当前 `API_BASE = "/api/v1/diet"` 写死为本服务后端路径；`USER_ID_KEY = "diet.userId"` 保存用户 ID；每个请求加 `X-User-Id`。没有模型配置读取、保存或请求头透传。这里的 `API_BASE` 是前端调用本地 FastAPI 的路径，不是模型供应商 API Base URL。

### `src/choice_agent/static/assets/js/app.js`

前端主要应用逻辑。当前使用 hash 路由，路由包括 `/`、`/diet/chat`、`/demo`、`/demo/decision/:id`、`/diet/meals/personal`、`/diet/meals/public`、`/admin/traces`、`/admin/evaluations`，没有 `/settings` 路由。`state.theme` 从 `localStorage` 读取，皮肤设置可作为设置页存储模式参考。

`submitGeneralDecision()` 中饮食问题进入 `/diet/chat`，非饮食问题调用 `ChoiceAgentDemo.createDecision()` 并进入 demo。当前没有根据 API Key 配置判断“正式模式 / 演示模式”。

### `src/choice_agent/static/assets/js/demo.js`

通用 demo fixture 和本地排序解释逻辑。当前不依赖后端、不依赖模型 API Key。

### `src/choice_agent/config.py`

后端环境变量配置包括 `CHOICE_AGENT_MODEL_API_KEY`、`CHOICE_AGENT_MODEL_BASE_URL`、`CHOICE_AGENT_MAIN_MODEL`、`CHOICE_AGENT_LIGHT_MODEL`、`CHOICE_AGENT_MODEL_TIMEOUT_SECONDS`、`CHOICE_AGENT_ENABLE_LLM`。`Settings.from_env()` 只在应用启动时读取环境变量。

### `src/choice_agent/main.py`

应用启动时创建 `app.state.settings = resolved` 和 `app.state.provider = OpenAICompatibleProvider(resolved)`。Provider 是全局单例，基于启动时 settings 创建。

### `src/choice_agent/api/routes.py`

饮食聊天和评估接口通过 `Depends(get_settings)` 和 `Depends(get_provider)` 注入全局 settings / provider。当前没有运行时模型设置接口，也没有从请求头或请求体读取模型配置。

### `src/choice_agent/providers/model.py`

`OpenAICompatibleProvider` 使用 `Settings` 拼接 `model_base_url.rstrip("/") + "/chat/completions"`，并通过 `Authorization: Bearer <model_api_key>` 调用模型。`enabled` 仅当 `settings.enable_llm` 且 `model_api_key` 非空时为 true。

### `src/choice_agent/agents/base.py` 和 `src/choice_agent/services/trace.py`

Trace 会持久化 `REQUEST_RECEIVED` 的 `inputPayload`，以及每个 AgentRun 的 `input_payload`，其中包括 `{"message": context.message, "data": context.data}`。因此模型密钥不能放入 `ChatRequest.context` 或 AgentContext `data`，否则会进入 Trace / AgentRun。

## 当前实现逻辑

首页提交时，`submitGeneralDecision()` 读取用户输入；饮食问题调用 `prepareChatFromHome(prompt)` 并导航到 `#/diet/chat`；非饮食问题调用 `ChoiceAgentDemo.createDecision(prompt, explicitDomain)` 并导航到 `#/demo/decision/:id`。非饮食场景天然进入 demo，饮食场景走本地真实链路。

饮食聊天由前端调用 `DietApi.createSession()` 和 `DietApi.chat(payload)`；后端 `chat()` 使用全局 `Settings` 和全局 `Provider`；`IntentAgent` 和 `ExplanationAgent` 在 `provider.enabled` 时尝试模型调用。模型调用失败时只捕获 `ValueError`、`KeyError`、`TypeError`，网络错误未被捕获，会导致请求失败。

评估接口中，`EvaluationAgent` 仅在 `include_llm_judge` 且 `provider.enabled` 时调用模型 Judge。

## 已有可复用能力

- 前端已有 `localStorage` 设置模式：皮肤和用户 ID。
- 前端已有 hash 路由和渲染函数结构，可加 `/settings`。
- `DietApi.request()` 可统一注入请求头。
- `Settings` dataclass 可用于生成每请求临时配置。
- `OpenAICompatibleProvider` 可复用，只需基于临时 settings 构造实例。
- demo 工作台已有完整未配置兜底体验。

## 潜在问题和隐患

- 浏览器保存 API Key 只能放在 `localStorage` 或内存中，安全性弱于后端 `.env`；必须在 UI 中明确“仅保存在本浏览器”。
- 如果把密钥放入请求 body 或 `context`，当前 Trace 会持久化密钥，风险较高。
- 如果前端未配置时强制禁用服务端环境变量，会破坏已有 `.env` 部署方式；如果不强制禁用，页面“未配置即演示模式”的语义需要限定为“浏览器侧通用入口”。
- 浏览器侧设置无法让纯前端通用 demo 变成真实通用 Agent，因为当前后端没有通用创建/推进 API。
- 若新增后端运行时设置 API 并持久化密钥，会扩大安全和存储范围，本次不适合。

## 约束

- 不把模型密钥写入数据库、Trace、AgentRun 或 URL。
- 不新增数据库表。
- 不修改通用 demo fixture 的基本工作方式。
- 不破坏 `.env` 配置方式。
- 不引入前端框架或构建流程。
- 不把非饮食通用 demo 升级为后端真实通用 Orchestrator。

## Plan 阶段需要决策的问题

- 前端设置是否保存 API Key 到 `localStorage`，还是仅本次会话内保存。
- 未配置时“演示模式”的 UI 范围如何表达，避免误导饮食本地规则链路。
- 请求头名称和后端临时 Provider 构造方式。
- 是否让评估接口也支持浏览器侧模型设置。
- 是否需要补充测试覆盖密钥不进入 Trace。