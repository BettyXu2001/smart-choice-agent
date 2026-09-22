# Travel Clarification and Web Search Plan

## 目标和成功标准

修复 Travel 场景多轮澄清和正式联网默认行为。

成功标准：

- 第一轮“周末想出去走走，但不想太累，应该去哪里？”只询问当前缺失的必要字段，可问“你从哪里出发？计划玩几天？”。
- 第二轮“苏州，2天，轻松”后，`conversationFields` 至少包含 `departure=苏州`、`days=2`、`priority=轻松`，不再重复询问出发地和天数。
- `departure + days` 齐全后直接进入 Candidate Retrieval；`priority` 不阻塞推荐。
- 正式 Travel 在 Search API 已配置并启用时使用 `auto`：优先 `OpenAIWebSearchProvider`，失败后回退 fixture。
- Web Search 失败 fallback 后，Trace 能观察到失败原因、fallback 行为和最终 `source.mode=fixture`。
- Demo、测试、评测仍可显式 fixture。

## 架构和逻辑设计

### 1. Travel 规则层短回答补全

在 `src/choice_agent/decision/assistance.py` 的 `prepare_turn()` 中新增 Travel 专属规则：

- 读取 `previous_question` 和当前 `conversationFields`。
- 只在 `d.domain == "travel"` 且本轮不是 hypothetical 时执行。
- 从本轮文本提取：
  - `days`：支持 `2天`、`两天`、`两天一夜`、`计划玩 2 天` 等；
  - `priority`：识别 `轻松`、`放松`、`人少`、`安静`、`自然`、`风景`、`省钱`、`预算`、`交通近` 等现有 Travel criteria 相关词；
  - `departure`：优先显式 `从X出发` / `X出发`；其次在上一轮问题包含“出发/哪里/几天/计划玩”且 `departure` 缺失时，从逗号、顿号、空格拆分的短片段中选择不像天数/预算/偏好的地点片段。
- 对验收 Case，“苏州，2天，轻松”应拆为 `苏州 -> departure`、`2天 -> days=2`、`轻松 -> priority`。
- 使用 `patch_fields(d, patch, source="conversation")` 写入，确保字段 confirmed 并同步权重/约束。

边界：不维护庞大城市词库，只做保守短片段识别；含数字、预算、小时、天数或偏好词的片段不作为 departure。

### 2. Travel 动态澄清问题

在 `ComparisonProfile` 增加一个可覆写方法，例如 `clarification_prompt(context)`，默认返回 `self.clarification_question`。`ComparisonProfile.clarify()` 改为使用 `blocking_question or self.clarification_prompt(context)`。

在 `TravelProfile` 覆写：

- 缺 `departure + days`：`你从哪里出发？计划玩几天？`
- 只缺 `departure`：`你从哪里出发？`
- 只缺 `days`：`计划玩几天？`
- 都不缺：返回通用 fallback，但正常不会被调用。

不询问 `priority`，因为它不阻塞 Travel 推荐。

### 3. 正式 Travel 默认使用 auto 搜索

调整 `src/choice_agent/static/assets/js/app.js` 的 `submitGeneralDecision()`：

- Demo 或预设 demo 入口继续显式 `context:{searchMode:"fixture", demoMode:true}`。
- 正式通用决策提交时，如果 `state.home.searchCapabilities.webSearchConfigured` 为 true 且目标领域支持 search，则传 `searchMode: "auto"`，让后端优先 Web Search 且失败回退 fixture。
- 如果未配置 Search API，则不传 `searchMode` 或保持 fixture。为减少行为变化，未配置时可继续传 fixture。
- 不再让未勾选 `realTimeSearch` 把已启用 Web Search 的正式 Travel 强制为 fixture。

### 4. 后端默认兜底

`GenericDecisionOrchestrator._safe_context()` 保留现有 settings default 语义，不把全局 fixture 强改为 auto，以免影响非 UI 客户端和测试。

### 5. Trace 和 fallback

复用 `ComparisonProfile._search(auto)`：Web Search provider enabled 时先调用 `self.web_provider.search(context)`；捕获 `RuntimeError` 后调用 fixture provider；写入 warning 和 `context.trace.fallback(...)`；Candidate Retrieval 输出 `runMode` 和 warnings；`domain_state.source.mode` 使用 fallback 后的实际 `run_mode`。

## 受影响文件

- `src/choice_agent/decision/assistance.py`：新增 Travel 短回答规则解析 helper，并在 `prepare_turn()` 调用。
- `src/choice_agent/domains/comparison.py`：新增 `clarification_prompt()` hook，`clarify()` 调用 hook。
- `src/choice_agent/domains/travel.py`：覆写 `clarification_prompt()`，动态生成缺失字段问题。
- `src/choice_agent/static/assets/js/app.js`：正式通用决策提交时 Search configured 的支持搜索领域使用 `auto`，避免 checkbox false 强制 fixture。
- `tests/test_general_conversation.py`：新增或扩展 Travel 多轮短回答、动态澄清、字段齐全不澄清测试。
- `tests/test_candidate_search_productization.py` 或 `tests/test_frontend_static.py`：覆盖 Search API 配置后正式入口不强制 fixture，或覆盖 stream/create auto fallback。
- `tests/test_trace_observability.py` / `tests/test_unified_decision.py`：已有 auto fallback 可复用；如验收需要更贴合 Travel 默认 auto，可新增 Travel-specific failing provider Case。
- `CHANGELOG.md`：记录 Travel 多轮澄清和正式联网默认行为变化。

## 兼容性和破坏性变更

API response shape 不变；`conversationFields` schema 不变；`searchMode` 仍只使用既有 `fixture/web/auto`；Demo fixture 行为不变。正式 UI 在 Search API 启用时会从 fixture 改为 `auto`，属于预期用户可见行为变化。显式 `context.searchMode="fixture"` 的测试/评测/客户端不受影响。

## 风险和边界情况

- 短文本地点识别可能误判；通过仅在上一轮确实询问出发地且缺 departure 时启用、过滤偏好/时间/预算片段来降低风险。
- “苏州”也可能是目的地而非出发地；但在上一轮问题明确问“从哪里出发”时，按 departure 解释符合对话上下文。
- Search configured 但 provider transport 失败会使用 fixture，需确保用户可见 source label/warning 不误导。
- 工作区已有用户改动，实施前后必须检查 `git diff`，避免覆盖无关改动。

## 验证方案

自动测试：

- `tests/test_general_conversation.py` 新增 Travel 短回答测试：create “周末想出去走走，但不想太累，应该去哪里？”；assert clarifying 且只问 departure/days；message “苏州，2天，轻松”；assert `departure=苏州`、`days=2`、`priority=轻松`、status decided。
- `tests/test_general_conversation.py` 新增动态澄清测试：已有 days 缺 departure 时只问出发地；已有 departure 缺 days 时只问天数；字段齐全不澄清。
- Search/default：使用 Search configured + failing transport + `auto` 确认 fallback 后 `source.mode="fixture"`、warning/fallback trace 存在。
- 前端静态测试：断言 `submitGeneralDecision()` 在 configured 情况下使用 `auto`，不再出现 `realtime ? "web" : "fixture"` 这种正式入口覆盖。

建议执行：

- `python -m pytest tests/test_general_conversation.py tests/test_unified_decision.py tests/test_trace_observability.py tests/test_candidate_search_productization.py tests/test_frontend_static.py`
- `python -m compileall -q src`
- `node --check src\choice_agent\static\assets\js\app.js`
- `git diff --check`

## 注意事项与技术折衷

- 本次不新增地名数据库，保持规则小而保守。
- 本次不改变 `OpenAIWebSearchProvider` HTTP/parse 逻辑。
- 本次不改变 Ranking、Evidence Validation、Hard Filter、Explanation。
- 前端保留实时搜索控件的 UI 展示，先修正式 Travel 默认行为；是否移除或改文案另行处理。

## Todo

- [x] 在 Travel turn preparation 中补充短回答字段解析。
- [x] 将 Clarification 改为 Travel 动态缺失字段问题。
- [x] 调整正式通用决策提交的 searchMode 选择，Search configured 时使用 `auto`。
- [x] 补充多轮字段、动态澄清、字段齐全不澄清测试。
- [x] 补充正式 Search configured 默认联网/auto fallback/Trace 可观察测试。
- [x] 更新 CHANGELOG。
- [x] 运行目标测试和静态检查，检查最终 diff。