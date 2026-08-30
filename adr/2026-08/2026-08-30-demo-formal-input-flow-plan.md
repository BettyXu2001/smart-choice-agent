# 演示模式正式化输入流程 Plan

## 目标和成功标准

目标：把通用演示模式从“打开即展示写死候选比较”调整为“像正式流程一样先准备/确认候选，再比较并生成结论”。底层仍可使用 fixture，但 UI 要让用户完整体验候选项需要填写、可编辑、可确认的过程。

成功标准：

- 非饮食 demo 创建后默认先进入候选准备阶段，而不是直接进入候选比较。
- 候选准备阶段展示“正式使用时这里需要补充候选项”的表单体验。
- 演示候选项可以预填或一键填入，但用户可编辑、删除、新增。
- 用户输入中包含候选名时，优先把这些候选名放入候选草稿。
- 至少 2 个有效候选后，用户才能确认进入比较阶段。
- 确认候选后沿用现有权重调整、排除候选、排序和生成结论能力。
- 结论生成只在候选确认后开放。
- 页面继续明确标注“演示数据 / 非实时”，不伪装成真实搜索结果。
- 饮食类输入仍进入真实饮食聊天链路，不进入通用 demo 候选准备。
- 刷新页面后 demo state 可从 localStorage 恢复。
- 不新增依赖，不新增后端 API，不修改数据库。

## 方案选择

采用“纯前端候选准备阶段”方案。

保留当前 `ChoiceAgentDemo` fixture、localStorage、rank 和 explain；在 demo state 中增加候选流程字段，并扩展工作台 UI：

```text
首页输入
  -> 饮食：真实饮食链路
  -> 非饮食：创建 demo decision
    -> stage = "candidate_input"
    -> 候选草稿来自用户输入 / fixture 示例
    -> 用户编辑候选
    -> 确认候选
    -> stage = "compare"
    -> 现有权重调整 / 排除 / 生成结论
```

本阶段不做：

- 不新增通用后端 Orchestrator。
- 不新增通用 demo API。
- 不把旅行、职业、学习、购物接入真实搜索。
- 不编辑候选的全部评分属性。
- 不引入前端构建链或测试框架。

## 架构或逻辑设计

### Demo State 扩展

在前端 demo decision 上增加轻量字段：

- `stage`: `"candidate_input"` 或 `"compare"`。
- `candidateInput`: 候选录入阶段状态。
- `candidateInput.items`: 候选草稿数组。
- `candidateInput.items[].id`: 稳定草稿 ID。
- `candidateInput.items[].name`: 用户可编辑候选名。
- `candidateInput.items[].summary`: 用户可编辑一句话说明。
- `candidateInput.prefilledFrom`: `"fixture"`、`"prompt"` 或 `"manual"`。

兼容旧数据：

- 如果旧 decision 没有 `stage`，但 `candidates` 存在，则按旧行为视为 `"compare"`。
- 如果新 decision 缺少 `candidateInput`，从现有 candidates 派生草稿。

### 创建 Demo Decision

修改 `ChoiceAgentDemo.createDecision()`：

- 对非 generic 领域仍克隆 fixture，但初始 `stage = "candidate_input"`。
- 初始 `candidateState = "draft"`。
- 初始 `nextAction = "collect_candidates"`。
- 初始 trace 当前步骤为“准备候选”。
- candidates 可以保留 fixture 候选作为内部候选池，但 UI 以 `candidateInput.items` 作为用户可编辑草稿来源。
- 如果用户 prompt 中抽到 2 个以上候选名，则用这些名称生成草稿，摘要可沿用 fixture 对应项或填默认说明。
- 如果没有抽到候选名，则默认把 fixture 候选作为可编辑预填草稿，表单上明确标注“已预填演示候选，可修改或清空”。

这样既能保证用户不被空表单卡住，也能体验候选项需要确认。

### 候选编辑能力

新增 demo 工具函数：

- `candidateDrafts(decision)`：返回兼容后的草稿候选。
- `updateCandidateDraft(decision, draftId, patch)`：更新候选名或摘要。
- `addCandidateDraft(decision)`：新增一个空白候选草稿。
- `removeCandidateDraft(decision, draftId)`：删除候选草稿，保留至少 1 行空白输入。
- `resetCandidateDrafts(decision)`：重新填入当前领域 fixture 候选。
- `confirmCandidateDrafts(decision)`：将有效草稿转换为 candidates，设置 `stage = "compare"`、`candidateState = "complete"`、`nextAction = "compare"`、清空 recommendation。

有效候选规则：

- name trim 后非空。
- 至少 2 个有效候选才能确认。
- summary 可空；空时自动生成“等待补充更多信息，当前先按演示维度比较。”。

### 草稿转 Candidate

确认时生成 candidates：

- 如果草稿对应原 fixture candidate，复用其 attributes 和 evidence，只替换 name/summary，并同步 evidence 的 `candidateId`。
- 如果是新增草稿，按当前 criteria 生成保守演示 attributes：
  - 每个 `higher_better` 维度给 68-82 的稳定分；
  - 每个 `lower_better` 维度给 28-42 的稳定值；
  - 用候选顺序做轻微差异，避免完全同分；
  - evidence claim 说明这是用户补充候选的演示属性。
- 所有候选 `eliminated = false`。

### 工作台阶段渲染

`renderDemoWorkbench()` 根据 `decision.stage` 分流：

- `candidate_input`：展示候选准备表单。
- `compare`：展示当前已有候选比较、权重、排除和结论。

候选准备阶段 UI：

- 顶部仍显示目标、领域、演示数据标签。
- 主区域标题：`候选项准备`。
- 说明：正式使用时这里需要补充候选项；演示模式已提供可编辑示例。
- 列表中每个候选一行：名称输入、说明输入、删除按钮。
- 底部操作：
  - `新增候选`
  - `填入演示候选项`
  - `清空`
  - `确认候选，开始比较`
- 右侧或下方保留“接下来会发生什么”：确认候选后会比较权重、生成排序、给出结论。

比较阶段 UI：

- 基本沿用当前 `renderDemoState()`、`renderDemoWeights()`、`renderDemoCandidate()`、`renderDemoRecommendation()`。
- 增加一个“返回编辑候选”按钮，允许回到候选准备阶段。
- `生成结论` 按钮只在 compare 阶段显示或启用。

## 关键流程

### 首页示例进入旅行 demo

用户点击旅行示例
→ 首页 textarea 填入示例 prompt 和 `data-demo-domain="travel"`
→ 提交
→ `ChoiceAgentDemo.createDecision(prompt, "travel")`
→ 创建 `stage = "candidate_input"` 的 travel decision
→ 候选草稿预填莫干山、绍兴、宁波东钱湖、苏州
→ 导航到 demo 工作台
→ 用户可编辑候选
→ 确认候选后进入比较。

### 用户输入已有候选名

用户输入“A 公司和 B 公司两个 Offer 各有优缺点”
→ 识别为 career
→ `candidateNames()` 抽取候选名
→ 候选草稿优先使用 A 公司、B 公司
→ 用户确认后生成 career candidates
→ 复用职业 criteria 排序。

### 用户新增候选

用户在候选准备阶段点击新增候选
→ 增加空白草稿行
→ 用户填写名称和说明
→ 确认时为新增候选生成演示 attributes 和 evidence
→ 进入比较阶段后可参与排序。

### 用户返回编辑候选

用户在比较阶段点击返回编辑候选
→ `stage = "candidate_input"`
→ 从当前 candidates 派生草稿
→ recommendation 清空
→ 用户编辑并再次确认
→ 重新排序。

## 受影响文件列表

### `src/choice_agent/static/assets/js/demo.js`

计划修改：

- 扩展 demo decision 初始状态，新增 `stage` 和 `candidateInput`。
- 增加候选草稿兼容和编辑函数。
- 导出候选准备相关函数。
- 调整 `createDecision()`，让非饮食 demo 默认进入候选准备阶段。
- 调整 `rank()` 和 `explain()`，在无有效候选或未确认候选时返回清晰空状态，不生成误导结论。
- 保持旧 localStorage decision 的 compare 兼容。

### `src/choice_agent/static/assets/js/app.js`

计划修改：

- `renderDemoWorkbench()` 根据 stage 渲染候选准备或比较工作台。
- 新增 `renderDemoCandidateInput()`。
- 新增候选草稿表单输入处理和按钮事件：
  - `demo-add-candidate`
  - `demo-remove-candidate`
  - `demo-reset-candidates`
  - `demo-clear-candidates`
  - `demo-confirm-candidates`
  - `demo-edit-candidates`
- 修改 `demo-complete`：未确认候选时提示先确认候选。
- 修改 demo header：候选准备阶段不显示“生成结论”主按钮，避免流程跳步。

### `src/choice_agent/static/assets/css/app.css`

计划修改：

- 增加候选准备表单样式，例如 `.candidate-input-panel`、`.candidate-draft-list`、`.candidate-draft-row`、`.candidate-draft-actions`。
- 保证移动端候选编辑行从多列降为单列，按钮和输入框不溢出。
- 复用现有颜色变量和表单样式，不做整体视觉重构。

### `README.md`

计划修改：

- 更新 Demo Mode 说明：通用 demo 使用本地 fixture，但会先让用户确认/编辑候选项，再进入比较和结论。
- 保持饮食场景真实规则链路说明。

### `CHANGELOG.md`

计划修改：

- 在 `2026-08-30` 下追加一条：通用演示模式新增候选项准备/编辑/确认流程。

### `tests/`

计划不新增 JS 测试依赖。

可选：如果实现中增加可通过 Node `--check` 验证的独立 JS 文件，使用 `node --check` 做语法验证；后端继续跑现有 Python 测试确认不回归。

## 兼容性和破坏性变更评估

- 饮食 API 不变。
- 饮食聊天、餐食库、Trace、评估路径不变。
- 通用 demo 路由不变，仍是 `#/demo` 和 `#/demo/decision/:id`。
- 旧 localStorage 中已经创建的 demo decision 应继续以 compare 阶段打开。
- 新创建的 demo decision 行为会变化：从直接比较改为先确认候选。这是预期的用户体验增强。
- 不新增依赖，不改构建或运行环境。
- 不改后端 Pydantic schema 和数据库。

## 风险和边界情况

- 旧 demo decision 缺少 `stage` 或 `candidateInput`：加载时必须兼容。
- 用户清空到 0 个候选：保持至少 1 个空草稿行，确认时提示至少需要 2 个候选。
- 用户只填 1 个候选：不能进入比较，提示再补一个备选。
- 用户新增候选缺少 attributes：确认时自动生成演示 attributes，否则排序会全部为 0。
- 用户编辑候选名后 evidence 仍指向旧候选：确认时同步 candidateId，claim 可以保留 fixture 语义或生成通用演示 claim。
- 返回编辑候选后旧 recommendation 可能不再有效：必须清空 recommendation。
- 用户误以为 demo 候选来自真实搜索：候选准备阶段和 evidence source 继续标注演示数据。
- 表单输入需要通过 `escapeHtml()` 渲染，避免把用户输入插入 HTML 时产生问题。
- `change` 事件对 textarea 触发较晚，如需更顺滑可用 `input` 事件；第一版可在确认按钮时读取 DOM 表单，减少状态同步复杂度。

## 验证方案

自动验证：

- `node --check src/choice_agent/static/assets/js/demo.js`
- `node --check src/choice_agent/static/assets/js/app.js`
- `python -m compileall -q src scripts`
- `python -m pytest`

静态行为检查：

- 读取修改后的 `demo.js`，确认新建 decision 默认 `stage = "candidate_input"`。
- 读取修改后的 `app.js`，确认 `demo-complete` 不会在候选未确认时生成结论。
- 读取修改后的 `app.css`，确认候选编辑表单有移动端布局。
- 检查 `README.md` 和 `CHANGELOG.md` 更新。

页面行为验证：

- 打开首页，点击旅行示例，提交后进入候选准备阶段。
- 旅行 demo 候选草稿预填且可编辑。
- 删除候选、新增候选、清空候选均可正常工作。
- 只有 1 个有效候选时点击确认会提示，不能进入比较。
- 至少 2 个有效候选时确认进入候选比较阶段。
- 调整权重后排序更新。
- 排除候选后主推荐不会选择该候选。
- 生成结论展示推荐理由和替代项。
- 返回编辑候选后 recommendation 清空，再确认后重新比较。
- 刷新页面后当前 demo state 能恢复。
- 输入饮食问题仍进入 `#/diet/chat` 并走真实饮食链路。

如浏览器控制不可用，至少完成静态 HTTP 页面加载、JS 语法检查、Node VM 级 demo 函数行为验证和 Python 后端测试，并明确说明未完成真实点击验收。

## 注意事项与技术折衷

- 第一版只编辑候选名称和摘要，不暴露每个维度的数值编辑。这样能满足“候选项需要填”的体验，同时避免把 demo 变成复杂数据表。
- Fixture 仍作为预填候选和演示属性来源，保证无网络、无 API Key 时稳定可跑。
- 候选确认阶段是前端 demo 的体验状态，不写入后端 `DecisionState`，避免提前定义通用后端 API。
- 生成新增候选 attributes 时使用稳定规则，不使用随机数，保证刷新和重现时排序可解释。
- 若实施中发现 `app.js` 继续膨胀明显，可只把纯数据和状态操作放在 `demo.js`，UI 渲染仍留在 `app.js`，不额外引入模块系统。

## Todo

- [x] 扩展 `demo.js` 的 demo state，新增候选准备阶段和旧数据兼容。
- [x] 在 `demo.js` 中新增候选草稿增删改、重置、清空和确认函数。
- [x] 调整 demo 创建逻辑，让新 demo 默认进入候选准备阶段。
- [x] 扩展 `app.js` 的 demo 工作台渲染，新增候选准备表单。
- [x] 增加候选准备相关事件处理，并阻止未确认候选时生成结论。
- [x] 在比较阶段增加“返回编辑候选”入口。
- [x] 补充候选准备表单 CSS 和响应式规则。
- [x] 更新 README 的 Demo Mode 说明。
- [x] 更新 CHANGELOG。
- [x] 执行 diff 检查、JS 语法检查、Python 自动测试和可行的页面行为验证。
## 验证备注

已完成 `node --check src/choice_agent/static/assets/js/demo.js`、`node --check src/choice_agent/static/assets/js/app.js`、`python -m compileall -q src scripts`、`python -m pytest`、Node VM demo 状态流验证，以及本地服务 `http://127.0.0.1:8001/`、`/assets/js/demo.js`、`/assets/js/app.js` HTTP 200 检查。当前环境的 Node REPL / Playwright 启动失败，未完成真实浏览器点击截图验收。
## 范围追加：约束准备

用户继续反馈演示模式中的约束来源也需要更正式。追加目标：新建通用 demo 时先进入约束准备阶段，约束可由 fixture 或领域默认示例预填，用户可以新增、删除、清空和确认；确认约束后再进入候选准备阶段，最后进入比较和生成结论。

追加设计：

- `stage` 增加 `"constraint_input"`。
- 新增 `constraintInput.items`，每项包含 `id`、`sourceConstraintKey`、`label`、`kind`、`value`。
- 新建 demo 默认 `stage = "constraint_input"`、`nextAction = "collect_constraints"`。
- 对没有显式 fixture constraints 的领域，提供领域默认约束草稿，例如 Offer 的“长期发展优先”、学习的“每周可投入时间有限”、购物的“适合高频通勤”。
- 允许 0 个有效约束进入候选准备，因为正式决策不一定都有硬约束；但 UI 要提示至少补充一个会更接近真实决策。
- 比较阶段增加“返回编辑约束”入口，返回后会清空旧 recommendation。

追加 Todo：

- [x] 扩展 `demo.js`，新增约束草稿、约束确认和返回编辑约束能力。
- [x] 调整新建 demo 默认进入约束准备阶段。
- [x] 扩展 `app.js`，新增约束准备表单和相关事件处理。
- [x] 比较阶段增加返回编辑约束入口。
- [x] 补充约束准备表单 CSS。
- [x] 更新 README / CHANGELOG。
- [x] 复跑 JS、Python、状态流和 HTTP 验证。
### 约束流程追加验证

已完成 `node --check src/choice_agent/static/assets/js/demo.js`、`node --check src/choice_agent/static/assets/js/app.js`、`python -m compileall -q src scripts`、`python -m pytest`、Node VM 约束到候选到比较状态流验证，以及本地服务 `/assets/js/demo.js`、`/assets/js/app.js` HTTP 200 检查。