# Evidence 产品展示与推荐追溯 Plan

日期：2026-09-05
状态：待用户审查与明确实施批准。依据同目录 2026-09-05-evidence-presentation-research.md。
本次仅写 Research / Plan；不沿用旧 ADR 的实施授权。

## 目标与成功标准

1. 每条关键依据可区分“用户输入 / 外部搜索 / 系统推断 / 演示数据 / 数据库记录 / 来源不明”；来源、陈述性质与核验状态分别表达。
2. 当前推荐理由与结构化取舍引用真实 Evidence ID；展开能看到原始陈述、来源、适用候选/条件、已知时间及限制。
3. “用户认为 B 公司成长空间大”标为用户判断，未经外部核实；“更倾向 B”标为系统推断，并引用候选说明与用户偏好。
4. URL 在搜索列表出现只显示“来源链接已校验，内容未独立核实”，不显示“事实已验证”。fixture 不冒充外部事实。
5. 规则与模型路径、创建/续聊/编辑/重算/刷新/历史恢复均适用，原有预算、排除、假设与幂等行为保持。

## 范围与取舍

完善现有购物、旅行、Generic 的 Decision Canvas 与历史依据。承接已存在的 Web Search Provider，不切换默认 searchMode、不新增搜索供应商或实际联网调用。共享 schema/validator 的 Diet 兼容纳入回归，不重做饮食专用推荐界面。

不实现自动全网事实核验、任意自然语言冲突检测、自动判定官方权威性、统一 freshness TTL、独立证据数据库或旧工作台剩余架构。未知项明确显示；“已验证”当前没有可信生产入口，不为展示效果制造验证结果。

## 数据契约

扩展现有 Evidence，新增字段均有保守默认值：
- source_kind：user / web / system / fixture / database / unknown。
- statement_kind：reported_fact / subjective_judgment / preference / inference / unknown。reported_fact 意为待核实的事实陈述。
- citation_status：matched / rejected / not_applicable / unknown，表达来源引用检查。
- claim_status：unverified / verified / not_applicable，独立表达陈述核验。
- verification_note：解释已执行或缺少的检查。verified 必须有可信服务端记录的核验说明；模型输出和用户上传不得设置。
- source_id、source_quote、recorded_revision、supporting_evidence_ids：链接资料/原文/轮次/推断依赖；缺原文不伪造 quote。
- 沿用 source_url/title、published_at、retrieved_at；retrieved_at 允许缺省为空，实际搜索由 provider 显式填采集时间，不能读取旧记录时自动填当前时间。

保留旧 verificationStatus 枚举与字段，明确它是历史内部兼容信号，UI 不再直接翻译为“事实已验证”。新增 citation_status 由服务端来源校验派生；claim_status 不能从旧 verified 推导。排序的来源合格判定集中复用 helper：web 需合法工具来源、同 criterion/value，拒绝项不可用；fixture/database/manual 延续各自数据规则。允许按未独立核实的搜索数据作条件性比较，结果明确标注。

RecommendationPoint 复用 evidenceIds（可多个）；tradeoffs 文本列表保留，填充已有 tradeoffDetails。analysis.reasons/tradeoffs 增加 evidenceIds；sourceId 保留为兼容首项别名，新输出的每个 ID 都必须可解析。

模型 AssistanceReason 增加可选的多引用结构（每项 source_id + quote），保留旧 source_id/quote 单引用输入；两种表示并存时必须一致，否则拒绝。模型只能引用服务端目录，不创建可信元数据。

## 规范化与来源记录

在 decision/evidence.py 扩展现有规范化能力：
1. 汇集 candidatePool 的原始 Evidence、手工候选说明/属性、assistance.facts、实际参与决策的 conversationFields。以 DecisionState.evidence 为当前权威集合，按 ID 去重。
2. ID 对同一内容和来源稳定；说明/值/来源改变时产生新 ID，旧快照保留旧内容。已有稳定 fact ID 可保留，旧 candidate:* 通过保守适配处理。
3. 用户主观描述无法可靠细分时显示“用户提供的描述，可能包含主观判断，未外部核实”；明确偏好字段标 preference。不要用模型标签把用户陈述升级为外部事实。
4. 用户来源从录入边界记录；演示初始化仅给初始示例材料标 fixture，Demo 后续补充/面板编辑标 user。旧 Demo 无法区分的材料显示来源待确认，不能从会话开关强行推断全部来源。
5. 模型提议条件仍标 system/inference、待确认；用户确认后记录为用户认可的条件，但不升级成外部已验证事实。
6. add/update_candidate 清除用户传入的可信标记、自带 Evidence ID 冒用和推断依赖；由服务端归一化。模型搜索结果同理。
7. 来源过滤与 ID 生成用于完整 source 路径及 rerank 路径；仅补充/重算时不能刷新旧 retrieved_at。
8. 排除/筛除候选可保留资料用于查看，但不进入可推荐目录。清空条件不能继续支撑当前理由。

## 推荐到 Evidence 的流程

规范化原始依据 → 排序 → 建立仅含允许依据的 catalog → 规则/模型解释 → 引用校验 → 保存分析及快照。

- catalog 从规范 Evidence 建立，携带来源、核验状态和原文，不再独立虚构来源目录。
- “A 的续航 X，B 为 Y”引用两边的具体属性 Evidence；取舍引用实际用到的维度，不能统一挂在 summary。
- “符合你更看重稳定的要求”同时引用用户偏好与候选说明；偏好是决策条件，不作为候选外部事实。
- 每个重要理由/取舍作为 system/inference 展示；需要独立推断 Evidence 时由服务端从已校验 RecommendationPoint 生成，supporting_evidence_ids 只指向本轮原始依据，禁止自引用/循环。
- 推荐必须有其候选的有效支撑，不能仅引用偏好。校验所有引用存在、候选归属、quote 相符；比较理由允许显式引用其他活跃候选。
- 数值校验收紧到该理由实际引用资料；summary 使用已通过校验的依据集合。原有允许推荐集合、排除/硬筛选、顾虑、保证性表述拒绝保留。此检查不承诺证明任意自然语言蕴含。
- 无有效依据的理由不输出为成立的推荐理由；给出“依据不足”与具体缺项，必要时 primaryCandidateId=null。已明确验证失败的资料仅作被拒绝项展示。
- 假设分析使用独立证据快照，不能覆盖当前 recommendation/条件或把假设当作已确认事实。

## Canvas 展示

复用现有“当前取舍”“依据”“需要接受的代价”，每条理由显示“系统推断”和“查看 N 条依据”的原生 details 展开：
- 依据正文与来源类别、陈述性质；
- 来源标题和安全 HTTP(S) 链接（合法链接可以打开，但不代表内容已验证）；
- “用户输入，未经外部核实”“来源链接已校验，内容未独立核实”“演示数据，不代表真实情况”“来源不明，待核实”等准确文案；
- 检索时间与网页发布时间分别标注。今天按浏览器当地日期计算，显示绝对时间辅助；缺时间显示“时间未知”，绝不把检索时间写成网页更新时间；
- freshness 仅作来源提示，价格等动态信息附“可能变化，请以当前来源为准”；不捏造过期阈值。

“当前比较”候选与详细比较共用 Evidence 渲染 helper，展示陈述而非只列标题。没有依据的候选显示“暂缺可靠依据”；依据来自用户时允许其主观判断参与条件性比较。键盘可展开、焦点可见、移动端长 URL/文本可换行；不只依赖颜色区分来源。

历史消息增加当轮分析依据入口，消费 conversationTurns.analysis 的证据快照；不能查询当前目录替代旧依据。旧记录缺快照显示“历史依据未保存”，保留原文本。当前假设与真实推荐使用各自目录。

## 受影响文件

下列路径除 tests/docs/CHANGELOG 外均相对 src/choice_agent：
| 文件 | 计划修改 |
| --- | --- |
| schemas.py | Evidence 增量元数据、时间默认兼容、多引用模型输入；复用推荐结构。 |
| decision/evidence.py | 单一规范化目录、来源与内容核验分离、稳定 ID、依赖/引用校验和评分来源 helper。 |
| providers/search.py、providers/candidates.py | 服务端赋来源和检索时间，不信任模型核验元数据；fixture/database 语义明确。 |
| decision/commands.py、agents/conversation.py、decision/conversation.py | 录入来源、手工修改清理、条件引用、旧状态只读兼容。 |
| decision/assistance.py、prompts/conversation.py | 统一 catalog、多证据理由/取舍、引用范围数值检查与明确降级。 |
| decision/ranking.py、domains/diet/evaluator.py | 接入一致的来源合格判定，保持排序与饮食引用行为。 |
| domains/comparison.py | 完整搜索与 rerank 统一证据同步，displayBlocks 携带一致证据。 |
| orchestration/generic.py | 保存不可漂移的当轮证据快照，假设隔离与 receipts 兼容。 |
| static/assets/js/evidence.js（新增） | 两处 UI 与历史入口共用的证据/引用渲染 helper。 |
| static/index.html、static/assets/js/conversation.js、app.js、static/assets/css/app.css | 加载 helper、理由展开、历史依据、候选证据、中文状态与响应布局。 |
| tests/test_evidence_presentation.py（新增）、test_decision_assistance.py、test_unified_decision.py、test_generic_api.py、test_general_conversation.py | 数据/引用/来源信任/多轮/旧数据/API 回归。 |
| CHANGELOG.md、docs/migration-matrix.md | 实施后记录产品变化与仍未实现的自动核验边界。 |

不新增依赖、API 路径、数据库表；不修改现有发布环境。若实施发现需新增可信核验服务或改变核心排序策略，先更新 Plan 并重新审查。

## 兼容与边界风险

- 旧 verified 不证明内容已核验，新字段缺失一律保守显示；旧时间若已保存可保留，但标“记录中的检索时间”，不推断真实性。
- 当前旧引用仅在能从同一快照确定匹配时适配；GET 不改数据库/revision，无法恢复的引用不补造。
- 共享 EvidenceValidator 不能使 Diet 的 scoreBreakdown 丢引用；兼容行为要有回归证据。
- 原始材料可能很长，页面渐进展开；生成模型目录延续有界上下文，不能因为截断 quote 导致无效引用被接受。
- 本次结构化校验提高可追溯性，不能确认网页陈述真实性、自动识别所有主观表达或消除模型幻觉。

## 验证方案

实施前跑当前全量 pytest 作为基线，不沿用旧 Plan 测试数量。实施后先审 git diff，再执行 pytest、python -m compileall -q src、修改 JS 的 node --check、git diff --check；项目无独立 typecheck/lint/前端 build，明确记为不适用。

专项自动验收：
- 用户说明/评分/偏好、演示初始资料与后续用户补充、数据库、模型推断、来源未知均正确分类。
- 合法工具 URL 仅 matched，claim_status 不自动 verified；非法/伪造 URL、用户伪造核验标记与 ID 被拒绝或清理。
- 所有当前理由及 tradeoffDetails 引用可解析；A/B 数值比较引用双方；无依据数字与已排除候选继续被拒绝。
- 用户编辑、更改偏好、清空、排除恢复、refresh、只 rerank 后无过时当前引用；历史 quote 不被新值覆盖。
- 缺时间不显示今天；检索时间和网页发布时间区分；同内容重算 ID 稳定。
- 旧 schema/临时目录/缺快照、假设、409、重试响应、跨用户读取保持正确。

浏览器行为验收（隔离测试数据库）：
1. Offer：查看用户主观判断 → 展开理由看到偏好和候选依据 → 补充通勤 → 原轮资料保持。
2. 购物/旅行 fixture：明确演示状态；mock 搜索数据展示链接/检索时间/未独立核实，不能冒充真实联网。
3. 无依据候选、失效引用、未知时间、危险 URL/HTML、长文本；桌面/移动、键盘展开、刷新恢复，无横向溢出和脚本错误。
4. Diet 原有推荐及关键条件编辑回归。

真实模型/Search 仅在已有授权配置可用时另行验收；不可用则明确未验证，mock 不算真实服务结果。

## 与并行方案的交界

收尾时已发现并读取同日三个 Plan：
- candidate-search-productization：搜索入口、能力查询、流式进度属于该方案；本次 Evidence helper 提供逐条来源/核验文案，避免两处独立翻译 verified。搜索默认值与进度协议不在本次修改范围。
- decision-canvas-what-if：如该方案先落地，依据组件接入其 currentAnalysis/whatIfAnalysis、keyReasons 和代价区域，并各持有自己的证据快照；不另建竞争的 Canvas 布局。不在本次实现其通勤筛选、What-if 建议或布局比例。
- decision-trace-observability：本次稳定 Evidence ID 与 supporting_evidence_ids 可被其时间轴引用；旧临时 catalog 兼容保留，不新增 Trace collector 或事件接口。

实施前重新检查工作区和已批准方案状态。共享文件按实际最终代码集成，保留其他任务改动；若并行方案改变本次契约或核心行为，需要更新本 Plan 后审查，不能仅以文件冲突为由回退其他任务。
## Todo

- [ ] 建立现有测试基线与来源/双候选引用回归样例。
- [ ] 完成兼容 Evidence 元数据与服务端来源信任边界，验证旧状态读取。
- [ ] 贯通用户/演示/搜索/条件 Evidence，验证创建、编辑、rerank、刷新的一致性。
- [ ] 完成规则/模型多依据引用、tradeoffDetails 与缺依据降级，验证数字和排除约束。
- [ ] 完成 Canvas、候选及历史依据展开，验证时间、链接、移动端和键盘行为。
- [ ] 验证假设/快照/幂等/409/饮食兼容，执行全量检查。
- [ ] 更新 CHANGELOG、迁移矩阵及本 Plan 验证记录，检查最终 diff。
