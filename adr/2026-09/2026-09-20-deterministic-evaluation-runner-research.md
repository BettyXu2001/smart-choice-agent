# Deterministic Evaluation Runner Research

日期：2026-09-20。状态：研究完成；实施前冲突审计已更新。

## 需求与研究范围

本次目标是增强 Smart Choice Agent 的 Evaluation Runner，确立 “Deterministic Evaluation First” 原则：优先依据 `DecisionState`、`Candidate`、`Constraint`、`Evidence`、`Recommendation`、`Trace` 与状态 `revision` 自动判定；无法可靠自动判断的语义质量进入人工审阅；Human Review 只作为补充标签，不参与确定性 Regression Gate；本轮不实现 LLM Judge。

需求覆盖 16 项现有质量指标，并要求每项结果记录 `evaluationMethod = deterministic | manual | not_evaluated`、报告 deterministic coverage、以明确的 required deterministic assertions 决定 PASS / FAIL，以及验证同一输入重复运行结果一致。

该改动会改变核心评测语义、指标聚合、Regression Gate、多次运行配对和测试数据，属于大改动。本阶段不修改产品代码。

## ADR / 历史方案检索

已按 evaluation、runner、regression、deterministic、LLM Judge、human review、assertion、Trace 和全部目标指标检索 `adr/`、`src/`、`tests/`、README、CHANGELOG。

- `2026-09-05-evaluation-dashboard-research/plan`：直接相关且已完成。定义了 17 项指标、人工语义审阅、不可变数据集、隔离回放，以及“全部必需断言可判定并通过”才能 verified 的原则。本次应修正当前实现与该原则的偏差。
- `2026-09-06-evaluation-regression-dataset-research/plan`：直接相关且已完成。建立 `core-regression/v1`、真实 Orchestrator 回放、固定 fixture 数据源、故障注入和 versioned seed，明确真实 LLM / Web Search 不属于稳定回归基线。
- `2026-09-20-evaluation-baseline-candidate-comparison-research/plan`：当前工作区未跟踪、尚未实施。计划修改 Runner、Service、Schema 和指标比较，但明确“不重构现有 17 项指标”。本次确定性评测是更基础的指标语义改动；实施时必须保留该文档，不假定其代码已经存在。
- `2026-09-20-reliability-regression-cases-research`：当前工作区未跟踪、尚无 Plan。与 `llm_fallback_success`、`agent_execution_failure_rate`、失败 Trace 和真实观测聚合高度重叠。本次 Plan 会吸收其中与 16 项指标直接相关的确定性观测要求，但不额外新增 `search_fallback_success` 或可靠性数据集 v2。
- `2026-09-19-decision-quality-p0-*` 及其未提交产品改动：DecisionState/质量能力正在演进。当前 Research 基于工作树真实代码；实施不得覆盖这些改动。

归档决策：新建本 Research / Plan。旧 Dashboard 与 Dataset ADR 已完成；直接追加会混淆历史实现和本次 Gate 语义修正。

## 当前核心文件与职责

| 文件 | 当前职责与已确认行为 |
| --- | --- |
| `evaluation/runner.py` | 在隔离 SQLite 中运行真实 Diet/Generic Orchestrator；逐条解释通用 path assertion；`manual` 只令 `passed=None`；Case 状态只检查 required assertion 是否显式失败。 |
| `evaluation/metrics.py` | 注册 16 项质量指标和 1 项 latency；按 assertion pass/fail 聚合；所有指标 `method` 固定为 `assertion`，未记录所需三态 `evaluationMethod`。 |
| `evaluation/schemas.py` | Case assertion 支持通用路径操作和 `manual`，有 `required`，但没有评测来源、结构化配对或确定性 evaluator 契约。 |
| `evaluation/observations.py` | 可生成精简业务投影，但当前 Runner 没有用它做多轮保持/What-if 比较。 |
| `evaluation/service.py` | 逐 Case / repetition 调 Runner、持久化 Result、汇总 Run，并按 Result status 更新 Bad Case 生命周期。重复次数彼此独立，尚未生成跨 repetition 稳定性断言。 |
| `services/trace.py` | Trace v2 已保存 revision before/after、正式状态初始投影、状态 diff、Recommendation before/after、model node、AgentRun、duration、commit 状态与失败信息。 |
| `evaluation/fixtures.py` | 20 条 Core 与 6 条 Fault Injection Case 主要使用通用 path/text assertion；`correction_coverage` 没有断言，多项指标只用 `speechText contains` 作为代理。 |
| `tests/test_evaluation_*.py` | 覆盖目录、基础聚合、真实 Orchestrator 和数据集运行；尚未覆盖 evaluationMethod、manual/Gate 隔离、结构化自动规则或重复运行一致性。 |

## 真实执行与数据流

`EvaluationService.create_run()` 读取不可变 Case snapshot，按 repetition 调用 `EvaluationRunner.run_case()`。Runner 在隔离数据库中执行真实 Orchestrator，输出最终 `decisionState`、逐轮 `turns` 和最后一轮 `traceSnapshot`，再逐条执行 Case 作者写入的 assertion。Result 保存 outputs、Trace、assertions、reviews 和 metrics；Run summary 重新从 Result assertions 聚合。

当前 Gate 逻辑是：存在 required assertion 且 `passed=False` 才失败；没有 assertion 才 `not_evaluated`。因此“只有 manual assertion”或“required assertion 无法判定”会被误判为 passed。`_sync_case_regression_status()` 又直接信任 Result status，可能把未被确定性证明的 Case 标记为 verified。

Human Review 保存到 `reviews_json`。`update_review()` 会重新调用 summary，但 `summarize_results()` 不读取 reviews，因此当前 review 实际不改变分数或 Gate；这个隔离是正确方向，但缺少显式契约和测试。

## 可复用的结构化事实

- `DecisionState`：domain、intent、constraints、candidates、candidateState、evidence、recommendation、excludedCandidates、agentRuns、traceRefs、revision、status、sources、searchRuns 和 domainState。
- `Candidate`：candidateId、attributes、evidence、eliminated、eliminationReasons、scoreBreakdown 和 evidenceIds。
- `Constraint`：key、kind、operator、value、unit、source、confidence。
- `Evidence`：evidenceId、candidateId、criterionKey、sourceId/sourceQuote、verification/citation/claim status、recordedRevision 和 supportingEvidenceIds。
- `Recommendation`：primary/alternatives、reasons、tradeoffDetails、evidenceIds、generatedFromRevision 和 rankingMethod。
- `Trace`：revisionBefore/revisionAfter、initialSnapshot、state diff、recommendationChange、model/agent events、request/commit status 和 duration。
- `turns`：每轮 message、traceId、speech/displayBlocks 和完整 DecisionState，可支持明确轮次的 before/after 比较。

这些结构足以做引用完整性、排除冲突、硬约束候选状态、revision 连续性、What-if 正式投影隔离、Fallback 发生与结果有效性、AgentRun 失败率等规则判断。Intent、约束、纠正目标、预期变化等仍需要 Case 金标签；不能从当前输出反向生成期望值。

## 16 项指标的可靠自动化边界

| 指标 | 可确定性判断的范围 | 必须人工或无法判断的范围 |
| --- | --- | --- |
| `intent_accuracy` | 对显式金标签 intent/domain 做精确比较。 | 未提供金标签时，不能仅凭原问题推断语义意图。 |
| `constraint_extraction_accuracy` | 对结构化期望的 key/kind/operator/value/unit/source/候选归属做集合比较。 | 自由文本约束的语义等价、隐含约束是否应抽取。 |
| `correction_update_accuracy` | 对指定 turn pair 检查 revision、新值、旧值移除和归属。 | 没有纠正目标金标签时不能自动确定用户真正想改什么。 |
| `hard_constraint_satisfaction` | 推荐不得命中 eliminated/excluded；可对结构化硬约束和候选属性执行明确运算。 | 自由文本或领域未知 operator 的可满足性。 |
| `exclusion_correctness` | 与显式期望排除集合比较，并检查误排、漏排和非法 candidate id。 | 未标注“应排除”集合时的业务判断。 |
| `recommendation_stability` | 相同 snapshot/config/source 的 repetition 间比较规范化 Recommendation。 | 非确定来源或配置不一致时不应给稳定性分。 |
| `sensitivity_to_condition_change` | 对显式 before/after turn 和预期 changed/unchanged 结论做配对判断。 | 条件变化后“应该怎样变”的开放语义。 |
| `reason_recommendation_consistency` | 校验 reason/tradeoff candidateId 属于候选且与 primary/alternative 关系、Evidence 关联结构一致。 | 理由文本是否充分、自然、真正支持结论。 |
| `evidence_reference_validity` | 校验 ID 存在、candidate/source 归属、source quote 可回溯、revision 不超前。 | 来源内容是否真实、权威，或 claim 的现实真实性。 |
| `unsupported_fact_rate` | 仅对已结构化 claim/evidence status 或受控故障中的明确禁止事实计算。 | 普通自然语言回答的 claim 拆分与事实支持性，默认 manual。 |
| `excluded_candidate_recommend_rate` | primary/alternative 与 excluded/eliminated 集合求交。 | 无。 |
| `multi_turn_state_retention` | 对标注为无正式编辑的 turn pair 比较规范化业务投影，忽略 revision/message/trace/what-if analysis。 | 未标注轮次意图时不能猜测哪些字段应该保持。 |
| `correction_coverage` | 对显式纠正目标检查 Trace/state diff 是否覆盖对应 path/candidate。 | 未提供纠正目标时不能定义分母。 |
| `what_if_isolation` | 识别标注 What-if turn，比较前后正式业务投影并要求 hypothetical analysis 与 revision 合法。 | 无法稳定识别的隐晦假设表达需 Case 标注。 |
| `llm_fallback_success` | Trace 中存在失败 model call，最终 request 成功、rules fallback 可观察、Recommendation/状态有效。 | 模型禁用不算失败；没有失败事件时不适用。 |
| `agent_execution_failure_rate` | 从所有回放 turn Trace 的 AgentRun/AGENT_CALL 精确计数 FAILED / total。 | 缺 Trace 的历史结果只能 not_evaluated。 |

## 当前缺口与风险

1. 当前 `method="assertion"` 无法表达 deterministic/manual/not_evaluated，也无法计算 deterministic coverage。
2. 通用 path assertion 本身可以是确定性的，但 `speechText contains` 经常只是弱代理；它不能自动证明全面语义质量。
3. Runner 只复制最后一轮 Trace；多轮 Agent failure、Fallback、revision 与 state diff 的完整判断需要每轮 Trace snapshot。
4. `recommendation_stability` 必须跨 repetition 计算，单次 Runner 无法可靠完成。
5. 只有 manual/unknown required assertion 目前会误过 Gate；这是 Regression Gate 的核心语义缺陷。
6. 手工 review 必须绑定具体 Result/output hash 才能避免输出变化后复用旧标签；即使保存 review，也不能进入 deterministic score/status/verified。
7. 旧 Dataset snapshot 必须继续可读；不能静默改写 `core-regression/v1`。若升级 seed assertion 契约，应发布新 dataset version。
8. 当前工作树已有用户未提交改动，且另有待审批的评测 Plan。实施应尽量局限 `evaluation/`、评测测试和文档；若必须修改已有冲突文件，应先停下更新 Plan。
9. LLM Judge 不在本次范围。未来若新增，只能写入 auxiliary/manual-like 结果，不能单独满足 required assertion 或决定 PASS / FAIL。

## Research 验证

已读取相关 ADR、Runner、Schema、Metrics、Service、Repository、核心 Decision/Trace 类型、fixtures 和主要测试。基线命令：

```text
.venv\Scripts\python.exe -m pytest tests\test_evaluation_runner.py tests\test_evaluation_metrics.py tests\test_evaluation_service.py -q
```

结果：10 passed；存在既有 `datetime.utcnow()` deprecation warnings。首次尝试系统 `python` 和 Codex bundled Python 分别因命令不存在、缺 pytest 失败，随后使用项目 `.venv` 成功。未运行全量测试，未修改产品代码或项目数据库。
## 实施前冲突审计补充（2026-09-20）

用户批准原 Plan 后重新检查工作树，发现原 Research 之后已有三组重叠能力完成实施，所以上文“当前实现”描述仅代表第一次研究时点，以下结论优先：

1. `evaluation-baseline-candidate-comparison` 已实施并验证：Runner 已接收类型化 Run configuration；Service/API/CLI 已支持严格 Baseline/Candidate 比较；新增 `evaluation/comparison.py`。本次不得覆盖配置、fingerprint、Result key、comparison API 或五类 Diff。
2. `model-call-trace-evaluation-cost-fallback` 已实施并验证：Trace 已扩展 Provider/usage/cost/fallback；Runner 已通过 `relatedTraces` 捕获 Case 全部轮次，并提供 observability/performance summary。本次直接复用，不再另造每轮 Trace 格式。
3. Reliability 相关代码已发布 `fault-injection-reliability/v2`，目录新增 `search_fallback_success`，并从 Trace observation 计算 Agent failure rate 与 latency。虽然对应 Plan 文档状态仍显示待审批，但当前代码和测试已经存在；本次将其视作必须保留的用户改动，不重复发布 Fault v2。
4. 当前指标目录为 18 项：17 项 scored quality metrics（包含用户要求的 16 项及新增 search fallback）和 1 项 latency。用户要求的 deterministic coverage 分母仍限定为其列出的 16 项；同时报告完整目录 coverage，避免隐藏 search 指标。
5. `EVALUATOR_VERSION` 仍为 `evaluation-v1`，但评分/Gate 口径即将改变。本次必须升级到 `evaluation-v2`，使现有严格 comparison 拒绝跨 evaluator 误比较。
6. README、CHANGELOG 和 Evaluation 测试均已有大量未提交修改。本次只能增量合并，不重写或回滚。

冲突审计基线：

```text
.venv\Scripts\python.exe -m pytest tests\test_evaluation_metrics.py tests\test_evaluation_runner.py tests\test_evaluation_service.py tests\test_evaluation_api.py tests\test_evaluation_cli.py tests\test_evaluation_comparison.py tests\test_trace_observability.py -q
```

结果：42 passed；仅有既存 `datetime.utcnow()` deprecation warnings。该结果证明重叠实现可作为本次增量开发基线，不代表 deterministic-first 需求已完成。