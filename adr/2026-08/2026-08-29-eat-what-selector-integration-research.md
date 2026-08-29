# eat-what 选择器整合 Research

## 当前需求和研究范围

本次研究目标是判断 `D:\Code\AI Coding\eat-what\Eat-What` 中哪些能力适合整合进 `choice-agent-v2`，并为后续小闭环实施计划提供事实依据。

研究重点：

- `eat-what` 的推荐策略、历史冷却、选择洞察是否可迁移；
- 这些能力应作为通用 Choice 能力，还是饮食领域专属能力；
- 与 `choice-agent-v2` 现有饮食推荐链路、数据模型、测试边界的兼容性；
- 后续实施如何保持范围克制，避免把小闭环扩展成通用架构重构。

本阶段只研究和编写 ADR，不修改产品代码。

## 核心文件及其职责

### eat-what

- `src/types.ts`：定义 `FoodItem`、`HistoryItem`、`RecommendationStrategy`、`AppPreferences` 等前端数据结构。
- `src/domain/picker.ts`：实现候选过滤和三种选择策略：`weighted`、`random`、`least-recent`。
- `src/domain/insights.ts`：实现历史摘要和单次选择洞察，包括近 7 天次数、最常选择项、多样性、候选数、命中概率和解释标签。
- `src/domain/picker.test.ts`：覆盖排除、筛选、近期冷却、随机、加权、最久未选和空候选。
- `src/domain/insights.test.ts`：覆盖历史摘要和选择洞察计算。
- `src/storage.ts`：本地浏览器数据加载、版本迁移、导入导出校验。
- `src/App.tsx`：React 单页应用，承载食物/饮品模式、快捷预设、动画抽取、历史侧栏、词库维护和导入导出。
- `src/components/InsightsPanel.tsx`：快捷场景预设和历史统计面板。
- `src/components/ResultCard.tsx`：结果卡片、命中概率、解释标签、评分和“暂时不想吃/喝”交互。
- `src/constants.ts`：食物、饮品、分类、场合和口味默认数据。

### choice-agent-v2

- `src/choice_agent/schemas.py`：定义通用 `DecisionState`、`Candidate`、`Recommendation`、饮食请求响应和反馈请求。
- `src/choice_agent/decision/engine.py`：当前饮食候选排序引擎，根据 7 个饮食槽位计算匹配分，支持显式排除和硬排除。
- `src/choice_agent/agents/diet.py`：饮食 Agent 实现，包含意图、理解、澄清、候选、调整、计划、审查、解释、风险和评估。
- `src/choice_agent/orchestration/diet.py`：饮食多 Agent 编排，负责会话、Trace、Agent 顺序和最终响应保存。
- `src/choice_agent/repositories/diet_repository.py`：会话、消息、餐食、槽位、反馈、Trace 和 DecisionState 持久化。
- `src/choice_agent/db_models.py`：SQLAlchemy ORM 模型，目前有 `recommend_feedback`，但没有独立的推荐选择历史表。
- `src/choice_agent/static/assets/js/app.js`：当前静态前端，包含聊天推荐、个人/公共餐食、Trace 和评估页面。
- `tests/test_engine.py`：覆盖稳定排序、历史排除和硬排除。
- `tests/test_orchestrator.py`：覆盖推荐、澄清、多轮槽位、换一批、三餐计划、健康风险、个人餐食 CRUD 和评估。
- `tests/test_rules.py`：覆盖意图、澄清、硬排除和风险规则。

## 关键调用链和数据流

当前 `choice-agent-v2` 普通推荐链路：

```text
POST /api/v1/diet/chat
  -> DietOrchestrator.chat
  -> IntentAgent
  -> UnderstandingAgent
  -> ClarificationAgent
  -> CandidateAgent
  -> DecisionEngine.rank
  -> CriticAgent
  -> ExplanationAgent
  -> RiskAgent
  -> 保存 session / decision / trace
  -> ChatResponse
```

当前“换一个”链路：

```text
用户消息命中 MEAL_ADJUST
  -> AdjustmentAgent 将 session.last_recommendations 写入 exclude_ids
  -> CandidateAgent 调用 DecisionEngine.rank 时排除这些 id
  -> 返回新的前 3 个候选
```

`eat-what` 的本地选择链路：

```text
当前食物或饮品列表
  -> filterCandidates 应用本次排除、场合、口味和近期冷却
  -> selectItem 按 random / weighted / least-recent 选择 1 个结果
  -> getSelectionInsights 计算概率和解释标签
  -> 写入最近 50 条本地历史
```

## 当前实现逻辑

`choice-agent-v2` 的 `DecisionEngine.rank()` 更像“相关性排序”：

- 7 个槽位等权；
- 每个有请求值的槽位按命中比例加分；
- 总分除以固定 7 个维度；
- 无查询槽位时保留所有候选；
- 有查询槽位但没有任何命中时过滤；
- 排序规则为 `score` 降序、`meal.id` 升序；
- 最多返回前 10 个；
- 由 `ExplanationAgent` 展示前 3 个。

`eat-what` 的 `selectItem()` 更像“最终拍板选择器”：

- `random`：有效候选中均匀随机；
- `weighted`：按 `rating` 权重随机；
- `least-recent`：优先选择历史中最久未出现或从未出现的候选；
- 支持传入随机函数，测试可确定性验证。

两者并不冲突：`choice-agent-v2` 可以继续用现有引擎产出候选和基础匹配分，再由通用选择器决定主推荐、备选和洞察。

## 已有可复用能力

可从 `eat-what` 迁移或翻译的能力：

- 策略枚举：`weighted`、`random`、`least-recent`；
- 候选过滤中的近期冷却思想；
- 加权选择算法；
- 最久未选算法；
- 选择概率计算；
- 历史摘要指标：总次数、近 7 天次数、唯一率、最常出现项；
- 解释标签生成；
- 单元测试样例结构。

可在 `choice-agent-v2` 中复用的承载能力：

- `DecisionState.domain_state` 可暂存选择策略、候选洞察和历史摘要，避免第一版扩展 API 顶层字段；
- `SessionRecord.last_recommendations` 可支撑会话级近期排除；
- `FeedbackRecord` 可作为用户对推荐质量的显式反馈来源；
- `Candidate.score` 和 `MealResponse.match_score` 可作为通用选择器的基础权重；
- 现有测试结构适合补充纯函数单测和编排集成测试。

## 潜在问题和隐患

- `eat-what` 的 `rating` 是用户维护的 1-5 星偏好，而 `choice-agent-v2` 当前餐食没有 rating 字段。第一版如果直接使用 rating 会引入数据模型变更；更低风险的做法是先用 `Candidate.score` 或 `RankedMeal.score` 做权重。
- `least-recent` 需要可靠历史。当前 `choice-agent-v2` 只有 `session.last_recommendations` 和反馈表，没有完整“最终被推荐/被接受”的历史模型。第一版应限制为会话级历史，或只从已展示推荐中推断。
- `weighted` 引入随机性后会改变当前稳定排序行为。测试和用户预期需要区分“排序候选”和“选择主推荐”。
- `ExplanationAgent` 当前默认展示前 3 个排序候选。如果加入选择器，需要明确主推荐和备选的顺序如何生成，避免同分、随机和解释不一致。
- 如果把策略配置做成用户偏好并持久化，会涉及新增表或 session 字段，范围会扩大。
- `eat-what` 的饮品模式不适合本次直接接入，因为 `choice-agent-v2` 当前 API、模型和文案都围绕 `diet/meal`。
- `eat-what` 的 React 前端和 PWA 能力不应直接迁移到当前静态前端，否则会引入依赖和构建体系变化。

## 与需求相关的约束

- 本次目标是“小闭环”，不是通用架构重构。
- 通用选择器应保持领域无关，只处理候选、分数、历史和策略。
- 饮食领域继续负责槽位理解、饮食安全、餐食仓储和 MealResponse 展示。
- 第一版不新增前端构建体系，不引入 React/Vite/Tailwind/Motion。
- 第一版不直接迁移 `eat-what` 的 localStorage 数据模型。
- 旧 `/api/v1/diet/*` 路径和主要响应行为应保持兼容。
- 若 API 响应扩展字段，应使用默认值或 `domain_state`，避免旧前端崩溃。

## Plan 阶段需要决策的问题

- 通用选择器放在 `choice_agent.decision.selector` 还是并入现有 `engine.py`。
- `weighted` 第一版使用匹配分作为权重，还是引入餐食 rating 字段。
- 历史冷却第一版使用 `session.last_recommendations`，还是新增独立选择历史表。
- 策略配置第一版从 `ChatRequest.context` 传入，还是放到 session 级默认值。
- 选择洞察输出放在 `DecisionState.domain_state`，还是扩展 `Recommendation` 或 `MealResponse`。
- 当前默认行为是否继续保持稳定排序，还是默认启用 `weighted`。

## Research 结论

`eat-what` 最适合整合的是领域无关的候选选择能力，而不是整套前端或饮品模式。推荐策略、历史冷却和选择洞察应沉淀为通用 `decision` 层的薄模块；饮食领域只负责把餐食候选转换成带基础分的通用候选，并消费选择结果生成饮食响应。

为了降低复杂度，第一版应保持克制：

- 不新增依赖；
- 不引入 React 前端；
- 不新增饮品领域；
- 不新增全局偏好系统；
- 优先用现有匹配分作为选择权重；
- 历史冷却先限定在会话已展示推荐内；
- 洞察先写入 `DecisionState.domain_state`。