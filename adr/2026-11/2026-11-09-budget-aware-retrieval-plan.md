# 预算变化后的候选检索策略 Plan

日期：2026-11-09
状态：已获用户批准，实施及验证完成。
依据：[Research](2026-11-09-budget-aware-retrieval-research.md)。

## 目标和成功标准

在现有增量执行链中，依据结构化预算方向和可信候选覆盖，选择最小安全路径。优先 Shopping，同时给 Travel 明确的领域策略。

- Shopping 预算 5000→4000：RERANK，池保留，活动候选和所有推荐均符合最新上限。
- Shopping 5000→8000、5000→None：覆盖未知或不足时 REFRESH；有明确且有效覆盖时允许 RERANK。
- 首次设置预算：即使数值上是收紧，不能仅据此证明原检索范围充分，缺覆盖时 REFRESH。
- 预算不变只改权重 RERANK；类别/用途变化、空池、显式刷新 REFRESH；首次运行 FULL；纯解释 EXPLAIN_ONLY；What-if 保持隔离。
- 新增预算范围内商品真实进入候选池并参与推荐；不只修改 mode 或 Prompt。
- 最新 fields/constraints、最终结果、revision、receipt 一致；失败不提交部分结论。
- 不清空手工候选/排除；复用时不重写原来源/证据时间。
- Trace 给出字段、前后预算、方向、选择原因、复用与刷新结果数量。
- 无公开 API、数据库 schema、依赖、Agent 数量变更；不重构 Orchestrator。

## 设计与关键流程

### 1. 预算描述和方向：复用既有基线

继续使用 capture_execution_baseline 和 _changed_conversation_fields，不增加另一套 State / 版本机制。默认领域无预算策略，Shopping 声明硬约束属性 price，Travel 声明 budget；通用 planner 不按 domain 字符串硬编码规则。

在 execution.py 内部增加小型预算快照/比较 helper（无需独立服务）：

- 从 baseline.fields / 当前 fields 提取预算值、confirmed、cleared 和来源，用于字段方向及诊断。
- 从 baseline.constraints / 当前 constraints 提取领域预算属性的硬数值上界。多个来源同时存在时取交集上限，保留约束来源和边界严格性。
- 常规 lte/lt 正有限数可明确比较；相同数值 lt→lte 属于放宽。布尔、NaN、Infinity、零负数和数字字符串不按普通合法上限比较。
- 区分 tightened / relaxed / unchanged / first_set / removed / unknown；字段初次赋值与有效上限首次建立均保留 first_set 信息。
- 新输入非法沿用 patch_fields 的显式异常；直接写入非法数值预算硬约束时在规划阶段明确报错，触发回滚。历史旧值不可解释时标记 unknown，不能默认为无限或“已覆盖”。
- 非普通上界（如价格 eq/gte）变化不强行比较数值方向；标记未知预算范围变化，保守刷新并继续让原硬过滤处理语义。
- 以实际硬约束为准决定有效过滤范围；同时跟踪查询会使用的预算字段。未确认建议不是硬约束，但字段会进入 Web 查询，因此预算建议改变不能被错当成已确认预算；缺少覆盖证明时保守刷新。
- 清空字段只移除 conversation_field 生成的约束，不删除独立用户约束。若独立上限仍限制范围，Trace 展示字段已取消与有效上限仍存在的区别。

不扩展通用约束系统，不引入货币换算；预算单位语义保留当前元。无法解释的兼容数据保守处理并给出原因。

### 2. 可信候选覆盖：由 Provider 声明并绑定检索

在内部 CandidateSearchResult 尾部增加可选 budget_coverage（默认 None，既有位置参数调用兼容）。该字段是 Python Provider 内部结果扩展，不改变 API schema 或 SearchRun 的必填结构。

最小覆盖信息包括：complete、budgetIndependent、可选 maxBudget。仅在 Provider 实现能保证完整覆盖当前声明集合/查询作用域时允许 complete=true；maxBudget 表示可证明覆盖的上界，不能从候选价格计算。

- ShoppingFixtureProvider 在固定类别/用途候选已完整返回后，由代码明确声明 complete + budgetIndependent。此声明仅对演示集合成立，不声称覆盖真实市场。
- TravelFixtureProvider 仅在返回集合具有固定模拟费用、适用出发地满足现有演示边界时声明预算无关的固定候选覆盖。非上海出发已删除费用时不声明充分覆盖，不新增真实路线/费用假设。
- OpenAIWebSearchProvider 不声明 complete。忽略模型返回 JSON 中任何自称覆盖充分的信息；有次数限制的 Web 搜索不能证明穷尽覆盖。
- 自定义测试 Provider 可明确声明有界覆盖，验证 8000 位于覆盖上界内/外的路由。生产 Web 不因这些测试声明获得默认覆盖能力。

ComparisonProfile 在 manual 合并前保留外部 Provider 声明，在验证成功并保存 candidatePool 时绑定到既有 domain_state.source 的可选 budgetCoverage：

- 声明版本、Provider、SearchRun ID；
- 领域和实际检索作用域（检索敏感字段、其余检索相关条件、搜索模式）；
- complete / budgetIndependent / maxBudget；
- 外部候选 ID 集合，用于确认池未丢失证书对应候选。新增手工候选不降低外部池覆盖证明。

来源/作用域必须与当前 State 对得上；缺失、损坏、过期绑定或池已丢失必要候选则不可复用。每次 REFRESH 都替换覆盖记录；本次结果无声明时清除旧覆盖，尤其保护 auto Web/fixture 切换。RERANK 保留原记录、SearchRun、Evidence 和来源时间。

历史只有 source.mode=fixture 的状态不自动授予证书，允许首次相关预算变更保守刷新。不能用候选最高价格、数量或 URL 数量作为覆盖证据。

### 3. 领域策略与执行优先级

在 DomainProfile 增加默认不介入的预算扩展点（预算属性和预算变化刷新判断）；Shopping/Travel 分别实现。内部 helper 和领域 hook 只服务当前需求，不建立通用约束变化框架。

逻辑顺序：

1. What-if、显式 FULL/REFRESH、阻塞澄清保持既有隔离和命令语义。
2. 新建/无基线及尚未启用增量的领域保持 FULL。
3. 非空基线但池缺失 → REFRESH。
4. 检索敏感字段变化 → REFRESH。
5. 领域预算策略要求刷新 → REFRESH。
6. 明确 RERANK 请求或其他决策输入变化 → RERANK。
7. 无输入变化 → EXPLAIN_ONLY。

将 requested RERANK 从无条件早返回改为“通过候选/检索安全检查后执行”，防止同轮预算放宽或类别变更被候选 dislike / misalignment 分支绕过。显式 refresh_candidates、自然语言重新搜索、batch reject 仍刷新，generate_recommendation 在无检索边界变化时仍重排。不改变 What-if 和澄清执行顺序。

| 领域/变化 | 有效覆盖证明 | 无证明或覆盖不足 |
| --- | --- | --- |
| Shopping 收紧 | RERANK | RERANK（旧池仍可重新硬过滤） |
| Shopping 放宽/取消/首次设置 | RERANK | REFRESH |
| Shopping 无法判断范围变化 | 仅可证明预算无关且作用域一致时 RERANK | REFRESH |
| Travel 固定费用演示集合的预算变化 | 证书证明固定集合且新范围覆盖时 RERANK | REFRESH |
| Travel Web/未知来源的预算变化，包括收紧 | 不接受一般目的地/价格覆盖作为完整方案证明 | REFRESH |
| Generic / Diet | 保留现有策略 | 保留现有策略 |

Travel 与 Shopping 的差异是有意设计：Web 查询可能根据预算重新组合住宿、交通和行程，收紧时旧方案过滤也可能损失更合适的新方案。当前没有完整行程生成器，本次不新增；仅给已有检索采取保守刷新策略。Travel fixture 的预算属性仍是模拟参考，不增加现实费用承诺。

### 4. 状态和候选处理

继续经 patch_fields / sync_dependencies 更新预算和字段生成的硬约束。预算更新后 recommendation 已被清空；两条执行路径都重新硬过滤、排序、解释并最终校验。

REFRESH 使用最新 State 调用原 _search，再合并原 manualCandidates；保留 excluded_candidates。RERANK 使用原未硬筛选 candidatePool，使降价后被排除的候选在再次放宽时仍可恢复（覆盖证书有效时）。不修改 category 分支原有重置语义。

直接约束预算变化也纳入方向检查，但不为本次优化自动覆盖用户独立硬约束，或把所有约束改写回 conversationFields。

不重写 Orchestrator。继续使用现有 revision compare-and-swap、receipt、_persist 和 rollback。异常发生在搜索、排序/解释、最终校验或保存阶段时，数据库保持上一轮已提交状态；允许保留上一轮有效推荐，不得把新预算的不完整结果标记为有效。

### 5. Trace 扩展

给内部 ExecutionPlan 增加默认空的诊断信息，由 StageRunner 写入现有 Execution Plan 节点、metadata 和 turnSummary：

- changedFields（排序稳定），必要时标记 constraints 变化；
- oldBudget / newBudget：字段值；oldEffectiveBudget / newEffectiveBudget：实际硬上限；
- budgetChangeDirection、来源、覆盖是否有效及不足原因；
- mode / reason、candidatePool.reused；
- candidateCountBefore，以及执行成功后的 candidateCountAfter/refreshedCandidateCount。

保留现有 candidatePool.candidateCount 的最终数量兼容；明确区分未过滤池数量与活动候选数，刷新失败不伪造成功后的数量。失败 Trace 继续由现有 rollback/FAILED 逻辑保存。无需改 Trace UI 或 schemaVersion。

## 受影响文件与计划修改

| 文件 | 修改内容 |
| --- | --- |
| `src/choice_agent/decision/execution.py` | 复用基线增加预算方向比较、覆盖校验、RERANK 安全升级及计划诊断；不改变五种 mode。 |
| `src/choice_agent/domains/profile.py` | 最小默认预算 hook，保持现有领域默认行为。 |
| `src/choice_agent/domains/shopping.py` | price 预算策略；固定全集检索后明确声明覆盖。 |
| `src/choice_agent/domains/travel.py` | 总预算/方案相关策略；符合模拟费用边界的固定 fixture 才声明覆盖。 |
| `src/choice_agent/providers/candidates.py` | CandidateSearchResult 尾部可选内部覆盖声明。 |
| `src/choice_agent/domains/comparison.py` | 持久化本次可信声明与查询作用域，刷新时替换/清除、复用时保留。 |
| `src/choice_agent/agents/conversation.py` | 解析「预算从 5000 降到 4000」等明确起止表达，以目标值更新现有字段。 |
| `src/choice_agent/agents/stages.py` | 在既有 Execution Plan Trace 中记录预算/原因和候选前后数量。 |
| `tests/test_execution_workflow.py` | 运行既有执行路径回归。新增预算方向和领域策略矩阵集中在预算专项文件。 |
| `tests/test_budget_retrieval.py`（新增） | 可控 Provider/transport 的真实 Orchestrator 多轮、候选结果、覆盖、来源和错误注入测试。 |
| `tests/test_general_conversation.py`、`tests/test_multiturn_replan_regression.py` | 仅在已有断言需要细化时增量补充；保留既有断言。 |
| `CHANGELOG.md` | 实施完成后在当天日期标题记录预算方向/覆盖驱动刷新和旅行保护。 |

预计无需修改 conversation.py、providers/search.py、orchestration/generic.py、数据库或公开 schemas；用测试验证已有字段同步与请求构造。若确实发现这些链路有阻断本目标的 bug，先明确证据和边界，重要设计变动更新本 Plan 再审批。

## 兼容性、风险和折衷

- 公开请求/响应字段、命令名称、五种执行模式不变；domainState/Trace 仅增加可选信息，旧数据正常读取。
- CandidateSearchResult 是内部扩展，新增字段放末尾并默认 None，保护全部既有 Provider 调用。
- 旧数据第一次放宽预算可能多一次刷新，这是缺乏覆盖证据时的质量取舍。
- Fixture 证书只证明受控演示集合完整；不证明市场、真实旅行路线或价格全面。
- Travel Web 收紧也刷新，成本可能高于现状，但避免错误复用预算相关方案；领域 hook 保留以后按真实方案覆盖优化的入口。
- 当前查询含旧 user_goal，但已有当前字段覆盖声明；mock 请求体验证新上限存在/取消生效，避免只测 mode。
- 非预算检索条件变化可令覆盖失效，允许保守多刷新，不尝试证明任意约束集合的蕴含关系。
- 不增加时间 TTL 或全市场完备性模型；已有 Evidence 新鲜度不在本次范围。
- 工作区已有未提交修改，禁止恢复文件到 HEAD；最终只核对本次增量。

## 自动化验证

### 规划与边界矩阵

覆盖：5000→4000、5000→8000、相同数值、首次预算、取消预算、有界覆盖内/外、预算无关固定全集、无元数据旧池、高价候选但无证明、损坏/不匹配覆盖、lt/lte、多来源硬上限、未确认模型字段、None、布尔/NaN/Infinity/字符串/非正数、软约束不冒充硬上限。

保护：权重 RERANK、类别/用途 REFRESH、空池 REFRESH、显式刷新 REFRESH、初次 FULL、纯解释 EXPLAIN_ONLY、What-if 不改正式池/证据/预算；同轮 RERANK 反馈不能绕过预算扩张。

### 真实结果与事务

使用注入 registry 的可控 Provider：旧查询只返回 5000 内商品，新查询增加 5000–8000 商品；断言调用次数、实际读取的预算/约束、新商品进池并进入活动比较/推荐。另用可信完整固定池验证扩张零新增搜索；不使用实时网络。

至少验证：

1. 5000→4000 复用池，活动候选与主/备推荐均≤4000，旧池内较贵候选仍保留。
2. 5000→8000 覆盖不足刷新，新增合适商品实际参与推荐且均满足最新上限。
3. 有可靠覆盖的 5000→8000 重排、不调用 Provider；仅最高价高不够。
4. 5000→None 在未知覆盖时刷新、充分覆盖时复用；独立手工硬约束继续生效。
5. 已有池首次设置预算：未知覆盖刷新、固定完整集合可复用。
6. 连续 5000→4000→8000→取消，多轮字段、constraints、候选与推荐始终一致。
7. 权重、类别、空池、显式刷新、纯解释和 What-if 回归。
8. 手工候选与排除跨刷新/重排保留；RERANK 的 SearchRun/Evidence/来源时间不变。
9. 使用 OpenAIWebSearchProvider fake transport 检查真实请求 JSON 中当前 fields/constraints 随预算替换和取消更新；不接受 response 自称 complete。
10. Travel Web 收紧/放宽均刷新；固定 fixture 证据充分时可复用；非上海缺费用不生成虚假预算推荐。
11. 搜索抛错、候选生成后排序/解释抛错、最终校验/保存抛错：数据库上一轮 fields、constraints、池、推荐、revision、receipt 不变，失败 Trace rolled_back；重试成功后幂等且无重复检索。

所有结果测试同时断言 ExecutionMode 和候选/最终推荐满足最新硬约束，复用现有 GenericRankingEngine / validate_recommendation，不复制生产排名算法。

### 命令和完整检查

研究基线已运行 45 tests（见 Research），实施后执行：

- 局部：`.venv/Scripts/python.exe -m pytest tests/test_budget_retrieval.py tests/test_execution_workflow.py tests/test_general_conversation.py tests/test_multiturn_replan_regression.py tests/test_decision_canvas.py tests/test_candidate_search_productization.py tests/test_unified_decision.py tests/test_trace_observability.py`
- 全量：`.venv/Scripts/python.exe -m pytest`
- 编译：`.venv/Scripts/python.exe -m compileall -q src scripts`
- `git diff --check` 与最终 diff；项目无独立 typecheck/lint 配置，不新增工具依赖。
- 重要写入后重新读取确认真实落盘。行为由真实 Orchestrator + mock Search Provider/transport 验证，纯后端路由优化不新增 UI。

遇到环境或既有失败时明确记录测试项、原因、替代证据和剩余风险，不宣称全部通过。

## 实施验证记录

- 预算专项 44 项通过。可控 Provider 验证新增商品进入候选池与最终推荐，真实 Provider 的 mock transport 验证提高和取消预算时的请求体。
- 最终全量 Python 测试 417 项通过，耗时 289.95 秒。购物、旅行、通用、饮食及 API 回归均纳入该次执行。
- Python compileall 与 Git diff 空白检查通过。保留既有未提交改动，按 2026-11-09 更新 CHANGELOG。
- 在线检索使用 mock transport 验证。Web 覆盖未知时刷新，旅行 Web 方案可能因此增加检索次数。

## Todo

- [x] 实现基于现有执行基线的预算字段/有效硬上限快照、方向与非法值处理，并通过矩阵测试。
- [x] 增加最小领域预算 hook，实现 Shopping / Travel 区分策略，保护 Generic / Diet。
- [x] 为内部 Provider 结果增加可选覆盖声明；fixture 明确声明、Web 默认未知。
- [x] 在 candidatePool/source 中绑定和校验覆盖，验证刷新替换、旧数据缺失和作用域失效。
- [x] 接入 plan_execution 优先级，验证预算放宽安全升级及命令/反馈/澄清/What-if 兼容。
- [x] 扩展既有 Execution Plan Trace，验证预算前后值、方向、原因、复用和刷新数量。
- [x] 完成可控 Provider 多轮候选及主/备推荐硬约束测试，证明新增预算商品真正参与比较。
- [x] 完成搜索/执行/保存异常回滚、revision、receipt、幂等及手工候选/排除保留测试。
- [x] 执行局部和全量测试、编译、diff 检查，记录未验证项与既有失败。
- [x] 按实施日期更新 CHANGELOG，核对最终增量和 Todo，输出完成情况及剩余风险。
