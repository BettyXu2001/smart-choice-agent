# Deterministic Evaluation v2 P0 Research

日期：2026-10-05。状态：Research 完成，等待 Plan 审批。

## 当前需求和研究范围

用户要求按 P0 优先级完成三组评估能力：

1. 完成 Deterministic Evaluation v2：指标三态 `deterministic / manual / not_evaluated`，manual 不参与自动得分和 Regression Gate，只有 required deterministic assertions 决定 Pass / Fail，没有可判定规则时必须是 `not_evaluated`，补 deterministic coverage，不做 LLM Judge。
2. 修正 Baseline / Candidate 对比语义：明确 `failed -> passed = fixed`、`passed -> failed = new_failure`、`not_evaluated -> passed = improved`、`passed -> not_evaluated = regressed`，且 `failed -> not_evaluated` 不能算 improved；Evaluation coverage 下降要明确提示。
3. 完善 Regression Dataset：发布 `core-regression/v2`，保留 v1，将弱文本匹配断言改为结构化断言，覆盖需求理解、硬约束、排除候选、多轮状态、What-if、Fallback，并验证同一 Case 重复执行稳定性。

这会影响评估核心语义、回归门禁、版本对比和测试覆盖，按大改动处理。本阶段未修改产品代码。

## ADR / 历史方案检索

已按 evaluation、deterministic、Regression Gate、baseline/candidate、comparison、core-regression、manual、not_evaluated、coverage、dataset、assertion 等关键词检索 `adr/`、`src/choice_agent/evaluation/`、`tests/`、`README.md`、`CHANGELOG.md`。

相关记录：

- `adr/2026-09/2026-09-20-deterministic-evaluation-runner-research.md` / `plan.md`：高度相关，记录 deterministic-first 评估、三态、manual/Gate 隔离、`core-regression/v2` 和重复运行稳定性。文档状态为已完成，但当前测试覆盖未完全达到其 Plan 中“覆盖 16 项规则路径”的要求。
- `adr/2026-09/2026-09-20-evaluation-baseline-candidate-comparison-research.md` / `plan.md`：高度相关，已实现严格 Run comparison 和五类 diff。当前实现沿用状态质量排序 `error < failed < not_evaluated < passed`，导致 `failed -> not_evaluated` 会被判定为 `improved`，与本次用户明确语义冲突。
- `adr/2026-09/2026-09-06-evaluation-regression-dataset-research.md` / `plan.md`：相关，建立 `core-regression/v1` 和不可变 snapshot。本次代码已保留 v1 并新增 v2。
- `adr/2026-09/2026-09-20-reliability-regression-cases-research.md` / `plan.md`：相关，已发布 `fault-injection-reliability/v2`，覆盖 LLM/Search/Agent failure 和 fallback/trace 指标；本次应复用，不扩大到新可靠性集。

归档决策：新建本 Research / Plan。既有 2026-09 文档均为已完成历史记录，本次是验收缺口修正和测试补强，追加旧文档会混淆历史语义。

## 核心文件及其职责

| 文件 | 当前实现 |
| --- | --- |
| `src/choice_agent/evaluation/schemas.py` | 已定义 `EvaluationMethod = deterministic/manual/not_evaluated`，断言支持 `auto` 和 `manual`；禁止 required manual assertion；禁止用户直接配置 `not_evaluated`。 |
| `src/choice_agent/evaluation/runner.py` | 执行真实 Orchestrator，逐条断言生成 `evaluationMethod`；`deterministic_gate_status()` 已实现 required deterministic-only Gate；缺 path 返回 `not_evaluated`。 |
| `src/choice_agent/evaluation/deterministic.py` | 已实现 16 项目标指标的 `auto` evaluator 和 repetition stability helper；普通 unsupported fact 默认不可判定，符合不做 LLM Judge。 |
| `src/choice_agent/evaluation/metrics.py` | `EVALUATOR_VERSION = evaluation-v2`；summary 只聚合 deterministic 有值指标，输出 deterministic coverage、manualReviewMetricIds、notEvaluatedMetricIds。 |
| `src/choice_agent/evaluation/service.py` | 默认 dataset 已指向 `core-regression/v2`；seed v1/v2/fault v2；重复运行后回写 `recommendation_stability`；Human Review 只更新 reviews，不改 summary/Gate。 |
| `src/choice_agent/evaluation/fixtures.py` | 保留 `core-regression/v1`，新增 `core-regression/v2` 的结构化 `auto` / `manual` assertions；fault v2 保留。 |
| `src/choice_agent/evaluation/comparison.py` | 严格校验两个 Run 可比性并输出五类 diff；当前 fallback 状态质量排序会把 `failed -> not_evaluated` 归为 `improved`。 |
| `tests/test_deterministic_evaluation.py` | 目前只覆盖 required manual 校验、Gate 和 missing path not_evaluated，未覆盖 16 项 evaluator。 |
| `tests/test_evaluation_comparison.py` | 覆盖部分五类 diff，但缺少用户明确列出的完整状态转换，特别是 `failed -> not_evaluated`。 |
| `tests/test_evaluation_service.py` | 已覆盖 v1/v2 seed、默认 v2 run、Human Review 隔离、repeat stability。 |

## 关键调用链和数据流

Evaluation run：

`EvaluationService.create_run()` -> `ensure_starter_cases()` -> 默认选择 `core-regression/v2` -> `EvaluationRunner.run_case()` -> 真实 Orchestrator 或 fixture actual -> `_evaluate_assertion()` -> `evaluate_auto_assertion()` -> `deterministic_gate_status()` -> 保存 Result -> `_finalize_repetition_metrics()` -> `summarize_results()` -> `_sync_case_regression_status()`。

Comparison：

`EvaluationService.compare_runs()` -> `compare_runs()` -> `_validate_runs()` -> 按 `(caseId, caseRevision, repetition)` 对齐 -> `_case_outcome()` -> `classify_case_diff()` -> `_aggregate_delta()`。

## 已确认满足的点

- 指标和 assertion result 已有三态 `evaluationMethod`。
- `manual` assertion 禁止 required，且 `aggregate_metric()` 不把 manual 纳入自动得分。
- Regression Gate 已只看 required deterministic assertions；只有 manual 或缺判定时返回 `not_evaluated`。
- 没有发现 LLM Judge 实现路径；deterministic evaluator 不访问网络或模型。
- `core-regression/v2` 已发布，`core-regression/v1` 仍 seed 和 dataset 共存。
- v2 core cases 已用结构化 `auto` assertions 替换大部分 v1 弱文本匹配，并显式保留 manual 边界。
- 同一 Case repeat=2 的 stability 已有 service 测试。

## 缺口和隐患

1. `classify_case_diff()` 当前先处理 fixed/new_failure，再比较分数，最后使用 `_STATUS_QUALITY = {"error":0,"failed":1,"not_evaluated":2,"passed":3}`。因此当 baseline failed、candidate not_evaluated 且没有可比分数时，会返回 `improved`。这与用户要求“failed -> not_evaluated 不能算 improved”冲突。
2. Comparison response 目前有 summary coverage，但没有对 “Evaluation coverage 下降” 给出专门提示字段；用户要求明确提示，不能只让调用方自己比 coverage 数字。
3. `tests/test_deterministic_evaluation.py` 没有覆盖 16 个 `_AUTO_EVALUATORS` 的 deterministic/manual/not_evaluated 规则边界。代码有实现，但 coverage 不足，容易回归。
4. `tests/test_evaluation_comparison.py` 缺少完整状态转换表：`not_evaluated -> passed`、`failed -> not_evaluated`、`passed -> failed`、`passed -> not_evaluated` 的显式断言。
5. `core-regression/v2` 的默认 dataset 选择依赖 service 中 `CORE_DATASET` 常量，目前正确；应补更精确测试确认默认选择版本是 v2，且 v1 不被覆盖。

## 约束

- 不改 `core-regression/v1` snapshot。
- 不新增 LLM Judge，不调用模型做评估裁判。
- 不新增数据库表或迁移，继续使用现有 JSON 字段。
- 不改变现有 metric id、dataset name、API 路径和 Run comparison 的可比性校验。
- 修改范围应限制在 evaluation comparison、测试、必要文档和 CHANGELOG。

## Plan 阶段需决策的问题

- `failed -> not_evaluated` 应归为 `regressed` 还是 `unchanged`？用户只明确“不能算 improved”。建议归为 `regressed`，因为 candidate 丢失了原本可判定失败的覆盖，属于 coverage/diagnostic 能力下降。
- coverage 下降提示放在 `aggregateDelta` 内，还是新增顶层 `coverageWarnings`？建议新增顶层 `coverageWarnings` 并在 `aggregateDelta.coverage` 提供结构化 delta，兼顾机器读取和 UI 展示。
- deterministic evaluator 测试采用直接调用 `evaluate_auto_assertion()` 的小型结构化 fixtures，而不是跑真实 Orchestrator，以保持快、稳定、精准。