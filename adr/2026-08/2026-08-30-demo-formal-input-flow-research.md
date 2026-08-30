# 演示模式正式化输入流程 Research

## 当前需求和研究范围

用户希望通用演示模式“假装得更正式一点”，用于完整体验正式使用流程。核心诉求不是去掉 fixture，而是让用户在演示中也经历“候选项需要填写、确认、可编辑”的路径：即使候选项底层来自写死的演示数据，也应以正式流程的交互方式呈现。

本轮研究范围：

- 通用演示模式的 fixture、状态创建、排序和解释逻辑。
- 首页进入通用 demo 的流程。
- demo 工作台候选项展示和交互方式。
- 相关样式和 README/CHANGELOG 影响。

本轮不修改产品代码，只产出 Research 和 Plan。

## ADR / 历史方案检索

已检索 `adr/`、`README.md`、`src/` 和 `tests/` 中的 `demo`、`演示`、`fixture`、`候选`、`candidate`、`choice` 等关键词。

相关记录：

- `adr/2026-08/2026-08-30-generic-demo-mode-research.md`
  - 与本需求高度相关。该文件确认通用 demo 当前采用纯前端 fixture 工作台，覆盖旅行、Offer、学习和购物，不新增后端 Orchestrator。
  - 本次需求是在该实现基础上调整体验层，不改变纯前端 demo 的基本边界。
- `adr/2026-08/2026-08-30-generic-demo-mode-plan.md`
  - 与本需求高度相关。该 Plan 已完成 demo fixture、localStorage、排序、解释、工作台渲染和 README/CHANGELOG 更新。
  - 其中成功标准偏“能进入并展示工作台”，没有覆盖“候选项录入/确认步骤”。
- `adr/2026-08/2026-08-29-home-general-decision-mode-research.md`
  - 说明首页已从饮食形态调整为通用入口，饮食是完整可用领域。
  - 与本需求相关的是首页开放式输入如何进入 demo。
- `adr/2026-08/2026-08-29-home-general-decision-mode-plan.md`
  - 已规划并完成通用首页和示例按钮。
  - 本次不会回退该信息架构，只在非饮食 demo 流程中加入更正式的候选确认体验。
- `adr/2026-08/2026-08-29-choice-agent-v1-borrowed-ideas-todo.md`
  - 长期架构 Todo 中提到 fixture 模式完整演示、用户补充候选、排除候选和明确 demo/rule/LLM 状态。
  - 本次只落地其中“演示流程更像正式使用”的前端部分，不推进通用后端架构。
- `adr/2026-08/2026-08-29-eat-what-selector-integration-plan.md`
  - 关注候选选择策略和饮食推荐排序，和本次 UI 录入流程关系较弱。

判断：应新建独立 Research / Plan。追加到已完成 generic demo mode Plan 会混淆“已完成的通用 demo”与“下一阶段正式化体验改造”的边界。

## 核心文件及职责

### `src/choice_agent/static/assets/js/demo.js`

当前通用 demo 的核心模块，负责：

- 定义 `fixtures`，覆盖 `travel`、`career`、`learning`、`shopping`。
- 通过 `demoCandidate()` 创建候选，每个候选含 `id`、`name`、`summary`、`attributes`、`eliminated` 和 `evidence`。
- `baseState()` 从 fixture 克隆出 demo decision，设置 `status = "comparing"`、`candidateState = "complete"`、`nextAction = "compare"`、trace、assumptions、revision 和时间。
- `candidateNames(prompt)` 从用户输入中粗略抽取候选名。
- `createGeneric(prompt)` 在无法匹配领域时生成 generic 候选，候选名不足时使用“方案 A / 方案 B”。
- `detectDomain(prompt, explicitDomain)` 识别旅行、职业、学习、购物或 generic。
- `createDecision(prompt, explicitDomain)` 直接创建完整 demo decision 并保存到 `localStorage`。
- `rank(decision)` 按 criteria 权重对 candidates 排序。
- `explain(decision)` 从当前排序生成演示结论。
- `updateDecision()` 克隆、更新 revision、保存。

关键现状：候选项在 `createDecision()` 之后已经完整存在，且 `candidateState` 通常直接是 `complete`。用户进入工作台时看到的是候选比较结果，而不是候选录入/确认步骤。

### `src/choice_agent/static/assets/js/app.js`

当前静态 UI 的主渲染和事件模块，负责：

- 首页 `renderGeneralHome()` 提供开放式输入和示例按钮。
- `submitGeneralDecision()` 判断饮食问题走真实 `/diet/chat`；非饮食问题调用 `ChoiceAgentDemo.createDecision()`，然后导航到 `#/demo/decision/:id`。
- `renderDemoWorkbench(route)` 加载 demo decision，立即计算 `rankings`，展示工作台。
- `renderDemoState()` 展示目标、约束、开放问题、假设和 trace。
- `renderDemoWeights()` 展示权重 slider。
- `renderDemoCandidate()` 展示候选卡、属性、证据和“排除候选”按钮。
- `completeDemoDecision()` 生成结论。
- `toggleDemoCandidate()` 切换候选排除状态。
- `answerDemoQuestion()` 回答开放问题。

关键现状：工作台主区域直接是“候选比较”。没有独立的候选输入表单、候选确认动作、示例候选项载入按钮、候选新增/删除/改名/改描述流程。

### `src/choice_agent/static/assets/css/app.css`

已有 demo 样式包括：

- `.demo-workbench`、`.demo-header`、`.demo-grid`。
- `.demo-list`、`.demo-trace`、`.weight-list`、`.weight-row`。
- `.demo-candidates`、`.demo-candidate`、`.demo-candidate-head`。
- `.attribute-grid`、`.evidence-list`、`.recommendation-copy`。
- 响应式规则覆盖 demo header、demo grid、attribute grid 和 candidate head。

关键现状：有候选列表展示样式，但没有候选输入表单、候选编辑行、空候选状态和“填入演示候选项”控件样式。

## 关键调用链和数据流

### 当前非饮食 demo 流程

首页输入或点击示例
→ `submitGeneralDecision(form)`
→ 非饮食时调用 `ChoiceAgentDemo.createDecision(prompt, explicitDomain)`
→ `createDecision()` 识别领域并克隆 fixture
→ fixture candidates 已完整注入
→ 保存到 `localStorage`
→ 导航到 `#/demo/decision/:id`
→ `renderDemoWorkbench()`
→ 直接展示目标、约束、权重、候选排序和结论入口。

### 当前候选交互

用户只能：

- 调整权重；
- 排除或恢复已有候选；
- 回答 fixture 中的开放问题；
- 生成结论。

用户不能：

- 在正式流程中补充候选；
- 在分析前确认候选；
- 修改候选名称或描述；
- 从空白或半空白候选清单开始；
- 点击“使用演示候选项”体验自动填充。

## 当前实现逻辑

- Demo 数据是纯前端 fixture，不依赖 API Key、网络或数据库。
- Demo decision 一创建就进入 `status = "comparing"`。
- 旅行、职业、学习、购物 fixture 的 `candidateState` 都是 `complete`。
- Generic prompt 如果抽到 2 个以上候选名则 `candidateState = "complete"`，否则为 `unknown`，但 UI 仍会展示默认“方案 A / 方案 B”。
- 排序函数不区分“用户已确认候选”和“示例预填候选”，只要 `decision.candidates` 存在就会排序。
- 结论生成不校验候选是否经过用户确认。

这解释了用户的感受：当前 demo 看起来像“系统已经把候选项都准备好了”，不像正式使用中“候选项需要用户填或确认”。

## 已有可复用能力

- `ChoiceAgentDemo.updateDecision()` 可复用来修改候选并自动更新 revision/localStorage。
- `demoCandidate()` 可作为生成新候选对象的基础，但目前未导出。
- `candidateNames(prompt)` 能从用户输入抽取候选名，可用于预填候选草稿。
- `rank()` 和 `explain()` 可在候选确认后继续复用。
- `renderDemoCandidate()` 的候选卡展示可保留为比较阶段视图。
- `state.demo.decision`、hash 路由和 localStorage 恢复机制可继续沿用。
- 现有 CSS 变量和表单控件样式可复用，不需要新增前端依赖。

## 潜在问题和隐患

- 如果直接把已有 candidates 改成空数组，用户可能无法快速体验，需要提供“使用演示候选项”或预填草稿。
- 如果新增候选编辑后不更新 evidence 和 attributes，排序和解释可能出现空值。需要为用户新增/编辑候选生成保守的演示属性和演示 evidence。
- 如果“候选确认”只是文案变化、底层仍直接比较，用户体验不会明显改善。需要让工作台有明确阶段：候选准备 → 比较权重 → 生成结论。
- 如果在 candidateState 未确认时仍允许生成结论，会破坏正式流程感。
- 如果每个领域的 candidate 属性维度不同，新增候选需要按当前 criteria 自动生成对应 attributes。
- 如果候选编辑表单过复杂，会把 demo 变成重型数据录入工具。第一版应只支持名称和一句话说明，属性用演示默认值自动生成。
- 如果将 demo 状态结构改动过大，可能破坏已存 localStorage 中旧 demo decision 的兼容性。需要在加载时做默认值兼容。

## 与需求相关的约束

- 本次仍应保持纯前端 demo，不新增后端 API、数据库表或通用 Orchestrator。
- 饮食问题继续走真实饮食链路，不进入通用 demo 候选录入流程。
- 页面必须继续标注“演示数据 / 非实时”。
- 候选项可以来自 fixture，但 UI 应表达为“演示候选项已预填，可编辑，也可清空重填”。
- 第一版不需要编辑每个候选的所有评分属性，以免扩大范围。
- 第一版应兼容已有 demo decisions，避免 localStorage 旧数据导致页面空白。
- 如果用户输入中已经包含候选名，应优先预填这些候选名，让“用户填了候选”的体验更真实。

## 尚未确定、需要在 Plan 阶段决策的问题

- 新建 demo decision 时是否默认进入候选准备阶段，还是仅 generic 场景进入候选准备阶段。
- fixture 候选是默认直接显示在编辑表单里，还是需要用户点击“填入演示候选项”后才出现。
- 候选确认后的 `status`、`candidateState`、`nextAction` 应如何命名以匹配现有前端状态。
- 最少需要几个候选才能进入比较阶段。
- 用户新增候选的 attributes 和 evidence 如何自动生成。
- 是否需要支持候选详情编辑，还是只支持名称与摘要。
- 是否需要更新 README 和 CHANGELOG。

## Research 结论

当前通用 demo 的数据、排序和结论能力已经完整，但入口直接创建“候选已完成”的 decision，工作台也直接展示候选比较。这满足演示稳定性，但削弱了正式流程感。

推荐下一阶段保留 fixture 和本地排序解释，同时新增一个轻量的“候选准备/确认”阶段：demo 创建后先展示候选输入区，候选可由演示数据预填、由用户输入抽取或手动增删改；用户确认候选后才进入当前候选比较、权重调整和生成结论流程。

该方案能让 demo 数据继续可控、无需后端支持，同时让用户体验到正式流程中“候选项需要提供或确认”的关键步骤。