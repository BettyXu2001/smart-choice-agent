# 运行模式常驻提示与 Trace 标记 Research

## 当前需求和研究范围

用户希望在当前交互界面持续、明确地看到 Choice Agent 正处于 Demo 还是实际运行模式，并在 Demo 首次进入会话、模式切换、Trace 详情和 Trace 导出中得到一致反馈。

研究范围包括对话页标题、全局状态、设置页与 Toast、浏览器真实模型 / Web Search 配置、Demo fixture、通用与饮食决策、Trace 生成 / 查询 / 详情 / 导出，以及相关测试。本阶段不修改产品代码。

## 改动规模判断

本需求同时影响会话 UI、运行时设置口径、Trace 数据结构、详情和导出格式，需要保证前后端对 Demo / Live 的判断一致，属于跨模块且存在行为口径取舍的大改动。

按项目规则执行：`ADR lookup -> Research -> Plan -> 用户批准 -> Implement -> Verify`。

## ADR / 历史方案检索

已按 `demo`、`fixture`、`live`、`real api`、`trace`、`export`、`conversation`、相关模块名和路径检索 `adr/`、`src/` 与 `tests/`。

直接相关记录：

- `adr/2026-08/2026-08-30-generic-demo-mode-research.md` / `plan.md`：定义通用 Demo fixture、`context.demoMode`、`searchMode=fixture` 和“演示数据 / 非实时”边界。
- `adr/2026-09/2026-09-09-browser-real-api-settings-research.md` / `plan.md`：定义浏览器真实模型 / 搜索配置、localStorage、运行时请求头和设置页反馈。
- `adr/2026-09/2026-09-05-decision-trace-observability-research.md` / `plan.md`：定义 Trace v3 的 `metadata`、`turnSummary`、`timeline`、状态差异和持久化结构。
- `adr/2026-09/2026-09-22-trace-management-ui-export-research.md` / `plan.md`：定义 Trace 详情页及当前 Trace / Session 的 JSON、Markdown 导出链路。
- `adr/2026-09/2026-09-04-general-conversation-panel-*` 与 `diet-conversation-panel-*`：与会话页标题和持续展示位置相关。

上述记录均已完成且边界不同。本需求需要统一 UI 与 Trace 的运行模式口径，追加旧记录会混淆历史语义，因此新建独立 Research / Plan。

## 核心文件及职责

| 文件 | 当前职责与真实行为 |
| --- | --- |
| `src/choice_agent/static/assets/js/conversation.js` | 渲染通用 / 饮食对话页。`renderChat()` 的 `.card-title` 同时展示 Agent 标题与会话操作，是常驻 Badge 最直接的位置。 |
| `src/choice_agent/static/assets/js/app.js` | 全局 state、路由、Toast、设置页、首页创建决策和 Trace 页面。设置保存 / 清除已有 Toast，但会话标题不会持续更新。 |
| `src/choice_agent/static/assets/js/api.js` | 保存浏览器真实模型 / 搜索设置，并为普通和流式请求注入运行时请求头。 |
| `src/choice_agent/static/assets/css/app.css` | 已有 `.badge`、`.settings-status`、`.mode-notice` 和浅色主题变量，可复用为轻量模式 Badge。 |
| `src/choice_agent/api/routes.py` | 根据浏览器请求头和服务端 Settings 构造 active settings/provider；`/api/v1/search/capabilities` 返回真实搜索是否可用。 |
| `src/choice_agent/config.py` | `Settings` 保存模型、搜索及 LLM 启用配置，是后端判定实际能力的输入。 |
| `src/choice_agent/orchestration/generic.py` | 通用请求 / command 的 TraceScope 入口；Demo 当前仅写 `metadata.executionProfile=demo_deterministic`。 |
| `src/choice_agent/orchestration/diet.py` | 饮食聊天与反馈的 TraceScope 入口，当前不记录统一 Demo / Live 字段。 |
| `src/choice_agent/services/trace.py` | 构造 Trace v3 并写入 `TraceRecord.trace_json`，当前顶层没有 `run_mode`。 |
| `src/choice_agent/static/assets/js/trace.js` | Trace 列表摘要、详情 hero、原始 JSON、Markdown/JSON 导出。 |
| `tests/test_frontend_static.py` | 通过静态源码断言关键 wiring，适合覆盖 Badge、首次提示、切换反馈和 Trace 展示。 |
| `tests/test_runtime_model_settings.py` | 覆盖浏览器运行时配置合并与密钥不落 Trace。 |
| `tests/test_trace_observability.py`、`tests/test_execution_workflow.py` | 覆盖 Trace 结构、Demo 确定性执行和真实 Orchestrator 行为。 |

## 当前模式来源和调用链

### 浏览器设置

`api.js` 将模型和搜索设置保存在 `choiceAgentModelSettings`。模型或搜索开关开启且存在对应 API Key 时，设置页显示“真实 API”。保存设置已有 Toast；清除设置时提示当前为演示模式。

### 首页创建通用决策

首页根据 `/api/v1/search/capabilities` 选择模式：真实搜索可用时使用 `searchMode=auto`；不可用时使用 `searchMode=fixture`，`startGeneral()` 同时设置 `context.demoMode=true`。固定 Demo 示例直接使用 `context={searchMode:"fixture", demoMode:true}`。

### 后端执行

通用 Orchestrator 在 `decision.context.demoMode` 为真时只把 Trace `metadata.executionProfile` 标为 `demo_deterministic`。饮食链路可以只用本地规则 / 数据库，也可以使用浏览器或服务端模型设置，但当前 Trace 无统一字段区分页面所称的演示和真实 API 状态。

## Trace 数据流

`TraceScope.begin_turn()` 记录初始状态与 metadata，`mark_committed()` 记录结束 revision 和推荐变化，`close()` 组装 payload 并写入 `TraceRecord.trace_json`。

查询链路：`TraceRecord.trace_json -> trace_response() -> DietApi.getTrace()/listSessionTraces() -> trace.js normalizeTrace() -> 详情 / 原始 JSON / 导出`。

JSON 导出直接包含完整 Trace 响应，因此后端响应携带 `run_mode` 后，JSON 导出自然包含它；Markdown 和详情 hero 需要显式增加展示。

## 现有可复用能力

- 对话标题已有 `.card-title` 和 `.eyebrow`，可在 Agent 名称旁增加紧凑 Badge。
- `.badge`、主题变量、Toast 和 `aria-live` 可满足轻量提示及可访问性要求。
- `context.demoMode`、`searchMode=fixture`、active Settings 和真实 API 配置可共同构成统一判定。
- `TraceScope` 是所有 Trace payload 的集中写入点。
- `trace.js` 集中负责详情和导出，无需新增后端导出 API。
- 现有静态测试和后端 Trace 测试可以覆盖主要契约，不需引入依赖。

## 当前缺口

1. 对话页没有常驻 Demo / Live Badge，离开设置页后无法持续确认。
2. Demo 首次进入会话没有统一的一次性轻提示。
3. 设置 Toast 与会话 Badge 没有共享同一模式判定。
4. 浏览器配置、服务端 `.env`、`context.demoMode` 和 fixture 可能给出不同线索；只看 localStorage 可能与后端实际执行不一致。
5. Trace 顶层没有 `run_mode`，详情、列表摘要和 Markdown 导出无法直接查看。
6. 旧 Trace 不含新字段，前端必须兼容缺失值，不能错误标成 Live。

## 运行模式口径

建议统一为：

- `demo`：请求显式标记 `demoMode`、明确使用 fixture，或本次 active settings 没有可用的真实模型 / 搜索能力。
- `live`：请求未被强制为 Demo，且 active settings 至少启用了一个有有效凭据的真实模型或搜索能力。

该字段描述“本轮请求采用的运行环境口径”，不等同于每个步骤都发生外部调用。Live 仍会使用确定性规则；外部调用失败后的规则降级仍属于本轮 Live，由既有 fallback 节点说明。

Demo fixture 优先于浏览器 Live 配置，避免把模拟候选误标为 Live。

## 首次提示的会话边界

“首次进入会话”按浏览器 tab 内的会话入口处理：

- 新建或首次加载一个 Demo 会话时显示一次；
- 同一会话因发送消息导致的重复渲染不重复提示；
- 切换到另一 Demo 会话可再次提示；
- Live 会话不显示。

可用前端内存集合按 `decisionId/sessionId` 去重，无需新增后端字段或持久化。

## 工作区现状与冲突风险

当前工作区已有与其他任务相关的未提交修改和测试临时文件删除。与本需求重叠的文件包括 `generic.py`、`conversation.js`、`index.html`、`tests/test_frontend_static.py`、`CHANGELOG.md` 和现有 2026-10-12 Plan。

实施时不得覆盖或回滚这些改动；应使用局部补丁并在最终 diff 中区分本需求修改。`.test-tmp` 删除项不属于本需求，不处理。

## 约束和风险

- 不新增大面积 Banner；首次提示用轻量 notice / Toast，常驻信息只用 Badge。
- `run_mode` 不包含密钥、provider URL 或其他敏感配置。
- Live 不承诺每个步骤都调用外部服务，也不覆盖既有 fallback 可观测性。
- Demo 示例即使配置真实 API，也必须标成 Demo。
- 旧 Trace 缺少字段时展示“未记录”，不能推断为 Live。
- 设置切换后 Badge 立即更新；历史 Trace 保持当时模式，不随当前设置变化。
- 静态 JS 不引入新框架或依赖。

## 待 Plan 决策

- 后端提供小型共享 helper，通用与饮食 Orchestrator 复用。
- `run_mode` 写在 Trace JSON 顶层，值严格为 `demo` / `live`，不新增数据库列。
- Trace 详情 hero、列表摘要和 Markdown 显式显示；原始 JSON 与 JSON 导出自然包含。
- 前端 Badge 优先使用 decision 的明确模式，缺失时使用运行时能力状态。
- 首次 Demo 提示按会话 ID 在当前 tab 内去重。

## Research 结论

该需求可在不新增依赖、不增加数据库列、不改变主要页面结构的前提下完成。关键是统一模式判定：请求上下文和 active Settings 共同决定本轮 `demo` / `live`，同一结果驱动会话提示和 Trace 记录。

最小可靠方案是复用当前真实 API 设置与 Toast，新增共享判定，在对话标题增加轻量 Badge，Demo 会话首次进入显示一次提示，并让 Trace 顶层、详情和导出体现 `run_mode`。
