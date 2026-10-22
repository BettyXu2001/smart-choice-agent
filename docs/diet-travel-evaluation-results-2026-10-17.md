# Diet / Travel Evaluation v1 离线评测结果

日期：2026-10-17

## 运行说明

- Dataset：`diet-travel-evaluation/v1`
- Evaluator：`evaluation-v3`
- Case：20 条，Diet 10 条、Travel 10 条
- Repeat：2，共 40 个 Result
- 环境：内存 SQLite、已初始化 Diet 固定数据、fixture 候选、`DisabledProvider`
- 真实链路：全部 Case 经过 `EvaluationRunner` 与对应 Orchestrator；没有使用 `fixtureActual`
- Dataset hash：`2289e4af9a804523239613a90ace9a307374e9de416fb42d5c38d0ff3ce94bf4`

Token 和成本为不可用，不记为 0：本次不调用付费模型；8 次受控模型调用没有 provider usage，`unreportedUsageCallCount=8`。

## 总览

| 项目 | 结果 |
| --- | ---: |
| Case / Result | 20 / 40 |
| Passed / Failed / Error | 38 / 2 / 0 |
| 通过率 | 95% |
| Overall | 99.16 |
| 质量指标覆盖 | 21/21（100%） |
| Deterministic target 覆盖 | 20/20（100%） |
| Deterministic assertion 覆盖 | 88/88（100%） |
| 平均延迟 | 517.40 ms |
| P95 延迟 | 1696 ms |

分类得分：需求理解 96.00、决策质量 100.00、解释质量 100.00、多轮交互 100.00、工程可靠性 99.78。

## 全部 23 项指标

低优指标展示原始发生率，越低越好。全部指标均有确定性分母，没有 manual 或 `not_evaluated` 指标。

| 指标 | 值 | 分子 / 分母 | 方法 |
| --- | ---: | ---: | --- |
| `intent_accuracy` | 100% | 4 / 4 | deterministic |
| `domain_routing_accuracy` | 100% | 4 / 4 | deterministic |
| `clarification_decision_accuracy` | 100% | 4 / 4 | deterministic |
| `constraint_extraction_accuracy` | 80% | 8 / 10 | deterministic |
| `correction_update_accuracy` | 100% | 4 / 4 | deterministic |
| `hard_constraint_satisfaction` | 100% | 10 / 10 | deterministic |
| `soft_preference_satisfaction` | 100% | 4 / 4 | deterministic |
| `safety_constraint_violation_rate` | 0% | 0 / 2 | deterministic |
| `exclusion_correctness` | 100% | 2 / 2 | deterministic |
| `recommendation_stability` | 100% | 6 / 6 | deterministic |
| `sensitivity_to_condition_change` | 100% | 2 / 2 | deterministic |
| `reason_recommendation_consistency` | 100% | 4 / 4 | deterministic |
| `evidence_reference_validity` | 100% | 4 / 4 | deterministic |
| `unsupported_fact_rate` | 0% | 0 / 4 | deterministic |
| `excluded_candidate_recommend_rate` | 0% | 0 / 4 | deterministic |
| `multi_turn_state_retention` | 100% | 2 / 2 | deterministic |
| `correction_coverage` | 100% | 4 / 4 | deterministic |
| `what_if_isolation` | 100% | 2 / 2 | deterministic |
| `llm_fallback_success` | 100% | 2 / 2 | deterministic |
| `search_fallback_success` | 100% | 10 / 10 | deterministic |
| `fallback_activation_rate`（不计分） | 10% | 4 / 40 Result | Trace observation |
| `agent_execution_failure_rate` | 0.66% | 2 / 304 AgentRun | Trace observation |
| `average_response_time_ms`（不计分） | 517.40 ms | 20696 / 40 Result | Trace observation |

`agent_execution_failure_rate` 的 2 次失败来自重复执行的受控 `CandidateAgent` failure Case，属于预期故障注入；该 Case 的错误状态、回滚和 Trace 断言均通过。

## 性能、Token 与成本

| 项目 | 结果 |
| --- | ---: |
| 延迟样本 | 40 |
| 平均延迟 | 517.40 ms |
| P95 延迟 | 1696 ms |
| Provider call | 8 |
| Token 样本 | 0 |
| Total / Average Token | N/A / N/A |
| Known / Estimated Cost | N/A / N/A |
| 未报告 usage 的调用 | 8 |
| 未知价格调用 | 0 |

耗时只代表本机离线基线，不作为线上 SLA。

## 路由诊断

重复执行后共有 4 个路由样本。Accuracy、Macro Precision、Macro Recall、Macro F1 均为 100%。

| 期望 \ 实际 | diet | travel |
| --- | ---: | ---: |
| diet | 2 | 0 |
| travel | 0 | 2 |

## 分组结果

### 领域

| 领域 | Passed / Total | 通过率 | Overall |
| --- | ---: | ---: | ---: |
| Diet | 18 / 20 | 90% | 99.00 |
| Travel | 20 / 20 | 100% | 99.92 |

### Case 类型

| Case Type | Passed / Total |
| --- | ---: |
| `clarification` | 4 / 4 |
| `conflict` | 2 / 2 |
| `correction` | 4 / 4 |
| `edge` | 6 / 6 |
| `hard_constraint` | 2 / 4 |
| `recommendation` | 4 / 4 |
| `reliability` | 2 / 2 |
| `routing` | 4 / 4 |
| `safety` | 2 / 2 |
| `soft_preference` | 4 / 4 |
| `stability` | 2 / 2 |
| `what_if` | 2 / 2 |

### 关键 Tag

| Tag | Passed / Total |
| --- | ---: |
| `diet` | 18 / 20 |
| `travel` | 20 / 20 |
| `hard_constraint` | 2 / 4 |
| `exclusion` | 2 / 4 |
| `fault_injection` | 6 / 6 |
| `fallback` | 4 / 4 |
| `multi_turn` | 8 / 8 |
| `stability` | 6 / 6 |
| `unsupported_fact` | 4 / 4 |

完整机器可读结果见 `docs/diet-travel-evaluation-results-2026-10-17.json`。

## Bad Case

唯一失败 Case：`diet-travel-v1.diet-hard-exclusion`，两个 repetition 均失败。

- 输入：`晚餐不要清淡，想吃咸鲜的`
- 正确行为：生成 `diet_exclusion=清淡` 后，不应再把 `清淡` 保留为正向 `healthGoal`。
- 实际行为：状态同时包含硬排除 `清淡` 和 `domainState.slots.healthGoal=["清淡"]`。
- 失败指标：`constraint_extraction_accuracy`，两次断言均失败，因此该指标为 8/10（80%）。
- 附加观察：当前 Case 没有可判定 Recommendation，单 Case 的 `hard_constraint_satisfaction` 和 `excluded_candidate_recommend_rate` 为 `not_evaluated`；这两项仍由批次中的其他 Case 提供有效分母。
- 影响：理解层存在互相冲突的正负条件，可能让后续解释或排序产生歧义。
- 本任务只记录问题，没有越过已批准范围修改 Diet 产品逻辑。

## Case 清单

### Diet

1. `diet-route`：自动路由。
2. `diet-recommendation`：完整推荐、理由、Evidence、稳定性。
3. `diet-clarification`：信息不足追问。
4. `diet-hard-exclusion`：排除项与正向偏好冲突；失败。
5. `diet-soft-preference`：清淡偏好评分。
6. `diet-safety`：医疗风险阻断。
7. `diet-correction`：餐次/口味纠正。
8. `diet-refresh`：换一批与候选排除。
9. `diet-unverified-restriction`：未知过敏原不静默过滤。
10. `diet-stability`：固定输入重复稳定。

### Travel

1. `travel-route`：自动路由。
2. `travel-clarification`：缺少出发地/天数时追问。
3. `travel-hard-budget`：预算硬筛选。
4. `travel-soft-preference`：人少偏好评分。
5. `travel-conflict`：不可满足预算不误推荐。
6. `travel-correction`：预算多轮纠正。
7. `travel-rain-what-if`：下雨假设隔离与不编造事实。
8. `travel-model-timeout`：完整推荐、解释、Evidence、状态保持和 LLM fallback。
9. `travel-search-fallback`：Search transport error 回退 fixture。
10. `travel-agent-failure`：CandidateAgent 失败、回滚与 Trace 定位。
