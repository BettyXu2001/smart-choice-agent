# Trace 管理页面优化与导出 Plan

## 状态

2026-09-22：用户批准“实施”后已完成前端 Trace 管理页优化、导出能力、静态测试和 CHANGELOG。JS 语法检查、前端静态测试、Trace observability 测试和全量 pytest 已通过；本地服务可在 8001 启动，但浏览器控制工具受 `windows sandbox failed: helper_unknown_error` 阻塞，未完成可视化截图验收。

## 目标与成功标准

在不改后端数据结构的前提下，让 Trace 管理页成为“运行记录 + 排查详情 + 可下载证据包”的开发者工作台。

成功标准：

- 页面为左侧 30% Trace 运行记录、右侧 70% Trace 详情，窄屏自动纵向。
- 左侧筛选紧凑，运行记录优先展示时间、状态、用户输入摘要、意图/领域、耗时；Trace ID / Session ID 只作为辅助信息。
- 右侧顶部突出用户输入、本轮状态、耗时、步骤数、Revision、推荐变化；Trace ID / Session ID 降为辅助信息。
- 时间轴复用现有 Trace 数据；节点标题中文化，包含状态、耗时和一句话摘要；正常节点默认折叠，FAILED / FALLBACK 自动展开。
- 输入 JSON、输出 JSON、引用、原始 Trace JSON 放到二级展开。
- Decision State Changes 在节点内优先展示，并用易读方式突出新增、删除、修改了什么。
- `MEAL_RECOMMENDATION` 等内部枚举有前端中文映射。
- 人工标注区域独立折叠在详情底部，不与 Trace 主流程混排。
- 详情页支持导出当前 Trace 和整个 Session，分别支持 JSON / Markdown 下载；导出时按 Trace ID / Session ID 重新获取完整后端 Trace 数据，不依赖页面已展开内容。
- Session 导出按时间升序排列，文件名包含 trace/session id 和日期。

## 设计

### 1. 前端数据适配与中文映射

在 `trace.js` 扩展纯前端 adapter，不改后端字段：

- `normalizeTrace(trace)`：统一解析 `traceJson`、`timeline`、legacy events、`metadata`、`turnSummary`、`recommendationChange`。
- `valueLabel(value, category)`：映射 intent、domain、requestKind、status、stage、change type、clarify action、source mode 等内部值。
- `stageLabel(stage)` 改为中文名称，覆盖 User Message、IntentAgent、UnderstandingAgent、ClarificationAgent、Candidate Retrieval、Evidence、Hard Filter、Ranking、PlanningAgent、CriticAgent、ExplanationAgent、RiskAgent、Feedback、Failure 等；未知阶段保留原值。
- `traceListSummary(trace)`：从 `turnSummary.userMessage`、`turnSummary.intent`、`metadata.domain`、`durationMs`、`createdAt`、`status` 提取左侧展示字段。
- `recommendationChangeText(trace)`：复用 `candidateLabel()`，显示首次推荐、改变、保持、清空、无推荐。

### 2. 页面布局

在 `app.js` 调整 `renderTraces()`：

- 根容器改为专用 `.trace-workbench`，桌面使用 `grid-template-columns: minmax(280px, 30%) minmax(0, 70%)`。
- 左侧为 `.trace-sidebar section`：标题、紧凑查询表单、运行记录列表。
- 右侧为 `.trace-main section`：未选择空状态或详情。
- 查询表单保留原字段，但使用更紧凑的两列/单列布局和短标签；Session ID 仍可筛选。
- 运行记录由表格改为列表按钮/card。每条记录展示时间、状态 badge、用户输入摘要、意图/领域、耗时，底部小字显示 Trace ID / Session ID 截断值和标注状态。
- 选择 Trace 后仍调用 `DietApi.getTrace(traceId)` 获取详情。

### 3. 详情顶部与时间轴

在 `trace.js` 重写/扩展渲染：

- `renderHero(trace)`：用户输入作为主标题区域；状态、耗时、步骤数、Revision、推荐变化作为指标；Trace ID / Session ID 放小号辅助行。
- `render(trace)` 输出：hero -> fallback/error alert -> timeline -> raw JSON details。
- `renderNode(node)`：`open` 条件改为 `status in ["failed", "fallback"]`；summary 中显示序号、中文阶段名、中文状态 badge、耗时、摘要；body 内先显示 Decision State Changes，再显示节点元数据，再以二级 `<details>` 展示输入 JSON、输出 JSON、引用 JSON、错误详情。
- `renderChanges(changes)`：将 `add/remove/replace/truncated` 映射为“新增/删除/修改/已截断”；对常见路径做中文化前缀；默认展示可扫读的 before/after 摘要，完整 JSON 放在单条 change 内的二级展开。

### 4. 人工标注区域

在 `app.js` 将标注表单移动为详情底部独立 `<details class="trace-label-panel">`：

- summary 显示“人工标注”，并显示当前标注状态。
- 表单字段和 `saveTraceLabel()` 逻辑保持不变。
- 保存后继续刷新 `DietApi.getTrace(traceId)` 并更新列表。
### 5. 导出能力

不新增后端导出路由，不改数据结构。前端使用现有完整 Trace 查询接口生成文件：

- `exportCurrentTrace(format)`：校验已选择 Trace；调用 `DietApi.getTrace(selected.traceId)` 重新获取完整 Trace；JSON 导出 `{ exportType, exportedAt, trace }`；Markdown 输出摘要、元数据、用户输入、intent/domain、recommendation change、initial snapshot 摘要、timeline 节点详情、events observability、人工标注和原始 JSON 附录摘要。
- `exportCurrentSession(format)`：校验 `selected.sessionId`；调用 `DietApi.listSessionTraces(selected.sessionId, 1000)`；按 `createdAt` 升序排序；JSON 导出 `{ exportType, exportedAt, sessionId, traceCount, limit, traces }`；Markdown 输出 Session 摘要、Trace 目录、每条 Trace 的摘要和节点详情。
- `downloadTextFile(filename, content, mimeType)`：使用 Blob 下载。
- 文件名：`trace-${safeTraceId}-${YYYY-MM-DD}.json|md`、`session-${safeSessionId}-${YYYY-MM-DD}.json|md`。
- 导出按钮放在详情顶部工具条：导出当前 Trace JSON / Markdown、导出整个 Session JSON / Markdown。
- 失败时使用现有 `guard()` / `showToast()` 反馈。

关于 `final DecisionState`：现有 Trace JSON 没有完整 `finalSnapshot` 字段。本轮导出在 JSON 中保留原始完整 Trace，不伪造字段；Markdown 中展示“最终可用摘要”，包括 `metadata.revisionAfter`、`recommendationChange.after`、节点 changes 和相关 output。若后续必须导出完整 final DecisionState，需要另立后端采集增强方案。

关于 Session 完整性：现有后端 Session Trace API 上限为 1000。本轮按该接口最大值重新拉取，导出元数据记录 `limit: 1000` 与实际条数；不新增分页或后端导出接口。

### 6. 样式

在 `app.css` 新增/调整：

- `.trace-workbench`、`.trace-sidebar`、`.trace-main`、`.trace-filter-compact`、`.trace-run-list`、`.trace-run-item`。
- `.trace-detail-hero`、`.trace-hero-input`、`.trace-hero-metrics`、`.trace-export-actions`。
- `.trace-node-*` 的状态样式和 `.trace-json-details` 二级展开样式。
- `.trace-change-list` 增加 add/remove/replace 的视觉区分。
- 移动端改为单列，保证按钮和文本不溢出。

保持现有整体视觉变量，不引入新依赖，不做无关全局重构。

## 受影响文件

| 文件 | 计划修改 |
| --- | --- |
| `src/choice_agent/static/assets/js/trace.js` | 增加 Trace adapter、中文映射、详情 hero、节点折叠策略、changes 易读展示、JSON/Markdown 导出格式生成。 |
| `src/choice_agent/static/assets/js/app.js` | 调整 Trace 页面布局、运行记录列表、标注折叠区域、导出按钮、导出事件处理和下载函数调用；保留已有模型设置占位符改动。 |
| `src/choice_agent/static/assets/js/api.js` | 如有必要只补充小型 helper 或保留现有 API；优先不改。 |
| `src/choice_agent/static/assets/css/app.css` | 新增 Trace workbench、运行记录、详情 hero、导出工具条、changes、响应式样式。 |
| `tests/test_frontend_static.py` | 补充静态断言：导出按钮/函数、按 ID 重新拉取完整 Trace、Session 排序、中文枚举映射、FAILED/FALLBACK 自动展开。 |
| `CHANGELOG.md` | 记录 Trace 页面优化与导出能力。 |

默认不改 `db_models.py`、`schemas.py`、`services/trace.py`、`api/routes.py`、repository 查询语义和依赖。如果实施中发现必须新增后端接口或数据字段，暂停并更新 Plan 后重新请求批准。

## 兼容性与风险

- API 契约不变，后端数据结构不变。
- 旧 Trace 继续通过 legacy events fallback 展示和导出。
- 导出 JSON 保留后端完整响应，不丢标注字段和 traceJson。
- Markdown 是阅读型摘要，不替代 JSON 完整结构。
- Session 导出最多 1000 条，受现有 API 约束；导出元数据显式记录。
- 现有 Trace 列表选择、标注保存和聊天 Trace 入口需保持可用。
- `app.js` 已有未提交占位符改动，实施时只改 Trace 相关区域，避免覆盖。

## 验证方案

1. 重新读取关键修改片段，确认写入真实落盘。
2. 检查 `git diff`，确认只包含 Plan 范围和已有用户改动，没有调试代码或无意义格式化。
3. JS 语法检查：`node --check src/choice_agent/static/assets/js/trace.js`、`node --check src/choice_agent/static/assets/js/app.js`；如修改 `api.js`，也执行对应检查。
4. Python 静态测试：`python -m pytest tests/test_frontend_static.py`。
5. 后端回归抽查：`python -m pytest tests/test_trace_observability.py`；如果环境允许，再运行 `python -m pytest`。
6. 启动本地服务并浏览器验证：布局 30/70、查询、列表信息、详情 hero、时间轴折叠、FAILED/FALLBACK 展开、changes、二级 JSON、标注保存、四个导出按钮、文件名、JSON 可解析、Markdown 可读、Session 导出时间升序。
7. 更新 Todo 和 CHANGELOG。

若当前 sandbox 初始化问题仍存在，必要命令需继续使用获批的非 sandbox 只读/验证方式；无法执行的验证必须在最终回复中说明。

## Todo

- [x] 扩展 `trace.js` 的 Trace adapter、中文映射、详情 hero、节点渲染、changes 展示和导出格式生成。
- [x] 调整 `app.js` Trace 页面为 30/70 工作台、紧凑筛选、运行记录列表、详情导出按钮和标注折叠区域。
- [x] 补充 `app.css` Trace 工作台、运行记录、详情、changes、二级展开和响应式样式。
- [x] 补充前端静态测试，覆盖导出 wiring、中文映射和折叠策略。
- [x] 更新 `CHANGELOG.md`。
- [ ] 执行 JS/Python/浏览器验证，检查 diff，并记录未验证项。