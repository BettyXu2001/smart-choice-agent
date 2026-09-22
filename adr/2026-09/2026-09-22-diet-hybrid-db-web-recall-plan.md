# Diet DB + Web Search Hybrid Recall Plan

Date: 2026-09-22

## Goal

将 Diet 单餐推荐候选召回升级为 DB + Web Search 混合召回，同时保持现有 Diet API、Evidence Validation、Hard Filter、Ranking、反馈和展示体验可用。

## Success Criteria

- 默认优先使用当前 `sourceMode` 对应的个人/公共餐食库。
- 当 DB 排序后有效候选少于 3 个，自动调用现有 Web Search Provider 补充候选。
- 当“换一批”或反馈“不合适”导致无足够新候选时，自动调用 Web Search Provider 补充候选。
- 包含附近餐厅、外卖、营业/排队/距离/实时价格等实时信息意图时，优先联网；Web 失败时回退 DB。
- Web Search 结果进入 Ranking 前已标准化到 Diet 七字段：`meal_time`、`mood`、`scene`、`health_goal`、`cuisine`、`taste`、`convenience`。
- Web 候选通过现有 `EvidenceValidator` 后，再复用 `GenericRankingEngine + DietCriterionEvaluator` 执行 Hard Filter 和 Ranking。
- Web Search 失败不会让 Diet API 返回 502；保留 DB 候选并在 `domain_state["source"]["warnings"]` / Trace fallback 中记录降级。
- 只有 DB 和 Web 两类候选源均没有可展示候选时，才展示空结果。
- 现有 DB-only Diet 测试继续通过，并新增混合召回测试覆盖 fallback、实时优先、换一批补充和 evidence/ranking 复用。

## Non-Goals

- 不把三餐计划 `MEAL_PLAN` 扩展为联网规划，第一版仍使用 DB 餐食库。
- 不改变 `ChatResponse.display_blocks` 和 `MealResponse.id` 的对外类型。
- 不实现独立事实核验、多源交叉验证、价格/库存 freshness 判断。
- 不新增新的搜索服务或依赖；复用 `OpenAIWebSearchProvider`。

## Design

### 1. Inject Web Provider Into DietProfile

在 `DietProfile.__init__` 增加可选 `web_provider: CandidateProvider | None`。

装配位置：

- `GenericDecisionOrchestrator.__init__` 已创建 `OpenAIWebSearchProvider`，把它传给 `DietProfile(...)`。
- `DietOrchestrator.__init__` 也创建同样配置的 `OpenAIWebSearchProvider`，传给 DietProfile。
- 保留 `web_provider=None` 兼容单元测试或未配置环境。

`OpenAIWebSearchProvider.enabled` 为 false 时，不尝试联网；记录 warning，但不抛给用户。

### 2. Diet Web Search Normalization

新增一个小型 Diet 专用候选 Provider/Adapter，建议放在 `src/choice_agent/domains/diet/web.py`：

- `DietWebCandidateProvider` 包装现有 `OpenAIWebSearchProvider`；
- 构造 Diet 专用 instruction；
- 调用 web provider；
- 将返回 candidates 标准化为 Diet 七字段。

标准化规则：

- 七字段全部保证存在且为 `list[str]`。
- 只保留非空字符串，并去重。
- 对未返回字段填空列表。
- 对 `attributes` 中 camelCase 兼容映射：`mealTime -> meal_time`、`healthGoal -> health_goal`。
- Web candidate id 统一为 `web:<raw-id>`，避免与 DB 数字 ID 冲突。
- Evidence 的 `key` / `criterion_key` 同步映射到 snake_case 七字段。
- `origin="web"`。

Search prompt 需要求返回 Diet 七字段，并提醒附近/外卖场景要给出餐厅/店铺/菜品候选及来源 URL。实现上优先扩展 `OpenAIWebSearchProvider` 支持可选 instruction override，或在 Diet adapter 中构造一个 Diet-specific provider 子类；不复制 HTTP/parse 大段逻辑。

### 3. Hybrid Recall Strategy

在 DietProfile 内部引入私有 helper：

- `_database_search(context) -> CandidateSearchResult`
- `_web_search(context, reason: str) -> CandidateSearchResult`
- `_merge_results(db_result, web_result) -> CandidateSearchResult`
- `_rank_candidates(context, result) -> DietRankResult`

默认阈值：

- `target_candidate_count = 3`
- 以 Evidence Validation + Hard Filter + Diet ranking + `score > 0` 后的正分候选数判断是否不足。

非实时类：

```text
DB search
  -> Evidence Validation
  -> Hard Filter + Ranking
  -> if positive ranked count >= 3: use DB only
  -> else try Web Search
       -> validate web evidence
       -> merge DB + Web
       -> re-run Hard Filter + Ranking over merged candidates
       -> if web fails: use DB result
```

实时类：

```text
try Web Search first
  -> if web returns candidates: optionally merge DB as fallback/supporting candidates
  -> if web fails or no candidates: DB search
```

实时触发关键词初版：

- `附近`、`周边`、`附近餐厅`、`外卖`、`配送`、`美团`、`饿了么`、`营业`、`开门`、`排队`、`距离`、`现在`、`实时`、`今天有什么店`

触发结果写入：

- `decision.domain_state["source"]["mode"]`: `database` / `web` / `hybrid`
- `decision.domain_state["source"]["realTime"]`: web 是否参与且实时优先
- `decision.domain_state["source"]["warnings"]`: web fallback、validation warnings
- `decision.domain_state["source"]["recallReason"]`: `db_sufficient` / `db_insufficient_web_supplement` / `realtime_web_first` / `web_failed_db_fallback`

Trace：

- Candidate Retrieval 节点输出每个源的候选数、最终 merged count、warnings。
- Web 失败时用 `trace.fallback()` 记录 `web_search -> diet_database`。
- Evidence、Hard Filter、Ranking 继续沿用现有节点，但说明候选源为 database/web/hybrid。

### 4. Ranked Candidate Display Adapter

新增 Diet 内部展示结构，避免所有逻辑继续强依赖 `RankedMeal`：

- `DietDisplayCandidate`
  - `candidate: Candidate`
  - `display_id: int`
  - `name: str`
  - `score: float`
  - `attributes: dict[str, list[str]]`
  - `source_type: SourceMode`
  - `reason_context: dict`

DB 候选：

- `display_id = int(candidate.candidate_id)`
- `source_type` 继续使用 DB `MealRecord.source_type`
- 可继续生成 `RankedMeal` 以降低旧逻辑改动。

Web 候选：

- `display_id` 使用稳定负整数，例如对 `candidate_id` hash 后映射到负数。
- `source_type` 为 `SourceMode.PUBLIC`，保持 `MealResponse` schema 兼容；真实来源通过 `Candidate.origin`、Evidence 和 `domain_state["source"]` 表达。
- `MealResponse` 的七字段来自 candidate attributes。

修改 `CriticAgent` 和 `ExplanationAgent`：

- 优先读取 `context.data["diet_display_candidates"]`。
- 若不存在，则兼容读取旧 `context.data["ranked"]`。
- Recommendation 的 `primary_candidate_id` 和 `alternative_candidate_ids` 使用真实 `Candidate.candidate_id`，不使用负数 display id。
- `display_blocks` 仍是 `MealResponse`，`id` 为 display id；同时 `decision.candidates` 保留真实 candidate id，供通用工作台和 evidence 使用。

反馈映射：

- 在 `decision.domain_state["displayCandidateMap"]` 保存 `{displayId: candidateId}`。
- `feedback()` 收到 `item_id` 后先映射到真实 candidate id，再写入 `excluded_candidates` 和 outcome。
- 旧 DB id 没有映射时保持原逻辑。

### 5. Rerank And "换一批" Fallback

`source_and_rank()` 用 hybrid strategy 处理正常 chat 和“换一批”刷新。

`rerank()` 改造：

- 先对现有 `candidatePool` 复用 Ranking。
- 如果排除 recent / disliked 后正分候选少于 1 或少于 target，且 web provider 可用，则触发 Web Search 补充。
- 补充后更新 `candidatePool`、`sources`、`search_runs`、`evidence`，再执行完整 ranking。
- Web 失败时保留 rerank 结果；只有 rerank 也无候选时展示空结果。

注意：反馈 DISLIKE 当前 `refresh_candidates=False`，所以这一步必须在 `rerank()` 内实现，否则“不合适后补充 web”不会发生。

### 6. API Capability

更新 `/api/v1/search/capabilities`：

- `supportedDomains` 增加 `diet`。
- `webSearchConfigured` 仍不泄露 key 和 provider 细节。
- 不改变现有字段结构。

### 7. Tests

新增/扩展测试：

- `tests/test_diet_hybrid_recall.py`
  - DB 候选足够时不调用 web provider。
  - DB 候选不足时调用 web provider，web 候选标准化七字段后参与 Ranking。
  - 附近/外卖/实时关键词优先调用 web provider。
  - Web Search 失败时返回 DB 候选，不抛 `SearchProviderError`。
  - DB 与 Web 均无有效候选时才空结果。
  - 反馈 DISLIKE / 换一批导致无新 DB 候选时触发 web 补充。
  - Web evidence 必须经 `EvidenceValidator` 后才贡献 scoring evidence。
  - `displayCandidateMap` 能把负数 display id 映射回真实 web candidate id。

回归测试：

- `tests/test_diet_panel.py`
- `tests/test_unified_decision.py`
- `tests/test_candidate_search_productization.py`

### 8. Documentation And Changelog

- `CHANGELOG.md`：记录 Diet 混合召回能力。
- 如实现新增环境或能力说明，更新 `docs/deploy.md` / `.env.example` 中 Diet 也支持 Web Search；若只是复用现有 search env，可简短补充。

## Affected Files

- `src/choice_agent/domains/diet/profile.py`：注入 web provider；添加 hybrid recall/rank helper；改造 `source_and_rank()` 和 `rerank()`；写入 source metadata / displayCandidateMap。
- `src/choice_agent/domains/diet/web.py`：新增 Diet web candidate adapter 和七字段标准化。
- `src/choice_agent/providers/search.py`：允许可选 instruction override 或 domain-specific instruction，尽量小改。
- `src/choice_agent/orchestration/diet.py`：创建并传入 `OpenAIWebSearchProvider`；feedback item id 映射到 candidate id。
- `src/choice_agent/orchestration/generic.py`：给 DietProfile 传入现有 web provider。
- `src/choice_agent/agents/diet.py`：Critic/Explanation 兼容 `DietDisplayCandidate`；保留旧 `RankedMeal` 路径。
- `src/choice_agent/api/routes.py`：search capabilities 增加 diet。
- `tests/test_diet_hybrid_recall.py`：新增混合召回测试。
- `tests/test_diet_panel.py`：必要时扩展反馈/换一批回归。
- `CHANGELOG.md`：记录用户可见变化。

## Compatibility

- 保持 `/api/v1/diet/chat`、`/api/v1/diet/feedback`、`ChatResponse`、`MealResponse` 形状不变。
- DB meal id 仍然以正整数展示。
- Web display id 使用负整数，仅作为旧 Diet 反馈 API 的展示层兼容 id。
- `DecisionState.candidates` 使用真实 `candidate_id`，web 候选不伪装成 DB meal id。
- Web Search 未配置或失败不会破坏 DB-only 使用。

## Risks

- Web candidate id 与 `MealResponse.id:int` 不匹配。通过 `displayCandidateMap` 和负整数 display id 缓解。
- ExplanationAgent 过去假设 `meal.id` 可转 int。通过 display adapter 解耦。
- Web Search 结果字段质量不稳定。通过 Diet prompt + adapter 标准化 + EvidenceValidator + ranking 正分过滤降低风险。
- 实时类 web first 可能返回餐厅而非菜品。允许 name 表达店铺/菜品组合，七字段用于 ranking，source/evidence 呈现真实来源。
- 反馈 DISLIKE 映射错误会排除失败。新增测试覆盖 display id 到 candidate id 映射。

## Verification Plan

运行：

- `python -m compileall -q src`
- `python -m pytest tests/test_diet_hybrid_recall.py`
- `python -m pytest tests/test_diet_panel.py tests/test_unified_decision.py tests/test_candidate_search_productization.py`
- `git diff --check`

若环境允许，再运行：

- `python -m pytest`

行为验证：

- 本地无 Web Search key 时，Diet 仍可 DB 推荐。
- Mock web provider 成功时，候选进入 Evidence -> Hard Filter -> Ranking。
- Mock web provider 失败时，API 返回 DB 推荐而非 502。
- 反馈“不合适”后如果 DB 无替代候选，mock web 候选可补充显示。

## Todo

- [x] 给 DietProfile / DietOrchestrator / GenericDecisionOrchestrator 接入可选 Web Search Provider。
- [x] 新增 Diet Web Candidate Adapter，标准化 web candidates 到 Diet 七字段和 evidence keys。
- [x] 实现 DB first、candidate-insufficient web supplement、realtime web first 和 web-failure DB fallback 策略。
- [x] 引入 Diet display candidate adapter，兼容 DB `RankedMeal` 与 web `Candidate` 展示。
- [x] 改造 CriticAgent / ExplanationAgent 支持 display adapter，保留旧路径。
- [x] 改造 feedback/rerank，让 `item_id` 可映射到真实 candidate id，并在新候选不足时联网补充。
- [x] 更新 search capabilities 支持 Diet。
- [x] 补充混合召回、实时优先、失败降级、换一批补充、evidence/ranking 复用测试。
- [x] 更新 CHANGELOG，并按需补充部署文档。
- [x] 执行 diff、compileall、相关 pytest 和可行的全量验证。