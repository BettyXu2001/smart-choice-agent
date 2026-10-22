# Evaluation Metric Coverage Research

日期：2026-10-17。状态：研究完成，待 Plan 审查。

## 需求与研究范围

本次需求是在现有 `evaluation-v2` 框架中新增此前确认的必要指标与汇总能力：领域路由、澄清决策、软偏好满足、安全约束违规、Fallback 激活率，以及 Case 比率、分领域/Case 类型/Tag 汇总和路由诊断。

研究范围包括 Evaluation Schema、Runner、确定性 evaluator、Trace observation、Run summary、Baseline/Candidate comparison、内置 Dataset、Dashboard 和自动化测试。现阶段不修改产品代码，不引入 LLM Judge，不迁移数据库。

## ADR / 历史方案检索

已按 evaluation、metric、routing、clarification、soft preference、safety、fallback、coverage、group summary 等关键词检索 `adr/`：

- `2026-10-05-deterministic-evaluation-v2-p0-research/plan`：直接相关。确立 `deterministic / manual / not_evaluated` 三态、required deterministic Regression Gate 和 16 项目标指标覆盖。本次必须延续三态及 Gate 语义。
- `2026-09-20-reliability-regression-cases-research/plan`：直接相关。已实现 LLM/Search Fallback 成功率、Agent failure rate、latency Trace observation 和 `fault-injection-reliability/v2`。本次应复用 Trace 观测，不重写故障注入框架。
- `2026-09-05-evaluation-dashboard-research/plan`：直接相关。建立指标目录、Run/Result summary、Dashboard 和 Bad Case 闭环。本次新增字段应保持动态指标渲染。
- `2026-08-31-diet-evaluation-parity-research/plan`：语义相关。Diet 局部 EvaluationAgent 已有 clarify、fallback、safety 等指标，但没有进入主 `evaluation-v2` Run 汇总；不能直接把该局部输出当作主框架指标。
- `2026-09-20-evaluation-baseline-candidate-comparison-research/plan`：相关。Comparison 依赖相同 evaluator version、Dataset snapshot 和 result key 集合；新增指标必须升级 evaluator version，防止新旧口径误比较。

上述记录均已形成独立历史边界，追加会混淆已完成的 v2 语义，因此本次新建 Research/Plan。

## 核心文件与职责

| 文件 | 当前职责与现状 |
| --- | --- |
| `src/choice_agent/evaluation/metrics.py` | 定义 18 项指标、17 项 scored quality metric、16 项 deterministic target；聚合 overall/category/coverage/caseCounts/performance。 |
| `src/choice_agent/evaluation/deterministic.py` | 实现 16 项目标指标的 auto evaluator；普通自然语言无法确定时返回 `not_evaluated`。 |
| `src/choice_agent/evaluation/runner.py` | 在隔离数据库运行真实 Orchestrator，生成 outputs、Trace、assertions 和 per-result metrics。Generic 路径总是把 `case_data.domain` 作为显式领域传入。 |
| `src/choice_agent/evaluation/service.py` | 执行 Dataset snapshot、保存 Result、调用 `summarize_results()`、同步回归状态和提供 comparison。 |
| `src/choice_agent/evaluation/schemas.py` | `EvaluationCaseData` 已有 `domain/setup/messages/commands/assertions/tags`，没有独立 `caseType`。 |
| `src/choice_agent/evaluation/fixtures.py` | 提供 `core-regression/v2` 20 条 Case 和 `fault-injection-reliability/v2` 8 条 Case；tags 可复用，但没有稳定的 Case 类型字段。 |
| `src/choice_agent/domains/registry.py` | `identify()` 在无显式 domain 时按消息识别 diet/travel/shopping，冲突时落到 generic 并给出澄清信息。 |
| `src/choice_agent/orchestration/generic.py` | `create()` 支持 `request.domain=None`，通过 Registry 自动路由，并把 `sceneResolution` 写入 DecisionState。 |
| `src/choice_agent/schemas.py` | Candidate 已有 `scoreBreakdown`；DecisionState 已有 domain/status/nextAction/clarifyingQuestions/riskFlags，可供确定性指标读取。 |
| `src/choice_agent/static/assets/js/evaluation.js` | 根据后端 metric definitions 动态渲染，但 deterministic count 的空值回退仍写死为 16。 |

## 当前调用链与数据流

```text
EvaluationService.create_run
  -> immutable Case snapshots
  -> EvaluationRunner.run_case
  -> DietOrchestrator 或 GenericDecisionOrchestrator
  -> outputs + traceSnapshot
  -> assertion / auto evaluator
  -> per-result metrics_json
  -> repetition stability finalize
  -> summarize_results
  -> summary_json
  -> comparison / dashboard
```

当前 `EvaluationRunner._run_generic()` 调用：

```text
GenericDecisionOrchestrator.create(
  GenericDecisionRequest(message=..., domain=case_data.domain)
)
```

因此现有 Case 即使写了 `intent_accuracy` 并断言最终 domain，也是在验证显式 domain 传递，不是在验证 Registry 自动路由。

## 当前可复用能力

1. `GenericDecisionRequest.domain` 本来就是可选字段，生产 Orchestrator 已支持自动路由，不需要新增生产路由逻辑。
2. `DecisionState.domainState.sceneResolution` 已保存 `domain/candidateDomains/needsClarification/question`，可用于路由诊断。
3. `DecisionState.status/nextAction/clarifyingQuestions/unansweredQuestions` 可确定性判断是否追问。
4. Primary Candidate 的 `scoreBreakdown` 包含 `criterionKey/normalizedScore/weight/weightedScore`，可判断软偏好是否进入排序及达到 Case 声明的最低匹配要求。
5. Diet 风险链路会写 `riskFlags`，风险命中后清空 candidates/recommendation/display blocks，可用于安全 Case 的确定性断言。
6. Trace 已保存 model/search/provider node、fallback node、`fallbackUsed` 和调用状态，可派生 Fallback 激活率。
7. Dataset 保存不可变 Case snapshots，其中已有 domain 和 tags；Run 执行期间可构建 Case metadata map，无需修改 Result 数据表。
8. `aggregate_metric()`、Trace observation、comparison directional delta 和动态 Dashboard 可复用。

## 关键缺口

### 1. 领域路由没有被真实评测

Case 的 `domain` 同时承担期望标签和执行参数，Runner 强制传入正确 domain。要评测路由，必须区分“期望领域”和“是否显式传入领域”。最小方案是在 Case `setup` 中加入 evaluation-only `autoRoute: true`；启用时仍以 `case_data.domain` 为金标签，但请求传 `domain=None`，并统一走 GenericDecisionOrchestrator，包括期望领域为 diet 的 Case。

### 2. 主框架没有澄清准确率

Diet 局部 EvaluationAgent 的 `clarifyNecessityAccuracy` 不在主 Run 输出。主框架应基于结构化状态判断 should clarify，而不是依赖文案 contains。

### 3. 硬约束覆盖不了软偏好排序质量

`constraint_extraction_accuracy` 只看抽取，`hard_constraint_satisfaction` 只看硬限制；没有确认用户强调的 criterion 是否出现在 Primary Candidate 的 score breakdown、是否具有有效权重和最低匹配分。

### 4. 安全行为没有独立可见指标

Diet 风险策略存在，但主目录只可能通过普通 path assertion 间接覆盖。过敏/极端节食/医疗承诺等失败不应被普通决策平均分掩盖。

### 5. Fallback 成功率不代表降级频率

现有 `llm_fallback_success/search_fallback_success` 只衡量故障场景中是否成功降级。系统可能高频进入 Fallback 但仍全部成功；当前 summary 无法显示这种退化。Fallback 激活率适合作为 Trace observation，且不应进入总分，因为 fault-injection Dataset 会刻意触发 Fallback。

### 6. 总体分数会掩盖局部退化

现有 summary 只有总体指标和 Case 数，没有比率或 domain/case type/tag 分组。Result 本身没有 Case metadata，但 Service 在执行时持有 snapshot，可以在汇总时显式传入 metadata；无需持久化迁移。

## 指标与汇总建议

### 新增一等指标

| metric id | category | direction | scored | 计算来源 |
| --- | --- | --- | --- | --- |
| `domain_routing_accuracy` | 需求理解 | higher | true | auto assertion；比较期望 domain、实际 domain，并保存 sceneResolution。 |
| `clarification_decision_accuracy` | 需求理解 | higher | true | auto assertion；比较 `shouldClarify` 与结构化 status/nextAction/questions。 |
| `soft_preference_satisfaction` | 决策质量 | higher | true | auto assertion；检查 Primary Candidate 的 scoreBreakdown 是否覆盖目标 criteria、权重和最低 normalized score。 |
| `safety_constraint_violation_rate` | 决策质量 | lower | true | auto assertion；安全 Case 未满足 risk flags、禁止推荐/候选或声明 checks 时计为违规。 |
| `fallback_activation_rate` | 工程可靠性 | lower | false | Trace observation；有可观测 Trace 的请求中出现 fallback node 或 `fallbackUsed=true` 的比例。 |

新增后指标目录为 23 项：21 项 scored、2 项 unscored。Deterministic target 从 16 项扩展为 20 项；Fallback 激活率不进入 deterministic target。

### 新增 summary 字段

- `caseRates`: `passRate/failureRate/errorRate/notEvaluatedRate`。
- `groups.byDomain/byCaseType/byTag`：每组输出 `caseCounts/caseRates/overallScore/categoryScores/metrics/coverage`；不递归生成 performance/groups，避免体积和循环。
- `routingDiagnostics`: `sampleCount/accuracy/macroPrecision/macroRecall/macroF1/perDomain/confusionMatrix`；无可判定路由样本时为 empty/null，不造 0 分。

`caseType` 应成为 `EvaluationCaseData` 的可选稳定字段，默认 `general`；tags 继续承载可多选标签。

## 兼容性和版本约束

1. 指标目录、quality metric 数量、deterministic target 和 overall score 口径均变化，必须把 `EVALUATOR_VERSION` 从 `evaluation-v2` 升级为 `evaluation-v3`。
2. 新旧 Run 不应比较；现有 comparison 的 evaluator version 校验应继续阻止跨版本比较。
3. Case schema 只新增带默认值字段，不迁移数据库；旧 snapshot 读取为 `caseType=general`。
4. 不修改现有 `core-regression/v2` snapshot。需要新增 `core-regression/v3`，让新增指标有真实分母，并保留 v1/v2。
5. Dashboard 主要动态渲染，无需大改；只需移除或更新写死的 16 fallback，并展示新增 summary 分组/路由诊断的最小入口。

## 风险与隐患

- 自动路由 Diet Case 若继续走 `_run_diet()` 会绕过 Registry；必须由 `autoRoute` 明确切到 Generic Orchestrator，且验证 DietProfile 返回兼容 DecisionState。
- `fallback_activation_rate` 若按 provider call 而非 Case 统计，会让多轮/多调用 Case 权重异常；应使用每 Case 0/1、Run 按可观测 Case 聚合。
- 安全违规率是 lower-is-better；断言 `passed=false` 才表示一次违规，聚合公式必须沿用现有低优指标语义。
- 软偏好并非所有 Case 都可判定；缺 Primary Candidate、scoreBreakdown 或 Case 期望时必须 `not_evaluated`，不得计 0。
- 分组 summary 若直接递归调用完整 `summarize_results()` 会嵌套 groups；应抽取不递归的核心汇总 helper。
- free-form tags 可能产生高基数；内置数据集应使用稳定标签，API 仅返回当前 Run 实际出现的 tag。

## 尚待 Plan 明确

1. 五项新指标的精确 auto assertion `expected` 结构与缺失语义。
2. `core-regression/v3` 的新增 Case 数量和四领域覆盖分布。
3. 分组 summary 的复用方式，避免递归与重复性能聚合。
4. Dashboard 是完整展示新增分组还是先只由 API/Run JSON 暴露。

## Research 结论

现有框架可以在不迁移数据库、不修改生产路由/推荐算法的前提下完成本次扩展。必要改动集中于 evaluation schema、Runner evaluation-only 执行开关、deterministic evaluator、Trace observation、summary、versioned fixtures、Dashboard 和测试。由于公开指标与评分口径变化，应作为 `evaluation-v3` 发布，并新增不可变 Dataset 版本。
