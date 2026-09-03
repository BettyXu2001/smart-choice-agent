# Diet Agent 迁移对照

| 原能力 | V2 实现 | 状态 |
| --- | --- | --- |
| Spring Boot HTTP 入口 | FastAPI 路由 | 已迁移 |
| DietOrchestratorService | DietOrchestrator | 已迁移 |
| Intent Agent | IntentAgent | 已迁移 |
| Clarify Agent + 规则 | ClarificationAgent + diet rules | 已迁移 |
| 推荐回复 Agent | ExplanationAgent | 已迁移 |
| 计划回复 Agent | PlanningAgent + ExplanationAgent | 已迁移 |
| Evaluation Judge Agent | EvaluationAgent，可选模型 Judge | 已迁移 |
| 健康 Risk Guard | RiskAgent + 确定性风险规则 | 已迁移 |
| MealSearch/MealRank | CandidateAgent + DecisionEngine | 已迁移并扩展 |
| 七维 SlotBundle | SlotBundle + 通用约束/标准 | 已迁移并扩展 |
| 个人/公共餐食库 | SQLAlchemy Repository | 已迁移 |
| MySQL 数据脚本 | 打包旧 SQL + SQLite 幂等导入 | 已迁移 |
| 会话和消息 | SessionRecord / MessageRecord | 已迁移 |
| 推荐反馈 | FeedbackRecord + 兼容 API | 已迁移 |
| 请求 Trace | TraceScope + AgentRunRecord | 已迁移并扩展 |
| Trace 人工标注 | Trace Label API 和原页面 | 已迁移 |
| 评估报告 | 完整规则指标 + 反馈归因 + 可选 LLM Judge | 已补齐核心指标 |
| 静态管理页面 | FastAPI StaticFiles 托管 | 已迁移 |
| 通用候选/证据/推荐 | DecisionState / Candidate / Evidence | 新增 |
| 硬约束/软偏好 | Constraint + DecisionEngine | 新增 |
| 通用决策状态查询 | /api/v1/decisions/{decision_id} | 已迁移 |
| 通用决策创建 API | POST /api/v1/decisions | 新增 |
| 通用决策文本推进 API | POST /api/v1/decisions/{decision_id}/messages | 新增 |
| Domain Plugin 注册表 | DomainRegistry + DietDomain + TravelDomain | 新增 |
| 旅行 fixture 后端领域 | TravelDomain | 新增 |

## 兼容边界

- 原项目保持只读，V2 使用独立数据库。
- 旧饮食 API 路径和主要请求响应字段保持兼容。
- V2 会在聊天响应中额外返回 decisionState，旧前端会忽略该扩展字段。
- 默认使用 SQLite；SQLAlchemy 模型保留切换 MySQL/PostgreSQL 的能力。
- 当前已包含完整饮食领域和后端旅行 fixture 领域；购物、职业、学习等仍保留为前端 demo/future domain。
