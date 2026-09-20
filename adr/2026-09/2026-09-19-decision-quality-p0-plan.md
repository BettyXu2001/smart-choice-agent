# 决策质量 P0 改进 Plan

日期：2026-09-19

## 目标和成功标准

目标：

1. 最终选择后可复盘实际结果、满意度和是否愿意再次选择。
2. 推荐明确区分匹配分、数据完整度和结论稳健度。
3. 除领域必需信息和歧义纠正外，只展示经敏感性分析后可能改变第一名的问题。

成功标准：

- 旧决策无需迁移即可读取，旧 API 继续有效。
- outcome 可保存、更新和清除一次最新复盘；改选时旧复盘清空。
- 历史区分未选择、待复盘、已复盘。选择满 7 天未复盘时加强提示，用户可提前复盘。
- 通用排序后生成数据完整度、前两名分差、有限扰动稳健度、敏感项和提示。
- UI 明确稳健度不是正确概率，候选分数只叫匹配分。
- Generic、Travel、Shopping 的前置必需信息仍可阻塞。
- 已有候选时，只有合理上下界至少一种会改变第一名才展示一个可选问题。
- 可选问题不清空暂定推荐，不切回 clarifying。
- Diet 现有流程保持通过。

## 架构与逻辑设计

### 1. 结果复盘

在 DecisionOutcome 内新增可选 review：

- status：successful、mixed、unsuccessful、changed。
- satisfaction：可选 1–5。
- would_choose_again：可选布尔值。
- note：可选结果说明。
- recorded_at：复盘时间。

第一版只保留单次最新复盘，不建立时间序列表。

新增接口：

- PUT /api/v1/decision-history/{decision_id}/outcome/review
- DELETE /api/v1/decision-history/{decision_id}/outcome/review

请求包含 revision。服务端继续校验 owner 和 revision；没有 outcome 时拒绝保存。候选或 label 改变时清空旧 review，只修改同一选择的 reason 时保留。

历史摘要派生 review 状态：no_outcome、not_due、due、reviewed。7 天只控制提示强度，不限制提前复盘。第一版不增加通知或后台任务。

### 2. 决策质量摘要

新增 src/choice_agent/decision/quality.py 纯函数模块，生成 DecisionQualityAssessment 并保存到 DecisionState.quality_assessment：

- status：available 或 insufficient_data。
- dataCompleteness：0–1。
- scoreMargin：第一、第二名当前匹配分差。
- robustness：0–1，有限扰动中第一名保持不变的比例。
- robustnessLevel：high、medium、low、unavailable。
- sensitiveCriteria：实际导致换榜的 criterion。
- warnings：缺失、来源限制和不可计算原因。
- scenarioCount：实际场景数。

计算规则：

- 数据完整度按 criterion 权重计算，raw_value 非空才算已提供，只统计前两名。
- 用户输入和 fixture 可算已提供，但 warnings 保留非外部核验语义。
- 每个正权重 criterion 分别测试 0.5 倍和 1.5 倍权重，并重新归一化。
- 缺失占位分别按标准化分 0 和 100 测试。
- robustness 是原第一名保持第一的场景比例；不足两个候选或无有效 breakdown 时不可计算。
- 分层阈值：不低于 0.8 为 high，不低于 0.5 为 medium，其余为 low。
- 敏感项只来自实际换榜场景，不由模型生成。

ComparisonProfile.source_and_rank 和 rerank 在正式排序后更新摘要。What-if 不写回正式摘要。

### 3. 信息价值追问

新增 src/choice_agent/decision/clarification.py，将问题分成：

- 前置阻塞问题：候选不足、Travel 缺出发地/天数、Shopping 缺类别、无法安全应用的歧义纠正。
- 排序后可选问题：针对前两名缺失 criterion 做边界测试后生成。

选择算法：

1. 找出前两名 raw_value 为空的 criterion。
2. 分别按 0 和 100 重算。
3. 至少一个场景改变第一名才具有结论价值。
4. 多个问题满足时，选排名差变化最大的一个。
5. 问题包含候选名、criterion label 和为什么可能改变结论。
6. 没有换榜可能时不生成问题。

结果写入 domain_state.assistance.currentAnalysis.decisionQuestion，包含 key、question、reason、candidateId、criterionKey 和 expectedImpact。missingInfo 优先展示它，但不修改 clarifying_questions、status 或 recommendation。

非必需模型问题不再直接触发阻塞 clarify；安全歧义纠正可继续阻塞，其余必须通过排序后的确定性边界测试。

### 4. 前端表达

Decision Canvas 在当前建议附近展示匹配分、数据完整度、结论稳健度和敏感项，并说明稳健度表示有限条件变化下的排序稳定性，不是 AI 正确概率。

还缺什么关键信息只展示 decisionQuestion 或真实前置问题，移除 Generic 固定的薪资、通勤和工作强度兜底。

历史详情在最终选择下增加结果状态、满意度、是否愿意再次选择和备注表单；历史列表展示待复盘/已复盘。

## 关键流程

新决策：

前置条件检查 → 必要时阻塞追问 → 候选检索与排序 → 质量摘要有限扰动 → 信息价值边界测试 → 推荐、稳健度、最多一个可选问题。

结果复盘：

保存最终选择 → 派生复盘状态 → 用户填写复盘 → owner / revision 校验 → outcome.review 写入 state_json → 历史摘要更新。

## 受影响文件

核心：

- src/choice_agent/schemas.py：新增 review、quality assessment、decision question 和请求/响应字段。
- src/choice_agent/decision/quality.py：新增质量计算。
- src/choice_agent/decision/clarification.py：新增信息价值问题选择。
- src/choice_agent/domains/comparison.py：排序后更新质量和问题，区分阻塞与可选问题。
- src/choice_agent/decision/assistance.py：合并确定性质量和问题，防止模型覆盖。
- src/choice_agent/decision/what_if.py：移除固定 Offer 缺失提示。

API 与前端：

- src/choice_agent/api/routes.py：review 保存/清除、改选清理、复盘状态。
- src/choice_agent/static/assets/js/api.js：review API。
- src/choice_agent/static/assets/js/app.js：历史复盘状态和表单，精确合并现有修改。
- src/choice_agent/static/assets/js/conversation.js：质量摘要、关键问题和匹配分文案。
- src/choice_agent/static/assets/css/app.css：对应样式。

测试与文档：

- tests/test_decision_quality.py：新增质量和换榜测试。
- tests/test_decision_assistance.py：问题价值、最多一个问题、推荐保留。
- tests/test_decision_history.py：review CRUD、owner、revision、改选和旧状态兼容。
- tests/test_frontend_static.py：API 接线和文案，精确合并现有修改。
- README.md、CHANGELOG.md：能力与语义说明。

## 接口与兼容性评估

- 不删除现有路径和字段。
- 新增字段均可选或有默认值，旧 JSON 可读取。
- 不新增数据库列和依赖。
- review 使用 outcome 子资源，不改变原 outcome 请求。
- 通用 ComparisonProfile 新增行为，Diet 保持原有流程。
- 旧记录无质量或 review 时前端降级展示。

## 风险和边界情况

- 单候选、零权重、breakdown 不完整时显示暂不可评估。
- 同分复用当前稳定 tie-breaker，避免伪换榜。
- 0/100 只是边界敏感性测试，UI 不展示为预测值。
- review 更新参与 revision。
- 时间采用项目现有约定，测试覆盖 7 天边界。
- 实施前后检查重叠文件 diff，不覆盖当前未提交修改。

## 验证方案

自动验证：

- python -m pytest tests/test_decision_quality.py tests/test_decision_assistance.py tests/test_decision_history.py tests/test_frontend_static.py
- python -m pytest
- python -m compileall -q src scripts
- node --check 检查改动 JS。
- git diff --check。

行为验证：

- 第一名明显领先：高稳健度且无无价值追问。
- 排名接近且关键值缺失：低/中稳健度，只问一个问题，推荐仍可见。
- 正式重排更新摘要，What-if 不污染摘要。
- outcome 可立即复盘，满 7 天未复盘显示待复盘。
- review 保存、更新、清除和改选清理均正确递增 revision。
- 旧记录正常降级。

## 注意事项与技术折衷

- 第一版只有最新复盘；真实使用需要 7/30 天多次随访时再设计 outcome event 表。
- 第一版只在历史页提示，不引入调度和通知。
- 稳健度是可解释的确定性敏感性，不是统计校准置信度。
- 满意度不自动改写资料或权重。
- 网页 claim 独立事实核验留在 P1 范围。

## Todo

- [x] 扩展 review、quality assessment、decision question 与历史 Schema，并验证旧状态。
- [x] 实现质量评估纯函数和专项测试。
- [x] 实现信息价值问题并接入 ComparisonProfile 与 assistance。
- [x] 移除无敏感性依据的固定缺失提示，保留必需追问。
- [x] 新增 review API、复盘状态和并发/owner 校验。
- [x] 更新 Decision Canvas 的质量摘要和问题交互。
- [x] 更新历史列表/详情的复盘状态和表单。
- [x] 补齐后端、前端和旧记录兼容测试。
- [x] 更新 README 与 CHANGELOG，保护现有未提交修改。
- [x] 检查最终 diff，运行专项与全量验证，逐项确认 Todo。