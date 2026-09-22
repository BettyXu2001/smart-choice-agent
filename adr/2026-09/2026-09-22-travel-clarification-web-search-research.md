# Travel Clarification and Web Search Research

## 当前需求和研究范围

修复 Travel 场景的两个问题：多轮澄清时短回答如“苏州，2天，轻松”应补全 `departure=苏州`、`days=2`、`priority=轻松`；正式 Travel 对话在 Web Search API 已配置并启用时，应默认走 Web Search，并允许失败后回退 fixture。

本次重点限定在 Travel 字段理解、Clarification 动态问题和候选数据源选择，不重写现有 Evidence Validation、Hard Filter、Ranking、Explanation 链路。

## ADR / 历史方案检索

已检索 `adr/`、`src/`、`tests/`、`docs/`、`CHANGELOG.md` 中的 `travel`、`conversationFields`、`clarif`、`searchMode`、`OpenAIWebSearchProvider`、`fixture`、`Candidate Retrieval`、`fallback` 等关键词。

相关记录：

- `adr/2026-09/2026-09-05-candidate-search-productization-research.md` / `plan.md`：高度相关。定义 Shopping/Travel 的 `fixture`、`web`、`auto` 语义；Demo 显式 fixture；`auto` 在 Web Search 可用时联网，失败回退 fixture 并暴露来源。
- `adr/2026-09/2026-09-20-reliability-regression-cases-research.md` / `plan.md`：相关。记录 Search transport error 应通过 `auto -> fixture` 成功返回，并在 Trace 中记录 failed search、fallback 和实际 source mode。
- `adr/2026-09/2026-09-05-decision-trace-observability-research.md` / `plan.md`：相关。定义 Trace timeline、AgentRun、fallback 观测方式。
- `adr/2026-09/2026-09-22-diet-hybrid-db-web-recall-research.md` / `plan.md`：相邻但不同领域。Diet 混合召回借鉴 ComparisonProfile 的 `_search()`，本次不复用 Diet 新增逻辑。

判断：当前需求主题与既有 Candidate Search 方案相关，但改动边界是 Travel 多轮澄清和正式入口默认数据源，追加到旧 ADR 会混淆已完成历史结论，因此新建本 Research 和 Plan。

## 核心文件及职责

- `src/choice_agent/domains/travel.py`：定义 `TravelProfile`、Travel criteria、fixture 候选、固定 `clarification_question`、`needs_clarification()` 和 Travel 约束。当前 `needs_clarification()` 只检查 `conversationFields.departure` 和 `conversationFields.days`。
- `src/choice_agent/domains/comparison.py`：通用比较领域流程。`clarify()` 当前在缺字段时使用 `blocking_question or self.clarification_question`，导致 Travel 固定问完整问题。`_search()` 已支持 `web` 强制联网、`auto` 联网失败回退 fixture、其他 fixture。
- `src/choice_agent/decision/assistance.py`：`prepare_turn()` 在每轮正式理解前执行规则更新；目前只为 Generic 处理短回答和上下文问题。`model_context()` 已把 `previous_question`、已有 `fields`、recent messages 传给模型理解。
- `src/choice_agent/decision/conversation.py`：定义 Travel 字段 `departure / days / budget / maxTransitHours / priority`，并由 `patch_fields()` 校验写入、`sync_dependencies()` 同步约束和权重。
- `src/choice_agent/orchestration/generic.py`：初始化 `OpenAIWebSearchProvider` 并注入 `TravelProfile(web_provider)`；`_safe_context(defaults=True)` 使用 `settings.search_provider` 填充缺省 `searchMode`。
- `src/choice_agent/api/routes.py`：runtime header 中 `searchEnabled + searchApiKey` 会把 `runtime_settings.search_provider` 设置为 `openai`；capabilities 返回 `webSearchConfigured` 与 `defaultSearchMode`。
- `src/choice_agent/static/assets/js/app.js`：`submitGeneralDecision()` 当前根据 `realTimeSearch` checkbox 传 `searchMode: realtime ? "web" : "fixture"`，会覆盖后端 runtime default。
- `src/choice_agent/static/assets/js/conversation.js`：`startGeneral()` 只有在 `options.searchMode` 存在时才写入 context；不传时后端可使用默认搜索模式。

## 关键调用链和数据流

正式 Travel 创建：前端 `submitGeneralDecision()` 调用 `conversation.startGeneral()`，后端 `GenericDecisionOrchestrator.create()` 通过 `_safe_context(defaults=True)` 写入默认 `searchMode`，随后 StageRunner 依次运行 Intent、Understanding、Clarification、Candidate Retrieval、Evidence、Hard Filter、Ranking、Explanation。

多轮 Travel 短回答：第一轮缺 `departure` 和 `days` 时进入 clarifying；`ComparisonProfile.clarify()` 写入 `assistance.lastQuestion`。第二轮“苏州，2天，轻松”进入 `prepare_turn()`，但当前没有 Travel 分支；模型未启用或模型返回未通过校验时 `departure` 不会被规则写入，`needs_clarification()` 再次看到缺字段，导致重复询问。

## 当前实现逻辑

- Travel 必填目前实际是 `departure + days`；`priority` 不应阻塞推荐。
- `departure` 主要依赖模型理解或含“出发/从”的显式语义，规则层没有把短文本城市名映射到上一轮所问字段。
- 澄清问题是类属性固定字符串，不根据缺失字段动态生成。
- `auto` 搜索回退已存在，Trace 中已有 fallback 节点和 CandidateAgent 的 `fallbackUsed`。
- 前端正式入口显式传 `fixture` 是导致“Search API 已启用但正式 Travel 仍可能用 fixture”的主要原因之一。

## 已有可复用能力

- `patch_fields()` 可安全写入 Travel 字段并同步约束/权重。
- `fields()` 可初始化和读取 `conversationFields`。
- `assistance.state(decision).lastQuestion` 已保存上一轮澄清问题。
- `OpenAIWebSearchProvider.enabled`、`ComparisonProfile._search(auto)` 和 Trace fallback 已可复用。
- 现有测试已有 Search auto fallback 和 Trace fallback 基础覆盖，可新增 Travel-specific Case 而不重写 provider。

## 潜在问题和隐患

- 不能把任意短中文都当 `departure`，否则“轻松”“人少”等偏好可能被误写成出发地。
- 如果只依赖模型理解，未启用 LLM 或模型解析失败时仍会重复澄清；因此需要规则层覆盖验收 Case。
- `explicit_patch()` 对模型显式纠正要求 quote 包含字段别名，短回答“苏州”不包含“出发/从”，不适合直接依赖该路径。
- 如果前端继续传 `fixture`，后端默认 `web/auto` 无法生效。
- 如果把后端全局默认改成 `auto`，可能影响测试、评测和非 UI 客户端；需限定在 runtime Search 已启用或前端正式入口不覆盖默认。
- 工作区已有用户改动，尤其 `CHANGELOG.md`、Diet、Trace、前端部分文件；实施时需只触及必要片段并保留已有改动。

## 约束

- 不重写 Travel Ranking 和 Evidence Validation 链路。
- Demo 入口继续显式 `searchMode="fixture"`、`demoMode=true`。
- 测试/评测可继续显式 fixture。
- Web Search 失败时使用 `auto` 语义 fallback；显式 `web` 仍可作为“失败即报错”的严格模式。
- `priority` 不作为 Travel 必填字段。

## Plan 阶段待决策

- 动态澄清问题放在 `TravelProfile` 专属方法，还是在 `ComparisonProfile` 加可覆写 hook。
- 正式 Travel 默认联网使用 `web` 还是 `auto`。基于用户目标 4，正式 Travel 更适合使用 `auto`，以便失败降级 fixture 且 Trace 可见。
- 前端正式入口是否完全不传 `searchMode`，还是当 capability configured 时传 `auto`。为了满足“失败降级”，计划让正式支持搜索领域在 Search configured 时传 `auto`，Demo 仍 fixture。