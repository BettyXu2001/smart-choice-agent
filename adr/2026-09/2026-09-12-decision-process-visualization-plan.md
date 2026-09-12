# 决策流程可视化前端优化 Plan

日期：2026-09-12

状态：待用户审查，尚未批准实施。依据同目录 `2026-09-12-decision-process-visualization-research.md`。

## 目标和成功标准

目标：参考 `tx` 文件夹的“可观察决策流水线”思路，把 `choice-agent-v2` 的通用决策体验从“聊天 + 功能区堆叠”优化为“自然语言输入 → 信息分层 → 候选召回 → 比较过滤 → 冲突取舍 → 推荐结论”的可视化流程。

成功标准：

- 首页能让用户在开始前直观看到 Choice Agent 的决策流程，而不是只看到静态价值卡。
- 通用决策详情页能清楚展示本轮决策的端到端流程，普通用户无需打开 Developer Trace 就能理解“为什么这么推荐”。
- 流程节点至少覆盖：需求理解、关键缺口 / 假设、候选池、过滤与比较、取舍解释、最终建议。
- 现有约束编辑、权重调整、候选排除 / 恢复、候选添加、推荐刷新等操作继续可用。
- 证据展示复用现有 `EvidenceView`，不重复制造证据渲染逻辑。
- Developer Trace 继续保留为高级调试视图，不暴露 Prompt / JSON 作为普通用户主体验。
- 旅行、购物、职业、学习、generic 等通用场景在字段缺失时都有合理空态。
- 饮食决策页面不发生布局和行为回归。
- 移动端页面不出现文本溢出、按钮挤压、卡片重叠或流程横向不可读。

## 设计原则

- 参考 `tx` 的表达逻辑，不照搬静态页面样式。
- 先重组现有 decision 数据，不做后端大改。
- 普通用户看“过程解释”，开发者看“Trace 细节”。
- 页面更像工作台，不做营销页。
- 每个流程节点只展示最能帮助决策的 1 到 3 个信息点。
- 允许信息不足时少展示，不伪造完整链路。

## 架构和逻辑设计

### 1. 首页增加轻量流程预览

在 `renderGeneralHome()` 中将当前 `value-flow` 从普通三列价值卡升级为轻量流程预览。

建议阶段：说出纠结点、拆出目标 / 候选 / 约束、先问关键缺口、找到候选并过滤、比较取舍、给出建议和变化边界。

首页只做“流程预期建立”，不展示复杂数据。仍保留示例 prompt 和开始决策按钮。

### 2. 通用详情页重组为决策工作台

保留 `renderGeneralDetails(decision)` 作为入口，但内部结构调整为三块：顶部决策摘要和当前状态、中部决策流程可视化、下部 / 侧栏候选比较、约束权重、推荐结论和可编辑操作。

桌面建议布局：左侧窄栏展示已知条件、关键缺口、权重、数据源；中间主区展示流程可视化和候选比较；右侧或下方强调区展示当前建议、理由、代价、什么会改变结论。

移动端建议布局：默认显示当前建议和流程；候选比较、条件编辑、证据详情纵向折叠；不新增复杂 tab，除非现有布局无法承载。

### 3. 新增用户侧流程模型 helper

为避免在 HTML 模板中塞入大量判断逻辑，新增轻量前端 helper：

```js
function buildDecisionProcess(decision) {
    return [
        { key: "understanding", ... },
        { key: "gaps", ... },
        { key: "retrieval", ... },
        { key: "filtering", ... },
        { key: "ranking", ... },
        { key: "recommendation", ... }
    ];
}
```

该 helper 优先读取：`decision.userGoal`、`decision.intentKey`、`decision.status`、`decision.constraints`、`decision.criteria`、`decision.candidates`、`decision.excludedCandidates`、`decision.domainState.candidatePool`、`decision.domainState.rankingCounts`、`decision.domainState.source`、`decision.domainState.assistance`、`decision.recommendation`、`decision.evidence`。

如果字段缺失，则输出明确空态，例如“还没有候选池”“本轮未记录过滤原因”“等待补充关键条件”。

### 4. 流程节点内容设计

#### 需求理解

展示用户目标、领域 / 意图、当前状态。来源：`decision.userGoal`、`decision.domain`、`decision.intentKey`、`decision.status`。

#### 信息分层

参考 `tx` 的“必须确认 / 可以推断 / 合理默认”，在通用场景中改为：需要你确认、我先做的假设、已知硬约束。

首版若后端没有结构化假设字段，先从现有数据降级：`decision.clarifyingQuestions` → 需要你确认；`decision.constraints` 中 `source === "user"` 或 `kind === "hard"` → 已知硬约束；`domainState.assistance.missingInfo` 或 recommendation 相关缺口 → 需要你确认；无法可靠推断的假设不硬造。

#### 候选召回

展示找到多少候选、候选来源、是否使用实时搜索、证据条数。来源：`candidatePool.length`、`candidates.length`、`domainState.source`、`decision.evidence`、`candidate.evidence`。

#### 过滤与比较

展示硬约束排除数、用户排除数、缺数据排除数、进入比较数。来源：`domainState.rankingCounts`、`excludedCandidates`、`candidates`。复用当前 `renderCandidateFunnel(...)`，但视觉上嵌入流程节点，而不是孤立放在候选标题下。

#### 冲突取舍

展示当前最重要的 2 到 4 个标准、推荐需要接受的代价、被放弃候选的主要原因。来源：`criteria`、`recommendation.reasons`、`recommendation.tradeoffs`、`candidate.scoreBreakdown`、`excludedCandidates`。

#### 最终建议

展示推荐候选、推荐摘要、关键理由、变化边界 / 还缺什么。来源：`recommendation.primaryCandidateId`、`recommendation.summary`、`recommendation.reasons`、`recommendation.tradeoffs`、`domainState.assistance.currentAnalysis`；旧字段缺失时降级到已有 recommendation。

### 5. 候选卡优化

保留 `renderGenericCandidate(candidate, decision)` 的编辑和排除能力，但做以下产品化调整：

- 候选卡顶部展示名称、摘要、状态、得分 / 待比较。
- 中间突出 2 到 4 个关键属性，而不是平铺全部 attributes。
- `scoreBreakdown` 改为更易读的权重 / 表现条，字段缺失时显示“缺少可比数据”。
- 已排除候选明确显示排除原因；原因缺失时显示“已从本轮比较中移除”。
- 证据详情继续用 `EvidenceView.candidate(evidence)`，默认折叠。

### 6. 推荐结论优化为“决策结果卡”

将当前 `demo-recommendation` 升级为更明确的结果卡：当前更推荐、为什么是它、你需要接受的代价、还缺什么信息、什么变化可能改变结论。

优先复用 `decision.domainState.assistance` 中已有字段；没有时从 `recommendation` 降级。

这部分与 `decision-canvas-what-if-plan.md` 的 Decision Canvas 目标一致，但本次只做前端结构化呈现，不扩大后端 What-if 能力。

### 7. Developer Trace 的关系

普通用户页不直接展示 Prompt、原始 JSON 或 state diff。如果当前 decision 能关联 trace id，后续可在 Developer Mode 下提供“查看 Trace”入口；首版计划不要求新增后端关联字段。

### 8. CSS 和视觉方向

复用现有 CSS 变量、`var(--radius-sm)` / `var(--radius-md)`、`demo-workbench` / `unified-workbench` 风格、`card-title`、`badge`、`btn`、`grid`、`subtle-divider`。

新增必要样式：`.decision-process`、`.process-rail`、`.process-step`、`.process-step-active`、`.process-step-muted`、`.process-signal-grid`、`.decision-result-card`、`.tradeoff-list`、`.candidate-compare-card`。

视觉要求：卡片半径不超过现有体系；不使用大面积单色渐变；不增加装饰性背景球、复杂插画或营销 hero；按工作台信息密度设计；中文文本在移动端不溢出。

## 受影响文件

### `src/choice_agent/static/assets/js/app.js`

计划修改：调整 `renderGeneralHome()` 的流程预览区域；在 `renderGeneralDetails(decision)` 中引入流程可视化结构；新增 `buildDecisionProcess(decision)`、`renderDecisionProcess(decision)`、`renderDecisionResultCard(decision)` 等局部 helper；调整 `renderCandidateFunnel(...)` 的复用位置；小幅优化 `renderGenericCandidate(...)` 的信息层级。

不计划修改：路由结构、API 调用方式、命令类型、会话状态管理。

### `src/choice_agent/static/assets/js/conversation.js`

原则上不改。只有当新布局需要在通用决策页保留详情展开状态或移动端展示状态时，才做最小修改。

### `src/choice_agent/static/assets/js/evidence.js`

原则上不改。继续复用 `EvidenceView.candidate(...)`。

### `src/choice_agent/static/assets/js/trace.js`

原则上不改。保留开发者 Trace 时间轴。

### `src/choice_agent/static/assets/css/app.css`

计划新增流程可视化和结果卡样式，并调整现有通用 workbench 局部样式。必须避免影响饮食页面。

### `tests/test_frontend_static.py`

根据现有测试内容补充或调整静态检查，覆盖新增脚本函数 / 页面关键文本 / 结构存在性。

### `CHANGELOG.md`

实施完成后，如用户可见前端体验发生变化，应在 `2026-09-12` 标题下追加简短记录。

## 兼容性和破坏性变更评估

- 不新增 API。
- 不新增依赖。
- 不改变后端数据结构。
- 不改变已有 hash 路由。
- 不改变现有命令行为。
- 旧 decision 缺少新字段时前端降级渲染。
- Developer Trace 页面保持原状。
- 饮食决策页面理论上不受影响；验证时必须覆盖。

## 风险和边界情况

- 通用详情页信息过多，可能变成更复杂的长页面；需要用折叠和优先级控制。
- 不同领域的字段差异较大，流程节点不能假设旅行或购物专属字段。
- 当前 `app.js` 已经很大，新增 helper 要保持局部且命名清晰，避免进一步难维护。
- 如果 `domainState.assistance` 字段在部分决策中缺失，结果卡必须优雅降级。
- 候选没有数值评分时，不能显示伪精确百分比。
- 证据数量统计需要去重，避免同一 evidence 在 decision 和 candidate 中重复计算。
- 移动端流程不能依赖横向滚动才能读懂。

## 验证方案

自动验证：

- `node --check src\choice_agent\static\assets\js\app.js`
- `node --check src\choice_agent\static\assets\js\conversation.js`
- `node --check src\choice_agent\static\assets\js\evidence.js`
- `node --check src\choice_agent\static\assets\js\trace.js`
- `python -m pytest tests/test_frontend_static.py`
- 如果改动触及通用决策命令或渲染依赖，再执行相关通用决策测试。
- `git diff --check`

行为验证：

- 首页打开后能看到轻量决策流程预览，示例按钮和提交仍可用。
- 创建旅行 / shopping / career / generic 示例决策后，详情页显示流程节点。
- 信息不足时流程节点显示缺口或空态，不出现 `undefined`、`null`、空白卡。
- 候选排除 / 恢复、权重调整、添加约束、重新推荐仍能触发命令并刷新页面。
- 有证据的候选仍能展开 Evidence。
- Developer Mode 下 Trace 入口和 Trace 页面不受影响。
- 移动端宽度下流程纵向可读，按钮和中文文本不溢出。
- 饮食聊天和饮食详情页面原有布局不被新 CSS 影响。

无法验证时需要说明：如果本地缺少 pytest 依赖，说明未能执行 pytest，并补充已执行的 JS syntax / diff 检查；如果后端服务无法启动，说明未能完成真实浏览器行为验证，并列出替代检查。

## 技术折衷

- 首版不从后端新增专用 `process` 字段，先由前端从现有 decision 数据生成展示模型。
- 首版不把 `trace.js` 复用为普通用户组件，避免泄露过多工程细节。
- 首版不新增独立路由，优先优化现有通用详情页。
- 首版不实现完整动画模拟，避免 `tx` 静态 demo 变成维护成本高的演示系统。
- 首版不改变饮食专用体验。

## Todo

- [x] 调整首页 `value-flow`，加入轻量决策流程预览。
- [x] 为通用决策详情新增前端流程模型 helper，支持字段缺失降级。
- [x] 在 `renderGeneralDetails(decision)` 中加入端到端流程可视化区域。
- [x] 将推荐结论重组为“当前建议 / 理由 / 代价 / 缺口 / 变化边界”的结果卡。
- [x] 优化候选卡的信息层级，并继续复用 Evidence 展示。
- [x] 补充 CSS，完成桌面和移动端响应式布局，确保不影响饮食页面。
- [x] 执行 JS 语法检查、前端静态测试、diff 检查和必要行为验证。
- [x] 根据实际用户可见变化更新 `CHANGELOG.md`。
