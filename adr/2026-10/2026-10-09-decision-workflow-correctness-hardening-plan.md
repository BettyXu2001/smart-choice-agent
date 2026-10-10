# 决策工作流正确性加固 Plan

日期：2026-10-09

状态：已于 2026-10-10 完成实施与验证。用户于 2026-10-09 明确回复“实施”批准本 Plan。依据同目录 `2026-10-09-decision-workflow-correctness-hardening-research.md`。

## 目标和成功标准

目标：保留当前 Decision Canvas、现有 API 和确定性排序架构，按 1→9 的顺序修复 Demo 暴露的状态副作用、偏好遗忘、路由冲突、阶段矛盾和交互闭环问题。

成功标准：

- 正式状态只在用户明确表达修改或点击采用时变化。
- What-if、解释问句、澄清回答和正式字段编辑有不同且可测试的语义。
- 页面对阶段、执行来源、质量和数据边界的描述与真实状态一致。
- 九项改进均有专项测试；旅行 Demo 按原案例完整回归。
- 不新增依赖、数据库迁移或新 API 路径。

## 实施顺序和设计

### 1. 修复正式修改与假设分析混用

- 将 `buildQuickFollowupPrompts()` 从字符串列表改为包含 `label / prompt / kind / scenarioId` 的描述。
- “为什么不选 X”继续走解释 chat；预算等假设必须带明确值并走现有 what-if handler。没有当前预算时不生成预算假设。
- `hypothetical()` 增加“会怎样 / 会不会改变”等保守兜底，但显式动作模式仍是主路径。
- 验证预算 What-if 后正式字段、推荐和 `currentAnalysis` 不变，结果只写入 `whatIfAnalysis`。

涉及：`conversation.js`、`assistance.py`、`test_decision_canvas.py`、`test_frontend_static.py`。

### 2. 修复已确认偏好被后续输入覆盖

- 新增 priority token 规范化和合并 helper。
- 普通补充追加新偏好；“改成 / 只看重 / 以 X 为主”执行替换；“不再优先 / 取消”移除指定偏好。
- 面板 `update_fields` 和经过校验的模型显式纠正保持覆盖语义；手工 criterion weight 继续优先。
- `assistance.changes` 记录新增、移除和替换，供变化解释使用。

涉及：`assistance.py`、必要时 `conversation.py`、`test_general_conversation.py`、`test_decision_assistance.py`。

### 3. 修复完整流程链接与 hash 路由冲突

- 将锚点改为 `button + data-diet-action`。
- handler 展开 `#generalDetailsPanel` 并滚动定位，不修改 `location.hash`。
- 验证点击后仍停留在 `#/decisions/:id`，详情可见，前进后退不受影响。

涉及：`conversation.js`、`app.css`、`test_frontend_static.py`。

### 4. 统一缺口、追问和阶段状态

- 新增单一 `decisionProgressView(decision)` 或等价 helper。
- `status=clarifying + clarifyingQuestions` 是阻塞澄清唯一来源。
- 比较后的 `decisionQuestion / currentAnalysis.question` 标记为“可提升结论质量”，不再与阻塞缺口混用。
- `workflowStatus()`、缺口文案和阶段提示统一读取该 helper。

涉及：`conversation.js`、`app.js`、`test_frontend_static.py`，必要时补 `test_general_conversation.py`。

### 5. 按真实执行路径展示模型、规则与降级

- 从 `currentAnalysis.mode` 显示 `model / rules / rules_fallback`。
- 结合 `interpretationWarning` 显示模型理解、规则理解或模型失败后的规则降级。
- 过滤和排序固定标记为规则；来源继续读取 `source.mode`。
- demo 文案改为“模型可用于理解和解释；未配置或失败时规则降级”。

涉及：`conversation.js`、`app.js`、`test_frontend_static.py`。

### 6. 重构质量指标语义

- “匹配分”改为“当前排序分”，明确不是成功率或置信度。
- “数据完整度”改为“评分字段覆盖”，说明统计边界。
- 从 `source.mode / realTime / warnings` 派生定性“来源可靠性”和“数据时效”。
- 保留稳健度及其有限条件扰动说明，不修改质量 schema。

涉及：`conversation.js`、`app.js`、`app.css`、`test_frontend_static.py`。

### 7. 增加结构化澄清快捷回答

- 澄清状态下根据 `conversationFields` 渲染缺失且可编辑的字段；Travel 首批覆盖 departure、days，并允许同时填写 budget、maxTransitHours、priority。
- label、type、unit 复用现有 field metadata。
- 只提交非空字段，通过现有 `update_fields` command 原子更新；自然语言输入继续保留。

涉及：`conversation.js`、`app.css`、`test_frontend_static.py`、`test_general_conversation.py`。

### 8. 降低首屏信息密度

- 首屏固定：当前建议、两个关键理由、主要代价、最可能改变结论的条件。
- 阶段和来源保留紧凑摘要；权重、完整质量、条件编辑、候选依据和完整流程进入可展开区域。
- 不删除能力，不新增布局系统，保持移动端 chat / canvas pane。

涉及：`conversation.js`、`app.css`、`test_frontend_static.py`。

### 9. 让敏感性分析支持试算与采用

- shadow decision 完成 What-if 后，对比正式 `conversationFields`，生成白名单 `proposedFields`。
- 仅包含已有 field definition 中值发生变化且可校验的字段，不复制候选、Evidence、事实、revision 或 recommendation。
- 前端始终显示“仅试算”；有安全差异时显示“采用这些条件”，通过 `update_fields` 正式提交。
- 天气等不可映射假设不显示采用按钮；正式更新后旧 What-if 标记 stale。

涉及：`assistance.py`、必要时 `what_if.py`、`conversation.js`、`test_decision_canvas.py`、`test_decision_assistance.py`、`test_frontend_static.py`。

## 受影响文件

预计修改：

- `src/choice_agent/decision/assistance.py`
- `src/choice_agent/decision/conversation.py`（仅偏好规范化需要时）
- `src/choice_agent/decision/what_if.py`（仅字段差异 helper 需要时）
- `src/choice_agent/static/assets/js/conversation.js`
- `src/choice_agent/static/assets/js/app.js`
- `src/choice_agent/static/assets/css/app.css`
- `tests/test_decision_canvas.py`
- `tests/test_decision_assistance.py`
- `tests/test_general_conversation.py`
- `tests/test_frontend_static.py`
- `CHANGELOG.md`

不计划修改数据库模型、迁移、API 路由或依赖。

## 兼容性和破坏性变更评估

- API 路径和主要 response schema 不变。
- `whatIfAnalysis` 增加可选 `proposedFields`，属于向后兼容扩展。
- `priority` 仍是字符串，内容可能从单值变成规范化多值文本。
- 自然语言、命令编辑和手工权重继续可用。
- 用户可见行为会变化：假设问句不再直接改正式推荐，属于预期修复。

## 风险和边界情况

- 偏好语言存在歧义；首版只处理明确关键词，无法可靠判断时保持旧偏好并提示编辑条件。
- “采用假设”只支持可验证字段，不支持一键采用天气、事实或候选级假设。
- 结构化澄清首批复用现有 field metadata，不建立新表单 schema。
- 页面层级调整需真实浏览器验证移动端高度和滚动。
- 当前工作区有重叠未提交前端改动，实施时必须逐段 patch，并在每次重要写入后重新读取。

## 验证方案

局部验证：

- `python -m pytest tests/test_decision_canvas.py tests/test_decision_assistance.py tests/test_general_conversation.py tests/test_decision_quality.py tests/test_frontend_static.py`
- `node --check src/choice_agent/static/assets/js/conversation.js`
- `node --check src/choice_agent/static/assets/js/app.js`
- `python -m compileall -q src`

完整验证：

- `python -m pytest`
- `git diff --check`
- 最终 diff 范围检查。

行为验证使用原旅行 Demo：确认偏好保持、解释追问无副作用、What-if 只试算、采用后才正式变化、详情入口不改路由，以及阶段、执行模式、字段覆盖和来源文案一致。

## CHANGELOG

这些修改包含用户可感知的 Bug 修复和核心流程行为调整，需要在现有 `### 2026-10-09` 标题下追加精简记录，不重复创建日期标题。

## Todo

- [x] 1. 将假设类快捷问句接入现有 What-if 隔离路径，并补正式状态不变测试。
- [x] 2. 实现偏好增量合并、明确替换与移除语义，并补多轮状态测试。
- [x] 3. 将完整流程入口改为不修改 hash 路由的展开与滚动操作。
- [x] 4. 统一缺口、追问、决策问题和流程阶段的前端状态派生。
- [x] 5. 按 `model / rules / rules_fallback` 与真实数据源展示执行路径。
- [x] 6. 将排序分、评分字段覆盖、来源可靠性和数据时效分开表达。
- [x] 7. 增加复用 `conversationFields + update_fields` 的结构化澄清表单。
- [x] 8. 调整 Decision Canvas 首屏层级，保留四个核心信息块并折叠深层细节。
- [x] 9. 为可安全映射的 What-if 增加 `proposedFields` 和“采用这些条件”闭环。
- [x] 补充与更新相关后端行为测试、前端静态测试和回归测试。
- [x] 执行局部测试、完整测试、JS 语法、Python 编译、diff 检查和真实浏览器行为验证。
- [x] 在 `CHANGELOG.md` 的现有 2026-10-09 条目下记录用户可见修复。
