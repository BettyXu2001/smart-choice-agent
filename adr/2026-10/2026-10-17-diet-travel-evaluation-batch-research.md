# Diet / Travel Evaluation Batch Research

日期：2026-10-17。状态：研究完成，待 Plan 审查。

## 需求与研究范围

本次需求是在已确认的饮食（diet）和旅行（travel）领域生成一批评测 Case，覆盖正常完整输入、信息不足需澄清、硬约束、约束冲突、边界/异常输入、多轮修改、同义改写与稳定性，并实际运行后整理全部指标。

研究范围包括现有 Evaluation v3 指标目录、Case/Dataset schema、Runner、内置 Dataset、CLI、饮食与旅行现有测试行为及当前离线结果。本阶段不修改产品代码，不运行新批次。

## ADR / 历史方案检索

已按 evaluation、dataset、case、metric、diet、travel、clarification、fallback、stability 等关键词检索 `adr/`：

- `2026-10-17-evaluation-metric-coverage-research/plan`：最直接相关。已发布 `evaluation-v3`、23 项指标、分组汇总和 `core-regression/v3`；本次应复用，不另建指标框架。
- `2026-10-05-deterministic-evaluation-v2-p0-research/plan`：确立 deterministic-first、三态 evaluationMethod 和 required deterministic Regression Gate。
- `2026-09-06-evaluation-regression-dataset-research/plan`：定义不可变 Dataset snapshot、versioned seed 和真实 Orchestrator 执行方式。
- `2026-09-20-reliability-regression-cases-research/plan`：定义模型、Search、Agent 故障注入与 Trace 可靠性指标。
- `2026-09-22-travel-clarification-web-search-research/plan`：记录 Travel 澄清与 Search fallback 的现有行为。
- `2026-09-22-diet-hybrid-db-web-recall-research/plan`：记录 Diet DB/Web 召回、降级和安全边界。

上述记录均已完成且主题边界明确。本次新建专项 Research/Plan，避免把一次新的领域评测批次混入历史框架升级记录。

## 当前工作区状态

当前工作区已有未提交的 Evaluation v3 改动，包括 `metrics.py`、`fixtures.py`、Runner、Service、Schema、Dashboard、测试、README、CHANGELOG，以及今天的 v3 Research/Plan 和结果文档。这些改动与本次高度相关，但属于既有工作；实施时只能在其基础上精确追加，不得覆盖或回退。

## 当前实现与调用链

```text
versioned EvaluationCaseCreate definitions
  -> EvaluationService seed / immutable Dataset snapshot
  -> EvaluationRunCreate(limit <= 20, repeat <= 3)
  -> EvaluationRunner.run_case
  -> DietOrchestrator 或 GenericDecisionOrchestrator(TravelProfile)
  -> deterministic assertions + Trace observations
  -> per-result metrics
  -> summarize_results
  -> case rates / domain-caseType-tag groups / routing diagnostics / performance
```

关键事实：

1. 当前 evaluator 是 `evaluation-v3`，目录固定包含 23 项指标，其中 21 项计分、2 项观测。
2. `core-regression/v3` 已有 20 条跨 generic/shopping/diet/travel 的核心 Case，但 Diet 仅 3 条、Travel 仅 5 条，不是本次要求的双领域专项批次。
3. Run 单次最多选择 20 条 Case，`repeat` 最大为 3；推荐稳定性只有 `repeat >= 2` 才能形成有效配对。
4. Case 已有稳定 `caseType` 和 tags，可直接生成 diet/travel、类型、风险与可靠性分组。
5. `setup.autoRoute`、`mockModel`、`mockSearch`、`mockAgent` 是现有 Runner 的受控评测能力，可覆盖路由、Fallback 和失败可观测性，不需要修改生产流程。
6. 性能 summary 已提供平均延迟、P95、Token、平均 Token、成本、provider call 和 usage/price 缺失计数。
7. 当前 fixture + `DisabledProvider` 运行不会发生真实模型调用，因此 Token/成本通常为不可用；不能伪造为 0。

## 全部指标目录

### 需求理解

- `intent_accuracy`
- `domain_routing_accuracy`
- `clarification_decision_accuracy`
- `constraint_extraction_accuracy`
- `correction_update_accuracy`

### 决策质量

- `hard_constraint_satisfaction`
- `soft_preference_satisfaction`
- `safety_constraint_violation_rate`
- `exclusion_correctness`
- `recommendation_stability`
- `sensitivity_to_condition_change`

### 解释质量

- `reason_recommendation_consistency`
- `evidence_reference_validity`
- `unsupported_fact_rate`
- `excluded_candidate_recommend_rate`

### 多轮交互

- `multi_turn_state_retention`
- `correction_coverage`
- `what_if_isolation`

### 工程可靠性

- `llm_fallback_success`
- `search_fallback_success`
- `fallback_activation_rate`（不计分）
- `agent_execution_failure_rate`
- `average_response_time_ms`（不计分）

此外 performance 汇总包含 P95、Token、平均 Token、已知成本、估算总成本、provider call 数及 usage/价格缺失计数；它们不是额外的 scored metric。

## 可复用的真实行为

### Diet

- 已有固定餐食数据和 `DietOrchestrator`，可稳定验证完整推荐、清淡偏好、候选/Evidence 和理由。
- 已有医疗承诺风险路径，例如糖尿病“保证治好”会触发 risk flags 并阻断推荐。
- 已有多轮继续、换一批、权重调整和三餐规划测试，可选取其中与本次类型直接相关的最小行为。
- Diet 自动路由、软偏好和安全指标已在 v3 Case 中验证，可作为专项 Case 的基线。

### Travel

- `TravelProfile` 已有 departure/days 澄清、预算/偏好字段、固定候选、Evidence、what-if 和多轮刷新路径。
- `searchMode=auto` 支持 Web Search 失败回退 fixture，并记录 source warning 与 fallback Trace。
- CandidateAgent 故障和非法 Search response 可通过现有白名单注入验证 error/rolled_back/AgentRun failure。
- Travel 自动路由、完整输入不多问、软偏好排序和无天气资料时不编造事实均有既有实现或测试基础。

## 本次批次的必要边界

1. 新批次应独立版本化，不能修改 `core-regression/v1/v2/v3` 或 `fault-injection-reliability/v2` 的不可变快照。
2. 总数应控制为 20 条，均衡为 Diet 10 条、Travel 10 条，适配现有 Run 上限。
3. 使用 `repeat=2`，使同一 snapshot 的推荐稳定性可以实际计算；Run 会产生 40 个 Result。
4. Case 类型使用单值 `caseType`，交叉属性继续用 tags 表达。
5. 所有 23 项指标必须出现在结果表中；没有可靠金标签或当前批次不适用时明确写 `manual` / `not_evaluated` / `N/A` 及原因，不得用 0 伪装已评测。
6. 语义类指标遵循 rule-first：可由结构化状态/Trace 判断的使用 deterministic assertion；`unsupported_fact_rate` 等缺少可靠结构化金标签的部分保留人工审阅。
7. 运行使用临时 SQLite、固定数据源和受控故障注入，避免污染用户数据库；不调用付费模型，除非用户另行明确授权 live/configured provider。

## 风险与未决问题

- Diet 与 Travel 对某些通用指标的结构化输出不同，不能机械复制 Shopping/Generic 的 assertion path；实施前需用现有测试和小范围 dry run 校验。
- “约束冲突”必须验证当前系统真实可观察的处理结果，不能为了让 Case 通过而把期待降成无意义的“请求成功”。
- `agent_execution_failure_rate` 在故障注入 Case 中出现非零是预期观测，不等同于评测 Case 失败。
- `fallback_activation_rate` 在受控故障 Case 中预计升高，且按设计不进入 Overall。
- 重复运行会使延迟和 AgentRun 分母翻倍；结果报告必须同时说明 Case 数和 Result 数。
- 当前工作区未提交的 v3 改动是本次前置依赖；若其行为变化，专项基线也会随之变化。

## Research 结论

无需新增评测指标或重构 Runner。最小可靠方案是在现有 v3 上追加一个不可变的 `diet-travel-evaluation/v1` Dataset，定义 20 条双领域专项 Case，以 `repeat=2` 在临时数据库中执行，并新增一份包含全部 23 项指标、performance、分组、路由诊断、失败明细和 N/A 原因的结果报告。

