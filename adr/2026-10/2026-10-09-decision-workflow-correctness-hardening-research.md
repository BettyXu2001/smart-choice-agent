# 决策工作流正确性加固 Research

日期：2026-10-09

## 当前需求和研究范围

用户实际运行旅行网页 Demo 后，要求按顺序修复九项问题：正式修改与假设分析混用、偏好覆盖、详情链接与 hash 路由冲突、缺口与阶段矛盾、执行来源失真、质量指标语义混淆、缺少结构化澄清、首屏信息过载，以及 What-if 缺少采用闭环。

这些改动影响多轮状态、What-if 隔离和核心用户流程，属于大改动。本 Research 只确认真实行为、复用能力和约束，不修改产品代码。

## 成功标准

- 假设分析不改正式条件或推荐，除非用户明确点击采用。
- 后续消息只增量更新明确提到的偏好，未被否定的已确认偏好继续生效。
- 完整流程可展开，不改变 SPA 路由。
- 缺口、追问和阶段只从一套一致状态派生。
- 页面按实际 `model / rules / rules_fallback` 展示执行来源。
- 排序分、字段覆盖、来源可靠性和数据时效分开表达。
- 澄清同时支持自然语言与结构化字段。
- 首屏聚焦建议、理由、代价和变化边界。
- What-if 先试算，只有安全字段差异可被采用。

## ADR / 历史方案检索

相关记录：

- `adr/2026-10/2026-10-09-decision-workflow-ux-optimization-research.md` / `plan.md`：高度相关，已设计并在当前未提交代码中实现阶段摘要、AI/规则说明、偏好重点、排除原因和快捷问句。Plan 文件头仍写“待审查”，但 Todo 已全部勾选，本轮不改写该历史记录。
- `adr/2026-09/2026-09-05-decision-canvas-what-if-research.md` / `plan.md`：明确 What-if 应独立保存，不污染正式推荐。
- `adr/2026-09/2026-09-22-travel-clarification-web-search-research.md` / `plan.md`：定义 Travel 必填字段、动态澄清和短回答解析。
- `adr/2026-09/2026-09-04-general-conversation-panel-*`：定义聊天与 Decision Canvas。
- `adr/2026-09/2026-09-12-decision-process-visualization-*`：定义完整流程、候选漏斗和结果卡。

判断：新建本 Research / Plan。旧记录解决“把能力展示出来”，本轮解决运行后暴露的状态正确性和交互闭环，追加旧记录会混淆范围。

## 当前工作区约束

当前工作区已有未提交的 README、CHANGELOG、前端工作流、Evaluation 和 ADR 改动。前端改动与上一轮 UX 优化重叠。本轮实施必须精确增量修改，不能回退、覆盖或整体格式化已有内容。

## 实际运行观察

旅行 Demo 先输入“不想太累”，再补充上海、两天、预算和交通，随后点击“为什么不选绍兴？”和“预算放宽会怎样？”。观察到：

1. 第一轮“轻松”成为重点，第二轮的“预算、交通”却整体覆盖 `priority`，轻松权重丢失。
2. “为什么不选绍兴？”只解释、不改推荐，行为合理。
3. “预算放宽会怎样？”走普通 quick-followup。后端 `hypothetical()` 只识别“如果 / 假如 / 假设 / 要是”，该句被当成正式消息；`_travel_priority()` 又把“预算”写成正式优先项，导致正式推荐变化。
4. “查看完整流程”使用 `href="#generalDetailsPanel"`，与 hash 路由冲突，点击后返回首页。
5. 澄清页同时出现“没有关键缺口”和“你从哪里出发？计划玩几天？”。
6. 离线规则模式仍显示“AI 理解 / AI 解释”。
7. “数据完整度 100%”实际只表示前两名评分字段都有值，与来源是否可靠、实时无关。

## 核心文件与真实职责

### `src/choice_agent/static/assets/js/conversation.js`

- `buildQuickFollowupPrompts()` 返回纯字符串，无法表达 chat 与 What-if 的不同语义。
- `handleDietAction()` 的 `what-if` 会带 `analysisMode="what_if"`，`quick-followup` 则无条件调用 `sendChatMessage()`。
- `renderWorkflowSummary()`、缺口区域和澄清区域分别推断状态，可能互相矛盾。
- `renderDecisionBoundary()` 固定写 AI，没有读取 `currentAnalysis.mode`。
- `qualityBlock` 将 `dataCompleteness` 直接称为数据完整度。
- `generalDetailsPanel` 已存在，可由按钮直接展开，无需 URL hash。

### `src/choice_agent/decision/assistance.py`

- `hypothetical()` 的识别范围较窄。
- `_travel_priority()` 只返回本轮值，`prepare_turn()` 随后通过 `patch_fields()` 覆盖旧值。
- `explain()` 已用深拷贝执行假设分析，并分别写入 `whatIfAnalysis` 与 `currentAnalysis`，现有隔离能力可复用。
- `currentAnalysis.mode` 已区分 `rules`、`model`、`rules_fallback`。

### `src/choice_agent/decision/conversation.py`

- `patch_fields()` 是原子字段更新入口，本身不判断追加、替换或移除语义。
- `sync_dependencies()` 从单一 priority 字符串匹配关键词并重算权重，手工权重优先。
- 为保持兼容，无需把 priority 改为数组；可继续使用规范化的“、”分隔文本。

### `src/choice_agent/decision/what_if.py`

- 已提供正式基线、变化原因和预设场景。
- 场景有稳定 `scenarioId` 和完整假设 prompt。
- 当前 `whatIfAnalysis` 不包含可安全采纳的字段差异。

### `src/choice_agent/decision/quality.py`

- `dataCompleteness` 是前两名候选按权重计算的评分字段覆盖率。
- warnings 已区分 web、fixture/demo 和 manual 来源。
- robustness 是有限权重扰动下的排序稳定比例，不是模型置信度。
- 首轮可只改展示语义，不改变公开质量 schema。

### `src/choice_agent/domains/comparison.py`

- `clarify()` 是阻塞性澄清入口，维护 `clarifyingQuestions` 和 `unansweredQuestions`。
- 排序后统一生成 `qualityAssessment` 与 `decisionQuestion`。
- 前端应优先从 `status + clarifyingQuestions + decisionQuestion` 生成单一进度视图。

### `src/choice_agent/static/assets/js/app.js`

- `currentRoute()` 解析完整 hash，页面锚点会被当成 SPA 路由。
- 已有完整详情、候选漏斗和结果卡，不需要建立第二套详情。

## 关键调用链

普通快捷追问：`buildQuickFollowupPrompts()` → `quick-followup` → `sendChatMessage()` → `DecisionApi.message()` → `prepare_turn()` → `patch_fields()` → 正式重排。当前所有快捷问句都走正式消息。

正确 What-if：`what-if` → context 带 `analysisMode="what_if"` 且 prompt 含“假设” → 深拷贝 DecisionState → 临时分析 → `whatIfAnalysis`，正式 fields / recommendation 不变。

偏好更新：自然语言 → `_travel_priority()` / 模型理解 → `patch_fields(priority=...)` → `sync_dependencies()`。当前没有追加、替换、移除语义层。

澄清与阶段：`ComparisonProfile.clarify()` 写入 `status=clarifying + clarifyingQuestions`，但前端还独立读取 `analysis.missingInfo` 和 `decisionQuestion`，导致冲突。

## 可复用能力

- 独立 `whatIfAnalysis` 与正式 `currentAnalysis`。
- `analysisMode / scenarioId` 请求上下文。
- 现有 `update_fields` command。
- `conversationFields` 的 label、type、unit、confirmed、source、impact。
- `currentAnalysis.mode`、`interpretationWarning`、Trace fallback。
- `qualityAssessment.warnings`、`source.mode`、`source.realTime`。
- `decisionQuestion`、`whatIfScenarios` 和现有详情 DOM。

## 风险与约束

- 仅扩大假设正则不能根治副作用；前端必须显式区分动作模式。
- 直接把 priority 改成数组会扩大 schema 影响，首轮不采用。
- 偏好合并必须支持明确替换和移除，否则用户无法降低旧偏好。
- “采用假设”不能复制整个 shadow decision，只能提交白名单 conversation field patch。
- 结构化澄清仍须走现有 revision、command 和 rerank 事务。
- 来源可靠度和时效只能给定性标签，不能伪造成概率。
- 不新增依赖、数据库表、迁移或 API 路径。
- 不重写 Decision Canvas，不影响 Diet、历史、Trace 和 Evaluation。

## Plan 阶段结论

1. 快捷问句升级为带 `kind / prompt / scenarioId` 的描述；解释走 chat，假设走 What-if。
2. priority 保持字符串，在规则理解层做增量合并；明确替换或移除才删除旧 token。
3. 详情入口改为 button，直接展开 details 并滚动定位。
4. 新增单一前端状态 helper，统一阶段和缺口。
5. 执行来源从 `currentAnalysis.mode` 与 source 状态派生。
6. `dataCompleteness` 改称评分字段覆盖，来源和时效单独展示。
7. 澄清表单复用 `conversationFields + update_fields`。
8. 首屏保留四个核心块，其余进入现有详情。
9. `whatIfAnalysis` 增加白名单 `proposedFields`，采用时调用 `update_fields`。