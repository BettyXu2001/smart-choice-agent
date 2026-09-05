# Evidence 产品展示与推荐追溯 Research

日期：2026-09-05
状态：代码研究完成；未修改产品代码。
规模：大改动，涉及共享 Evidence 契约、解释数据流和关键展示行为。

## 需求与范围

让用户区分自己提供的信息、外部资料、系统推断、仍不确定的信息；当前决策侧栏（Decision Canvas）的重要推荐理由与取舍能够追溯原始依据。本次完善已有搜索数据的承接，不新增搜索服务、不启用真实联网搜索、不进行部署。以购物、旅行和 Generic（含 Offer、学习）为展示范围；共享类型和校验器对 Diet 保持兼容。

## ADR 检索与归档决定

正式代码研究前已按 Evidence、引用、数值、Canvas、排除及模块路径检索 adr/，相关记录：
- 2026-09-04-generic-decision-external-benchmark-research.md：提出来源、陈述、结论之间的追溯关系；其旧实现描述不能代替当前代码。
- 2026-09-04-generic-decision-evidence-workbench-plan.md：已实现共享模型、来源白名单；明确仍缺完整 EvidenceValidator 策略。旧方案剩余项不自动纳入本次。
- 2026-09-04-conversation-decision-assistance-research.md / plan.md：当前解释引用、原文更新、数值拒绝及历史快照基础；Plan 记录上一轮已完成。
- 2026-09-04-general-conversation-panel-research.md / plan.md：当前对话主导、右侧当前决策、详细比较展开区。

本次新建成对文档，避免把新的产品契约追加到已完成记录，也不恢复旧工作台主导方向。

## 核心文件与已核实行为

| 文件（src/choice_agent/ 下） | 职责及现状 |
| --- | --- |
| schemas.py | Evidence 有 ID、candidate/criterion、claim、来源、时间、confidence、verificationStatus；无逐条来源类别、陈述类别或独立事实核验语义。RecommendationPoint 支持 evidenceIds；tradeoffDetails 已存在。 |
| providers/search.py | 已有 OpenAIWebSearchProvider，通过工具 sources/annotations 收集 URL 并解析候选；并非完全未接入 Search。来源标题被用作 publisher；时间可来自模型；不执行陈述级核实。 |
| providers/candidates.py | fixture/database 的 Evidence 直接设 verified；ManualCandidateProvider 读取手工候选，通常没有 Evidence。 |
| decision/evidence.py | 按内容派生 ID，补 candidate/criterion/claim。HTTP(S) URL 在工具来源白名单即 verified；未命中则 rejected。并非内容真实性验证。 |
| decision/ranking.py | web 数值必须有同 key、同 value 且 verified 的 Evidence 才评分；fixture/manual 数值可直接评分。硬约束与排除另行执行。 |
| decision/commands.py | 手工候选强制 origin=manual、清零评分、证据降为 unverified；add/update 返回 rank，可能不经过 source_and_rank。 |
| agents/conversation.py、decision/conversation.py | 对话候选经 apply_command 录入；条件记录 source/confirmed/updatedRevision。confirmed 表达用户确认，与外部事实真伪无关。 |
| decision/assistance.py | 候选补充保存在 assistance.facts；catalog 临时生成 candidate:* 与 fact:* 引用。模型引用检查 candidateId、quote、允许推荐集合；解释数值只对全目录数字集合检查。 |
| domains/comparison.py | source_and_rank 写 decision.evidence、candidatePool 后排序；rerank 只复用候选池；explain 共用 assistance。 |
| orchestration/generic.py | 创建/消息/命令进入统一阶段，revision 更新后保存；conversationTurns 保存 analysis 与 displayBlocks，receipts 保存响应快照。 |
| repositories/decision_repository.py | DecisionState 通过 Pydantic 读取 state_json，CAS 保存；无需新表即可保存增量字段。 |
| static/assets/js/conversation.js | 当前 Canvas 在 renderGeneralPanel；理由只显示文本及粗略来源，demoMode 会覆盖逐条来源判断；历史读取保留候选卡，但没有把 turn.analysis 交给消息展示。 |
| static/assets/js/app.js | 详细比较显示 verificationStatus 原始英文及来源标题，不显示完整陈述/检索时间；理由没有追溯交互。 |
| domains/diet/profile.py、evaluator.py | 共用 EvidenceValidator，饮食贡献项依赖旧 verified；必须回归，不能改枚举就破坏引用。 |

## 调用链与数据流

1. create/message → GenericDecisionOrchestrator → UnifiedDecisionOrchestrator → interpret → 字段/手工候选/assistance.facts。
2. ComparisonProfile.source_and_rank → provider + manual merge → EvidenceValidator → decision.evidence + candidatePool → GenericRankingEngine。
3. 命令 rank → rerank（不重新检索）→ explain；因此证据规范化不能只放搜索路径。
4. assistance.explain → rule_analysis + catalog → 可选模型 → 引用/推荐/数字校验 → analysis.sources 与 recommendation。
5. _persist → 当前 DecisionState、conversationTurns、幂等 receipts → public_decision → 当前侧栏和历史消息。

## 关键缺口与风险

- 两套引用目录不一致：recommendation.reasons.evidenceIds 实际放 candidate:* / fact:*，通常不存在于 decision.evidence。web 数值目录还丢失真实来源 URL。
- 单条比较理由可能包含 A/B 两个数值，但 point 只引用 A；规则取舍也可能用 summary 引用支撑多个属性或补充事实。
- 用户偏好参与推断但没有进入理由引用链；用户主观评分也可能仅作为裸属性展示。
- verified 当前混合工具 URL 校验、fixture、数据库来源，不能直接展示为“事实已验证”。
- demoMode 是会话级；Demo 后用户补充仍应为用户输入。旧记录未保留足够来源时不能凭空重建原文或时间。
- facts.confirmed=True 只证明用户说过；“稳定、成长”不能因此成为客观事实；系统解释是基于资料的推断。
- 数字全目录检查允许模型借用其他候选或其他维度的数字；本次只收紧引用范围，不能宣称解决自然语言蕴含与所有数值语义问题。
- 字段默认 retrieved_at 会使旧数据看似刚检索；“今天”必须区分检索时间和网页更新时间。
- 来源刷新、手工说明修改会让原引用过时；历史理由必须使用当轮快照，不能指向当前资料。
- 模型或手工 API 上传的验证元数据不能自动产生可信“已验证”标签。
- URL 白名单、内容值一致、事实正确是不同检查；当前没有官方来源识别器或陈述核实服务。

## 可复用能力与约束

复用 Evidence、RecommendationPoint、tradeoffDetails、现有来源白名单与排序器、领域流程、条件来源、原文 facts、state_json、历史快照、共享侧栏、escapeHtml。保留 API 路径、请求幂等、所有权校验、预算筛选、排除候选和假设副本行为。不新增依赖、数据库表、独立 Agent 或搜索服务。

现有 tests/test_unified_decision.py 覆盖 URL 拒绝、工具来源解析与 web 缺依据不评分；test_decision_assistance.py 覆盖多轮取舍、引用错误、无依据数字、模型超时、假设与排除；另有 generic API、general conversation、Diet 回归。工程为 Python/FastAPI + 原生 JS；pyproject 配置 pytest，无独立前端构建或 typecheck/lint 脚本。

## Plan 需决策事项

- 如何保留旧 verificationStatus 的内部兼容，同时给用户独立准确的核验语义。
- 如何把用户说明、补充、偏好与真实 Evidence 合为可解析引用，并支持多依据理由。
- 如何处理旧记录来源不明、时间缺失、失效引用与历史快照。
- 如何用渐进展开呈现原始资料，避免侧栏堆满所有来源。
- 哪些边界能由本地校验保证，哪些必须诚实标为未核实。

## 本轮验证与环境

初始 git status --short 为空。默认终端沙箱仍报 setup refresh had errors；经工具审核使用沙箱外只读命令后完成研究。研究阶段未运行产品测试、未调用真实模型/搜索、未修改产品代码。旧 Plan 的测试结果仅作历史背景，不作为本次验证结果。

## 收尾时发现的并行 ADR

初次检索后，工作区新增了同日 candidate-search-productization、decision-canvas-what-if、decision-trace-observability 等 Research/Plan。已读取上述三个 Plan 中的相关设计；它们是并行方案，不能当成当前已实现代码。

Search 方案负责搜索开关、流式进度和来源模式；Canvas 方案新增 currentAnalysis/whatIfAnalysis 与固定展示区域；Trace 方案记录 Evidence 与推荐变化。三者与本次在 schemas、assistance、comparison、orchestration、前端文件存在交界。保持独立归档，只在本 Plan 明确组合方式，不覆盖其他任务文档。最终 Git 检查发现其他新增 ADR，本任务只创建 evidence-presentation 两份文档。