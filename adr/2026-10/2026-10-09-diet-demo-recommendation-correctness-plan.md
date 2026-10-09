# 饮食 Demo 推荐正确性 Plan

日期：2026-10-09

状态：待用户审查，尚未批准实施。依据同目录 `2026-10-09-diet-demo-recommendation-correctness-research.md`。

## 目标和成功标准

目标：保持现有 Diet API、DecisionState、反馈闭环和餐食库边界，严格按 1→7 的顺序修复真实 Demo 暴露的推荐正确性与交互问题。

成功标准：

- 每一项先补失败用例，再做最小实现，再执行对应局部验证；通过后才勾选该项并进入下一项。
- 推荐理由、候选标签、score breakdown 和结构化槽位互相一致。
- 首页“今晚吃什么”用同一案例可稳定得到合理公共候选。
- 快捷回复与来源切换均只产生一次用户动作和一次预期系统响应。
- Diet 专项与全量回归通过，不破坏旅行/通用决策、三餐、风险、反馈、Trace 和 Evaluation。
- 不新增依赖、数据库迁移或 API 路径，不覆盖当前工作区已有改动。

## 实施顺序和设计

### 1. 修复推荐理由与候选标签冲突

- 在 `agents/diet.py` 增加最小的候选匹配摘要 helper，输入 `SlotBundle + Candidate/Meal attributes`，输出真实命中和未命中的字段值。
- 规则理由只描述真实交集；候选仅命中“晚餐”而未命中“清淡”时，明确说明适合餐次但未匹配清淡目标。
- 模型解释输入补充候选 attributes、score breakdown 和规则匹配摘要；模型输出仍按候选 ID 白名单覆盖，并校验不得声称不存在的显式标签，否则回退规则理由。
- 增加解释测试，覆盖土豆炖牛肉标签为“补能、湘菜、辣”但需求为“清淡”的场景。

涉及：`src/choice_agent/agents/diet.py`、`tests/test_orchestrator.py`，必要时 `tests/test_diet_hybrid_recall.py`。

### 2. 保留“清淡但不寡淡”的关键口味语义

- 在 `domains/diet/rules.py` 加入保守平衡口味识别。
- 仅识别明确短语，如“清淡但不寡淡”“不想太寡淡”“清淡但有味道”；当槽位选项确实包含“咸鲜”时，追加 `taste=咸鲜`。
- 保留原有 `healthGoal=清淡`，不得把“不寡淡”误解析为排除清淡或泛化为麻辣/重口味。
- 通过 `understand_fields()` 现有 conversation-confirmed 路径持久化，不新增字段。

涉及：`src/choice_agent/domains/diet/rules.py`、`tests/test_rules.py`、`tests/test_diet_panel.py`。

### 3. 修复首页默认候选源质量不足

- 将首页新建饮食会话的默认来源从 `PERSONAL` 调整为 `PUBLIC`，与 `ChatRequest` 和 Repository 的默认值一致。
- 不自动混合个人与公共库，不改变用户显式选择“个人餐食”的含义；历史会话继续从服务端恢复原来源。
- 首页进入饮食 Demo 后应直接得到公共库中至少两个正匹配候选；用户切换个人库仍只查询个人数据。

涉及：`src/choice_agent/static/assets/js/conversation.js`、`tests/test_frontend_static.py`、`tests/test_orchestrator.py`。

### 4. 生成可区分候选的排序解释

- 复用第 1 项匹配摘要，按餐次、健康目标、口味、场景等实际命中生成候选专属理由。
- 对前几名相同分数，理由分别展示各自额外标签或便利特征；不伪造“第一名明显更优”。
- 最多提示一个重要未命中偏好，避免理由过长。
- 模型关闭或失败时，确定性理由也必须可读且候选之间有差异。

涉及：`src/choice_agent/agents/diet.py`、`src/choice_agent/prompts/diet/recommend-response.txt`、`tests/test_orchestrator.py`。

### 5. 修正饮食匹配分口径与展示语义

- 仅修改 `DietCriterionEvaluator`：用户本轮未请求的 criterion 返回零权重 contribution，不进入总分分母；已请求字段仍按命中比例计算。
- 主流程百分比改为“本轮已表达条件匹配度”。例如晚餐和清淡均命中时为 100%，只命中其一时为 50%。
- 保留旧 `DecisionEngine` 及其兼容测试，避免扩大为全局评分重构。
- 前端将餐食卡“匹配”改为“条件匹配”，并提供简短口径说明；零分仍应可见。

涉及：`src/choice_agent/domains/diet/evaluator.py`、`src/choice_agent/static/assets/js/app.js`、Diet evaluator 专项测试、`tests/test_frontend_static.py`。

### 6. 让饮食快捷回复一次点击即发送

- `quick-message` 点击后直接复用 `conversation.submitChat()` / `sendChatMessage()` 的现有发送路径。
- 保留 draft、pending、retry、revision、幂等和 busy 防重逻辑；不新增第二套请求实现。
- 一次点击只创建一个用户消息和一个请求；失败时保留原快捷文本供重试。

涉及：`src/choice_agent/static/assets/js/app.js`、`src/choice_agent/static/assets/js/conversation.js`（仅必要导出/入口）、`tests/test_frontend_static.py`，并做真实浏览器点击验证。

### 7. 去除来源切换后的重复状态消息

- 将 `set_source` 的用户动作文本与 assistant 确认文本分离：历史中记录“切换到公共餐食库”，响应中只出现一次“已切换为公共餐食库”。
- 保留 revision、command receipt、Trace、候选重算和数据源状态更新。
- 不全局重写所有 panel command；只抽取满足来源切换所需的最小命令结果结构，避免影响字段编辑文案。

涉及：`src/choice_agent/orchestration/diet.py`、`tests/test_diet_panel.py`。

## 关键流程

```text
首页饮食输入
  → 公共餐食库默认召回
  → 规则/模型理解槽位
  → 澄清餐次
  → 仅按已表达字段计算条件匹配度
  → 候选真实命中摘要
  → 差异化推荐理由
  → 快捷回复 / 反馈 / 来源切换
  → versioned DietOrchestrator 写入与 Trace
```

## 受影响文件

预计修改：

- `src/choice_agent/domains/diet/rules.py`
- `src/choice_agent/domains/diet/evaluator.py`
- `src/choice_agent/agents/diet.py`
- `src/choice_agent/prompts/diet/recommend-response.txt`
- `src/choice_agent/orchestration/diet.py`
- `src/choice_agent/static/assets/js/conversation.js`
- `src/choice_agent/static/assets/js/app.js`
- `tests/test_rules.py`
- `tests/test_orchestrator.py`
- `tests/test_diet_panel.py`
- `tests/test_diet_hybrid_recall.py`（仅解释路径需要时）
- `tests/test_unified_decision.py`（或一个现有 Diet evaluator 测试文件）
- `tests/test_frontend_static.py`
- `CHANGELOG.md`

不计划修改数据库模型、迁移、API 路由、通用 RankingEngine、Travel/Shopping/Generic Profile 或依赖配置。

## 兼容性和破坏性变更评估

- API 路径和响应字段不变。
- `matchScore` 字段继续为 0～1，但 Diet 主流程语义从“七维固定平均”变为“本轮已表达条件匹配度”；这是预期正确性修复。
- 首页新饮食会话默认从公共库开始；已存在会话及用户显式来源选择不变。
- 规则新增“咸鲜”映射只在现有选项支持时生效，不创建未知槽位值。
- 推荐排序可能因分数重新归一化出现并列关系变化，但命中数量的相对顺序应保持；稳定 tie-breaker 和选择策略继续生效。

## 风险和边界情况

- “不寡淡”仍有主观性；首版只映射到现有“咸鲜”，不推断辣、酸、甜或具体菜系。
- 条件匹配 100% 不表示营养正确率、模型置信度或用户一定喜欢，UI 必须写清口径。
- 用户主动切回个人库时应诚实显示低匹配和未命中项，而不是自动混入公共库。
- 模型可能返回与真实标签不一致的自由文本；接受模型 reason 前需要做显式标签一致性校验，否则回退确定性理由。
- 前端文件与当前未提交的通用工作流修复重叠，必须逐段 patch，并在每次重要写入后重新读取。

## 验证方案

### 每项局部验证

1. 理由真实性：断言未命中“清淡”的候选理由不含“符合清淡”。
2. 语义保留：断言 `healthGoal=清淡` 且 `taste=咸鲜`，来源为 conversation-confirmed。
3. 默认来源：静态测试 + 浏览器从首页启动，断言首轮公共候选不少于两个，显式个人切换仍有效。
4. 差异化解释：断言三个公共候选理由不全相同，且只引用各自标签。
5. 匹配分：测试未请求字段不进入分母、全命中为 1、半命中为 0.5、无请求边界明确。
6. 快捷回复：静态接线和真实点击均确认一次点击发送、只新增一条 user message。
7. 来源消息：编排测试断言 user/assistant 文案角色正确且完成态只出现一次。

### 综合验证

- `python -m pytest tests/test_rules.py tests/test_orchestrator.py tests/test_diet_panel.py tests/test_diet_hybrid_recall.py tests/test_unified_decision.py tests/test_frontend_static.py`
- `python -m pytest`
- `python -m compileall -q src`
- `node --check src/choice_agent/static/assets/js/app.js`
- `node --check src/choice_agent/static/assets/js/conversation.js`
- `git diff --check`
- 检查最终 diff、Todo、调试代码和计划外文件。
- 使用独立临时数据库真实运行“今晚吃什么”网页流程：首轮输入、快捷澄清、公共推荐、标签/理由、匹配分、不合适、个人/公共切换和会话恢复。

如果外部模型或 Web Search 未配置，使用 DisabledProvider 验证确定性路径，并明确记录外部路径未验证；不得宣称全部外部联通通过。

## CHANGELOG

实施验证后，在现有 `### 2026-10-09` 下追加一条精简记录，不重复创建日期标题。

## Todo

- [ ] 1. 修复推荐理由与候选标签冲突，并补真实性测试。
- [ ] 2. 保留“清淡但不寡淡”的结构化口味语义，并补规则/状态测试。
- [ ] 3. 将首页新饮食会话默认来源调整为公共库，并验证显式个人来源不受影响。
- [ ] 4. 生成候选专属、可区分且仅引用真实标签的解释。
- [ ] 5. 将 Diet 匹配分改为仅按本轮已表达条件归一化，并更新 UI 语义。
- [ ] 6. 让饮食快捷回复一次点击直接发送且不重复请求。
- [ ] 7. 分离来源切换的用户动作与系统确认，去除重复完成态消息。
- [ ] 执行逐项局部验证、饮食专项回归和完整测试。
- [ ] 执行 Python/JS 语法、diff 与最终范围检查。
- [ ] 用独立临时数据库完成真实浏览器回归。
- [ ] 更新 `CHANGELOG.md` 并记录外部模型/Web Search 未验证项。