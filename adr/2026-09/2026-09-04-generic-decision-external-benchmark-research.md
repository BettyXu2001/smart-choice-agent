# 通用决策能力外部基准 Research

## 当前需求和研究范围

用户希望进一步明确“真实搜索 + 丰富 schema + 多领域后端 + 工作台编辑闭环”具体代表什么，并确认这些判断是否经过 GitHub 高质量仓库检索。

本 Research 覆盖：

- 核实 `choice-agent-v2` 当前通用决策链路的真实实现，而不是沿用历史文档结论。
- 对比本地旧 `choice-agent` 和 `diet-agent` 已有能力，识别仍未整合的部分。
- 检索 GitHub 上与检索型 Agent、结构化 Agent、持久状态、人机协作 UI、多准则决策相关的高质量开源项目。
- 给出四项能力的工程定义、当前差距、可借鉴模式和后续 Plan 需要决策的问题。

本阶段不修改产品代码，也不形成可直接实施的 Plan。

## ADR / 历史方案检索

已检索 `adr/`、`docs/`、`CHANGELOG.md` 中与通用决策、搜索、证据、schema、Domain Plugin、工作台和多领域相关的记录。

高度相关记录：

- `adr/2026-09/2026-09-02-generic-decision-from-diet-foundation-research.md`：确认上一阶段的目标是先建立通用后端骨架，并明确将外部真实搜索和完整工作台排除在第一阶段之外。
- `adr/2026-09/2026-09-02-generic-decision-from-diet-foundation-plan.md`：已完成 `GenericDecisionOrchestrator`、`DomainRegistry`、`DietDomain` 兼容壳、旅行 fixture 和通用创建/消息 API。
- `adr/2026-08/2026-08-29-choice-agent-v1-borrowed-ideas-todo.md`：长期清单已经列出证据质量、搜索 Provider、通用推进 API 和工作台，但未经过外部项目基准研究。
- `adr/2026-08/2026-08-30-generic-demo-mode-research.md`：确认职业、学习、购物、旅行工作台最初是前端 fixture demo，不是通用后端能力。
- `docs/migration-matrix.md`：当前仅将 Diet 标为完整领域，Travel 是后端 fixture；购物、职业、学习仍属于前端 demo/future domain。

判断：现有记录回答的是“如何从 Diet 基座搭出第一阶段通用骨架”，本次回答的是“下一阶段的能力定义和外部工程基准”。继续追加会混淆已完成阶段与新研究边界，因此新建本 Research。

## 研究方法与样本选择

外部样本优先满足以下条件之一：

- 官方框架或维护方仓库，能通过源码/官方文档验证接口和行为；
- 有论文、公开评测或明确研究背景；
- 有活跃维护、测试、版本或较大实际使用面；
- 与“证据驱动决策”高度同类，即使成熟度不足，也能作为产品边界参考。

没有仅按 Star 数量下结论。README 中无法由代码、测试或论文交叉验证的能力只作为项目自述，不作为已证明事实。

## 外部仓库基准

### 1. LangChain Deep Agents

仓库：[langchain-ai/deepagents](https://github.com/langchain-ai/deepagents)

这是当前活跃的通用 Agent harness，建立在 LangGraph 上，提供子 Agent、可插拔文件后端、持久记忆、Human-in-the-loop、Skills、MCP 工具、Tracing 和 Evaluation。其动态子 Agent 模式还明确给出 fan-out/synthesize、adversarial verification、generate/filter、tournament 和 loop-until-done 等编排方式。

可借鉴：

- 把“领域能力”表示为可注册的工具/子 Agent/策略，而不是在一个总 Agent 中不断增加条件分支。
- 搜索任务需要规划、并行获取、验证和综合，而不是一次模型调用返回候选。
- 工具权限与沙箱边界必须在运行时控制，不能依赖提示词自律。

不建议当前直接迁入整个框架。v2 的核心流程仍较小，先借鉴 Provider、阶段契约和持久状态思想，能避免一次性引入较重依赖。

### 2. GPT Researcher

仓库：[assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher)

该项目把研究分为规划、问题生成、抓取/检索、单来源总结与追踪、过滤聚合、报告生成，并支持多种检索器、网页与本地文档来源。它说明“真实搜索”不只是调用搜索 API，而是对来源进行持续追踪并把检索结果保存为后续综合的输入。

可借鉴：

- `SearchProvider`/Retriever 可替换，业务状态不绑定 Tavily、OpenAI Web Search 或某个爬虫。
- 每个来源先形成可追踪的中间产物，再由推荐阶段消费。
- 搜索失败、无结果、来源不足必须成为显式状态，不能让生成阶段自由补全事实。

风险提示：该仓库公开 issue 中存在空上下文时生成报告可能虚构来源的反馈，因此 Choice Agent 必须采用“无证据不生成事实性理由”的确定性门禁，不能只照搬提示词。

### 3. STORM / Co-STORM

仓库：[stanford-oval/storm](https://github.com/stanford-oval/storm)

STORM 有 Stanford OVAL 背景和 NAACL/EMNLP 论文支撑。它把流程分为互联网研究收集参考资料、生成提纲、基于参考资料写作；通过多视角问题生成和基于来源的模拟访谈扩大覆盖面。Co-STORM 进一步允许用户参与讨论、改变研究重点，并维护动态 mind map 作为人机共享知识空间。

可借鉴：

- 搜索前先从不同决策视角生成问题，例如价格、风险、便利性、长期价值，而不是只搜索用户原句。
- “用户编辑闭环”不应只允许最终改权重，也要允许用户在研究中途改变关注方向。
- 候选结论与检索来源之间必须保留引用关系。

STORM 的产物是研究文章而不是候选决策，适合借鉴检索深度与人机协作，不适合照搬其文章生成数据模型。

### 4. Open Deep Research（历史参考）

仓库：[langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research)

该项目支持 Tavily、OpenAI/Anthropic 原生搜索和 MCP，配置中包含结构化输出重试、澄清开关、并发研究单元、研究迭代次数、工具调用上限和不同阶段模型，并使用 Deep Research Bench 做评估。仓库已于 2026-08-21 归档，因此只能作为已验证设计参考，不应作为新的长期依赖。

可借鉴：

- 搜索 Provider、模型、并发、重试、内容长度和迭代预算应显式配置。
- 搜索能力需要评测集和成本/质量指标，不应只靠 demo 观感验收。

### 5. Pydantic AI

仓库：[pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai)

Pydantic AI 支持以 Pydantic model、dataclass、TypedDict 或动态 JSON Schema 定义结构化输出，模型输出经过校验，并可在校验失败时重试。其 graph 能力使用类型标注定义状态和节点，durable execution 支持长任务、失败恢复和 Human-in-the-loop。

可借鉴：

- 每个 Agent 阶段都应有独立输入/输出 schema，而不是共同修改任意 `dict`。
- “丰富 schema”不是增加字段数量，而是让事实、来源、评分、编辑和推荐之间形成可验证引用。
- LLM 只负责生成候选结构，Pydantic 和确定性业务规则负责验证、拒绝和降级。

v2 已经使用 Pydantic，因此第一步可直接补强现有模型和阶段契约，不必为了结构化输出立即更换框架。

### 6. LangGraph

仓库：[langchain-ai/langgraph](https://github.com/langchain-ai/langgraph)；官方文档源码：[Persistence](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/persistence.mdx)、[Checkpointers](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/checkpointers.mdx)

LangGraph 用 checkpointer 保存每一步图状态，支持 thread 内持续会话、interrupt/resume、`update_state`、checkpoint replay/fork 和失败恢复。状态更新会创建新 checkpoint，而不是破坏原历史。

可借鉴：

- 工作台编辑应生成一个新 revision/事件，再从受影响阶段重算，而不是直接覆盖旧状态。
- 用户编辑、搜索返回、推荐生成都应基于同一权威 revision，陈旧异步结果不能覆盖新状态。
- 保存“状态历史 + 运行事件”比只保存最新 JSON 更适合审计、回退和方案分支。

不建议仅为了 UI 编辑立刻引入 LangGraph；v2 已有 revision 和状态机，可以先实现小型 command/event 模型。若后续出现长时间搜索、并行任务、暂停恢复和分支比较，再评估迁移到图运行时。

### 7. AG-UI / CopilotKit

仓库：[ag-ui-protocol/ag-ui](https://github.com/ag-ui-protocol/ag-ui)、[CopilotKit/CopilotKit](https://github.com/CopilotKit/CopilotKit)

AG-UI 定义 Agent 与前端之间的事件协议，包括生命周期、消息、工具调用、完整状态快照和基于 JSON Patch 的状态增量。CopilotKit 在此基础上提供共享状态、前后端双向更新、Generative UI 和 Human-in-the-loop。

可借鉴：

- 工作台需要权威状态快照和增量事件，而不是聊天响应结束后一次性刷新页面。
- 搜索进度、证据到达、候选变化、重排和推荐生成应是结构化事件，而不是解析自然语言日志。
- UI 修改权重、约束或候选后，应把结构化 command 发回后端，由后端验证并返回新状态。

当前 v2 静态前端规模较小，可以先定义自己的最小 SSE/command 合约；只有需要跨框架互操作时再引入 AG-UI/CopilotKit。

### 8. Scikit-Criteria

仓库：[quatrope/scikit-criteria](https://github.com/quatrope/scikit-criteria)

Scikit-Criteria 是面向科学 Python 栈的多准则决策分析库，覆盖 TOPSIS、ELECTRE 等方法。它不是 Agent 框架，但说明排序层应与搜索和语言模型分离：候选矩阵、目标方向、权重、归一化和决策方法都应是确定性、可测试的输入。

可借鉴：

- `Criterion` 需要方向、量纲、目标值/阈值和缺失值策略。
- 排名结果需要 criterion-level score breakdown 和方法版本。
- 第一阶段仍可保留当前加权评分；只有需求明确需要 TOPSIS/ELECTRE 等方法时才增加依赖。

### 9. MingJian（同类产品参考）

仓库：[dashitongzhi/MingJian](https://github.com/dashitongzhi/MingJian)

该项目定位与 Choice Agent 最接近：从来源发现、证据提取、分析/模拟、多角色辩论、推荐、版本时间线，到来源变化刷新和结果反馈。它还描述了企业与军事双领域、来源健康、可回放 Trace 和推荐版本。

可借鉴的是产品闭环：证据、推荐版本、刷新和结果反馈应属于同一个 Decision Record。由于目前研究主要核对到仓库结构与 README，自述中的数据源数量、确定性和自修复效果未做运行验证，因此不把它作为核心技术选型依据。

## 四项能力的具体工程定义

### 真实搜索

“真实”不是候选名字来自 LLM，而是每次动态事实都能追溯到实际检索运行和来源。

完整链路至少包括：

```text
DecisionSpec
  -> SearchPlan（按 criteria/constraints 拆查询）
  -> SearchProvider（fixture / web / domain API / local docs）
  -> SourceDocument（URL、标题、发布者、发布时间、抓取时间）
  -> EvidenceClaim（候选、维度、claim、规范化值、置信度、验证状态）
  -> Candidate merge/deduplicate
  -> Evidence quality gate
  -> deterministic ranking
  -> cited recommendation
```

必要行为包括超时、限流、无结果、来源冲突、过期、重复 URL、抓取失败和离线 fixture 降级。fixture 必须明确标记，不能伪装实时结果。

### 丰富 schema

“丰富”指能表达并校验决策关系，而不是把 `dict` 做得更大。最小完整模型应拆分：

- `DecisionSpec`：目标、领域、硬约束、偏好、开放问题、假设。
- `Constraint`：稳定 ID、label、kind、operator、typed value、unit、source、confidence。
- `Criterion`：方向、权重、target/threshold、unit、missing policy。
- `Candidate`：稳定 ID、来源、属性及属性级 provenance。
- `SourceDocument` 与 `EvidenceClaim`：来源元数据、claim、candidate ID、criterion ID、normalized value、freshness、verification/conflict 状态。
- `ScoreBreakdown`：每维原值、归一化值、权重、贡献、硬约束结果、排序方法版本。
- `Recommendation`：主选、备选、理由、trade-off，并通过 evidence IDs 引用依据。
- `DecisionRevision` / `EditEvent` / `SearchRun`：谁在何时为何修改了什么，以及使用哪个 Provider/模型/配置运行。

### 多领域后端

“多领域”不是首页有多个场景卡片，也不是一个 registry 里有多个 key，而是至少两个非同构领域都能经过后端完成理解、澄清、候选获取、归一化、约束过滤、排名、解释、风险和评估。

领域插件边界至少需要声明：

- 领域识别与支持范围；
- 领域专属输入 schema 和澄清策略；
- 默认 criteria/constraint 语义；
- Candidate Provider 与外部数据源策略；
- 属性规范化和风险规则；
- 排序参数/方法；
- 展示转换与评估 fixture。

通用层负责 revision、状态机、Trace、Provider 生命周期、证据校验、命令处理和持久化；领域层负责业务语义。无法识别领域时应进入 `generic/unsupported` 澄清，而不是默认误路由到旅行。

### 工作台编辑闭环

闭环指用户编辑后，修改进入后端权威状态并触发正确的局部重算，最终推荐、证据和 Trace 与编辑一致。

建议的最小命令集合：

- `answer_question`
- `set_constraint` / `remove_constraint`
- `set_criterion_weight`
- `add_candidate` / `exclude_candidate` / `restore_candidate`
- `refresh_candidates`
- `generate_recommendation`

每个命令需要 `expected_revision`、结构化 payload、权限/领域校验和幂等策略。后端返回新 revision，并明确 invalidated stages。例如改权重只需重排和重做解释；改预算可能需要重新过滤；改目的地范围需要重新搜索。异步搜索返回时若 revision 已变化，应拒绝覆盖或进入待合并状态。

## v2 当前真实能力与差距

### 已有基础

- `DecisionState`、状态机、revision、Trace、`AgentRuntime` 和 JSON 持久化已经存在。
- `GenericDecisionOrchestrator` 已能通过 `DomainRegistry` 创建、推进并保存决策。
- Travel 能走后端 fixture 候选、排序和解释。
- Diet 已有成熟的多 Agent、数据、风险、反馈和评估链路。
- 旧 `choice-agent` 已提供可复用的搜索 Provider、丰富 schema、证据覆盖/冲突检查和工作台交互原型。

### 真实搜索差距

- v2 没有 `SearchProvider`、`SearchRun`、网页抓取、来源去重或失败/预算模型。
- `TravelDomain` 明确使用本地 fixture，并设置 `realTime=False`。
- 通用请求中的 `context` 当前没有传入 `DecisionState` 或插件，创建和消息 API 实际忽略该字段。
- 当前 pipeline 一次执行 `understand -> clarify -> candidates -> rank -> explain`，没有查询规划、并发检索、证据验证和增量候选合并阶段。

### schema 差距

- v2 `Constraint` 只有 `key/kind/values/source`，缺少 label、operator、typed value、unit 和 confidence。
- `Criterion` 缺少 direction、target、unit 和 missing policy。
- `Evidence` 没有稳定 ID、candidate/criterion 引用、claim、publisher、published time、freshness 和验证状态。
- `Recommendation` 的理由和 trade-off 不能引用 evidence IDs。
- 没有 `SearchRun`、`ScoreBreakdown`、`EditEvent` 和推荐版本模型。
- `DecisionState.intent` 仍绑定饮食 `Intent` enum，非饮食意图只能放在自由 `domain_state`。

### 多领域后端差距

- 默认 registry 只有 `DietDomain` 和 `TravelDomain`。
- `DietDomain` 在通用 pipeline 中只是兼容声明：不澄清、不取候选、不排名，只提示真正能力位于 `/api/v1/diet/chat`。
- 因此目前不是两个完整领域共用一个后端框架，而是“一个完整 Diet 旁路 + 一个 Travel fixture 验证域”。
- 未识别输入默认返回 Travel，存在把职业、学习、购物等问题错误路由成旅行的风险。
- `DomainPipelineAgent` 把全部阶段包进一次 Agent run，阶段级输入输出、失败、重试和 Trace 不可独立观察。

### 工作台闭环差距

- 通用后端只有 create、message、get，没有结构化编辑、刷新候选或重做推荐 API。
- `message()` 会把 `user_goal` 直接替换为最新消息，而不是保留原目标并把补充内容建模为 edit/clarification。
- 每次 pipeline 运行会重建全部 `candidate_state` 为 active，缺少对用户排除、手工候选和局部编辑的稳定合并规则。
- 旧版和 v2 demo 中的权重调整、候选增删/排除等交互主要停留在浏览器本地状态，不是后端权威 DecisionState。
- 没有异步搜索进度事件、状态增量、checkpoint/revision 历史或从某次编辑重新计算的能力。

## 用户反馈后的统一架构补充研究

用户指出 Travel 和 Diet 应统一为一套决策逻辑，领域只在应用时微调。复核 DietOrchestrator、diet agents、DecisionEngine、DietRepository 和回归测试后，确认该判断成立，并且需要修正上一版 Plan 中“本轮不迁 Diet”的边界。

### 当前两套逻辑的对应关系

Diet 当前流程为：

    intent
      -> understand
      -> health-risk / other early exit
      -> optional adjust
      -> clarify
      -> candidate or meal-plan
      -> critic
      -> explain
      -> risk
      -> persist

Generic 当前流程为：

    understand
      -> clarify
      -> candidates
      -> rank
      -> explain
      -> persist

两者不是本质不同的架构。Diet 多出来的是条件阶段和领域策略，而不是需要独立 Orchestrator：

- health risk 是通用 SafetyStage 中注册的 DietRiskPolicy。
- meal adjust 是候选选择策略 least_recent/exclude_previous。
- meal plan 是可选 CompositionStage，把多个候选组合成计划。
- 餐食库查询是 DietCandidateProvider。
- 七维 slots 是 DietProfile 的领域输入 schema 和 criterion evaluator。
- 饮食文案与 MealResponse 是领域 presenter/API adapter。

### 应统一的核心与允许微调的边界

统一核心必须负责：

- session/decision 恢复、owner、revision 和消息历史；
- route、understand、clarify、source、evidence、filter/rank、critic、explain、risk、persist；
- AgentRuntime 和阶段级 Trace；
- Provider 生命周期、错误、降级和预算；
- command、状态失效、重算和幂等；
- Recommendation 证据引用与状态机。

领域只允许提供：

- 领域 ontology、intent 定义、required fields 和澄清问题模板；
- CandidateProvider；
- constraint/criterion 定义及单维值归一化；
- hard constraint、risk 和 critic policy；
- 可选 CompositionStrategy；
- response presenter 和 evaluation fixtures。

领域不再实现整条 understand/candidates/rank/explain pipeline。否则每增加一个领域仍会复制流程。

### Diet 统一的兼容难点

- Diet 依赖 diet_sessions 和 diet_messages；通用链路当前只保存 DecisionRecord。统一后 DecisionState 应成为业务权威状态，旧 session/message 表由兼容 adapter 继续维护。
- Diet 当前每轮创建新 decision_id。统一后一个 session 应恢复并推进同一个当前 Decision；旧记录通过 latest-by-session 兼容读取。
- ChatResponse、MealResponse 和 SessionPhase 是旧 API 合约，不能进入通用核心；由 DietApiAdapter 从统一结果转换。
- PlanningAgent 不是普通单候选排名，应抽为可选 CompositionStrategy，而不是把 meal plan 逻辑推广到所有领域。
- Diet 的 categorical list 匹配与 Travel/Shopping 数值评分不同。统一 RankingEngine 负责聚合、约束、缺失值和稳定排序，领域 CriterionEvaluator 只负责把单维原始值转换为规范分。
- RiskAgent 的健康文案属于 Diet policy；统一 SafetyStage 执行领域注册的 policies，没有 policy 的领域不运行健康逻辑。

### 修正后的结论

真正统一不是让 Travel 调用 DietAgent，也不是让所有 DomainPlugin 各自实现相同方法，而是让所有领域进入同一个阶段运行器。领域差异应表现为数据、规则和可插拔策略；旧 Diet API 只作为兼容适配层。后续 Plan 必须把 Diet 迁入统一运行器作为成功标准，否则“多领域后端”仍然只是接口统一。

### Diet-first 路线纠正

进一步 Review 后，需要再纠正实施方向：不能先设计一个抽象的 UnifiedDecisionOrchestrator，再把 Diet 当作迁移对象。这样仍然是从不完整的 Generic 逻辑出发，容易丢失 Diet 已经具备的澄清、调整、计划、审查、风险、Trace、反馈和评估闭环。

正确做法是以现有 DietOrchestrator 及其 characterization tests 为可执行规格，原地逐步通用化：

1. 先保持 /api/v1/diet/chat 作为主调用入口。
2. 从 DietOrchestrator 当前顺序中提取 StageRunner，但第一位调用者仍是 Diet。
3. 把 DietRepository.list_meals 抽成 CandidateProvider，把 DecisionEngine 中餐食维度算法抽成 CriterionEvaluator。
4. 把 health risk、hard exclusions、critic 抽成 policies，把 PlanningAgent 抽成可选 CompositionStrategy。
5. 每抽取一个边界立即运行对应 Diet 回归，确保通用化没有降低最完整领域的能力。
6. 当 Diet 已完整运行在参数化主干上后，将该主干命名为 UnifiedDecisionOrchestrator。
7. 最后用 Travel 和 Shopping 接入验证通用性，并删除现有简化 GenericDecisionOrchestrator。

因此，Diet 不是需要适配到通用框架的一个普通插件，而是通用框架的来源和首个验收基准。

## 关键结论

### 1. 四项能力必须作为一条链设计

真实搜索产出来源和 claims；丰富 schema 保存可验证关系；多领域后端把不同业务数据归一成同一决策协议；工作台编辑再通过 revision 和命令触发重新搜索、过滤、排序和解释。缺一项，其他项就容易退回 demo：

- 无 schema 的真实搜索会退化成不可审计文本。
- 无真实 Provider 的丰富 Evidence 只是 fixture 外壳。
- 无后端领域实现的多领域只是前端场景切换。
- 无服务端命令与 revision 的工作台只是本地计算器。

### 2. 不存在一个应整包迁入的“标准仓库”

更可靠的组合是：

- 检索与来源追踪：借鉴 GPT Researcher、STORM、Deep Agents。
- 类型与结构化校验：延续 Pydantic，并借鉴 Pydantic AI 的阶段输出验证。
- 状态历史与重放：先用现有 revision/event 模型实现，复杂后再评估 LangGraph。
- UI 状态同步：先做最小 command + SSE，互操作需求明确后再评估 AG-UI/CopilotKit。
- 排序：保持确定性实现，复杂 MCDA 需求明确后再评估 Scikit-Criteria。

### 3. 本地旧 choice-agent 值得迁语义，不值得原样迁实现

旧版已经有 `SearchProvider`、结构化 Evidence、证据覆盖/冲突、revision 校验和工作台交互，是 v2 最近的直接参考。但其 Web Search 仍存在不足，例如无效 URL 被替换成 `example.com`、来源真实性缺少独立验证、搜索结果和推荐解释主要依赖模型。因此应迁移数据契约和交互语义，并用更严格的证据门禁重写后端实现。

### 4. 下一阶段首个真实搜索领域应有限定边界

旅行适合继续作为试点，但应限定为可由公开来源验证的候选发现和事实比较，不做实时库存、价格承诺或代订。购物也可作为第二候选，但价格时效和反爬复杂度更高。职业、医疗、金融、法律不适合做首个真实搜索闭环。

## 推荐的后续阶段顺序（非 Plan）

1. 先补证据、来源、评分和编辑事件 schema，并定义兼容策略。
2. 抽 `CandidateProvider/SearchProvider`，保留 fixture，再接一个真实 Web Provider。
3. 把 pipeline 拆成可观察阶段，加入失败、超时、预算和证据门禁。
4. 增加结构化 command API 和后端权威重算。
5. 让工作台消费后端快照/增量事件，完成编辑闭环。
6. 将 Diet 真正适配到通用协议，再新增第二个非同构完整领域。
7. 建立搜索质量、证据引用、排序稳定性和编辑一致性的评估集。

## Plan 阶段需要决策的问题

- 首个真实 Provider 使用 OpenAI 原生 Web Search、Tavily、SearxNG，还是先定义接口并只实现其中一个？
- 是否允许一个 EvidenceClaim 同时关联多个来源，还是第一版保持一 claim 一 source？
- schema 扩展采用原字段兼容扩展，还是引入 versioned `DecisionStateV2`？
- 编辑历史使用追加式 `EditEvent`，还是只保存 revision 快照？
- 搜索采用同步 API、后台任务轮询，还是 SSE 增量推送？
- Diet 何时从兼容壳迁入通用 pipeline，是否与真实搜索阶段拆开实施？
- 第一阶段是否只做 Travel，还是同时加入 Shopping 证明 Provider 可跨领域复用？

## Research 结论

此前“真实搜索 + 丰富 schema + 多领域后端 + 工作台编辑闭环”的判断主要来自本地旧 `choice-agent` 与 `diet-agent` 对比，当时没有完成外部 GitHub 基准检索。本次已经补做。

外部高质量项目验证了方向，但也修正了表述：目标不应是简单增加 Web Search、字段、领域 key 和编辑按钮，而应建立一条可追溯、可校验、可重算、可审计的 Decision Record 链路。v2 已具备状态机、revision、Trace、Pydantic 和 Diet 完整业务基础，适合渐进补齐；当前最关键的结构性缺口是 Provider/证据模型和服务端编辑命令，而不是更换整个 Agent 框架。