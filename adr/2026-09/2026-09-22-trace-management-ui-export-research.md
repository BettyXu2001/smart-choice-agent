# Trace 管理页面优化与导出 Research

## 需求与范围

2026-09-22。优化 Trace 管理页面的信息架构和导出能力，不改后端数据结构。

范围包括：左侧 30% Trace 运行记录、右侧 70% Trace 详情；左侧查询条件紧凑化；列表优先展示时间、状态、用户输入摘要、意图/领域、耗时；右侧突出用户输入、本轮状态、耗时、步骤数、Revision、推荐变化；Trace ID / Session ID 降为辅助信息；Agent 时间轴复用现有 trace 数据并中文化；FAILED / FALLBACK 自动展开；输入/输出 JSON 和原始 Trace JSON 放到二级展开；Decision State Changes 用易读形式突出新增、删除、修改；内部枚举增加中文映射；人工标注区域独立折叠；支持当前 Trace 和整个 Session 的 JSON / Markdown 导出。

该需求涉及开发者核心页面、导出格式、API 客户端和前端交互边界，按大改动处理。本阶段只做 Research / Plan，不改产品代码。

## ADR / 历史方案检索

已按 Trace、observability、DecisionState、annotation、Session、Trace ID、AgentRun 和相关文件路径检索 `adr/`、`src/`、`tests/`、`docs/`、`CHANGELOG.md`。

相关记录：

- `adr/2026-09/2026-09-05-decision-trace-observability-research.md` / `plan.md`：直接相关，定义 Trace v3 的 `timeline`、`turnSummary`、`recommendationChange`、状态差异、旧事件兼容和前端时间轴。
- `adr/2026-09/2026-09-20-model-call-trace-evaluation-cost-fallback-research.md` / `plan.md`：直接相关，已把 provider、model、token、cost、retry、fallback 写入 Trace / AgentRun / Evaluation；当时明确未重做 Trace 前端。
- `adr/2026-08/2026-08-31-diet-evaluation-parity-*`：相关，Trace 标注和 Evaluation 依赖旧 `events` / label 字段，不能破坏现有口径。
- `adr/2026-08/2026-08-30-frontend-api-settings-research.md`：相关，模型密钥不能进入 Trace，前端请求头配置不得被导出或落库。
- `adr/2026-09/2026-09-22-recommendation-feedback-loop-*`：相关，近期反馈闭环会进入 Trace，页面和导出需保留这些节点。

上述记录主题已完成且边界不同；本次新建 Research / Plan。当前工作区 `git status --short` 显示 `src/choice_agent/static/assets/js/app.js` 已有未提交修改。`git diff` 确认只改了模型设置占位符，与 Trace 页面无直接冲突；实施时必须保留。

## 核心文件及职责

| 文件 | 真实行为 |
| --- | --- |
| `src/choice_agent/static/assets/js/app.js` | 全局状态、路由、Trace 查询表单、Trace 列表、详情、标注表单和事件处理。当前 `renderTraces()` 使用通用 `.split` 布局；`renderTraceTable()` 以 Trace ID / Session ID 表格为主；`renderTraceDetail()` 将概要、时间轴和标注表单混排。 |
| `src/choice_agent/static/assets/js/trace.js` | Trace 时间轴渲染模块。当前支持 `traceJson()`、legacy events fallback、summary cards、节点详情、Decision State 变化、原始 Trace JSON。正常节点按 `sequence <= 2` 默认展开，不符合新需求。 |
| `src/choice_agent/static/assets/js/api.js` | `DietApi.listTraces()`、`getTrace()`、`listSessionTraces()`、`labelTrace()` 已存在。没有导出 API，但前端可复用现有完整 Trace 查询接口组装下载。 |
| `src/choice_agent/static/assets/css/app.css` | 包含 `.split`、`.trace-*`、`.json-box` 等样式。当前 `.split` 是 `1fr / 0.8fr`，不是 30/70。 |
| `src/choice_agent/api/routes.py` | `trace_response()` 返回 TraceRecord 全字段和 `traceJson`；单条 Trace、Session Trace、时间范围 Trace API 已存在。 |
| `src/choice_agent/repositories/diet_repository.py` | `trace()` 按 user_id + trace_id 查询单条；`session_traces()` 当前按 `created_at desc` 返回；`traces()` 也按倒序。 |
| `src/choice_agent/services/trace.py` | Trace v3 生成 `metadata`、`turnSummary`、`recommendationChange`、`initialSnapshot`、`timeline`、`events`；节点含 `input`、`output`、`changes`、`refs`、`durationMs`、`status`、`summary`；AgentRun event 含 provider/model/token/cost/fallback 字段。 |
| `src/choice_agent/schemas.py` / `db_models.py` | `Intent` 枚举含 `MEAL_RECOMMENDATION` 等内部值；`TraceLabelRequest` 与 `TraceRecord` 已有人工标注字段；`AgentRun` / `AgentRunRecord` 已有 observability 字段。 |
| `tests/test_trace_observability.py` | 覆盖 Trace v3、fallback、provider usage、Search retry / cost 等后端数据采集。 |
| `tests/test_frontend_static.py` | 现有前端测试通过静态源码断言关键文案和 wiring，可补充导出与布局相关静态断言。 |
## 当前调用链和数据流

Trace 查询页：`#/admin/traces` -> `renderTraces()` -> `traceFilterForm` -> `searchTraces()` -> `DietApi.listTraces()` 或 `DietApi.listSessionTraces()` -> `state.traces.rows` -> `renderTraceTable()` -> `selectTrace(traceId)` -> `DietApi.getTrace(traceId)` -> `renderTraceDetail()` -> `TraceTimeline.render(trace)`。

标注：`traceLabelForm` -> `saveTraceLabel()` -> `DietApi.labelTrace(traceId, payload)` -> `DietApi.getTrace(traceId)` 刷新详情和列表行。

导出可复用路径：

- 当前 Trace：从详情按钮触发，必须调用 `DietApi.getTrace(selected.traceId)` 获取完整 Trace 后导出。
- 整个 Session：从详情按钮触发，必须调用 `DietApi.listSessionTraces(selected.sessionId, 1000)` 获取后端当前允许返回的完整集合；前端按 `createdAt` 升序排序。
- 不使用页面已展开状态，也不只导出 `state.traces.rows` 中的摘要。

## Trace JSON 可用信息

`traceJson` 当前可用于详情和导出：基础元数据、用户输入、intent/domain、timeline 全部节点、每个节点 input/output/changes/refs/error、`initialSnapshot`、`recommendationChange`、fallback/error、provider/model/token/cost 相关 observability、人工标注字段。

注意：现有 Trace JSON 没有专门的完整 `finalSnapshot` 字段。导出 JSON 会保留完整原始后端 Trace；Markdown 只能展示现有可用的最终摘要，例如 `metadata.revisionAfter`、`recommendationChange.after`、timeline output/changes。不能伪造完整 final DecisionState。若严格要求完整 final state，需要后续后端采集增强，已超出“不改后端数据结构”的本轮范围。

## 当前实现问题

1. 布局不是 30/70，左侧和右侧宽度不符合需求。
2. 左侧筛选是普通表单网格，占用空间大；运行记录是表格，Trace ID / Session ID 信息权重过高。
3. 列表没有直接提取 `turnSummary.userMessage`、`turnSummary.intent`、`metadata.domain` 等更有用的排查信息。
4. 详情顶部缺少本轮状态、耗时、步骤数，且 Trace ID / Session ID 仍比较显眼。
5. `stageLabel()` 仍大量英文；内部枚举未中文化。
6. 节点默认展开前两个，不符合 FAILED / FALLBACK 自动展开、正常折叠。
7. 输入/输出 JSON、引用、原始 Trace JSON 不是二级展开，页面噪音较大。
8. `renderChanges()` 只显示 path/type 和 before/after JSON，不够突出“新增/删除/修改了什么”。
9. 人工标注表单混在详情主流程里，影响阅读 Trace。
10. 没有导出按钮和格式生成工具。
11. Session 导出如果直接复用列表行，会导出已加载或已展开子集；需求明确要求按 ID 拉完整后端 Trace 数据。
12. 前端静态测试没有覆盖 Trace 导出 wiring。

## 可复用能力

- 现有 Trace API 已返回完整 `traceJson` 和人工标注字段，当前 Trace 导出不需要新增后端接口。
- `DietApi.getTrace()` 和 `DietApi.listSessionTraces()` 可保证按 ID 重新获取后端 Trace 数据。
- `trace.js` 已有 JSON 解析、legacy timeline 兼容、HTML 转义，可继续扩展。
- `app.js` 已有集中事件分发，可增加 `data-action` 导出按钮处理。
- 浏览器可用 `Blob`、`URL.createObjectURL` 和临时 `<a download>` 实现下载，无需新增依赖。
- `tests/test_frontend_static.py` 适合做轻量静态断言。

## 约束与风险

- 用户明确“不改后端数据结构”，不得新增表字段或改变 Trace JSON 采集结构。
- 不新增导出后端接口时，Session 导出超过 1000 条受现有 API limit 限制；本轮可导出后端当前允许的完整结果集，并在导出元数据中记录数量和上限。
- 不能让导出包含浏览器本地模型 API Key 或请求头；只导出后端已经落库且已脱敏的 Trace 数据。
- 旧 Trace 可能只有 `events` 没有 `timeline`，必须保持 legacy fallback。
- `app.js` 已有用户未提交改动，必须保留。
- 当前环境 sandbox 初始化异常，shell 读命令需获批脱离 sandbox；实施和验证时若继续异常，需要如实记录。

## 待 Plan 决策

- 不新增后端导出路由，前端复用现有完整 Trace 查询并本地生成 JSON/Markdown。
- Session 导出排序在前端完成，避免改变现有列表 API 倒序展示。
- final DecisionState 保守呈现，不伪造 `finalSnapshot`。
- `trace.js` 负责 Trace 数据提取、中文映射、详情渲染和导出格式；`app.js` 负责页面布局、按钮和下载调用。

## 研究验证

已完成 ADR 检索、核心代码阅读、未提交改动检查和关键数据字段核对。本阶段未运行测试、未修改产品代码。