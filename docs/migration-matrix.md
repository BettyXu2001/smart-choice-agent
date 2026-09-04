# Diet Agent 迁移对照

| 原能力 | V2 实现 | 状态 |
| --- | --- | --- |
| Spring Boot HTTP 入口 | FastAPI 路由 | 已迁移 |
| DietOrchestratorService | Diet 兼容 facade + UnifiedDecisionOrchestrator/StageRunner | 共用主干 |
| Intent Agent | IntentAgent | 已迁移 |
| Clarify Agent + 规则 | ClarificationAgent + diet rules | 已迁移 |
| 推荐回复 Agent | ExplanationAgent | 已迁移 |
| 计划回复 Agent | DietMealPlanCompositionStrategy + ExplanationAgent | 已抽取 |
| Evaluation Judge Agent | EvaluationAgent，可选模型 Judge | 已迁移 |
| 健康 Risk Guard | RiskAgent + 确定性风险规则 | 已迁移 |
| MealSearch/MealRank | DietMealProvider + GenericRankingEngine + DietCriterionEvaluator | 已抽取 |
| 七维 SlotBundle | SlotBundle + 通用约束/标准 | 已迁移并扩展 |
| 个人/公共餐食库 | SQLAlchemy Repository | 已迁移 |
| MySQL 数据脚本 | 打包旧 SQL + SQLite 幂等导入 | 已迁移 |
| 会话和消息 | SessionRecord / MessageRecord + DecisionState 饮食轮次快照 | 原子保存、幂等重试、刷新恢复 |
| 饮食对话决策面板 | 对话 + 可编辑条件/确认/当前推荐 + 移动抽屉 | 已实现，待用户试用验收 |
| 推荐反馈 | FeedbackRecord + 兼容 API | 已迁移 |
| 请求 Trace | TraceScope + AgentRunRecord | 已迁移并扩展 |
| Trace 人工标注 | Trace Label API 和原页面 | 已迁移 |
| 评估报告 | 完整规则指标 + 反馈归因 + 可选 LLM Judge | 已补齐核心指标 |
| 静态管理页面 | FastAPI StaticFiles 托管 | 已迁移 |
| 通用候选/证据/推荐 | DecisionState / Candidate / Evidence | 新增 |
| 硬约束/软偏好 | Constraint 运算符过滤 + Criterion 权重 | 已扩展，自然语言偏好策略待深化 |
| 通用决策状态查询 | /api/v1/decisions/{decision_id} | 已迁移 |
| 通用决策创建 API | POST /api/v1/decisions | 新增 |
| 通用决策文本推进 API | POST /api/v1/decisions/{decision_id}/messages | 新增 |
| Domain Plugin 注册表 | DomainRegistry + Diet/Travel/Shopping/Generic Profile | 已统一 |
| 旅行 fixture 后端领域 | TravelProfile + ComparisonProfile | 共用比较流程 |
| 购物 fixture 后端领域 | ShoppingProfile，按商品类别选取离线模拟数据 | 已接入 |
| 工作台编辑 | Command API + revision/CAS + EditEvent | 已接入 |
| 真实搜索 | Responses Web Search + 工具来源白名单 | 已实现，真实服务待验收 |

| 通用对话与结果侧栏 | conversation.js，共用会话恢复、编辑、重试和抽屉 | 已推广到购物/旅行/Generic |
| 场景识别 | POST /api/v1/decision-domains/resolve | 后端唯一入口，混合场景澄清 |
| 通用会话幂等 | 创建/消息 requestId，命令 commandId，事务及历史快照 | 已实现并验证并发创建 |
| 定性候选比较 | 对话录入与编辑，不要求评分 | 已实现；真实模型/搜索待凭据验证 |

| 决策辅助 | 规则取舍、候选事实/顾虑、短回答和假设分析 | 四类 Demo 多轮内容已验证 |
| 模型决策解释 | 上下文理解、原文纠正、候选与引用校验、显式降级 | mock 验证，真实模型服务待凭据验收 |

## 兼容边界

- 原项目保持只读，V2 使用独立数据库。
- 旧饮食 API 路径和主要请求响应字段保持兼容。
- V2 会在聊天响应中额外返回 decisionState，旧前端会忽略该扩展字段。
- 默认使用 SQLite；SQLAlchemy 模型保留切换 MySQL/PostgreSQL 的能力。
- Diet、Travel、Shopping、Generic 使用同一 StageRunner；职业/学习等未知领域走 Generic 手工比较，不误路由为旅行。
- Diet 单餐、调整、三餐、风险、评估兼容；旧 Agent 名称保留用于 Trace/Evaluation，旧 CandidateAgent/PlanningAgent 的重复实现已移除。
- 仍待完成严格类型化的阶段 hook、独立 Source/Evidence Trace 和证据 freshness/conflict/coverage 完整策略。共享调度已落地不等于全部架构细化已完成。
