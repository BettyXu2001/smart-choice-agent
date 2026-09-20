# Reliability Regression Cases Research

日期：2026-09-20。状态：研究完成，待 Plan 审查。

## 需求与范围

目标是在现有 `fault-injection-reliability` Regression Dataset、`EvaluationRunner` 和真实 Orchestrator 链路上，补齐模型、Web Search 与 Agent 异常的可靠性回归，不另建评测框架。

范围包括 LLM timeout、LLM invalid JSON、Web Search transport error、Web Search invalid response、Agent execution failure，以及 `llm_fallback_success`、`search_fallback_success`、`agent_execution_failure_rate`、response latency。所有 Case 必须通过真实 Runner/Orchestrator，不能用 `fixtureActual` 伪造最终结果；还需自动化测试和实际运行生成的示例结果。

这是数据版本、Runner 异常语义、Trace 观测和指标聚合的跨模块改动，按大改动处理。本阶段不改产品代码。

## ADR / 历史方案检索

已按 fault injection、regression、fixtureActual、fallback、timeout、invalid JSON、search error、Agent failure、Trace、latency 和 metric 检索 `adr/`、`src/`、`tests/`、README 与 CHANGELOG。

相关记录：

- `2026-09-06-evaluation-regression-dataset-research/plan`：最直接相关，已实现 Core Case、`fault-injection-reliability/v1`、versioned seed、白名单注入和真实 Orchestrator 执行。本次应发布不可变的新版本，不改 v1 snapshot。
- `2026-09-05-evaluation-dashboard-research/plan`：定义现有指标、Result/Run 汇总和 Dashboard。
- `2026-09-05-decision-trace-observability-research/plan`：定义 Trace v2、AgentRun、model call、fallback、failed 与 rolled_back。
- `2026-09-05-candidate-search-productization-research/plan`：定义显式 `web` 失败与 `auto` 回退 fixture，以及来源 mode/warning 的用户可见要求。
- `2026-09-04-conversation-decision-assistance-research/plan`：定义模型理解/解释校验和 rules fallback。

归档决策：新建本 Research/Plan。2026-09-06 Plan 已完成，直接追加新指标语义、失败执行封装和 v2 Case 会混淆历史边界。

## 核心文件与职责

| 文件 | 当前职责与本需求关系 |
| --- | --- |
| `evaluation/fixtures.py` | 定义 Core 与 v1 fault seed；现有 6 条含 model timeout、三类内容校验失败、search missing key 和 transport error。 |
| `evaluation/runner.py` | 隔离 SQLite 中运行真实 Diet/Generic Orchestrator；支持白名单 `mockModel` / `mockSearch`；仅 `fixtureActual` 非空时跳过真实链路。 |
| `evaluation/service.py` | 幂等 seed、不可变 Dataset snapshot、批量 Run、Result 持久化和 summary。单 Case error 不会中断整批。 |
| `evaluation/metrics.py` | 注册 17 项指标并按断言 pass/fail 聚合；Agent failure rate 和 latency 尚未按真实观测计算。 |
| `services/trace.py` | 保存 Trace v2；失败写 `FAILED`、`rolled_back`、error 和 Failure 节点。 |
| `agents/base.py` | `AgentRuntime` 在失败时写具体 Agent、`FAILED`、latency、完整 error 后重新抛出。 |
| `providers/model.py` | 真实 provider 用 `json.loads` 解析响应；invalid JSON 产生 `JSONDecodeError`（`ValueError` 子类）。 |
| `decision/assistance.py` | 模型理解/解释捕获解析与运行错误，保留规则结果并写 fallback Trace；解释 mode 为 `rules_fallback`。 |
| `providers/search.py` | transport/parse 失败重试，最终抛 `SearchProviderError`；空候选被拒绝，不会进入排序。 |
| `domains/comparison.py` | `web` 显式失败；`auto` 回退 fixture，写 warning、Fallback Trace 和实际来源 mode/label。 |

## 真实调用链

1. `EvaluationService.create_run()` 逐 Case 调用 `EvaluationRunner.run_case()`。
2. Runner 创建隔离 SQLite，注入受控 provider/registry，调用真实 `GenericDecisionOrchestrator.create/message/command()`。
3. Orchestrator 建立 `TraceScope`，`StageRunner` 经 `AgentRuntime` 执行真实 Intent、Understanding、Candidate、Critic、Explanation 等阶段。
4. 可恢复模型错误在 `assistance.py` 内转 fallback，仍返回有效 DecisionState。
5. 不可恢复 Agent 错误由 `AgentRuntime` 记录后抛出；Orchestrator 回滚业务状态，Trace 独立保存 FAILED/rolled_back。
6. 成功时 Runner 复制 response 与 Trace；异常时当前实现返回空 outputs/空 Trace/status=`error`，已落库的失败 Trace 因而丢失在 EvaluationResult 之外。
7. Result 保存 `metrics_json`，但 Run summary 当前只重新聚合 assertions，没有使用真实观测指标。

## 当前实现结论

### LLM

- timeout 注入已存在，会经真实 Explanation 路径得到 `rules_fallback`，请求不失败。
- invalid JSON 尚无独立注入；真实解析错误属于现有 fallback 捕获范围。新注入应模拟 `JSONDecodeError`，不能伪造 DecisionState。
- v1 timeout 只断言 analysis mode，未验证 recommendation、revision/status、Trace fallback 和 latency。

### Web Search

- 既有策略是显式 `web` 失败即 error；`auto` 才回退 fixture，并暴露 warning、Fallback Trace 与实际 source mode。
- Runner 看到 `mockSearch` 就强制 `searchMode=web`，因此现有 transport Case 没测试 auto fallback。
- invalid response 会在 CandidateAgent 中失败且不会进入 ranking；但 Runner 当前丢失失败 Trace，无法证明具体 Agent。
- 真实 search provider 将 transport/parse 错误统一包装为 `SearchProviderError`（`RuntimeError` 子类），测试 stub 应遵循同一契约。

### Agent failure 与状态

- AgentRuntime 已正确保存 agentName/status/latency/error；Trace 已正确保存 FAILED/rolled_back。
- 缺口在 Runner：应把失败 Trace 和结构化 execution error 带入 EvaluationResult，才能断言具体 Agent、完整错误和非 success 状态。
- “回归 Case 通过”与“产品 execution 成功”必须分层：预期故障被正确观察时 Case 可通过，但 execution/Trace/AgentRun 仍必须是 error/FAILED。

### Reliability 指标

- `llm_fallback_success` 已存在，适合由 Case 的结果/状态/Trace 断言计算。
- `search_fallback_success` 不存在，现有目录允许新增同类比例指标。
- `agent_execution_failure_rate` 当前实际是相关断言失败率，并非失败 AgentRun / 全部 AgentRun。
- `average_response_time_ms` 当前也按布尔断言聚合，无法输出毫秒均值。
- Trace 已包含 `durationMs` 与 AGENT_CALL events，无需新增数据库字段即可派生真实观测。

## 可复用能力

- versioned seed、稳定 seedId、不可变 Dataset snapshot；
- Result `metrics_json`；
- Trace 的 `durationMs`、timeline、AGENT_CALL；
- `auto` search fallback、source label 和 warning；
- 模型 rules fallback；
- AgentRuntime 失败记录与 Orchestrator rollback；
- 单 Case error 不打断批量 Run。

## 约束与风险

1. v1 snapshot 不可变，应新增 v2 并保留已有 v1。
2. 当前工作树已有用户未提交改动，包含 `assistance.py`、`comparison.py` 等相关文件。实施优先不改这些文件；如必须冲突，先暂停确认。
3. fatal Case 的 DecisionState 会回滚甚至不存在；完整性应通过 LLM fallback 的有效 State，以及 fatal Case 的 rolled_back/无误报 success 验证。
4. 故障注入继续使用枚举白名单，不接受任意异常类、URL、代码或路径。
5. `EvaluationRunCreate.limit <= 20` 不变，v2 总数须小于限制。
6. latency 环境相关，只断言存在、非负和聚合公式，不设固定阈值。
7. 历史 Result 缺 observation 时须标记 not applicable/not evaluated，不能当 0。
8. 新增 search 指标后目录由 17 变 18，需同步硬编码测试和 README。

## Plan 决策

- 发布 `fault-injection-reliability/v2`，不新建框架；
- 至少 5 个专门 Case，并保留有价值的 v1 模型校验 Case；
- 新增 `mockModel=invalid_json`，分别覆盖 search auto fallback 与 explicit error；
- 用 execution envelope 和失败 Trace snapshot 支持预期失败断言；
- 从 Trace 派生 Agent failure rate 与 latency，并让 Run summary 聚合 Result metrics；
- 新增 `search_fallback_success`；
- 示例必须由实际 `EvaluationService -> EvaluationRunner -> Orchestrator` Run 生成。

## Research 验证边界

本 Research 基于当前工作树的真实代码、主要调用方、测试与 ADR 的只读检查。未改产品代码，未运行测试。
