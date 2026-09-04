# 基于 Diet 主干升级统一决策内核 Plan

## 计划状态

用户已明确回复“实施吧”，并于 2026-09-04 要求“继续”。当前处于实施与验证阶段，尚未全量验收。

本版再次按用户 Review 修正实施方向：Diet 不是迁入新通用框架的对象，而是通用框架的来源。现有 DietOrchestrator、Diet Agents、DecisionEngine、Repository 行为和测试共同构成可执行规格；实施必须从这条完整链路原地抽取通用边界，然后才接入 Travel 和 Shopping。现有简化 GenericDecisionOrchestrator 将被替换。
## 目标

- 以现有 DietOrchestrator 为唯一主干，原地提炼通用阶段、状态、Provider、Policy、Evaluator、CompositionStrategy 和 Presenter。
- 在每一步抽取中保持 Diet 推荐、澄清、换一批、三餐计划、审查、解释、健康风险、Trace、反馈和评估不回归。
- Diet 主干完成参数化后，将其作为 UnifiedDecisionOrchestrator；不并行创建另一套空泛通用流程。
- 用 Travel 接入验证第一个非 Diet 领域，再用 Shopping 验证第三个领域。
- 删除现有简化 GenericDecisionOrchestrator 的独立业务逻辑，使 Generic API 和 Diet API 都调用 Diet 演化出的同一主干。
- 修复 context 被忽略、未知输入误路由 Travel、消息覆盖 user_goal、通用 Decision 无 owner 校验。
- 在统一主干上补充真实 Web Search、丰富证据 schema 和服务端工作台编辑闭环。
- 保留现有 /api/v1/diet/* 请求响应、餐食库、反馈、Trace 和 Evaluation 行为。

## 核心原则

### Diet 是架构源，不是迁移目标

当前 Diet 流程是唯一经过完整业务和测试验证的主干：

    session and revision
      -> intent
      -> understanding
      -> health-risk early guard
      -> optional adjustment
      -> clarification
      -> candidate recommendation or meal-plan composition
      -> critic
      -> explanation
      -> final risk guard
      -> persist session, messages, decision and trace

实施从这条链路原地抽取通用边界。任何抽象都必须先服务 Diet，且不能削弱上述能力。不存在“先完成 Generic，再迁 Diet”的阶段。

### 一个逐步演化的内核

抽取完成后的统一顺序为：

    restore/create decision
      -> route and intent
      -> understand
      -> pre-safety
      -> optional adjustment
      -> clarify
      -> source candidates
      -> normalize evidence
      -> filter and rank
      -> optional compose
      -> critic
      -> explain
      -> post-safety
      -> persist and present

阶段、状态机、revision、Trace、错误处理和持久化只有一套；intent/capability 可以决定跳过哪些可选阶段。

### 领域只提供策略

领域不得拥有整条流水线。DomainProfile 只声明 metadata、matcher、ontology、intent、required fields、CandidateProvider、CriterionEvaluator、hard constraint/safety/critic policies、可选 CompositionStrategy、Presenter 和 evaluation fixtures。

### 统一状态，兼容接口

DecisionState 是业务权威状态。Diet API 继续保持原合约，通过薄适配层转换统一结果；Generic API 直接返回统一状态。Diet session/message/feedback 表继续承担兼容和管理职责。

## 成功标准

- Diet、Travel、Shopping 的请求都由 UnifiedDecisionOrchestrator 执行，代码中不再存在独立 Diet 业务编排链。
- Diet 推荐的 AgentRun/Trace 显示统一阶段名称，同时保留领域 policy/provider 的具体运行记录。
- Diet 的澄清、换一个、least_recent、个人/公共餐食、三餐计划和健康风险测试全部通过。
- /api/v1/diet/chat 的主要字段、responseType、displayBlocks、nextAction、sessionId 和 revision 兼容。
- context 在创建、消息和 command 中保存、合并，并能影响 Diet selection strategy 和其他领域 search mode。
- 未识别请求进入 Generic 澄清，不再出现 Travel fixture。
- Travel 和 Shopping 使用同一 CandidateProvider、EvidenceValidator、RankingEngine 和 command。
- 真实搜索只接受工具实际返回的来源 URL；无证据不生成事实性理由。
- 工作台修改约束、权重和候选后，由服务端局部重算并返回新 revision。
- get/message/command 均校验 owner。
- 无模型和无搜索 Key 时三个领域仍能使用规则/fixture/数据库运行。

## 非目标

- 不引入 LangGraph、Deep Agents、Pydantic AI、CopilotKit 或 AG-UI。
- 不增加数据库表迁移；DecisionState 继续保存在 decision_state.state_json。
- 不删除 diet_sessions、diet_messages、meal_item、feedback 或 diet trace 表。
- 不实现后台任务、WebSocket 或 SSE；真实搜索先同步执行并限制超时。
- 不抓取任意网页，不支持医疗、法律、金融领域。
- 不引入复杂 MCDA 依赖。
- 不在本轮统一 Diet Evaluation 的领域标签 schema；只保证现有评估继续消费统一 Trace 的兼容投影。

## 架构设计

### 1. 从 DietOrchestrator 原地提炼 UnifiedDecisionOrchestrator

不先新建一套平行实现。采用可回归的小步提取：

1. 给现有 Diet 流程补齐 characterization tests，冻结各 intent、状态、Trace 和响应行为。
2. 在 DietOrchestrator 内先引入 StageContext 和 StageRunner，但执行顺序保持不变。
3. 逐个把现有 Diet Agent 的通用职责移到公共 Stage；Diet 规则留在 Profile/Policy。
4. Diet endpoint 始终调用正在演化的主干，每个提取步骤完成后运行 Diet 专项测试。
5. 当主干已不依赖 SlotBundle、MealRecord、DietRepository 或 Diet API schema 时，再命名/移动为 UnifiedDecisionOrchestrator。
6. 将 /api/v1/decisions 切换到该主干，并删除现有 GenericDecisionOrchestrator 的独立 pipeline。
7. 最后把 DietOrchestrator 缩减为 DietApiAdapter 或兼容 facade，只做请求/响应与旧表映射。

统一主干负责 decision/session 恢复、owner、revision、消息/context、路由、阶段调度、AgentRuntime/Trace、保存和 Presenter 调用。

### 2. StageRunner

新增固定阶段接口：

- RouteStage：确定 DomainProfile 和 intent 候选。
- UnderstandStage：用通用 extractor 契约和领域 ontology 更新目标、字段、约束、标准和 intent_key。
- SafetyStage(pre)：运行领域前置风险政策，可中止候选搜索。
- ClarifyStage：根据 required fields、candidate state 和领域问题模板决定是否澄清。
- SourceStage：调用领域 CandidateProvider。
- EvidenceStage：规范化、去重、校验来源和引用。
- RankStage：硬约束、单维评分、权重聚合和稳定排序。
- ComposeStage(optional)：将候选组合为计划；仅支持声明 capability 的领域。
- CriticStage：运行通用完整性检查和领域 critic policies。
- ExplainStage：只根据 rank/compose/evidence 生成引用式推荐。
- SafetyStage(post)：对最终输出运行领域风险与免责声明政策。
- PersistStage：revision、edit/search events、DecisionState 和兼容状态保存。

每个 Stage 作为独立 BaseAgent 运行，具备独立输入输出、耗时、失败和 Trace；不再把整条 Domain pipeline 记成一次 AgentRun。

### 3. DomainProfile

以组合式 Profile 替代当前拥有整条 pipeline 方法的 DomainPlugin。

建议接口：

    DomainProfile
      metadata
      matcher
      ontology
      intents
      required_fields
      default_criteria
      candidate_provider
      criterion_evaluators
      hard_constraint_policies
      safety_policies
      critic_policies
      composition_strategies
      presenter

允许窄 hook，但 hook 输入输出必须是 Pydantic schema，不能直接任意改写 DecisionState。

### 4. DietProfile

DietProfile 复用现有成熟规则，但重新放到统一扩展点：

- classify_intent/extract_slots -> Diet ontology + intent/extractor。
- clarify -> required field/clarification policy。
- DietRepository.list_meals -> DietMealProvider。
- DecisionEngine 的单维 categorical 匹配 -> DietCriterionEvaluator。
- hard_exclusions -> DietHardConstraintPolicy。
- selectionStrategy/avoidRecentCount/换一个 -> 通用 CandidateSelectionPolicy 的参数。
- PlanningAgent -> DietMealPlanCompositionStrategy。
- CriticAgent -> DietCandidateCriticPolicy。
- RiskAgent -> DietHealthRiskPolicy。
- MealResponse 文案和卡片 -> DietPresenter。

Intent 使用通用 intent_key 字符串；旧 Intent enum 仅在 DietApiAdapter 和评估兼容层转换。

### 5. Diet API 兼容适配

DietApiAdapter 负责：

- 创建/校验 diet session。
- 将 ChatRequest 转为统一 create/message 输入。
- 根据 session_id 读取当前 DecisionState。
- 调用 UnifiedDecisionOrchestrator。
- 将统一结果转为 ChatResponse/MealResponse/SessionPhase。
- 继续写 diet_messages、session slots、last_recommendations。
- 保持 feedback、meal CRUD、trace label 和 evaluation 路由不变。

DecisionRepository 新增 latest_for_session。旧 Diet 历史每轮一个 decision 的记录保持可读；统一后同一 session 推进当前 Decision，不再每轮新建互不相连的状态。

### 6. Generic、Travel、Shopping Profile

GenericProfile 是最终 fallback：不生成虚构候选，进入澄清；用户手工加入至少两个候选后可进入比较。

TravelProfile 提供旅行 ontology、required fields、公开事实 evaluator、fixture/web provider 参数和旅行 Presenter。

ShoppingProfile 首期支持电脑、手机、耳机、家电；提供预算、能力、便携/续航、耐用和售后风险维度。价格证据必须带 freshness，不承诺实时库存或促销。

三个 Profile 与 Diet 共用相同 StageRunner。

### 7. context 与消息修复

DecisionState 新增 context 和 messages。

- 创建 context 写入状态并进入 StageContext。
- 后续 context 浅合并，新值覆盖同名键。
- 客户端 context 不得覆盖受保护状态。
- 原始 user_goal 首次创建后保持稳定。
- 后续消息追加到 messages，由 UnderstandStage 转成 constraint/answer/intent update。
- Diet selectionStrategy 和 avoidRecentCount 从统一 context 获取，证明 context 真正透传。

### 8. 丰富 schema

兼容扩展现有模型，不新建 DecisionStateV2：

- Constraint：constraint_id、label、operator、typed value、unit、confidence。
- Criterion：direction、target、unit、missing_policy。
- Evidence：evidence_id、candidate_id、criterion_key、claim、publisher、published_at、freshness、verification_status。
- Candidate：summary、origin、score_breakdown、evidence_ids。
- Recommendation：结构化 reasons/tradeoff_details、generated_from_revision、ranking_method。
- DecisionState：owner_user_id、context、messages、search_runs、edit_events、schema_version、intent_key、composition。
- 新增 SourceDocument、SearchRun、ScoreContribution、RecommendationPoint、EditEvent、CompositionResult。

旧 fields 保留默认值和兼容转换。旧 Evidence ID根据内容确定性派生。

### 9. CandidateProvider

统一 Provider 协议返回 CandidateSearchResult：candidates、sources、evidence、run、warnings。

实现：

- DietMealProvider：查询个人/公共餐食库，不属于 fixture，source kind 为 database。
- FixtureCandidateProvider：Travel/Shopping 离线数据，real_time=false。
- OpenAIWebSearchProvider：OpenAI Responses Web Search，独立配置。
- ManualCandidateProvider：工作台手工候选。
- CompositeCandidateProvider：按领域策略合并 manual/database/fixture/web。

独立搜索配置：

- CHOICE_AGENT_SEARCH_PROVIDER
- CHOICE_AGENT_SEARCH_API_KEY
- CHOICE_AGENT_SEARCH_BASE_URL
- CHOICE_AGENT_SEARCH_MODEL
- CHOICE_AGENT_SEARCH_TIMEOUT_SECONDS
- CHOICE_AGENT_SEARCH_MAX_QUERIES

fixture、web、auto 语义保持明确。显式 web 失败返回错误；auto 才允许带 warning 降级。

### 10. EvidenceValidator 与 RankingEngine

工具 source URL 形成 allowlist。模型 Evidence URL 必须是有效 HTTP(S) 且在 allowlist 中，否则 rejected。数据库和 fixture 来源使用各自可验证 source kind，不伪装 URL。

EvidenceValidator 校验引用、去重、freshness、conflict、coverage 和 Recommendation evidence IDs。

GenericRankingEngine 统一负责：

- hard constraint 结果；
- missing policy；
- 权重归一化；
- score contribution；
- 排除候选；
- evidence coverage；
- 稳定排序。

领域 CriterionEvaluator 只把某一维原始属性转换为 0-100 和解释，不控制总排序。这样 Diet 的列表匹配和 Travel/Shopping 的数值评分可以共用同一聚合逻辑。

### 11. 可选 CompositionStage

不是所有请求都等价于“选一个候选”。统一内核支持可选 CompositionStrategy：

- Diet MEAL_PLAN：为早餐/午餐/晚餐分别选择候选并避免重复。
- 普通 Diet/Travel/Shopping：跳过 ComposeStage。
- 后续行程组合可增加 TravelItineraryStrategy，但本轮不实现。

CompositionResult 进入统一 Recommendation 和 Trace，不再由独立 PlanningAgent 绕开公共流程。

### 12. 结构化 command API

新增：

    POST /api/v1/decisions/{decision_id}/commands

命令包括：

- answer_question
- set_constraint / remove_constraint
- set_criterion_weight
- add_candidate
- exclude_candidate / restore_candidate
- refresh_candidates
- generate_recommendation

共同字段：commandId、type、expectedRevision、context。

CommandHandler 校验 owner、revision、幂等，记录 EditEvent，并按依赖图失效阶段：

- 权重 -> rank/explain/post-safety。
- 排除/恢复 -> rank/compose/explain/post-safety。
- 约束 -> filter/rank/compose/explain，候选范围变化时 source。
- 回答澄清 -> understand 之后按状态继续。
- 刷新 -> source/evidence/rank/compose/critic/explain。
- 重新推荐 -> rank/compose/critic/explain。

搜索合并必须保留 manual candidates 和用户排除状态。

### 13. owner 边界

DecisionState 新增 owner_user_id。create 写 owner，get/message/command 校验。旧状态无 owner 时只允许默认 user 1，并在下次保存时补写。正式多租户列迁移另开 ADR。

### 14. 工作台

统一工作台直接消费 DecisionState：

- 目标、领域、intent、阶段、revision。
- 约束和权重编辑。
- 候选添加、排除、恢复。
- score breakdown、来源、coverage、conflict、freshness。
- composition 结果。
- 刷新候选、重新推荐。
- 409 刷新最新状态。
- Web Search 错误保留当前状态。
- Diet 页面可以继续使用专用聊天/卡片外观，但操作和状态来自同一内核。

本轮不做 SSE。

## 迁移顺序

### 阶段 A：冻结 Diet 可执行规格并修具体问题

- 扩充 Diet characterization tests，覆盖所有 intent、分支、session、Trace、反馈和评估。
- 修复 context、Generic fallback、user_goal 和 owner，但不改变 Diet 主流程顺序。
- 扩展兼容 schema、StageContext 和 DomainProfile 最小契约。

### 阶段 B：从 Diet 主干逐步抽取通用阶段

- 在 DietOrchestrator 内引入 StageRunner。
- 按现有顺序提取 intent、understand、safety、clarify、source、rank、compose、critic、explain、persist。
- 每提取一个阶段立即运行对应 Diet tests。
- 此阶段 Diet 始终是第一调用者和验收基准。

### 阶段 C：把 Diet 专属能力下沉为策略

- DietRepository.list_meals -> DietMealProvider。
- DecisionEngine 餐食单维匹配 -> DietCriterionEvaluator。
- hard exclusions/health risk/critic -> Diet policies。
- PlanningAgent -> DietMealPlanCompositionStrategy。
- MealResponse/ChatResponse -> DietPresenter/DietApiAdapter。
- 确认演化后的主干不再依赖 Diet 类型后，将其命名为 UnifiedDecisionOrchestrator。

### 阶段 D：替换旧 Generic 并验证 Travel

- /api/v1/decisions 改用 Diet 演化出的统一主干。
- Travel 改为 DomainProfile + Provider + Evaluator。
- 删除现有 GenericDecisionOrchestrator 的独立 understand/candidates/rank/explain pipeline。
- 对比 Diet/Travel Trace，确认使用同一阶段集合。

### 阶段 E：第三领域与真实搜索

- 新增 ShoppingProfile。
- 实现 fixture/manual/composite providers。
- 实现 EvidenceValidator、通用 RankingEngine 和 OpenAIWebSearchProvider。
- Travel/Shopping 验证真实搜索；Diet 继续使用数据库 Provider。

### 阶段 F：command 与工作台

- 实现 command、revision、幂等、阶段失效和局部重算。
- 通用工作台接入统一 DecisionState。
- Diet 专用界面继续保留领域体验，但状态和操作来自同一内核。

### 阶段 G：清理、文档和完整验证

- 搜索并移除双轨编排和无调用旧代码。
- 更新 README、配置、迁移矩阵、CHANGELOG 和 Todo。
- 完整自动测试和真实行为验证。



## 受影响文件

### 新增

- src/choice_agent/orchestration/unified.py
- src/choice_agent/agents/stages.py
- src/choice_agent/domains/profile.py
- src/choice_agent/domains/generic.py
- src/choice_agent/domains/shopping.py
- src/choice_agent/domains/diet/profile.py
- src/choice_agent/providers/candidates.py
- src/choice_agent/providers/search.py
- src/choice_agent/decision/evidence.py
- src/choice_agent/decision/ranking.py
- src/choice_agent/decision/commands.py
- src/choice_agent/decision/composition.py
- src/choice_agent/presenters/base.py
- src/choice_agent/presenters/diet.py
- 对应 stage/profile/provider/ranking/command/adapter 测试文件。

### 重点修改

- src/choice_agent/schemas.py：统一 state、stage、evidence、composition、command schema。
- src/choice_agent/domains/base.py、registry.py、travel.py、diet/domain.py：迁移到 Profile。
- src/choice_agent/orchestration/generic.py：改为统一入口 facade。
- src/choice_agent/orchestration/diet.py：删除业务编排，改 Diet API adapter/facade。
- src/choice_agent/agents/diet.py：拆成可复用 Diet policies/evaluators/composition，移除重复阶段 Agent。
- src/choice_agent/decision/engine.py：迁移 Diet 单维 evaluator，公共聚合进入 ranking.py。
- src/choice_agent/repositories/decision_repository.py、diet_repository.py：统一 Decision 恢复并保留 Diet 数据源/兼容写入。
- src/choice_agent/services/trace.py：抽离对 DietRepository 的硬依赖。
- src/choice_agent/api/routes.py：统一 orchestrator、command、owner 和错误映射。
- src/choice_agent/config.py、.env.example：搜索配置。
- src/choice_agent/static/assets/js/api.js、app.js、demo.js、CSS：统一工作台和兼容 UI。
- 全部 Generic/Diet 测试、README、migration matrix、CHANGELOG。

## 兼容与删除策略

- 不删除任何公开 Diet API。
- DietOrchestrator 的调用方先迁到 DietApiAdapter；确认无内部调用后再删除旧业务实现，避免长期保留双逻辑。
- 旧 Intent、SlotBundle、ChatResponse、MealResponse 暂保留在 API compatibility namespace；统一核心不依赖它们。
- 旧 DecisionState JSON 通过 validators/adapter 读取。
- 不修改数据库 schema。
- Diet session/message 表继续用于兼容和现有管理能力；DecisionState 是业务判断的权威状态。
- 原有 Agent 名称可能在 Trace 中变化，Evaluation 不能依赖固定完整 Agent 列表；测试改为校验统一阶段与关键 Diet policy 都执行。
- 若外部调用方依赖旧 AgentRun 名称，需要在 Trace 中增加 legacyAgentName 兼容映射。

## 主要风险

- Diet 是当前最完整功能，迁移回归面大；必须按 intent 分批迁移并保持旧测试作为 characterization tests。
- Diet session revision 与 Decision revision 当前来源不同，统一时必须定义唯一 revision，并由 adapter 映射。
- 旧流程每轮新建 Decision，统一后推进同一个 Decision；需要兼容历史查询语义。
- 三餐计划属于组合决策，若 CompositionStage 设计过于通用会过度抽象；本轮只定义最小接口。
- Diet categorical scoring 与数值评分不同；只能共享聚合器，不能强迫共享单维算法。
- TraceScope 当前依赖 DietRepository，应先抽通用 TraceRepository，避免“统一内核仍依赖 Diet”。
- 同步 Web Search 有延迟和失败；必须在 Diet 迁移稳定后接入。
- owner 存 JSON 是过渡措施，不等同正式多租户安全。

## 验证方案

自动验证：

- python -m compileall -q src scripts
- python -m pytest
- node --check src/choice_agent/static/assets/js/api.js
- node --check src/choice_agent/static/assets/js/app.js
- node --check src/choice_agent/static/assets/js/demo.js
- git diff --check

统一性检查：

- 搜索代码确认只有 UnifiedDecisionOrchestrator 持有阶段调度。
- DietOrchestrator 不再直接实例化 IntentAgent、CandidateAgent、PlanningAgent 等。
- DomainProfile 不包含完整 rank/explain 流程实现。
- Generic、Diet、Travel、Shopping 的 AgentRun 都使用同一阶段名集合。
- 没有新的领域专用状态机或 revision 实现。

Diet characterization 回归：

- 普通推荐。
- 澄清与 slots 复用。
- 换一个和 least_recent。
- 个人/公共餐食源。
- 三餐计划。
- 健康风险前置中止。
- Explanation 模型失败降级。
- Critic 失败显式错误。
- session revision、消息、Trace、feedback、evaluation。

通用行为验证：

1. Diet 与 Travel Trace 显示同一核心阶段。
2. 未知请求进入 Generic 澄清。
3. context 在不同领域可见且不覆盖受保护状态。
4. Shopping 与 Travel 使用相同 Provider/RankingEngine。
5. web 结果来源通过 allowlist，虚构 URL 被拒绝。
6. 工作台编辑产生新 revision 和 EditEvent。
7. 权重修改不重复搜索，候选范围修改按需搜索。
8. user 2 无法访问 user 1 的 Decision。
9. 无 Key 时 Diet database、Travel/Shopping fixture 都能运行。
10. 桌面和移动 UI 无重叠或溢出。

## 实施暂停点

- 每个公共抽象必须先由 Diet 当前行为驱动；如果抽象要求 Diet 降级、绕路或复制状态，暂停并更新 Plan。
- 阶段 B/C 每提取一个 Diet 分支都先运行对应 characterization tests。
- Diet 全量回归且统一主干不再依赖 Diet 类型后，才允许接入 Travel。
- Travel 成功后才删除旧 Generic pipeline；删除前检查全部调用方。
- 若统一需要数据库迁移、改变 Diet API 必填字段或无法兼容 session revision，暂停并重新批准。
- 若 Web Search 需要新增依赖或改变密钥边界，先更新 Plan。



## 实施授权

用户已明确授权实施 Diet-first 方案。本节保留授权事实；未完成项不得仅因代码已写而勾选。


## 2026-09-04 实施进度与验收边界

已落地并经过本地回归的主干：
- Diet/Travel/Shopping/Generic 共用 StageRunner；Generic 与 Travel/Shopping 共用 ComparisonProfile。
- Diet API 保留原接口，通用入口也可运行 Diet 澄清、推荐、三餐和风险分支。
- DecisionState 作为权威 revision，兼容 session 同步；仓储更新使用 revision 条件更新避免过期覆盖。
- 通用命令支持调权、硬约束、候选添加/排除/恢复与刷新；refresh 保留手工候选。
- Diet evaluator 已移至 domains/diet；旧 CandidateAgent/PlanningAgent 重复代码已删除。
- Generic 默认使用用户主观的 fit/cost/risk 0-100 评分；不会把缺少评分的候选宣称为最优。
- Search Provider 按官方 Responses Web Search sources 协议提取 URL，保留最多两次传输尝试。URL 通过白名单不等于事实核验。
  官方协议依据：https://developers.openai.com/api/docs/guides/tools-web-search

已执行验证：
- 当前全量 pytest：68 passed；compileall 和三个前端脚本语法检查通过。
- Playwright 实际请求验证：调权、排除/恢复、预算硬约束、两候选手工比较、409 过期版本、404 跨用户访问。
- 1440x1000 与 390x844 页面无横向溢出、无 pageerror；截图存于当前任务 visualization 目录。
- Web Search 只完成 mock transport、重试、返回文本分块与来源校验测试，当前未配置 CHOICE_AGENT_SEARCH_API_KEY；真实凭据端到端验收未执行，已验证未配置时明确返回 502。

尚未完成，不得据共享调度已落地而关闭整个 Plan：
- Source/Evidence/Rank 在完整 run 中仍聚合在兼容 CandidateAgent 内；尚未拆成各自独立 Trace。
- DomainProfile 的 hook 目前仍使用 AgentContext/dict，尚未完成严格的 Pydantic 输入输出契约。
- Diet deny-list 保留旧约束 key 兼容分支，尚未完全抽成独立 hard-constraint policy。
- EvidenceValidator 尚未完整实现去重、冲突、freshness/coverage 及结论引用的统一审计策略。
- Diet 专用聊天页保留旧交互；通用工作台 command 可操作 Diet 状态，但专用页的 command 控件及 composition 展示还需继续对齐。
- 自然语言领域偏好到评分权重的语义映射仍需深化，不能将 fixture 演示结果当作真实领域推荐。

## Todo

- [x] 建立 Diet 全分支和 Generic 现有行为 characterization test 基线。
- [x] 修复 context 保存/合并/透传、未知领域 fallback、user_goal 和 owner。
- [x] 兼容扩展 DecisionState、Evidence、Score、Composition 和 Command schema。
- [x] 在现有 DietOrchestrator 中引入 StageContext 和最小 DomainProfile。
- [x] 从 Diet 调用顺序提取统一 StageRunner，保持 Diet 为第一调用者。
- [x] 抽通用 TraceRepository，移除阶段运行时对 DietRepository 的依赖。
- [x] 将 DietRepository.list_meals 抽为 DietMealProvider。
- [x] 将 DecisionEngine 拆为通用聚合 RankingEngine 与 DietCriterionEvaluator。
- [ ] 将 hard exclusions、health risk 和 critic 抽为 Diet policies。
- [x] 将 PlanningAgent 抽为 DietMealPlanCompositionStrategy。
- [x] 将 Diet 响应转换抽为 DietPresenter/DietApiAdapter。
- [x] 确认 Diet 全量回归后，将演化主干定名为 UnifiedDecisionOrchestrator。
- [x] 将 /api/v1/decisions 切换到统一主干。
- [x] 将 Travel 迁入统一 Profile/Provider/Evaluator/StageRunner。
- [x] 删除现有 GenericDecisionOrchestrator 的独立业务 pipeline。
- [x] 新增 GenericProfile，修复未知领域误路由 Travel。
- [x] 新增 ShoppingProfile 和 fixture，验证第三领域。
- [ ] 实现 EvidenceValidator、CandidateProvider registry 和 manual/composite provider。
- [x] 实现 OpenAIWebSearchProvider 和 source allowlist。
- [x] 新增 command API、幂等、阶段失效和局部重算。
- [ ] 将通用工作台和 Diet 领域视图接入同一 DecisionState/command。
- [x] 更新配置、README、迁移矩阵和 CHANGELOG。
- [x] 完成单内核搜索检查、compileall、pytest、JS 检查和桌面/移动行为验证。
