# Diet Evaluation Parity Research

## Scope

用户要求补齐 `diet-agent` 中已有但 `choice-agent-v2` 尚未完整迁移的能力，当前优先级是评估（eval）。

本次研究范围限定在饮食评估链路：Trace 标注、评估 API、EvaluationAgent、反馈归因、指标聚合、现有测试，以及旧 `diet-agent` 的评估语义。意图修正和个人餐食库空状态也被识别为相关缺口，但不纳入本轮第一批实现。

## ADR Lookup

- `adr/2026-08/2026-08-29-diet-agent-python-migration-research.md`：记录旧系统包含 Trace 管理和评估页面，是本轮功能基线来源。
- `adr/2026-08/2026-08-29-diet-agent-python-migration-plan.md`：计划中要求迁移 Trace、反馈和 Agent 评估，但当前实现只覆盖了最小路径。
- `adr/2026-08/2026-08-29-choice-agent-v1-borrowed-ideas-todo.md`：提到完整多 Agent 业务闭环和评估样例，说明 eval 后续应沉淀为领域插件能力。
- `adr/2026-08/2026-08-30-frontend-api-settings-research.md` / `plan.md`：评估接口支持浏览器侧模型配置，且模型密钥不得进入 Trace。

已有迁移文档已经收尾，本轮主题是补齐迁移后的语义缺口，因此新建本 Research 和对应 Plan。

## Current Implementation

`src/choice_agent/api/routes.py` 的 `POST /api/v1/diet/evaluations` 已存在，会按时间读取 Trace，逐条构造 `EvaluationAgent` 上下文，并返回 `totalTraces`、`labeledTraces`、`avgScore`、`metricAverages` 和 `traceResults`。

当前限制：

- 上下文只传入 `expected_intent` 和 `expected_clarify_action`，没有传 `expected_slots`。
- `userFeedbackScore` 固定为 `None`。
- `metricAverages` 只聚合 `intentAccuracy` 和 `clarifyAccuracy`。
- LLM Judge 和规则分使用简单平均，不复刻旧系统的权重组合。
- 明细 `detail` 没有输出 predicted/expected 对照、反馈数量等诊断信息。

`src/choice_agent/agents/diet.py` 中 `EvaluationAgent` 当前只从 Trace events 提取 `IntentAgent.outputPayload.intent` 和 `ClarificationAgent.outputPayload.action`。规则指标只有 `intentAccuracy`、`clarifyAccuracy`、`safetyCompliance`、`score`。可选 LLM Judge 只评估 `explanationQuality` 和 `naturalness`。

`TraceRecord` 已有 `expected_slots`，`TraceLabelRequest` 也支持 `expected_slots`，`DietRepository.label_trace()` 会保存它。`FeedbackRecord` 已保存用户反馈，但当前 repository 没有面向评估的反馈查询方法。

## Old diet-agent Baseline

旧 `EvaluationService` 的单条 Trace 指标包括：

- `intentAccuracy`
- `slotAccuracy`
- `clarifyNecessityAccuracy`
- `tokenCost`
- `tokenCostScore`
- `latencyMs`
- `latencyScore`
- `fallbackRate`
- `fallbackScore`
- `safetyCompliance`
- `hallucinationControl`
- `multiTurnConsistency`
- 可选 `explanationQuality`
- 可选 `naturalness`

旧实现还会将 session 反馈近似归因到 Trace，并通过 `weightedScore(ruleScore, llmJudgeScore, userFeedbackScore)` 生成最终分数。

## Reusable Capabilities

- Trace JSON 中已有 events 和 AgentRun 输出，可以提取实际 intent、slots、clarify action、候选列表、最终推荐列表和异常状态。
- Trace label 已支持 expected slots。
- FeedbackRecord 已落库，可按 user/session/time 范围关联。
- 前端评估页已能展示动态 `metricAverages` 和 `userFeedbackScore` 字段，不需要第一批大改 UI。

## Constraints

- v2 Trace event 结构与旧 Java 不完全一致，指标提取必须兼容缺字段。
- feedback 没有 traceId，只能按 session 近似归因；这与旧系统一致，但报告 detail 应体现反馈数量。
- token usage 目前未必被 provider 写入 Trace，`tokenCost` 应允许为 `None`。
- hallucinationControl 依赖“最终推荐 item 是否来自候选/排名列表”。如果 Trace 缺候选或最终推荐，不能误判失败，应按通过处理。
- multiTurnConsistency 依赖 adjustment/avoid recent 语义。第一批实现只做可从 Trace 稳定提取的推荐 item 与 avoid/excluded item 对照；缺数据返回 `None`。

## Open Questions For Plan

- 指标提取函数放在 `EvaluationAgent` 内，还是拆成独立 helper。
- feedback 查询放在 repository 的新方法还是直接在 route 查询。
- 规则分和最终分的权重是否完全复刻旧系统。
- 是否本轮同步更新 `docs/migration-matrix.md` 和 `CHANGELOG.md`。