# Diet DB + Web Search Hybrid Recall Research

Date: 2026-09-22

## Scope

用户希望将 Diet 候选召回从单一数据库检索升级为 DB + Web Search 混合召回：默认优先使用个人/公共餐食库；候选不足或“换一批”没有足够新候选时自动调用现有 Web Search Provider；附近餐厅、外卖、实时信息类需求优先联网；联网结果标准化到 Diet 七字段后继续复用 Evidence Validation、Hard Filter 和 Ranking；Web Search 失败时降级数据库；只有所有候选源均无结果时才展示空结果。

这是大改动，因为它改变 Diet 核心候选召回策略、候选数据结构、联网失败语义、反馈“换一批”路径、展示块生成和测试边界。按项目流程，本阶段只做 Research / Plan，不修改产品代码。

## ADR Lookup

已检索 `adr/`、`src/choice_agent/`、`tests/`、`docs/` 和 `CHANGELOG.md` 中与 Diet、Candidate Search、Web Search、Evidence、Ranking、Hard Filter 和 Selection 相关的记录。

相关记录：

- `adr/2026-09/2026-09-05-candidate-search-productization-research.md` / `plan.md`：高度相关。记录了现有 Web Search Provider、SearchRun、Evidence Validation、Ranking、进度和 Search Capability 的产品化边界。但该方案主要覆盖 Shopping/Travel 等 ComparisonProfile 领域，不改 Diet。
- `adr/2026-09/2026-09-02-generic-decision-from-diet-foundation-research.md` / `plan.md`：高度相关。记录 Diet 被抽成通用 StageRunner/DomainProfile 的基础，约束不能破坏 `/api/v1/diet/*` 兼容链路。
- `adr/2026-08/2026-08-29-diet-agent-python-migration-research.md` / `plan.md`：相关。记录 Diet 原始多 Agent 闭环、餐食库、Trace 和评估迁移，是当前 Diet 兼容行为的来源。
- `docs/migration-matrix.md`：相关。说明 `MealSearch/MealRank` 已迁到 `DietMealProvider + GenericRankingEngine + DietCriterionEvaluator`，Evidence 展示已接入但事实核验仍有限。

判断：本需求应新建 Research / Plan。旧候选搜索产品化 ADR 已完成且主题是通用候选搜索；追加会混淆 Diet 专属召回策略和已完成历史。

## Core Files And Responsibilities

- `src/choice_agent/domains/diet/profile.py`：Diet 主领域 Profile。`source_and_rank()` 当前只调用 `DietMealProvider(self.repository)`，再执行 `EvidenceValidator`、`GenericRankingEngine`、`select_candidates`。`rerank()` 当前只复用 `domain_state["candidatePool"]`，并重新从 DB 读取 `MealRecord`，强依赖候选 ID 能在 DB 中找到。
- `src/choice_agent/providers/candidates.py`：`DietMealProvider` 将个人/公共餐食库的 `MealRecord` 转成通用 `Candidate` 和 database Evidence。`CompositeCandidateProvider.merge()` 可合并多个 `CandidateSearchResult`，但当前只按 `candidate_id` 去重，不处理来源优先级、web ID 命名或 Diet 字段标准化。
- `src/choice_agent/providers/search.py`：`OpenAIWebSearchProvider` 已实现 OpenAI Responses + `web_search` 工具调用、结构化候选解析、SourceDocument/Evidence/SearchRun 输出、两次重试和 Trace provider call。当前 `SEARCH_INSTRUCTION` 是通用候选搜索提示，不要求 Diet 七字段，也不要求附近/外卖类语义。
- `src/choice_agent/decision/evidence.py`：`EvidenceValidator.validate()` 校验 web evidence 的 URL 必须来自工具返回 source。对 web evidence，URL matched 后会标记 `verification_status=verified`、`citation_status=matched`、`claim_status=unverified`，即“来源链接校验通过，内容未独立核实”。
- `src/choice_agent/decision/ranking.py`：`GenericRankingEngine.rank()` 已统一处理用户排除、硬约束、缺失数据、评分和 diagnostics。这正是新 web Diet 候选应该复用的 Hard Filter + Ranking 路径。
- `src/choice_agent/domains/diet/evaluator.py`：`DietCriterionEvaluator` 读取 `DecisionState.domain_state["slots"]`，按七个 Diet criterion 与候选 `attributes` 的列表值交集评分。这要求 web 候选的 `attributes` 必须标准化为七字段列表，否则得分会为 0 或缺失。
- `src/choice_agent/agents/diet.py`：`CriticAgent`、`ExplanationAgent` 和 `_meal_response()` 当前强依赖 `context.data["ranked"]` 中的 `RankedMeal`，而 `RankedMeal` 又强依赖 `MealRecord` 和整数 meal id。Web 候选不是 DB `MealRecord`，因此不能只改 provider；必须补 Diet 候选展示/解释适配。
- `src/choice_agent/domains/diet/composition.py`：三餐计划 `DietMealPlanCompositionStrategy` 当前仍只使用 `DietMealProvider` 和 DB `MealRecord`。本需求没有明确要求三餐计划联网；默认应先限定单餐推荐/换一批，避免扩大范围。
- `src/choice_agent/orchestration/diet.py`：Diet 兼容 API 编排。`_context()` 传入 `source_mode`、slots、slot_options、recent recommendation ids、selection strategy、avoid recent count。`feedback(DISLIKE)` 当前执行 rerank，不刷新候选池；当没有 DB 替代候选时直接展示空结果。
- `src/choice_agent/orchestration/generic.py`：通用 Orchestrator 已创建 `OpenAIWebSearchProvider` 并注入 Travel/Shopping/GenericProfile。DietProfile 目前只接收 repository/settings/model provider，没有 web provider。
- `src/choice_agent/domains/comparison.py`：非 Diet ComparisonProfile 已有 `_search()`：`web` 强制联网，`auto` 有 web provider 时尝试联网，失败回退 fixture。可作为 Diet 混合召回的模式参考，但 Diet 需要 DB 优先、候选不足 fallback、换一批 fallback、附近/实时优先联网，规则不同。
- `src/choice_agent/api/routes.py`：`/api/v1/search/capabilities` 当前 `supportedDomains` 只包含 `shopping`、`travel`。Diet API 捕获 `SearchProviderError` 会返回 502；新需求要求 Web Search 失败时降级 DB，因此 Diet 内部不应让 fallback 后的 SearchProviderError 泄漏到 API。

## Current Diet Candidate Flow

单餐推荐主路径：`DietOrchestrator.chat -> UnifiedDecisionOrchestrator.run -> StageRunner.run -> DietProfile.intent / understand / clarify -> DietProfile.source_and_rank -> DietMealProvider.search -> EvidenceValidator.validate -> GenericRankingEngine.rank(DietCriterionEvaluator) -> score > 0 filtering -> select_candidates -> RankedMeal -> CriticAgent -> ExplanationAgent -> MealResponse`。

“换一批”路径：`IntentAgent` 在有历史时将“换一个/换一批”等识别为 `MEAL_ADJUST`，`AdjustmentAgent` 将最近推荐加入 `exclude_ids` / `excluded_candidates`，随后正常 `source_and_rank()` 会刷新 DB 候选。

反馈“不合适”路径：`DietOrchestrator.feedback(DISLIKE)` 将选中项加入 `decision.excluded_candidates`，再调用 `recompute(refresh_candidates=False)`，进入 `DietProfile.rerank()` 复用旧 candidatePool。该路径不刷新候选池，所以当前如果 DB pool 没有可替代项，会空结果。

## Existing Reusable Capabilities

- `OpenAIWebSearchProvider` 已能返回通用 `CandidateSearchResult`、`SourceDocument`、`Evidence` 和 `SearchRun`。
- `EvidenceValidator` 已能阻止 web evidence 使用非工具返回 URL，并清楚标注“来源已校验，内容未独立核实”。
- `GenericRankingEngine` 已统一 Hard Filter、缺失值、用户排除、候选状态和 diagnostics。
- `DietCriterionEvaluator` 可直接对标准化后的 Diet 七字段评分。
- `select_candidates()` 已支持 ranked/random/weighted/least_recent 和 `avoidRecentCount`。
- `context.trace.fallback()` 在 ComparisonProfile 中已有使用范式，可用于记录 web fallback 到 DB。

## Key Gaps

1. DietProfile 没有 Web Search Provider 依赖。
2. Web Search 通用提示不保证 Diet 七字段标准化。
3. Diet `source_and_rank()` 只返回 DB 候选，缺少“DB 不足 -> web 补充”策略。
4. Diet `rerank()` 无法在候选池不足或已排除后刷新 web 候选。
5. Diet Critic/Explanation/MealResponse 只认 `RankedMeal/MealRecord`，web 候选会卡在展示层。
6. `FeedbackRequest.item_id` 和 `MealResponse.id` 都是 `int`，如果 web 候选用非数字 id，将无法参与旧 Diet feedback display block。
7. `/api/v1/search/capabilities` 没有声明 Diet 支持 web search。
8. Web Search 失败目前可能冒泡成 502；需求要求 Diet fallback 到 DB，除非所有源都没有候选。

## Constraints

- 不能破坏现有 `/api/v1/diet/*` 响应形状，尤其 `ChatResponse.display_blocks: list[MealResponse]`。
- Diet 个人/公共餐食库仍应是默认优先来源。
- Web Search 结果只能在 Evidence Validation 之后参与 Ranking。
- Web evidence 的“verified”仍只代表 URL/source matched，不代表事实独立核实。
- 不应把三餐计划联网纳入第一版，除非用户明确要求扩大范围。
- 当前工作区已有其他未提交改动：`CHANGELOG.md`、Diet prompt、前端 CSS/JS、Trace ADR 等。实施时必须避开无关改动并只做本 Plan 范围。

## Open Questions For Plan

- 候选不足的阈值应是多少？建议以最终 ranked positive 候选少于 3 个为默认，因为 ExplanationAgent 最多展示 3 个。
- Web candidate 的 display block 需要 `int id`。应使用稳定负整数/映射，还是修改 schema 支持 string？为了兼容，建议使用稳定负整数并在 `candidate_id` 保留 `web:...`。
- “附近餐厅/外卖/实时信息”优先联网的判定应在规则层还是 Profile 层？建议 Profile 层基于 message + scene/convenience 关键词判断，不改 Intent enum。
- Web fallback 后是否混合 DB + Web，还是附近/实时完全 web first？建议实时类先 web，web 失败再 DB；非实时类 DB first，不足才 web 补充。