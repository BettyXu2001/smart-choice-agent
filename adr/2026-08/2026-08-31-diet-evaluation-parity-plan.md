# Diet Evaluation Parity Plan

## Goal

补齐 `choice-agent-v2` 的饮食评估能力，使其从“能生成最小评估报告”提升到接近旧 `diet-agent` 的规则指标语义。

成功标准：

- 评估报告包含旧系统核心指标：intent、slot、clarify、token、latency、fallback、safety、hallucination、multi-turn、可选 LLM Judge。
- Trace 标注中的 `expectedSlots` 参与 `slotAccuracy`。
- 用户反馈按 session 近似归因，并输出 `userFeedbackScore`。
- `metricAverages` 聚合所有数值指标，跳过 `None`。
- 单条 trace detail 输出 predicted/expected 对照和反馈数量，便于排查。
- 现有评估 API 和前端调用方式保持兼容。
- 补充针对完整指标的测试。

## Design

### EvaluationAgent

在 `src/choice_agent/agents/diet.py` 中扩展 `EvaluationAgent`，优先保持单文件小范围实现。

新增内部 helper：

- 从 events 中提取 predicted intent、predicted slots、predicted clarify action。
- 从 Agent 调用事件中累计 latency。
- 从 Trace 中识别失败和 fallback：Trace status 为 `FAILED`、Agent event status 为 `FAILED`、eventType 含失败事件或 payload 有 error 时视为 fallback。
- 从候选/推荐相关事件提取 ranked item ids 和 response item ids，用于 `hallucinationControl`。
- 从调整请求或上下文中提取 avoid/excluded item ids，用于 `multiTurnConsistency`；提取不到则返回 `None`。

实现指标：

- `intentAccuracy`：无 expected intent 时为 1.0，否则精确匹配。
- `slotAccuracy`：无 expected slots 时为 1.0；有 expected slots 时按字段和值集合匹配比例计算。
- `clarifyNecessityAccuracy`：无 expected clarify action 时为 1.0，否则精确匹配。
- `tokenCost`：Trace 中存在 token 字段时累加，否则 `None`。
- `tokenCostScore`：`None` 或 `<=1000` 为 1.0，`>=3000` 为 0.0，中间线性衰减。
- `latencyMs`：可提取 latency 时累加，否则 `None`。
- `latencyScore`：`None` 或 `<=1000ms` 为 1.0，`>=5000ms` 为 0.0，中间线性衰减。
- `fallbackRate`：单条 Trace 使用 1.0/0.0。
- `fallbackScore`：`1 - fallbackRate`。
- `safetyCompliance`：无失败和高风险违规为 1.0，否则 0.0。
- `hallucinationControl`：最终推荐为空或候选为空时为 1.0；否则最终 item ids 必须都来自候选 ids。
- `multiTurnConsistency`：无法判断时 `None`；能判断时 1.0/0.0。

`ruleScore` 使用可用规则分指标平均，跳过观测值 `tokenCost`、`latencyMs` 和 `None`。

### Feedback and Score

在 `src/choice_agent/repositories/diet_repository.py` 增加只读查询方法，按 `user_id`、session ids、时间范围读取 `FeedbackRecord`。

反馈分规则：

- rating 存在时使用 `rating / 5`。
- 无 rating 时，`ADOPT=1.0`、`LIKE=0.8`、`DISLIKE=0.0`。
- 同一 trace 使用其 session 的反馈均值；无反馈为 `None`。

最终分：

- 仅 ruleScore：`score = ruleScore`
- rule + judge：`score = 0.8 * ruleScore + 0.2 * llmJudgeScore`
- rule + feedback：`score = 0.7 * ruleScore + 0.3 * userFeedbackScore`
- rule + judge + feedback：`score = 0.6 * ruleScore + 0.1 * llmJudgeScore + 0.3 * userFeedbackScore`

### API Output

修改 `src/choice_agent/api/routes.py`：

- 将 `expected_slots` 传入 EvaluationAgent。
- 获取时间范围内相关 session 的 feedback。
- 输出完整 `metrics`。
- `metricAverages` 动态聚合所有数值型 metrics，跳过 `None`。
- `detail` 增加 predicted/expected 对照、feedbackCount 和 Judge 可用性状态。

保持原字段名 `traceId/sessionId/score/ruleScore/llmJudgeScore/userFeedbackScore/metrics/detail` 不变。

## Files

- `src/choice_agent/agents/diet.py`
- `src/choice_agent/api/routes.py`
- `src/choice_agent/repositories/diet_repository.py`
- `tests/test_orchestrator.py` 或新增 `tests/test_evaluation.py`
- `docs/migration-matrix.md`
- `CHANGELOG.md`

## Compatibility and Risks

- API 不删除现有字段，前端应继续可用。
- 新增指标会改变 `avgScore` 数值，这是预期行为。
- 旧 Trace 缺少 token 或候选字段时，指标必须合理降级，不能导致 500。
- feedback 仍按 session 近似归因，可能不能精确定位到某一轮推荐，这是旧数据模型限制。
- LLM Judge 失败仍不应阻断评估，但应在 detail 中保留不可用状态。

## Verification

- 运行现有测试。
- 新增或扩展评估测试，覆盖 expected slots、feedback、metric averages、缺字段降级和 fallback 指标。
- 检查 `git diff`，确认没有计划外修改。

## Todo

- [x] 扩展 `EvaluationAgent` 的 Trace 快照提取和完整规则指标。
- [x] 增加 repository 反馈查询，并在评估 API 中完成 session 反馈归因。
- [x] 调整评估 API 的 score、metricAverages 和 detail 输出。
- [x] 补充评估指标测试。
- [x] 更新 migration matrix 和 changelog。
- [x] 运行测试并检查最终 diff。