# 运行模式常驻提示与 Trace 标记 Plan

## 状态

2026-10-13：Research 已完成，等待用户 Review 和明确实施批准。当前未修改产品代码。

## 目标和成功标准

目标：让用户在整个对话过程中持续确认当前是 Demo 还是 Live，并让该模式进入每条新 Trace 的详情和导出数据。

成功标准：

- 通用决策与饮食对话页的 Agent 名称附近始终显示轻量模式 Badge。
- Demo 显示 `Demo`，实际运行显示 `Live`；颜色有明显区分，但不使用大面积 Banner。
- 每个 Demo 会话首次进入时显示一次：`当前为 Demo 模式，部分推荐结果或工具调用为模拟数据。`
- 设置保存、清除或有效模式发生切换后，立即显示 `已切换至 Demo 模式` / `已切换至 Live 模式`，且会话 Badge 同步更新。
- 每条新 Trace 顶层包含 `run_mode`，值严格为 `demo` 或 `live`。
- Trace 运行列表、详情 hero、原始 JSON、当前 Trace / Session JSON 导出和 Markdown 导出均能看到运行模式。
- 旧 Trace 缺少字段时显示“未记录”，页面和导出不报错。
- 不覆盖当前工作区已有未提交修改，不引入依赖或数据库迁移。

## 运行模式定义

新增共享判定，口径如下：

1. 请求 / DecisionState 明确带有 `demoMode=true`，或明确使用 `searchMode=fixture`：`demo`。
2. 否则，本次 active Settings 启用了带有效凭据的真实模型或真实搜索：`live`。
3. 其余情况：`demo`。

Live 代表本轮允许使用真实外部能力，不代表过滤、排序等确定性步骤会改为模型执行；Live 中发生 provider fallback 时仍记录 `live`，具体降级原因继续由 Trace fallback 节点表达。

固定 Demo 示例优先标为 Demo，即使浏览器配置了真实 API，也不得把模拟候选标为 Live。

## 设计

### 1. 后端统一运行模式判定

新增一个小型共享 helper，输入 active `Settings` 与本轮 decision context，返回 `Literal["demo", "live"]`：显式 Demo / fixture 返回 Demo；否则真实模型或真实搜索已有效配置时返回 Live；其余返回 Demo。

通用和饮食 Orchestrator 在创建 `TraceScope` 时传入结果。避免在 `TraceScope` 内导入 Orchestrator 或 API 层，也避免两条链路复制条件。

### 2. Trace 数据结构

扩展 `TraceScope`：

- 构造时接收 `run_mode`；
- `close()` 生成 payload 时写入顶层 `run_mode`；
- 值只允许 `demo` / `live`；
- 不新增 `TraceRecord` 数据库列，不做迁移，继续保存在 `trace_json` JSON 中。

覆盖通用 message/create、通用 command、饮食 chat/command、饮食 feedback 四类入口。失败 Trace 也必须保留构造时的 `run_mode`。

### 3. 前端模式状态

在前端集中增加 `resolveRunMode(decision?)` / `runModeLabel(mode)` 一类小型 helper，不把判定散落在模板中。

来源优先级：

1. 当前 decision 明确的 Demo context / fixture source；
2. 后端运行时 capability 返回的有效模式；
3. 浏览器当前真实模型 / 搜索配置；
4. 默认 Demo。

扩展现有 capability 响应，返回非敏感的 `runMode`，让服务端 `.env` 配置和浏览器运行时请求头也能反映到 UI。页面启动、直接进入会话和设置保存 / 清除后都刷新 capability；不返回 API Key、Base URL 或模型名。

设置切换反馈复用现有 Toast：

- 比较保存前后的 effective mode；
- 发生变化时显示 `已切换至 Live 模式` 或 `已切换至 Demo 模式`；
- 模式未变化时保留“设置已保存”语义，不伪报切换；
- capability 刷新失败时使用本地安全回退并显示错误反馈。

### 4. 对话页常驻 Badge

在 `conversation.js` 的对话标题 `.card-title` 中，将 Badge 放在标题 / Agent 名称附近：

- Demo：`<span class="run-mode-badge" data-run-mode="demo">Demo</span>`；
- Live：`<span class="run-mode-badge" data-run-mode="live">Live</span>`。

Badge 每次 `renderChat()` 都根据 state 重建，因此发送消息、恢复会话、打开面板和响应式切换后仍可见。

样式复用浅色主题变量：Demo 使用柔和的暖色 / notice 色，Live 使用现有 primary 绿色；小尺寸、圆角、短文本，不占独立整行；移动端允许随标题自然换行。

### 5. Demo 首次进入提示

在当前 tab 内维护已提示会话 ID 集合：通用决策使用 `decisionId`，饮食会话使用 `sessionId`，尚未创建会话时使用临时入口 key。

当 `renderChat()` 首次渲染一个 Demo 会话时，在标题下方插入轻量 `.run-mode-notice`，文案严格为：

`当前为 Demo 模式，部分推荐结果或工具调用为模拟数据。`

同一会话后续重渲染不再显示；新会话可再次显示。提示使用 `role="status"`，不使用遮挡式弹窗或大面积 Banner。

### 6. Trace 列表、详情和导出

扩展 `trace.js`：

- `normalizeTrace()` / `traceListSummary()` 读取 `trace.traceJson.run_mode`，兼容可选 camelCase 回退，但新数据以 `run_mode` 为准；
- Trace 左侧运行记录增加紧凑 Demo / Live Badge；
- 详情 hero 增加“运行模式”指标；
- 缺失时显示“未记录”；
- `traceMarkdown()` 增加 `Run Mode: Demo|Live|未记录`；
- JSON 导出继续导出完整响应，保证 `trace.traceJson.run_mode` 原样保留；
- Session JSON / Markdown 复用相同逻辑，每条 Trace 均体现模式。

### 7. CHANGELOG

在现有 `### 2026-10-13` 下追加，不重复日期标题：

- 对话页新增 Demo / Live 常驻提示和切换反馈，Trace 详情及导出新增 `run_mode`。

## 受影响文件

| 文件 | 计划修改 |
| --- | --- |
| 新增单一运行模式 helper 文件 | 提供后端共享 `demo` / `live` 纯判定，避免把 UI / Trace 语义塞入配置 dataclass。 |
| `src/choice_agent/schemas.py` | 扩展运行时 capability 响应的非敏感 `runMode` 字段。 |
| `src/choice_agent/api/routes.py` | capability 返回 effective run mode，复用 active runtime settings。 |
| `src/choice_agent/orchestration/generic.py` | 在请求和 command TraceScope 入口传入 run mode；保留当前未提交工作流改动。 |
| `src/choice_agent/orchestration/diet.py` | 在 chat/command 和 feedback TraceScope 入口传入 run mode。 |
| `src/choice_agent/services/trace.py` | TraceScope 接收模式并在 Trace JSON 顶层写入 `run_mode`。 |
| `src/choice_agent/static/assets/js/api.js` | 暴露 / 规范化前端 effective mode helper，不泄露密钥。 |
| `src/choice_agent/static/assets/js/app.js` | 保存 capability mode、设置切换反馈、Trace 列表 Badge。 |
| `src/choice_agent/static/assets/js/conversation.js` | 对话标题常驻 Badge、Demo 首次提示；保留即时发送消息的未提交修改。 |
| `src/choice_agent/static/assets/js/trace.js` | Trace 模式读取、详情 hero、Markdown 和 Session 导出展示。 |
| `src/choice_agent/static/assets/css/app.css` | 新增轻量 Badge / notice 及移动端适配，保持浅色 UI。 |
| `tests/test_runtime_model_settings.py` | 覆盖服务端 / 浏览器 active settings 的模式判定和 capability。 |
| `tests/test_trace_observability.py`、`tests/test_execution_workflow.py`、必要的 Diet 测试 | 覆盖 demo/live Trace、失败 Trace 和主要入口。 |
| `tests/test_frontend_static.py` | 覆盖常驻 Badge、首次提示、切换 Toast、Trace 详情和导出；保留当前未提交测试。 |
| `CHANGELOG.md` | 追加 2026-10-13 条目，不覆盖当天已有记录。 |

实施时如发现现有 capability 不是可靠的 UI 状态入口，允许在不改变上述口径的前提下新增只读 runtime capability endpoint；若需要新增显式 Demo / Live 强制覆盖协议或改变现有 API 设置语义，则属于重要设计扩展，暂停并更新 Plan 后重新批准。

## 兼容性与破坏性变更评估

- 新 Trace JSON 增加顶层字段，是向后兼容的附加字段。
- 不新增数据库列，不迁移旧 Trace；旧记录显示“未记录”。
- capability 响应增加信息，不删除或改名现有字段。
- 现有真实 API 请求头和设置结构保持兼容。
- Demo fixture、确定性规则、Live provider fallback 和候选排序行为不改变。
- Trace JSON / Markdown 导出新增字段；现有前端导出不做固定 schema 校验。

## 风险和边界情况

- 浏览器设置与服务端 `.env` 不一致：以 capability 使用的 active settings 为准。
- 固定 Demo 示例与全局 Live 设置冲突：显式 Demo / fixture 优先。
- Live 外部调用失败并规则降级：`run_mode` 仍为 Live，fallback 节点解释实际降级。
- 设置切换发生在已有会话中：Badge 立即反映 effective mode；历史 Trace 不回写；下一轮新 Trace 按新模式记录。
- 同一会话频繁重渲染：首次提示用会话 ID 去重。
- 旧 Trace：展示“未记录”，不根据 provider event 反推。
- 当前工作区存在重叠未提交修改：实施前后检查局部 diff，不格式化整个文件，不处理 `.test-tmp` 删除项。

## 验证方案

### 写入与 Diff 验证

1. 每次重要编辑后重新读取修改片段，确认真实落盘。
2. 检查 `git diff`，确认本需求只触及 Plan 范围并保留原有未提交修改。
3. 搜索 `TODO`、`console.log`、`debugger` 和无意义占位符。

### 自动验证

- `python -m compileall -q src`
- `node --check src/choice_agent/static/assets/js/api.js`
- `node --check src/choice_agent/static/assets/js/app.js`
- `node --check src/choice_agent/static/assets/js/conversation.js`
- `node --check src/choice_agent/static/assets/js/trace.js`
- `python -m pytest tests/test_runtime_model_settings.py tests/test_trace_observability.py tests/test_execution_workflow.py tests/test_frontend_static.py`
- 根据 Diet Trace 实际落点补跑对应专项测试。
- 专项通过后，环境允许时运行 `python -m pytest`。

### 行为验证

1. 无真实 API 配置进入通用和饮食会话：显示 Demo Badge。
2. Demo 会话首次进入显示指定提示；发送消息和重渲染不重复；新会话再次显示。
3. 保存有效真实 API 配置：立即 Toast `已切换至 Live 模式`，会话 Badge 变为 Live。
4. 清除真实 API 配置：立即 Toast `已切换至 Demo 模式`，会话 Badge 变为 Demo。
5. Live 配置下进入固定 fixture Demo：仍显示 Demo，Trace 为 `demo`。
6. 分别产生 Demo 与 Live Trace：数据库 `trace_json.run_mode` 为 `demo` / `live`。
7. Trace 列表与详情显示正确模式；旧 Trace 显示“未记录”。
8. 导出当前 Trace JSON / Markdown 和整个 Session JSON / Markdown，检查每条 Trace 的模式。
9. 缩窄视口，确认 Badge 不遮挡标题和会话按钮。

真实 Live 端到端验证需要可用模型或搜索 API Key。若没有凭据，至少验证 capability / 请求头 wiring、后端判定单测和构造的 Live Settings Trace，并说明未执行真实外部调用。

## 技术折衷

- 不新增数据库列：`run_mode` 属于单次 Trace 属性，放在 `trace_json` 即可满足详情和导出。
- 不使用全局大 Banner：常驻 Badge + 首次轻提示满足持续可见和低干扰。
- 不根据“是否真的发生 provider call”动态改写模式：模式描述本轮配置，provider 节点描述实际调用和 fallback。
- 不回填旧 Trace：历史推断存在误判，显示“未记录”更诚实。

## Todo

- [ ] 新增并测试后端共享 run mode 判定。
- [ ] 将 `run_mode` 接入通用与饮食的所有 TraceScope 入口，包括失败 Trace。
- [ ] 扩展 capability 与前端 effective mode 状态同步。
- [ ] 在通用 / 饮食对话标题增加常驻 Demo / Live Badge。
- [ ] 增加按会话去重的 Demo 首次轻提示和可访问性标记。
- [ ] 完善设置保存 / 清除后的模式切换 Toast 与 Badge 即时刷新。
- [ ] 在 Trace 列表、详情、JSON / Markdown 与 Session 导出中体现运行模式并兼容旧 Trace。
- [ ] 补充后端与前端专项测试。
- [ ] 更新 `CHANGELOG.md` 的 2026-10-13 条目。
- [ ] 执行 JS / Python / 行为验证，检查最终 diff，并记录未验证项和剩余风险。
