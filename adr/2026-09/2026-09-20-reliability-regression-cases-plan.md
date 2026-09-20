# Reliability Regression Cases Plan

日期：2026-09-20。状态：待用户审查与明确实施批准。

## 目标与成功标准

在现有 Evaluation / Fault Injection 框架内发布 `fault-injection-reliability/v2`，通过真实 `EvaluationRunner -> Orchestrator -> AgentRuntime` 链路验证外部能力和 Agent 异常。

成功标准：

1. v2 至少覆盖 LLM timeout、LLM invalid JSON、Web Search transport error、Web Search invalid response、Agent execution failure。
2. 所有 v2 Case 的 `fixtureActual` 均为空，结果来自真实 Orchestrator。
3. 两个 LLM Case 返回有效 response/DecisionState/recommendation，mode 为 `rules_fallback`，Trace 有 failed model call 和 fallback，execution 为 success。
4. Search transport Case 走既有 `auto -> fixture`，返回有效结果，source mode/label/warning 与 Trace 明确来源变化。
5. Search invalid response 不产生可排序错误候选；采用显式 `web` error，要求 CandidateAgent/Trace 为 FAILED、提交 rolled_back、无 success execution。
6. Agent failure Case 可从 EvaluationResult Trace 定位 Agent，保留异常类型和消息，并区分 Case 通过与产品执行失败。
7. `llm_fallback_success`、`search_fallback_success` 有真实分母；Agent failure rate 按失败 AgentRun / 全部 AgentRun；latency 输出实际毫秒均值且不计总分。
8. 自动化测试覆盖 seed/version、真实链路、失败 Trace、指标、批量不中断，并生成一次实际 v2 Run 的示例结果。

## 总体设计

不新增评测框架、数据库表或生产 fallback 策略。改动限定在 Evaluation 数据、Runner 执行封装、指标聚合和测试/文档。

```text
fault-injection-reliability/v2
  -> EvaluationService.create_run
  -> EvaluationRunner（隔离 DB + 白名单 fault setup）
  -> GenericDecisionOrchestrator -> StageRunner -> AgentRuntime
  -> response 或 structured execution error
  -> Trace snapshot + assertions + observed metrics
  -> EvaluationResult -> Run summary -> 示例 JSON
```

## Dataset 与 Case

### 版本策略

- seed 目标升级为 `fault-injection-reliability/v2`；已有 v1 不修改。
- 现有数据库幂等补齐 v2 Case/Dataset；按 name + version 精确选择。
- v2 总数控制在 10 条以内，保持 Run limit 20。

### 必需 Case

1. `model-timeout`
   - `mockModel=timeout`；
   - 断言 execution success、response/recommendation/DecisionState 有效、revision/status 合法、`rules_fallback`、Trace failed model + fallback、committed；
   - 计入 `llm_fallback_success`。

2. `model-invalid-json`
   - `mockModel=invalid_json`，抛贴近真实 provider 的 `JSONDecodeError`；
   - 断言解析失败后仍 success、规则结果有效、非 500 语义、Trace 记录 model failure + fallback；
   - 计入 `llm_fallback_success`。

3. `search-transport-error`
   - `mockSearch=transport_error`，context 为 `searchMode=auto`；
   - stub 使用 `SearchProviderError` 契约；
   - 断言执行成功、source mode=`fixture`、label/warning 明示 fallback、Trace 有 Fallback、候选/推荐有效；
   - 计入 `search_fallback_success`。

4. `search-invalid-response`
   - `mockSearch=invalid_response`，context 为 `searchMode=web`，声明预期 execution error；
   - 断言 execution error、Trace FAILED、commitStatus rolled_back、CandidateAgent FAILED、错误完整、无成功 Ranking、错误候选未进入 outputs；
   - Agent failure rate 与 latency 由 Trace 派生。

5. `agent-execution-failure`
   - Evaluation-only 白名单 `mockAgent=CandidateAgent` 或等价 profile/stage wrapper；
   - 故障必须在真实 `agent.execute()` 内抛出，由现有 AgentRuntime 记录；
   - 断言具体 AgentRun/timeline FAILED，error 同时含类型和稳定消息，execution/Trace 非 success，commitStatus rolled_back。

保留 v1 中有价值的 unknown candidate、false quote、invented number 校验 Case；可保留 missing-key Case。所有 v2 Case 均不设 `fixtureActual`。

## Runner 设计

### 白名单注入

- Model 增加 `invalid_json`；
- Search 仅接受 `missing_key | transport_error | invalid_response`，异常契约对齐真实 provider；
- `_run_generic()` 尊重 Case 显式 `searchMode`，不再因任意 mockSearch 无条件强制 web；
- Agent failure 仅允许预定义 Agent 名，并通过真实 AgentRuntime 捕获，禁止手工拼 AgentRun。

### Execution envelope

断言上下文增加：

```json
{
  "execution": {
    "status": "success | error",
    "errorType": null,
    "errorMessage": null
  },
  "traceSnapshot": {}
}
```

- 成功 response 字段保持不变，只补 execution 和可断言 Trace。
- 失败时在隔离 DB 关闭前读取本 Case 新产生的 FAILED Trace。
- 只有显式白名单的预期失败 Case继续跑 assertions；普通意外异常仍为 Result `error`。
- 预期失败 Case 可因断言成立而 passed，但 execution/Trace/AgentRun 必须保持 error/FAILED。
- 错误输出不得包含密钥、完整 prompt 或敏感配置。

### DecisionState 完整性

- LLM Case 通过 revision、status、recommendation、traceRefs 和 committed Trace 验证 State 可用。
- Fatal Case 通过 rolled_back、无成功 response、无半成品 State 验证状态未错误提交。
- 不改生产 Orchestrator 事务边界或 DecisionState schema。

## 指标设计

- `llm_fallback_success`：由两个 LLM Case 的“故障发生 + fallback 成功 + 结果有效”断言聚合。
- 新增 `search_fallback_success`：由 transport Case 的“搜索故障 + fixture fallback + 来源可见”断言聚合。
- `agent_execution_failure_rate`：从 Trace AGENT_CALL 统计 `FAILED / total`。
- `average_response_time_ms`：取各 Trace `durationMs` 的算术平均，`scored=false`。
- observation 写入现有 Result `metrics_json`；`summarize_results()` 对这两项聚合 Result metrics，其余继续聚合 assertions。
- payload 保持 `value/numerator/denominator/eligibleCount/evaluatedCount/missingReason/method`，观测项 method 为 `trace_observation`。
- 历史 Result 无 observation 时标记 not applicable/not evaluated，不回算为 0。

## 示例结果

新增 `docs/reliability-regression-example.json`，由测试环境实际执行 v2 后导出并稳定化，包含：

- dataset name/version、evaluator version；
- Case counts；
- 五个必需 Case 的 Evaluation status 与 execution status；
- 四项 Reliability 指标；
- LLM/Search fallback 与 Agent failure 的精简 Trace 证据；
- 生成命令，以及“固定 stub 不代表供应商 SLA、latency 为环境观测值”的说明。

若实际 Run 有失败，示例必须如实记录，不能手填成功。

## 受影响文件

| 文件 | 计划修改 |
| --- | --- |
| `src/choice_agent/evaluation/fixtures.py` | 发布 v2 seed 与 5 类必需 Case/断言。 |
| `src/choice_agent/evaluation/runner.py` | 扩展白名单注入、searchMode、execution envelope、失败 Trace、观测指标。 |
| `src/choice_agent/evaluation/metrics.py` | 新增 search 指标，支持 Agent failure/latency observation 聚合。 |
| `src/choice_agent/evaluation/service.py` | 将 Result metrics 纳入 Run summary，保持历史兼容。 |
| `tests/test_evaluation_runner.py` | 覆盖真实链路、无 fixtureActual、5 类行为、失败 Trace/State/来源。 |
| `tests/test_evaluation_metrics.py` | 覆盖 18 项目录、加权 failure rate、平均 latency 和历史兼容。 |
| `tests/test_evaluation_service.py` | 覆盖 v2 backfill、v1 共存、精确版本、summary。 |
| `docs/reliability-regression-example.json` | 保存实际 v2 Run 示例。 |
| `README.md` | 17 更新为 18 项，补充 Reliability v2/示例入口。 |
| `CHANGELOG.md` | 在 2026-09-20 唯一标题下记录可靠性回归与指标修正。 |

实施前重新检查工作树。已有 `assistance.py` / `comparison.py` 用户改动原则上不触碰；如真实验证发现必须修改生产 fallback，暂停并更新 Plan。

## 兼容性与风险

- API/数据库无删除或迁移；metricDefinitions 新增一项是向后兼容扩展。
- v1 immutable snapshot 保留，v2 新增，用户 Case 不覆盖。
- Runner outputs 仅增加 execution/trace assertion context，原 response 字段保留。
- 修正两个名实不符指标的口径；历史缺失数据不当 0。
- Dashboard 按动态 definitions 渲染，不计划改前端。
- 风险：失败 Trace 关联错 turn。执行前记录 trace ids，只接受本次新 Trace，并测试多轮。
- 风险：Evaluation wrapper 绕过 AgentRuntime。故障必须在 `agent.execute()` 内触发。
- 风险：预期失败被误报产品成功。required assertions 强制检查 error/FAILED/rolled_back。
- 风险：latency 抖动。只验证非负与聚合公式。
- 风险：observation 与 assertion 双计数。观测指标只走唯一 trace aggregation。

## 验证方案

1. 回读重要写入；`git diff --check`；检查无调试日志、临时文件或占位符。
2. 搜索 v2 Case，确认无 `fixtureActual`，fault setup 全在白名单。
3. 定向测试：
   `python -m pytest tests/test_evaluation_metrics.py tests/test_evaluation_runner.py tests/test_evaluation_service.py tests/test_trace_observability.py tests/test_candidate_search_productization.py`
4. 完整测试：`python -m pytest`。
5. 编译：`python -m compileall -q src scripts`。
6. 实际运行 v2，核对五类 Case、四项指标和原始 Trace 计数。
7. 从该 Run 生成并复核示例 JSON。

## Todo

- [ ] 再次检查工作树和调用方，确认与用户未提交改动无冲突。
- [ ] 发布 `fault-injection-reliability/v2`，补齐 5 类必需 Case并保留有价值的既有 Case。
- [ ] 扩展 Runner 白名单注入、searchMode 与 execution/Trace 断言上下文。
- [ ] 捕获预期失败 Trace，同时保持 execution/AgentRun/Trace 非 success。
- [ ] 新增 `search_fallback_success`，实现 Agent failure rate 与 latency 观测聚合。
- [ ] 更新 Service summary、历史兼容和 versioned seed 测试。
- [ ] 补齐 Runner/指标/Trace/Search 自动化测试。
- [ ] 实际运行 v2，生成并核对示例结果。
- [ ] 更新 README 与 CHANGELOG。
- [ ] 完成定向测试、全量测试、compileall、diff 和 Todo 对照。
