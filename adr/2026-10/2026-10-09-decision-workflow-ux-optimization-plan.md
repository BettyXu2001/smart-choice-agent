# 决策工作流体验优化 Plan

日期：2026-10-09

状态：待用户审查，尚未批准实施。依据同目录 `2026-10-09-decision-workflow-ux-optimization-research.md`。

## 目标和成功标准

目标：在不改后端核心算法和 API 的前提下，逐项优化用户侧工作流体验，让用户清楚看到阶段流程、模拟交互、AI 的作用、规则的作用、权重变化、候选排除原因和推荐变化边界。

成功标准：

- 通用决策页第一眼能看出本次流程正在 / 已经走到哪一步。
- 用户能理解 AI 负责自然语言理解、追问和解释，确定性规则负责硬约束过滤、权重排序和状态流转。
- 用户偏好变化后，页面显示当前权重重点和推荐变化原因。
- 候选排除原因从“数量统计”升级为候选级可见说明。
- 推荐解释更自然：保留关键数值，但先用用户语言说明取舍。
- 提供 3 到 5 个当前场景相关快捷交互，降低继续追问成本。
- Demo / fixture / realtime / manual 来源提示更显眼，避免用户误解演示数据。
- 现有约束编辑、权重调整、候选排除 / 恢复、候选添加、Evidence 展示和 What-if 继续可用。
- 饮食聊天、Developer Trace、Evaluation 页面不发生回归。

## 总体策略

按“最小可验证闭环”逐项优化，不重做架构。

第一批优先优化真实通用决策页和后端 fixture demo 进入后的体验，因为这是用户刚刚实际跑到的路径。纯前端 scripted demo 暂不作为第一批，避免同时维护两套 demo 体验。

## 优化项 1：流程阶段更可见

### 改什么

将 `renderGeneralPanel()` 中的详细比较入口从纯折叠内容，调整为更明显的流程摘要入口：

- 在 Canvas 顶部当前建议后增加“流程阶段摘要”，展示 4 到 6 个阶段：理解、澄清、候选、过滤、排序、解释。
- 每个阶段标注状态：已完成、当前、等待补充。
- 详细 `renderGeneralDetails()` 仍放在 `<details>` 中，但 summary 改为更明确的“查看完整流程、候选漏斗和证据”。

### 为什么

`renderDecisionProcess()` 已存在，但藏在详细比较里。用户跑 demo 时最想知道“工作流是什么样”，应在主 Canvas 就看到阶段摘要。

### 涉及文件

- `src/choice_agent/static/assets/js/conversation.js`
- `src/choice_agent/static/assets/css/app.css`
- `tests/test_frontend_static.py`

### 验证标准

- 通用决策 Canvas 中出现阶段摘要。
- status 为 `clarifying` 时，澄清阶段显示为当前。
- status 为 `decided` 时，排序 / 解释阶段显示完成。
- 详细比较入口仍可展开。

## 优化项 2：AI / 规则边界说明

### 改什么

在通用 Canvas 或详细流程中增加轻量边界说明：

- AI：理解用户输入、提炼条件、生成解释、提出追问。
- 规则：应用硬约束、按权重排序、记录排除和状态变更。
- 数据：显示来源为演示数据、实时搜索、用户输入或数据库。

流程节点可增加小标签，例如 `AI 理解`、`规则过滤`、`数据来源`、`规则排序`、`AI 解释`。

### 为什么

当前项目的核心产品价值就是“AI + 确定性引擎”，但用户页没有直说。讲清楚边界能提高信任，也能避免把 fixture 结果误认为真实旅行建议。

### 涉及文件

- `src/choice_agent/static/assets/js/app.js`
- `src/choice_agent/static/assets/js/conversation.js`
- `src/choice_agent/static/assets/css/app.css`
- `tests/test_frontend_static.py`

### 验证标准

- 页面出现“AI 负责 / 规则负责 / 数据来源”说明。
- demoMode 或 fixture 时明确显示“演示数据，未核验真实价格 / 路线 / 库存”。
- realtime/web 时仍保留实时来源提示。

## 优化项 3：权重变化和偏好重点可见

### 改什么

新增 `renderPreferenceFocus(decision)` 或等价 helper，展示当前最重要的 3 个权重：

- 如旅行 demo 第三轮显示：放松程度、人流压力为当前重点，交通和预算降为次级。
- 若 `assistance.lastOfficialChange` 可用，展示“推荐从 A -> B”；否则展示“当前排序更受这些维度影响”。
- 在候选 score breakdown 中补充权重说明，例如 `表现 78 · 权重 2.4`，避免只显示 normalized score。

首版不做跨 revision 历史 diff，不从数据库读取旧版本。只使用当前 `criteria`、`scoreBreakdown` 和已有 `assistance` 字段。

### 为什么

用户偏好变化后，后端确实重排了，但 UI 不够明显。首版只展示当前重点，就能解释“为什么从苏州变绍兴”。

### 涉及文件

- `src/choice_agent/static/assets/js/app.js`
- `src/choice_agent/static/assets/js/conversation.js`
- `src/choice_agent/static/assets/css/app.css`
- `tests/test_frontend_static.py`

### 验证标准

- 决策详情显示当前高权重标准。
- 候选评分拆解能看到权重值。
- 无 scoreBreakdown 时显示空态，不出现 `undefined`。

## 优化项 4：候选排除原因更显眼

### 改什么

新增候选状态说明 helper：

```js
function candidateStatusText(candidate, decision) { ... }
```

优先级：

1. `candidate.eliminationReasons`
2. `decision.domainState.candidateState[candidateId].reason`
3. `decision.excludedCandidates` 命中时显示“你已从本轮比较中排除”
4. fallback 显示“已从本轮比较中移除”

在候选漏斗下增加“被排除候选”摘要，展示最多 3 个候选及原因。

### 为什么

当前 funnel 只有数量，用户不知道莫干山为何出局。候选级原因可以把硬约束过滤变成可解释能力。

### 涉及文件

- `src/choice_agent/static/assets/js/app.js`
- `src/choice_agent/static/assets/css/app.css`
- `tests/test_frontend_static.py`

### 验证标准

- 硬约束排除候选显示原因。
- 用户手动排除候选显示“你已排除”。
- 没有原因时有合理 fallback。

## 优化项 5：推荐解释更自然

### 改什么

调整前端展示文案层级，不改后端 `speechText`：

- 结果卡先显示自然语言摘要，例如“如果你更想放松、人少，绍兴比苏州更贴近这个目标。”
- 数值依据放到“关键依据”列表中。
- 代价区明确写“选择它要接受什么”，而不是泛泛“取舍”。

实现上优先从 `recommendation.summary`、`reasons`、`tradeoffs`、`assistance.currentAnalysis` 读取；如果后端只给数值理由，就用前端模板包一层更用户化的标题和分组，不伪造新事实。

### 为什么

真实 demo 的回应有效但偏数值。产品上应先给用户能感知的取舍，再给数值证据。

### 涉及文件

- `src/choice_agent/static/assets/js/app.js`
- `src/choice_agent/static/assets/js/conversation.js`
- `tests/test_frontend_static.py`

### 验证标准

- 结果卡保留理由、代价、缺失信息和变化边界。
- 数值依据仍可见，但不是唯一表达。
- 证据展示仍复用 `EvidenceView`。

## 优化项 6：快捷交互更贴近当前阶段

### 改什么

扩展 `buildQuickFollowupPrompts()` 或在通用 Canvas 中增加阶段相关快捷按钮：

- 偏好类：`更看重放松`、`更看重预算`、`更看重交通短`。
- 对比类：`为什么不选 X？`
- 约束类：`预算放宽会怎样？`
- 排除类保持使用候选卡的排除按钮，不新增重复入口。

按钮仍通过现有 chat / command 路径发送自然语言或现有命令，不新增 API。

### 为什么

用户已经看到“这项对你有多重要？”，快捷按钮可以让下一步更顺，尤其适合 demo 展示。

### 涉及文件

- `src/choice_agent/static/assets/js/conversation.js`
- `tests/test_frontend_static.py`

### 验证标准

- 旅行 / 购物场景出现与 criteria 相关的快捷按钮。
- 没有候选时不出现“为什么不选 X”。
- 按钮仍使用现有 `quick-followup` 机制。

## 优化项 7：Demo 入口说明和稳定性

### 改什么

首版不重做纯前端 scripted demo，只优化 `#/demo` 入口说明和错误状态：

- 按钮文案说明“用后端 fixture 体验真实流程”。
- 卡片明确“不需要 LLM Key，但需要本地服务运行”。
- 如果 API 失败，错误文案提示可返回首页或检查服务。

纯前端 scripted demo 单独作为后续项，避免当前批次扩大范围。

### 为什么

用户刚刚运行的是后端 fixture demo。先把现有真实流程解释清楚，比引入第二套 demo 更稳。

### 涉及文件

- `src/choice_agent/static/assets/js/app.js`
- `tests/test_frontend_static.py`

### 验证标准

- Demo 入口明确 fixture / 非实时 / 无需 LLM Key。
- API 错误时不空白，错误可见。

## CHANGELOG 规则

本次属于用户可见前端体验优化，实施完成后需要在 `CHANGELOG.md` 的 `2026-10-09` 标题下追加精简记录；如果该日期不存在则新增。

## 验证方案

自动验证：

- `node --check src\choice_agent\static\assets\js\app.js`
- `node --check src\choice_agent\static\assets\js\conversation.js`
- `node --check src\choice_agent\static\assets\js\demo.js`
- `python -m pytest tests/test_frontend_static.py`
- `git diff --check`

行为验证：

- 启动本地服务并打开 `http://127.0.0.1:8000/`。
- 从 `#/demo` 进入旅行示例，确认阶段摘要、来源提示、权重重点、候选排除原因、结果卡都可见。
- 模拟用户偏好变化，确认推荐变化和权重重点表达正确。
- 测试候选排除 / 恢复、权重滑动、查看 Evidence、What-if 快捷按钮仍可用。
- 检查移动端窄宽度无明显重叠或文本溢出。
- 抽查饮食聊天页面、Developer Trace 页面不受影响。

无法验证时必须说明具体原因和剩余风险。

## 兼容性和破坏性变更评估

- 不新增 API。
- 不改数据库。
- 不新增依赖。
- 不改后端排序算法。
- 不改变现有 hash 路由。
- 不改变命令类型。
- 旧 decision 字段缺失时降级显示空态。
- Developer Trace 保持开发者视图，不变成普通用户默认内容。

## Todo

- [x] 在通用 Decision Canvas 增加可见流程阶段摘要，并保留完整详细比较入口。
- [x] 增加 AI / 规则 / 数据来源边界说明，强化 demo / fixture / realtime 区分。
- [x] 展示当前偏好重点和候选评分中的权重信息。
- [x] 为候选卡和候选漏斗增加候选级排除原因。
- [x] 优化结果卡文案层级，让自然语言取舍先于数值明细。
- [x] 增加当前场景相关快捷交互按钮，复用现有 quick-followup 路径。
- [x] 优化 `#/demo` 入口说明和 API 失败错误提示。
- [x] 补充或调整前端静态测试。
- [x] 执行 JS 语法检查、前端测试、diff 检查和本地行为验证。
- [x] 按 CHANGELOG 规则记录用户可见变化。