# 推荐反馈闭环 Research

## 范围与状态

2026-09-22。完善饮食推荐卡片现有“喜欢 / 采纳 / 不合适”反馈，使反馈进入对话、决策状态和 Trace；“不合适”复用现有推荐链路换一个结果。该需求改变公开反馈接口、核心推荐轮次和持久化边界，按大改动处理。本阶段只完成 Research / Plan，尚未修改产品代码。

成功标准：三类反馈均持久化且有自然语言 Agent 响应；采纳形成可查询的本次决策结果；不合适只排除所点候选、保留已有约束并自动得到新推荐；Trace 能看到反馈类型、原推荐及反馈后的推荐；不新增 Agent 或额外 LLM 调用。

## ADR 检索与归档决定

已按 feedback、推荐、排除、DecisionOutcome、Trace、饮食对话、重算和相关路径检索 `adr/` 正文。相关记录如下：

- `2026-09-04-diet-conversation-panel-research.md` / `plan.md`：定义饮食对话、可恢复轮次、版本、回执和统一事务；现有反馈当时仅要求保留，没有设计反馈后的对话闭环。
- `2026-09-04-generic-decision-evidence-workbench-plan.md`：确认 DecisionState 为业务权威状态，同时保留饮食 feedback 表和 API 兼容边界。
- `2026-09-05-decision-trace-observability-research.md` / `plan.md`：定义每轮 Trace、状态差异、推荐变化和真实执行节点；可直接承载反馈事件。
- `2026-09-05-consumer-navigation-decision-history-*`：已有 DecisionOutcome、历史最终选择和复盘语义，可承载“采纳”的最终选择。
- `2026-08-29-eat-what-selector-integration-plan.md`：已有换一批和近期推荐排除背景，但不能代替单候选“不合适”的精确排除语义。

本需求边界独立且会同时触及反馈 API、饮食编排、前端交互和 Trace。追加旧文档会混淆已经完成的历史验收，因此新建本组 Research / Plan。

## 核心文件与真实行为

| 文件 | 当前职责与已核实行为 |
| --- | --- |
| `src/choice_agent/static/assets/js/app.js` | `renderMealCard` 在当前及历史餐食卡片上渲染反馈按钮；`saveFeedback` 仅调用 API，成功后只弹 Toast。 |
| `src/choice_agent/static/assets/js/conversation.js` | 从 DecisionState.messages 与 `dietTurns` 恢复对话；chat/command 已处理版本、重试、刷新和 409，但反馈没有进入此路径。 |
| `src/choice_agent/static/assets/js/api.js` | `DietApi.saveFeedback` 调用 `POST /api/v1/diet/feedback`。 |
| `src/choice_agent/api/routes.py` | feedback 路由直接调用 Repository，返回 204；不校验 owner、当前候选或 revision，不创建 Trace。 |
| `src/choice_agent/repositories/diet_repository.py`、`db_models.py` | `recommend_feedback` 已持久化 user/session/item/action/rating/reason；默认自行提交。无需迁移。 |
| `src/choice_agent/orchestration/diet.py` | chat/command 已有 owner、revision、幂等回执、单事务、消息、DecisionState、Trace、Presenter 和 `recompute`；目前没有 feedback 写路径。 |
| `src/choice_agent/domains/diet/profile.py` | `rerank` 复用 `candidatePool`，排序读取 `excluded_candidates`；候选池缺失时会重新检索。三餐 compose 也带入既有排除项。 |
| `src/choice_agent/agents/stages.py`、`agents/diet.py` | recompute 复用 Candidate/Rank、Critic、Explanation、Risk；反馈本身无需新 Agent 或 LLM。 |
| `src/choice_agent/services/trace.py` | 已有 begin_turn、timeline、推荐前后快照、commit 状态和 recommendationChange。 |
| `src/choice_agent/schemas.py` | FeedbackRequest 只有 sessionId/itemId/action/rating/reason；action 任意字符串；DecisionOutcome 可保存采纳结果。 |
| `tests/test_orchestrator.py`、`test_diet_panel.py`、`test_trace_observability.py`、`test_frontend_static.py` | 已覆盖反馈计分、事务/幂等/版本、Trace 和前端接线，但没有反馈闭环测试。 |

当前调用链是：按钮 → `DietApi.saveFeedback` → feedback route → `DietRepository.save_feedback` → 204 / Toast。它不经过 Agent 编排，因此没有 assistant message、revision、DecisionOutcome、排除重算、dietTurns 或 Trace。

## 可复用能力

1. `recommend_feedback` 继续记录 LIKE / ADOPT / DISLIKE，不新增表。
2. `DietOrchestrator` 的 owner、revision、回执、事务和消息模式可复用为唯一反馈写入口。
3. LIKE 记录用户对具体候选的正向信号，不从候选标签反推长期 Profile 或槽位。
4. ADOPT 复用 `DecisionOutcome`，使历史决策显示最终选择。
5. DISLIKE 把候选 ID 合并进 `excluded_candidates`，调用现有 `recompute(refresh_candidates=False)`。
6. 对话恢复继续使用 DecisionState.messages + `dietTurns`。
7. Trace 用 Feedback operation node 记录 action、原推荐和反馈后推荐；重算内部原有节点继续保留。

## 关键问题与隐患

1. 当前 API 不校验 session owner，闭环入口必须走 `_session` / `_decision`。
2. action 为自由字符串，未知反馈无法定义状态与响应。
3. 历史卡片也可点击；必须限定当前 `displayBlocks` 候选，前端历史卡只读。
4. 反馈当前独立 commit；应与 DecisionState、消息、session 同事务，避免半份结果。
5. DISLIKE 只能新增所点候选，不能复用 AdjustmentAgent 的“排除全部历史推荐”。
6. 完整 `run` 会再次理解意图并可能污染约束；应直接 `recompute`。
7. ADOPT 只写反馈表时历史决策看不到 final choice，应设置 DecisionOutcome。
8. LIKE 不等于自动修改长期资料；当前没有候选级学习模型，自动推导口味会引入假设。
9. 无替代候选时仍应记录 DISLIKE 和排除项，不得放宽约束或重推原候选。
10. 网络重试和并发反馈需沿用 requestId + expectedRevision。
11. 通用 recommendationChange 不足以表达 feedback 类型和被点候选，需要显式 Feedback 节点。

## 约束与待 Plan 决策

- 首期只覆盖当前实际存在按钮的饮食推荐，不扩展通用决策卡片。
- 不新增 Agent、Prompt、模型调用或依赖；DISLIKE 复用现有解释并加固定自然语言前缀。
- 不做长期画像学习、跨会话协同过滤或推荐模型训练。
- 不改变 LIKE / ADOPT / DISLIKE 评估计分口径。
- Plan 明确请求契约、轮次状态、候选校验、采纳结果、重算、无候选、Trace、按钮状态与兼容策略。

## Research 验证记录

已读取真实路由、Repository、模型、饮食编排、重算/三餐、Trace、前端状态恢复和相关测试。工作区已有用户未跟踪文件 `adr/2026-09/2026-09-22-homepage-scripted-demo-research.md`、`start.bat`，本轮不修改或归入成果。当前阶段未运行产品测试，也未修改产品代码。
