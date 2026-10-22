# Evaluation v3 离线评测结果

日期：2026-10-17

运行方式：临时 SQLite 数据库、已初始化 Diet 固定数据、`DisabledProvider`、真实 `EvaluationRunner` 与 Orchestrator。耗时数据受本机环境影响；无模型调用，因此 Token 与成本不可用。

## 总览

| Dataset | Case | 通过率 | Overall | 质量指标覆盖 | Deterministic target 覆盖 | 断言覆盖 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `core-regression/v3` | 20 | 100% | 100.00 | 14/21 | 14/20（70%） | 32/32（100%） |
| `fault-injection-reliability/v2` | 8 | 100% | 99.61 | 6/21 | 5/20（25%） | 29/29（100%） |

两个 Run 均为 0 failed、0 error、0 not_evaluated Case。指标级 `not_evaluated` 表示该 Dataset 没有对应金标签或需要人工审阅，不等同于 Case 失败。

## 全部 23 项指标

`—` 表示本 Dataset 不适用或未评测。低优指标展示原始发生率，越低越好。

| 指标 | Core v3 值 | Core 分母 | Fault v2 值 | Fault 分母 |
| --- | ---: | ---: | ---: | ---: |
| `intent_accuracy` | 100% | 2 | — | 0 |
| `domain_routing_accuracy` | 100% | 5 | — | 0 |
| `clarification_decision_accuracy` | 100% | 3 | — | 0 |
| `constraint_extraction_accuracy` | 100% | 1 | — | 0 |
| `correction_update_accuracy` | 100% | 2 | — | 0 |
| `hard_constraint_satisfaction` | 100% | 3 | — | 0 |
| `soft_preference_satisfaction` | 100% | 2 | — | 0 |
| `safety_constraint_violation_rate` | 0% | 1 | — | 0 |
| `exclusion_correctness` | 100% | 1 | — | 0 |
| `recommendation_stability` | — | 0 | — | 0 |
| `sensitivity_to_condition_change` | — | 0 | — | 0 |
| `reason_recommendation_consistency` | 100% | 4 | — | 0 |
| `evidence_reference_validity` | 100% | 4 | 100% | 1 |
| `unsupported_fact_rate` | manual review | 0 | 0% | 1 |
| `excluded_candidate_recommend_rate` | — | 0 | 0% | 1 |
| `multi_turn_state_retention` | — | 0 | — | 0 |
| `correction_coverage` | 100% | 2 | — | 0 |
| `what_if_isolation` | 100% | 2 | — | 0 |
| `llm_fallback_success` | — | 0 | 100% | 14 |
| `search_fallback_success` | — | 0 | 100% | 6 |
| `fallback_activation_rate`（不计分） | 0% | 20 Case | 75% | 8 Case |
| `agent_execution_failure_rate` | 0% | 197 AgentRun | 2.35% | 85 AgentRun |
| `average_response_time_ms`（不计分） | 284.80 ms | 20 Case | 127.62 ms | 8 Case |

Core 的 `recommendation_stability` 需要 `repeat >= 2`，本次实际 Run 使用默认单次执行，因此按设计为 `not_evaluated`。`unsupported_fact_rate` 在 Core 中包含人工审阅断言，未被伪造成确定性分数。

## 分类与性能

Core v3 的需求理解、决策质量、解释质量、多轮交互、工程可靠性分类得分均为 100%。平均响应时间 284.80 ms，P95 为 781 ms；Fallback 激活 0/20，Agent 执行失败 0/197。

Fault v2 的解释质量为 100%，工程可靠性为 99.22%，Overall 为 99.61。平均响应时间 127.62 ms，P95 为 298 ms；Fallback 激活 6/8，Agent 执行失败 2/85。Fault Dataset 会主动注入故障，因此 75% Fallback 激活率是预期观测值，且该指标不进入总分。

## 路由诊断

Core v3 路由样本 5 条，Accuracy、Macro Precision、Macro Recall、Macro F1 均为 100%。

| 期望 \ 实际 | diet | generic | shopping | travel |
| --- | ---: | ---: | ---: | ---: |
| diet | 1 | 0 | 0 | 0 |
| generic | 0 | 2 | 0 | 0 |
| shopping | 0 | 0 | 1 | 0 |
| travel | 0 | 0 | 0 | 1 |

Fault v2 没有路由金标签，路由诊断按设计为空，不计 0 分。

## 分组结果

Core v3 按领域：diet 3/3、generic 6/6、shopping 6/6、travel 5/5 全部通过。

按 Case 类型：clarification 2/2、correction 2/2、evidence 1/1、hard_constraint 2/2、recommendation 3/3、routing 5/5、safety 1/1、soft_preference 2/2、what_if 2/2 全部通过。

Fault v2 按领域：generic 5/5、shopping 2/2、travel 1/1 全部通过；历史 Case 未设置 `caseType`，均兼容归入 `general`（8/8）。完整 tag 分组通过 API/Run Summary 的 `groups.byTag` 提供。
