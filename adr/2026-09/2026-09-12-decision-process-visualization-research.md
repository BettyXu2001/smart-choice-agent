# 决策流程可视化前端优化 Research

日期：2026-09-12

## 当前需求和研究范围

用户希望参考 `D:\Code\AI Coding\tx` 文件夹中的可视化决策流程思路，优化 `choice-agent-v2` 的前端页面。本轮目标是形成可审查的 ADR Research / Plan，暂不修改产品代码。

研究范围限定为：当前通用决策首页与决策详情页、Trace / Evidence / Demo 相关能力、`tx` 中决策流程可视化页面、已有 ADR / Plan 与本次优化的关系。

不包含：后端决策算法重构、新增外部依赖或前端框架迁移、重新设计饮食决策全流程、真实模型 / 搜索 / 评估系统改造。

## ADR / 历史方案检索

已检索 `adr/`、`README.md`、`CHANGELOG.md`、`src/` 和前端文件。发现以下相关记录：

- `adr/2026-09/2026-09-05-decision-trace-observability-plan.md`：已覆盖后端业务时间轴、Trace timeline、Prompt / 输出 / state diff / refs 展示。它可作为工程观测层的数据来源和开发者视图，但不适合作为普通用户的主要决策流程表达。
- `adr/2026-09/2026-09-05-decision-canvas-what-if-plan.md`：已覆盖 Decision Canvas、当前建议、理由、代价、缺失信息、What-if。它与用户侧决策理解高度相关，本次计划应复用 Canvas 思路，重点补足“端到端流程可视化”。
- `adr/2026-09/2026-09-05-evidence-presentation-plan.md`：与证据展示、候选依据和可信度表达相关。候选卡与推荐解释应复用证据展示，而不是单独制造依据文案。
- `adr/2026-09/2026-09-05-homepage-value-positioning-offer-demo-plan.md`：与首页价值表达和示例体验相关。首页可加入更明确的“流程预览”，但不应改成营销页。
- `showcase/`：当前项目中已存在 `solution-process.html`、`interactive-demo.html`、`evaluation.html` 等静态展示页面，与 `tx` 文件夹内容高度相似，说明 `tx` 思路已经部分沉淀为 showcase，但尚未产品化整合进主 SPA。

判断：本次计划应新建独立 Research / Plan。原因是已有 Trace / Canvas / Evidence 方案已完成或偏工程能力，本次主题是“参考 tx 的用户侧流程可视化改版”，追加到旧计划会混淆历史语义。

## 核心文件及职责

- `src/choice_agent/static/index.html`：SPA 壳，负责加载 CSS、前端脚本、主渲染容器 `#app` 和全局 toast。
- `src/choice_agent/static/assets/js/app.js`：当前前端主入口，负责路由分发、首页 `renderGeneralHome()`、通用决策详情 `renderGeneralDetails(decision)`、Demo workbench、候选漏斗、候选卡、表单和命令处理。
- `src/choice_agent/static/assets/js/conversation.js`：负责聊天模式和通用 / 饮食会话切换。`renderGeneralDetails(decision)` 由该模块在通用决策页面中调用。
- `src/choice_agent/static/assets/js/trace.js`：负责 Trace 时间轴开发者视图，适合保留在 Developer Mode / Trace 页面，不宜直接作为普通用户的默认体验。
- `src/choice_agent/static/assets/js/evidence.js`：候选详情通过 `window.EvidenceView.candidate(evidence)` 展示候选依据，本次应继续复用。
- `src/choice_agent/static/assets/css/app.css`：已有主题变量、全局卡片风格、首页、demo / workbench、候选、约束、权重、漏斗等局部样式，本次不引入新的视觉体系。

## `tx` 参考结论

`tx` 中最有参考价值的页面：

- `solution-process.html`：角色分工、端到端流程、缺失信息三类处理、信息源链路、人机协同泳道、每步输入输出、示例链路。
- `interactive-demo.html`：左侧输入与协同边界，右侧 live simulation，包含进度条、需求理解、工具调用、候选召回、冲突取舍、最终方案和取舍解释。
- `travel-plan-evaluation.html`：体验指标和评估表达，可作为后续评估页面参考，但不是本次主线。

`tx` 的核心价值不是视觉样式本身，而是把一次 AI 决策拆成可观察、可解释、可复盘的流水线。

## 当前实现逻辑

### 首页

首页以“把选择题想清楚”为主标题，用户输入自然语言问题后进入通用决策。首页已有四个价值点：不用先整理、看清决策条件、先补关键缺口、理解推荐边界。

问题：这些价值点仍是静态描述，用户还没有在首页看到“决策流程会怎样展开”；`value-flow` 是普通卡片网格，缺少类似 `tx` 的端到端流程感。

### 通用决策详情

当前 `renderGeneralDetails(decision)` 已组织出一个 `demo-workbench unified-workbench`：左侧为约束、添加约束、权重、数据源；右侧为澄清问题、候选比较、候选漏斗、候选卡、推荐结论。

已有数据来源包括：`decision.constraints`、`decision.criteria`、`decision.candidates`、`decision.excludedCandidates`、`decision.domainState.candidatePool`、`decision.domainState.rankingCounts`、`decision.evidence`、`candidate.evidence`、`decision.recommendation`、`decision.domainState.source`。

问题：结构是功能区堆叠，不是流程叙事。候选漏斗已有数字，但没有和“信息分层、候选召回、冲突取舍、推荐边界”形成完整链路。推荐结论与候选卡、约束、权重之间的因果关系展示较弱。

### Trace 视图

Trace 已具备完整工程时间轴，但内容包括 Prompt、JSON、state diff 等，适合调试，不适合用户默认阅读。它可以作为流程节点的“高级详情”来源或跳转目标。

## 关键调用链和数据流

1. 用户在首页提交 `generalDecisionForm`。
2. `submitGeneralDecision(form)` 读取 prompt、domain、search mode。
3. `conversation.startGeneral(...)` 创建或进入通用决策会话。
4. 路由进入 `#/decisions/:id`。
5. `renderGenericDecision(route)` 调用 `conversation.enter("general", decisionId)`。
6. `conversation.js` 加载 / 维护 `state.chat.decision`。
7. `renderGeneralDetails(decision)` 渲染通用决策详情。

通用详情命令包括：`refresh_candidates`、`generate_recommendation`、`set_constraint`、`remove_constraint`、`set_criterion_weight`、`exclude_candidate`、`restore_candidate`、`add_candidate`、`update_candidate`、`answer_question`。这些命令通过 `sendGenericCommand(...)` 复用 `sendDietCommand(...)`，由后端更新 decision 后重新渲染。

## 已有可复用能力

- 自然语言决策入口。
- 首页示例 prompt。
- 搜索进度 `state.home.progress`。
- 通用决策约束、权重、候选、排除、推荐结论。
- 候选漏斗和 ranking counts。
- 证据展示组件 `EvidenceView`。
- Trace timeline 的 stage label、summary 和 refs。
- Demo workbench 样式与交互按钮。
- `showcase/` 中已经沉淀的静态流程展示稿。

## 潜在问题和隐患

- `app.js` 体积较大，继续堆叠 HTML 字符串会降低维护性；但本次不宜做大规模拆分。
- 当前通用详情中存在较多动态表单和事件绑定，改版需要避免绑定范围扩大到全局导致重复监听。
- 如果强行复用 Trace JSON，可能把开发者信息暴露给普通用户，增加理解成本。
- 不同 domain 的 decision 字段完整度不同，流程节点必须支持缺数据空态。
- `decision.domainState.assistance`、`rankingCounts`、`source`、`candidatePool` 可能在旧历史或部分场景缺失。
- 移动端不能把聊天、详情、流程、候选全部堆叠成长页面，需要明确优先级。
- 视觉优化不能把当前 SaaS 工作台风格改成概念稿或营销页。

## 与需求相关的约束

- 遵循项目原则：小范围、精确修改、复用已有能力。
- 本次计划阶段不得修改产品代码。
- 后续实施前需要用户明确批准。
- 不新增依赖、不换框架。
- 不改变现有 API 路径和必填字段。
- 优先用户侧可解释，不替代 Developer Trace。
- 饮食决策页面应保持现有布局和行为。
