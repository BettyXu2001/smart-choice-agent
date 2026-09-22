# 推荐反馈闭环 Plan

## 状态与范围

2026-09-22：用户已明确回复“实施”，批准按本 Plan 进入实现。实现与自动验证已完成。依据同目录 `2026-09-22-recommendation-feedback-loop-research.md`。

范围仅为饮食推荐卡片现有“喜欢 / 采纳 / 不合适”。不扩展通用决策 UI，不新增 Agent、Prompt、模型调用、依赖或数据库表；“不合适”只复用现有 rerank / recommendation / risk 链路。

## 目标与成功标准

1. LIKE 持久化候选级正向反馈，并在对话区显示简短确认；不自动推导长期资料或槽位。
2. ADOPT 持久化反馈并写入 DecisionOutcome，在对话区确认采纳，把当前推荐轮次标为已结束。
3. DISLIKE 持久化负向反馈，将所点当前候选并入本轮排除列表，保留 slots、constraints、criteria 和上下文，直接重算并自动展示新结果。
4. 三类反馈都有独立 Trace，能看到 action、候选、原推荐、反馈后推荐；DISLIKE Trace 继续展示真实过滤、排序和解释节点。
5. 反馈写入、DecisionState、assistant message、session 和 Trace 成功状态一致；失败不留下半份业务写入。
6. 只有当前有效推荐可反馈；旧轮次、无权会话、陈旧 revision、未知 action 和非当前候选被拒绝。
7. 网络重试不重复记录反馈、不重复加 revision 或消息。

## API 与状态设计

### FeedbackRequest

在现有字段上增加：

- `requestId`：可选但前端始终传，用于幂等回执；兼容旧客户端不传。
- `expectedRevision`：可选但前端始终传；提供时执行并发校验，兼容旧客户端调用。
- `action` 收紧为 `LIKE | ADOPT | DISLIKE`。
- 三类按钮均要求 `itemId`，服务端验证它属于当前 `domainState.displayBlocks`。

`POST /api/v1/diet/feedback` 从 204 改为返回 `ChatResponse`。现有调用方只依赖请求成功，不依赖空响应；Evaluation 直接调用 Repository，不受响应变更影响。

### DecisionState 内反馈轮次

在既有 JSON `domainState` 中维护有界的 `feedbackRound`：当前状态（active/adopted）、最后 action、candidateId、traceId、revision。它用于前端关闭已采纳轮次和恢复状态，不新建表。

`recommend_feedback` 是反馈事实记录；LIKE 不修改用户 Profile。ADOPT 同时设置 `DecisionOutcome(candidate_id, label, reason="用户采纳推荐")`。DISLIKE 将字符串候选 ID 去重合并到 `excluded_candidates`。

反馈幂等回执放入内部 `domainState.feedbackReceipts`，公开状态时移除，策略与 dietReceipts 一致；同 ID 同 payload 返回原响应，同 ID 不同 payload 报错。

## 三类反馈流程

### LIKE

1. 校验 owner、revision、当前候选和轮次可操作。
2. 在同一事务写 `FeedbackRecord(action=LIKE)`。
3. 记录 assistant message：“收到，你喜欢「候选名」，我已记录这条偏好。”
4. 保持 recommendation、排除项和轮次 active，不执行推荐链路，不调用 LLM。
5. 追加 dietTurn、revision、反馈 Trace 和回执，返回 ChatResponse。

### ADOPT

1. 校验并写 `FeedbackRecord(action=ADOPT)`。
2. 写入 DecisionOutcome，轮次状态设为 adopted，保留当前 recommendation 供回看。
3. assistant message：“好的，已采纳「候选名」，本轮推荐已结束。”
4. 不重排、不调用 LLM；前端刷新后当前轮次按钮隐藏或禁用。
5. 后续仍可开始新聊天请求，但本轮不设计自动新建 session。

### DISLIKE

1. 校验当前候选并写 `FeedbackRecord(action=DISLIKE)`。
2. 把 itemId 合并进 `decision.excluded_candidates`，不调用 AdjustmentAgent，不排除其他历史推荐。
3. 从当前 DecisionState 构造上下文，保留 slots、constraints、criteria、sourceMode、风险与选择配置。
4. 调用 `UnifiedDecisionOrchestrator.recompute(..., refresh_candidates=False)`；候选池缺失时由现有逻辑重新检索。三餐继续通过现有 compose。
5. 有新推荐时，assistant 文案为“这款不太合适，我帮你换一个。”加现有 ExplanationAgent 说明；无候选时明确已排除但暂无新结果，不放宽约束、不恢复原候选。
6. 更新 displayBlocks、session.lastRecommendations、recommendation、dietTurn、revision 和 active feedbackRound，返回新卡片。

## Trace 设计

每次反馈创建新的 TraceScope：

- `requestKind = feedback`，metadata / turnSummary 加 `feedbackType` 和 `feedbackCandidateId`。
- `FEEDBACK_RECEIVED` 事件包含 action、candidateId、expectedRevision。
- `Feedback` timeline node 的 input 显示 action、候选与原 recommendation；output 显示保存结果、轮次状态与反馈后 recommendation，changes 使用现有 snapshot diff。
- LIKE / ADOPT 的 recommendationChange 为 unchanged；ADOPT diff 显示 outcome / feedbackRound。
- DISLIKE 保留现有 Hard Filter、Ranking、Critic、Explanation、Risk 节点；顶层 recommendationChange 显示 changed / cleared / unchanged，并能看到 `user_excluded`。
- 业务成功后 `mark_committed`；异常 rollback 后记录 FAILED。

不新增 LLM 总结 Trace，也不改变旧 Trace / Evaluation 结构和计分。

## 前端交互

1. 把 `saveFeedback` 接入与 chat/command 同级的受控操作：传 requestId、expectedRevision，消费 ChatResponse 并重新 loadCurrent / syncDietState。
2. 发送期间禁用反馈按钮；失败显示现有错误与可重试状态，409 重新加载最新状态。
3. 只有当前决策面板的当前 `displayBlocks` 显示按钮；历史消息卡片只读。
4. LIKE 后新增确认，当前卡仍可采纳或标不合适；成功后把 LIKE 标为已记录，防止误连点。
5. ADOPT 后显示“已采纳”并关闭三个按钮。
6. DISLIKE 后旧候选留在历史轮次，当前面板自动显示新推荐；对话显示换推荐反馈与新卡片。

## 受影响文件

| 文件 | 计划修改 |
| --- | --- |
| `src/choice_agent/schemas.py` | 收紧 FeedbackRequest action，增加 requestId / expectedRevision。 |
| `src/choice_agent/api/routes.py` | feedback 改走 DietOrchestrator，返回 ChatResponse，沿用错误映射。 |
| `src/choice_agent/orchestration/diet.py` | 新增 feedback 写路径、校验、回执、状态处理、DISLIKE recompute、消息/轮次/Trace/事务。 |
| `src/choice_agent/repositories/diet_repository.py` | feedback 写入支持现有 `commit=False` 事务，保留默认兼容。 |
| `src/choice_agent/services/trace.py` | 仅在现有字段不足时增加小型 feedback helper；优先直接用现有 event/node。 |
| `src/choice_agent/static/assets/js/api.js` | 适配 feedback 返回 ChatResponse。 |
| `src/choice_agent/static/assets/js/app.js` | 当前卡按钮状态、feedback 入口和历史只读参数。 |
| `src/choice_agent/static/assets/js/conversation.js` | pending/retry、版本同步、当前/历史轮次渲染。 |
| `tests/test_diet_panel.py` | 三类反馈、约束、排除、无候选、三餐、边界、幂等、rollback。 |
| `tests/test_trace_observability.py` | action、原/新推荐、排除和提交/失败 Trace。 |
| `tests/test_frontend_static.py` | 请求参数、响应同步、历史只读、采纳关闭和错误接线。 |
| `tests/test_orchestrator.py` | 保持 Evaluation 反馈计分兼容。 |
| `CHANGELOG.md` | 验证后在 2026-09-22 同一标题下追加变化。 |

如确认 `services/trace.py` 无需修改，则不为形式完整而改动它。

## 兼容性、风险与取舍

- 数据库结构不变。新请求字段可选；HTTP 成功响应由空变为 ChatResponse，是有意的接口增强。
- action 从任意字符串收紧为三种已存在值；未知值 422 是预期边界修复。
- 不把 LIKE 自动写入 UserProfile，避免候选标签被错误当成明确长期偏好。
- DISLIKE 复用现有 ExplanationAgent；启用模型时沿用现有解释调用，但本需求不新增额外调用。
- 候选池耗尽时不自动刷新外部 Search 或放宽约束。
- ADOPT 记录 DecisionOutcome，但不关闭整个 session；“结束”只表示当前推荐轮次关闭。
- 同一候选先 LIKE 后 DISLIKE 时保留两条按时间记录的事实。

## 验证方案

1. LIKE 只记录且不重算；ADOPT 记录 outcome 并关闭轮次；DISLIKE 只排除所点候选且新主推荐不同，slots/constraints/criteria 不变。
2. 覆盖替代候选为空、三餐、非当前候选、旧历史卡、itemId 缺失、未知 action、跨用户、stale revision、同 ID 重放/冲突。
3. 故障注入确认 FeedbackRecord、消息、revision、排除状态均 rollback，FAILED Trace 可查。
4. 三类 Trace 均断言 feedbackType、candidate、before / after；DISLIKE 断言 `user_excluded` 与新推荐；LIKE/ADOPT 无 Agent/模型节点。
5. 回归 chat/command、换一批、三餐、风险、Evaluation feedback score、DecisionOutcome、Trace 页面。
6. 浏览器验证对话响应、自动换卡、采纳关闭、历史只读、重试、409、刷新、移动/桌面。
7. 执行 `python -m pytest`、`python -m compileall -q src`、受影响 JS 的 `node --check`、`git diff --check`，检查无调试代码和计划外改动。
8. 无外部模型凭据时使用 DisabledProvider / mock provider，并明确未验证外部联通。

## Todo

## 实施与验证记录

- LIKE 记录候选级正向反馈并返回确认，不写入长期 UserProfile；ADOPT 写入 DecisionOutcome 并关闭当前反馈轮次；DISLIKE 只排除所点候选，复用现有 recompute、Critic、Explanation 和 Risk 链路。
- feedback API 已接入 owner、revision、当前候选校验、幂等回执与统一事务；失败注入验证 FeedbackRecord、消息和 DecisionState 均回滚。
- Trace 记录 feedbackType、candidate、原推荐、反馈后推荐和 recommendationChange；DISLIKE 继续展示 user_excluded、Ranking 与 Explanation。
- 前端历史推荐卡改为只读；当前卡接入 pending、重试、409、刷新恢复，并显示“已喜欢 / 已采纳”状态。
- 专项反馈测试 20 passed；完整 pytest 222 passed；Python compileall、app.js / conversation.js node syntax、前端静态测试和真实临时服务 HTTP 端到端通过。
- Windows 浏览器自动化在 Edge 和内置浏览器初始化时均因 sandbox helper 错误退出，未完成真实鼠标点击与截图验收；以 JS 静态接线、语法检查、完整测试和真实 HTTP 状态恢复替代。外部模型联通未验证，规则模式与现有 mock/回归已覆盖。
- 临时验收服务已停止，独立 `feedback_qa.db` 已删除；未修改工作区原有未跟踪文件。

## Todo

- [x] 完成 FeedbackRequest、路由与统一 DietOrchestrator feedback 入口。
- [x] 完成 LIKE 正向反馈记录与对话确认，不引入偏好推断。
- [x] 完成 ADOPT DecisionOutcome、轮次结束与对话确认。
- [x] 完成 DISLIKE 单候选排除、保留约束、现有链路重算和无结果处理。
- [x] 完成三类 feedback Trace、原推荐/新推荐和失败回滚观测。
- [x] 完成前端当前卡反馈、历史只读、pending/retry/revision 与自动刷新。
- [x] 完成专项/全量测试、JS/Python 检查；浏览器自动化限制已记录。
- [x] 检查最终 diff，更新 CHANGELOG，并记录未验证项与剩余风险。
