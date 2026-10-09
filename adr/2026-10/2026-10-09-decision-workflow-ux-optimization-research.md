# 决策工作流体验优化 Research

日期：2026-10-09

## 当前需求和研究范围

用户在运行旅行网页 demo 后，询问优化空间，并要求“优化空间的项目，逐个优化”。本轮研究聚焦用户侧决策工作流体验：阶段流程、模拟用户交互、系统回应、AI / 规则边界、权重变化、候选排除原因和快捷反馈。

本轮不改后端决策算法、不新增 API、不新增依赖、不改变数据库结构。由于会影响核心用户体验、前端工作台布局和 demo 交互，按大改动处理。本阶段只做 Research / Plan，尚未修改产品代码。

## 成功标准

- 用户打开 demo 或通用决策详情时，能清楚看到流程阶段，而不是只看到结果卡和候选列表。
- 用户能区分：AI 负责理解 / 解释 / 追问，确定性规则负责约束过滤 / 权重排序 / 状态流转。
- 用户修改偏好后，页面能明确展示权重变化和推荐变化原因。
- 被排除候选的原因更明显，尤其是硬约束排除、用户排除和缺数据排除。
- 系统回应更像给用户解释选择，而不是只复述数值。
- 快捷交互能覆盖常见偏好调整，不要求用户每次手写自然语言。
- 现有通用决策命令、Evidence 展示、Developer Trace 和饮食页面不回归。

## ADR / 历史方案检索

已按 demo、workflow、工作流、阶段、解释、权重、候选、交互、Decision Pipeline 等关键词检索 `adr/`、`docs/`、`README.md`、`CHANGELOG.md` 和前端源码。

相关记录：

- `adr/2026-09/2026-09-12-decision-process-visualization-research.md` / `plan.md`：高度相关。已完成首页流程预览、通用详情流程节点、结果卡和候选卡优化。当前问题不是没有流程可视化，而是流程仍偏静态、详细比较默认折叠在 Canvas 内，权重变化和 AI / 规则边界表达不足。
- `adr/2026-09/2026-09-22-homepage-scripted-demo-research.md`：相关。指出 `#/demo` 仍通过后端 fixture / Orchestrator，不是纯前端固定剧本；也指出 demo 体验需要稳定展示候选差异、澄清问题、偏好更新和推荐结果。当前没有对应 plan 文件。
- `adr/2026-09/2026-09-04-general-conversation-panel-research.md` / `plan.md`：相关。建立通用对话和 Decision Canvas，是当前真实对话页的基础。
- `adr/2026-09/2026-09-05-evidence-presentation-research.md` / `plan.md`：相关。Evidence 展示应继续复用，不能另造一套来源说明。
- `adr/2026-09/2026-09-05-decision-canvas-what-if-research.md` / `plan.md`：相关。已有“什么会改变结论”的设计，本轮应把它变成更明显的用户交互和变化解释。
- `adr/2026-08/2026-08-29-choice-agent-v1-borrowed-ideas-todo.md`：相关。早期已明确要区分 demo / rule / LLM 状态提示。

判断：本轮新建独立 Research / Plan。原因是旧流程可视化方案已完成，本轮是基于真实 demo 运行后的第二轮产品化打磨，追加旧文档会混淆历史完成状态。

## 当前运行观察

使用本地服务 `http://127.0.0.1:8000/`，以旅行 demo 模拟：

1. 用户输入“周末想出去走走，但不想太累，应该去哪里？”
   - 后端执行 `IntentAgent -> UnderstandingAgent -> ClarificationAgent`。
   - 系统回应“你从哪里出发？计划玩几天？”

2. 用户补充“上海出发，两天一夜，预算1000以内，单程交通最好3小时内。”
   - 后端执行 `CandidateAgent -> CriticAgent -> ExplanationAgent -> RiskAgent`。
   - 候选池中 `莫干山` 和 `宁波东钱湖` 因硬约束排除，`苏州` 与 `绍兴` 进入比较。
   - 首轮更倾向苏州，原因是交通和预算更优，同时提示绍兴在放松程度、人流压力上更好。

3. 用户补充“其实我更想放松一点、人少一点，交通不用最短，只要别太折腾就行。”
   - 权重变为：交通时间 1，预算压力 1，放松程度 2.4，人流压力 2.2，自然景观 0.9。
   - 推荐切换为绍兴，回应强调绍兴放松程度和人流压力更优。

结论：底层能力已经跑通，优化重点在前端如何把这条变化链路展示清楚。

## 核心文件及职责

### `src/choice_agent/static/assets/js/app.js`

- `renderHomeDecisionProcess()` 已渲染首页六步流程预览。
- `buildDecisionProcess()` 从 `DecisionState` 生成用户侧流程节点：需求理解、信息分层、候选召回、过滤与比较、冲突取舍、最终建议。
- `renderDecisionProcess()` 渲染流程节点。
- `renderDecisionResultCard()` 渲染推荐结论：为什么是它、代价、缺失信息、变化边界。
- `renderGeneralDetails()` 将通用详情嵌入 `<details class="general-details">`。默认在右侧 Decision Canvas 中折叠，普通用户不一定会展开。
- `renderCandidateFunnel()` 展示候选漏斗数量，但仍是静态数字列表。
- `renderGenericCandidate()` 展示候选卡、前四个属性、score breakdown 和 Evidence。
- `renderDemoWorkbench()` 的新版 demo 卡片仍调用 `conversation.startGeneral(... demoMode:true)`，实际依赖后端 API 和 fixture orchestrator。
- 旧本地 demo 的约束 / 候选准备、权重调整、生成结论函数仍保留，但当前 `#/demo` 入口没有直接进入这套轻量流程。

### `src/choice_agent/static/assets/js/conversation.js`

- `renderGeneralPanel()` 是用户实际看到的右侧 Decision Canvas。
- 它已经展示当前建议、质量、为什么、代价、变化原因、缺失信息、What-if、条件编辑、当前比较。
- `sourceNote` 已能区分 fixture / web / manual，但表达埋在底部小字里。
- `quickPrompts` 已存在，但主要集中在右侧建议卡，未和流程阶段、权重变化形成显式联动。
- 详细比较通过 `<details class="diet-panel-section general-details">` 展开；这会让流程可视化、候选漏斗和候选卡不够第一眼可见。

### `src/choice_agent/static/assets/js/demo.js`

- 维护本地 fixture、约束草稿、候选草稿、排序和解释。
- `rank(decision)` 使用确定性加权排序。
- `explain(decision)` 生成通用结论，当前话术说明“不是实时搜索结论，而是固定演示数据展示结构化决策过程”。
- 旧 demo 的推荐理由主要来自 evidence 前两条或最高权重维度，取舍文案较泛。

### `src/choice_agent/static/assets/css/app.css`

- 已有 `.home-process`、`.decision-process`、`.process-step`、`.decision-result-card`、`.candidate-compare-card`、`.score-breakdown` 等样式。
- 当前样式支持流程卡，但没有专门的“AI / 规则边界”、权重变化、候选排除原因、快捷偏好按钮样式。

### `tests/test_frontend_static.py`

- 现有前端测试以静态源码断言为主，覆盖流程可视化函数、候选 funnel、候选卡 Evidence、权重控制等。
- 缺少可执行的 demo 状态机测试，也缺少针对“AI / 规则边界”、“权重变化提示”、“排除原因文案”的断言。

## 关键调用链和数据流

### 真实通用决策入口

`renderGeneralHome()` -> `submitGeneralDecision()` -> `conversation.startGeneral()` -> `DecisionApi.createStream()` 或 `DecisionApi.create()` -> `#/decisions/:id` -> `conversation.enter("general")` -> `renderGeneralPanel()` -> 用户展开 `renderGeneralDetails()`。

### demo 入口

`renderDemoWorkbench()` -> `startDemoChat()` -> `conversation.startGeneral(message, domain, {context:{searchMode:"fixture", demoMode:true}})` -> 后端 fixture / orchestrator -> 真实通用决策页。

### 通用详情命令

`sendGenericCommand()` 复用 `sendDietCommand()`，支持 `refresh_candidates`、`generate_recommendation`、`set_constraint`、`remove_constraint`、`set_criterion_weight`、`exclude_candidate`、`restore_candidate`、`add_candidate`、`update_candidate`、`answer_question`。

## 当前实现逻辑

1. 首页已经给出流程预览，但它是静态预期，不展示真实示例的阶段回应。
2. 真实对话页的主体验是聊天 + 右侧 Canvas；详细流程可视化在折叠详情内。
3. Canvas 的“当前结论为什么发生变化”依赖 `assistance.lastOfficialChange` 或 `current.lastChange`，但如果后端没有填充，会显示“本轮没有改变当前倾向”。
4. `renderDecisionProcess()` 已能从 `rankingCounts`、`source`、`criteria`、`recommendation` 生成流程节点，但不会突出“这一步由 AI 做”或“这一步由规则做”。
5. 候选漏斗能显示排除数量，但候选卡只对用户排除显示“已从本轮比较中移除”，不能解释硬约束排除的具体原因。
6. 候选卡 score breakdown 显示 normalized score，但用户不容易看出“权重变化导致推荐变化”。
7. Demo 的后端 fixture 流程更真实，但对“模拟用户交互”不如固定剧本稳定；旧本地 demo 更稳定但入口较重。

## 已有可复用能力

- `decision.context.demoMode`、`domainState.source`、`searchRuns`、`sources` 可用于来源和演示模式提示。
- `agentRuns` 可用于阶段标签，但用户页不应暴露 prompt / JSON。
- `criteria.weight`、`scoreBreakdown.weight` 和 `scoreBreakdown.normalizedScore` 可用于权重变化或权重说明。
- `domainState.rankingCounts` 可用于候选漏斗。
- `candidateState` 可用于候选 active / eliminated 状态。
- `excludedCandidates` 可用于用户排除状态。
- `domainState.assistance`、`recommendation.reasons`、`recommendation.tradeoffs` 可用于结果解释。
- `EvidenceView.candidate()` 和 `EvidenceView.point()` 可继续承担证据展示。
- 现有 `quick-followup` / `what-if` 已支持快捷追问和假设分析。

## 主要问题和隐患

1. 阶段感不足：流程可视化已有，但位置偏深，用户需要展开详细比较才看到。
2. AI 作用不够明确：页面没有把“AI 理解 / 追问 / 解释”和“规则过滤 / 排序 / 状态更新”分开讲清楚。
3. 系统回应偏数值：真实回应里会出现“放松程度为 78，人流压力为 42”，对用户有解释价值但不够自然。
4. 权重变化不明显：用户偏好变化后，权重确实变了，但 UI 没有专门展示“刚刚哪些权重变了、因此推荐从 A 切到 B”。
5. 排除原因不够显眼：硬约束排除数量可见，但具体候选为什么被排除不够第一眼可见。
6. 快捷交互还可以更主动：已有 quick followups，但缺少“更看重放松 / 更看重预算 / 更看重交通 / 排除这个候选”这类与当前流程直接绑定的按钮。
7. Demo 稳定性取舍：后端 fixture demo 能展示真实链路，但如果服务异常就不可用；纯前端 demo 更稳定，但当前入口没有采用。
8. 测试多为静态断言，无法验证 demo 状态转换或权重变化展示的真实输出。

## 与需求相关的约束

- 不新增前端框架或依赖。
- 优先修改现有前端展示和 demo 交互，不改后端核心算法。
- 不把 Developer Trace 的 prompt、raw JSON、state diff 暴露为普通用户主体验。
- 不破坏饮食聊天、通用对话、历史决策和评估页面。
- 不扩大到真实搜索质量、模型提示词、评分算法重构。
- 当前工作区已有未提交改动：`CHANGELOG.md`、`README.md`、evaluation 相关文件、`adr/2026-10/`。后续实施必须限定 diff，避免覆盖无关改动。

## Plan 阶段需决策的问题

1. 第一轮优化是否优先做真实通用决策页，而不是纯前端 scripted demo？
2. 是否把详细比较从折叠区提升为更可见的“流程抽屉 / 默认展开摘要”？
3. 权重变化展示首版是否只用当前权重和推荐变化，不追求跨 revision diff？
4. 候选排除原因是否首版从 `candidateState.reason`、`eliminationReasons`、`excludedCandidates` 降级生成？
5. 是否把“AI / 规则边界”做成顶部说明条和流程节点标签，避免新增复杂教育页？