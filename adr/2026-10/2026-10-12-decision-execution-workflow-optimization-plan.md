# 决策增量执行与工作流优化 Plan

日期：2026-10-12

状态：已于 2026-10-12 获用户明确批准实施。依据同目录 `2026-10-12-decision-execution-workflow-optimization-research.md`。

## 目标和成功标准

目标：在不改变外部 API、数据库 schema 和确定性排序原则的前提下，把当前固定完整流水线升级为按本轮变化范围增量执行的决策内核，并按 P0 → P1 → P2 顺序完成结果校验、Demo 稳定性、澄清 / 状态 / Trace 一致性和真实回归评测。

成功标准：

- Explain-only 轮次没有 CandidateAgent、Provider Search、Evidence 重建或 Ranking。
- 偏好 / 权重 / 硬约束 / 排除 / 候选事实更新复用 candidatePool，并执行 Rank → Critic → Explain → Final Validation。
- 检索敏感字段变化、候选池缺失、显式刷新执行完整候选刷新。
- What-if 不修改正式字段、候选、Evidence、SearchRun、Recommendation 和正式状态，只保存独立分析结果。
- Demo 在存在浏览器模型 / 搜索配置时仍保持 fixture + rules 确定性结果。
- 非空正式推荐通过统一不变量校验；非法结果回滚并留下 FAILED Trace。
- DecisionStatus、progress 和 Trace 对同一执行路径表达一致。
- Diet / Travel / Shopping / Generic 现有 API、revision、receipt、fallback、反馈和评测兼容。
- core regression 与 fault injection 通过，并新增执行路径专项 Case / assertions。

## 总体设计

```text
Request / Command
  -> Intent + Understanding
  -> Blocking Clarification Policy
  -> ExecutionPlanner
       FULL | REFRESH | RERANK | EXPLAIN_ONLY | WHAT_IF
  -> Shared StageRunner executor
  -> Candidate / Recommendation invariant validation
  -> Persist Decision + Receipt + Trace in one transaction
```

执行计划是内部确定性类型，不进入公开 API。自然语言消息和结构化命令都映射到同一类型。

## P0：增量执行、Demo 确定性与最终结果校验

### 1. 新增内部 ExecutionPlan

新增 `src/choice_agent/decision/execution.py`：

- `ExecutionMode`：`full`、`refresh`、`rerank`、`explain_only`、`what_if`；
- `ExecutionPlan`：包含 mode、reason、changed_fields、candidate_pool_available、skip_reasons；
- `plan_execution(profile, context)`：比较 `official_baseline` 与当前 decision，读取 `turn_intent`、`is_hypothetical`、候选池、约束、权重、排除、候选事实和搜索上下文；
- `CommandMutation.mode` 到 ExecutionMode 的映射 helper。

规则优先级：

1. 新建 / 无 baseline → `full`；
2. What-if → `what_if`；
3. 阻塞性澄清由 StageRunner 提前返回；
4. 候选池缺失、显式刷新、检索敏感字段或搜索模式变化 → `refresh`；
5. 字段 / 权重 / 约束 / 排除 / 候选事实变化 → `rerank`；
6. explain 且无业务状态变化 → `explain_only`；
7. 其他可比较消息默认 `rerank`，不默认重新搜索。

为 `DomainProfile` 增加内部 hook：

- `retrieval_sensitive_fields()`；
- 必要时 `supports_incremental_execution(context)`，首批 Travel / Shopping / Generic 返回 true，Diet 默认 false。

### 2. 扩展 StageRunner 为按计划执行

修改 `src/choice_agent/agents/stages.py` 和 `orchestration/unified.py`：

- 保留 Intent、Understanding、Safety、Adjustment、Clarification 的既有顺序；
- 在候选阶段前生成 ExecutionPlan；
- `refresh/full` 调用 source_and_rank / compose；
- `rerank` 调用 rerank / compose；
- `explain_only` 跳过候选和排序，直接执行 Explanation 与必要的 post-safety；
- `what_if` 跳过正式候选修改，调用现有 shadow analysis 解释路径；
- 对每个跳过阶段写明确 Trace skipped node，不伪造执行成功。

现有 `run()` / `recompute()` 暂保留兼容签名；内部委托统一执行函数，待调用方迁移完成后再判断是否删除重复分支。

### 3. 自然语言和命令共用计划

修改 `orchestration/generic.py`：

- `_run()` 将 baseline 传入统一执行计划；
- `command()` 把 `CommandMutation` 映射到 ExecutionPlan，再调用同一执行入口；
- 保持 request / command receipt、revision、事务和响应格式不变；
- `speech_text`、display blocks 与原路径兼容。

### 4. 固定 Demo 确定性运行配置

修改 `orchestration/generic.py` 的 stage data / provider 选择：

- `demoMode=true` 时强制使用 `DisabledProvider`；
- 创建时把 Demo 搜索模式规范为 fixture；
- Trace metadata 记录 `executionProfile=demo_deterministic`；
- 普通正式决策继续使用用户配置的模型和 searchMode。

不修改前端 API Key 设置，也不删除真实模型模式。

### 5. 新增最终推荐不变量校验

新增或扩展 `src/choice_agent/decision/validation.py`：

- 校验 candidate IDs 唯一、score 范围；
- recommendation primary / alternatives 必须来自当前 active candidates；
- 不得命中 `excluded_candidates`；
- 推荐候选不得违反当前硬约束；
- RecommendationPoint / score breakdown 引用的 Evidence ID 必须存在；
- 无有效候选时允许 recommendation 为空，但不得引用已排除候选；
- 校验失败抛出明确业务异常，触发现有 rollback / FAILED Trace。

StageRunner 在排序后保留现有 Critic；Explanation 后增加 `Recommendation Validation` operation，再进入 post-safety / commit。

### 6. P0 测试

新增 / 修改：

- `tests/test_execution_planner.py`：纯计划矩阵；
- `tests/test_decision_assistance.py`：解释、偏好、约束、事实、What-if 多轮行为；
- `tests/test_generic_orchestrator.py`：AgentRun / Trace 证明跳过或复用；
- `tests/test_trace_observability.py`：planned / executed path、skip reason；
- `tests/test_decision_validation.py`：推荐不变量；
- `tests/test_runtime_model_settings.py`：Demo 忽略 runtime model，正式请求不受影响；
- 相关既有 unified / API / streaming 测试。

P0 完成标准：局部测试通过，旅行 / Offer / Shopping Demo 行为验证通过，Todo 勾选后再进入 P1。

## P1：澄清、状态、Progress 与 Trace 一致性

### 7. 明确两类问题

复用 `select_decision_question()`，不另建评分系统：

- Blocking clarification：搜索前缺少领域必需字段，由 Profile `needs_clarification / clarification_prompt` 决定；
- Optional decision question：排序后用于提升结论质量，继续写入 `assistance.decisionQuestion`，不改变 status 为 clarifying。

新增结构化 `clarificationReason` / `questionKind` 到可选 domainState 或 Trace output，不修改公开必填 schema。

Travel / Shopping 的阻塞问题只询问当前缺失字段；Generic 仍要求至少两个候选；Diet 保持现有 required slot 规则。

### 8. 统一阶段语义

在 `decision/execution.py` 或相邻内部模块定义阶段常量 / 映射，供 StageRunner、progress 和 Trace 使用：

```text
understanding -> clarifying -> searching -> comparing -> explaining -> decided
```

- REFRESH 在真实 Provider 调用前转换为 SEARCHING；
- 排序前 / 完成后保持 COMPARING；
- 合法正式 Recommendation 完成后转换为 DECIDED；
- EXPLAIN_ONLY 保持正式 status，不伪造搜索 / 比较；
- WHAT_IF 不改变正式 status；
- Clarification 保持 CLARIFYING。

旧 DecisionState 仍可加载；不新增数据库列。

### 9. 扩展 Trace 摘要

修改 `services/trace.py`：

- metadata / turnSummary 增加 `plannedPath`、`executedPath`、`skipReasons`；
- 记录 candidate pool reused / refreshed；
- 记录 provider call count 与是否为 deterministic demo；
- 保持 schema 向后兼容。

前端 Developer Trace 仅在需要时增加这些摘要字段；普通用户 Decision Canvas 不暴露 raw payload。

### 10. P1 测试

- required clarification 与 optional question 不混淆；
- Explain-only / What-if status 不跳到 SEARCHING；
- refresh 流式 progress 顺序与 Trace 一致；
- rerank 不发 searching_candidates；
- 旧 decision JSON 缺少新增可选字段时正常加载；
- streaming final / error 行为不变。

## P2：共享内核收敛与评测加固

### 11. Diet / Generic 共享执行语义

不合并外部 API。实施顺序：

1. Diet 复用 ExecutionMode、结果校验和 Trace path 字段；
2. 保持 Diet Intent / Adjustment / Composition / hybrid recall 决策权；
3. 为 Diet 的“为什么”“换一个”“反馈不合适”“三餐计划”“健康风险”建立专项计划矩阵；
4. 只有全部 characterization tests 通过后，才让 Diet 的安全分支接入增量执行；否则保持 `full`，但继续使用共享校验和可观测性。

不为了形式统一抽取通用事务基类；只有 Generic / Diet 存在完全相同且已有测试覆盖的代码时，才提取小型 helper。

### 12. 扩充 Regression Dataset 和确定性断言

扩展 `evaluation/fixtures.py`、`evaluation/runner.py` 和 deterministic evaluator：

- Explain-only：Trace 不包含 Candidate Retrieval / Ranking；
- Rerank：Trace 包含 candidatePool reused，不包含 Search provider call；
- Refresh：Trace 包含 Candidate Retrieval / Evidence；
- What-if：正式 fields / recommendation / searchRuns 不变；
- Demo deterministic：providerCallCount 为 0，source=fixture；
- Invalid recommendation：execution error、rolled_back、Trace 定位 Recommendation Validation；
- Diet characterization：换一批、反馈、计划和风险行为不回归。

保持 Baseline / Candidate 可比性、deterministic-only Gate 和 fault-injection v2 现有语义。

### 13. 文档和迁移说明

更新：

- `README.md`：说明增量执行模式与 Demo 确定性边界；
- `docs/migration-matrix.md`：记录自然语言和命令已共用 ExecutionPlan；
- `CHANGELOG.md`：在 `### 2026-10-12` 下精简记录用户可感知的延迟、稳定性和 Trace 改进，同日不重复标题。

## 受影响文件

预计新增：

- `src/choice_agent/decision/execution.py`
- `src/choice_agent/decision/validation.py`（如无可复用同类文件）
- `tests/test_execution_planner.py`
- `tests/test_decision_validation.py`

预计修改：

- `src/choice_agent/agents/stages.py`
- `src/choice_agent/orchestration/unified.py`
- `src/choice_agent/orchestration/generic.py`
- `src/choice_agent/orchestration/diet.py`
- `src/choice_agent/domains/profile.py`
- `src/choice_agent/domains/comparison.py`
- `src/choice_agent/domains/travel.py`
- `src/choice_agent/domains/shopping.py`
- `src/choice_agent/domains/generic.py`
- `src/choice_agent/services/trace.py`
- `src/choice_agent/evaluation/fixtures.py`
- `src/choice_agent/evaluation/runner.py`
- 相关 deterministic evaluator / schema（仅新增断言需要时）
- 相关测试、`README.md`、`docs/migration-matrix.md`、`CHANGELOG.md`

前端只在 Developer Trace 或 Demo 边界提示确有缺口时精确修改，不重做已完成的 Decision Canvas。

## 兼容性和破坏性变更评估

- 不新增或删除 API 路径。
- 不新增数据库表或迁移。
- 不新增依赖。
- response schema 只允许可选字段增量，现有字段语义不变。
- revision、receipt、owner 校验和事务边界保持不变。
- Demo 行为有意变为完全确定性；正式决策模型能力不变。
- 自然语言后续轮次的 AgentRun / Trace 数量会减少，这是预期行为变化。
- Diet 外部 API 和 MealResponse 保持兼容。

## 风险和边界情况

- 解释中夹带明确字段修改时，planner 必须以结构化 diff 为准升级执行模式。
- 候选池来自旧数据或缺失时，rerank 必须自动升级 refresh。
- Web Search 检索敏感字段不能误判为纯重排。
- What-if 必须验证 searchRuns、sources、evidence、candidatePool 等正式数据也不变，不能只检查字段和 recommendation。
- 最终校验器需要支持合法空推荐、澄清和风险中断。
- Diet 分支复杂，不能为追求统一而改变 hybrid recall、反馈和计划逻辑。
- Trace 新字段不能泄漏 API Key、prompt 原文中的敏感字段或用户资料；继续复用 `_redact()`。

## 验证方案

### 每个批次的局部验证

- `python -m pytest` 运行该批次新增和直接受影响测试；
- `python -m compileall -q src`；
- 如修改前端，运行对应 `node --check` 与 `tests/test_frontend_static.py`；
- `git diff --check`；
- 重新读取重要写入位置确认真实落盘。

### 完整自动验证

- `python -m pytest`
- `python -m compileall -q src scripts`
- 相关 JS `node --check`
- `git diff --check`
- 搜索 `TODO|console.log|debugger|pass$|...`，排除占位和调试代码。

### 行为验证

至少真实运行：

1. Travel：模糊输入 → 澄清 → 完整候选 → 偏好更新 rerank → 为什么 explain-only → What-if；
2. Offer：稳定偏好 → 候选事实顾虑 → 解释 → 硬条件排除；
3. Shopping：预算重排、用途 / 类别变化刷新；
4. Diet：推荐、换一批、反馈不合适、三餐计划、健康风险；
5. Demo：即使浏览器配置模型 / search key，结果和 provider call 仍确定；
6. Revision conflict、request replay、Web auto fallback、严格 web failure。

## 实施暂停条件

出现以下任一情况时暂停后续批次、更新 Plan，并在涉及重要设计变化时重新请求批准：

- 现有 What-if 无法在不改 schema / API 的情况下避免正式搜索状态变化；
- Profile 无法可靠声明检索敏感字段；
- Diet 接入共享 ExecutionMode 会改变兼容响应或 hybrid recall；
- 推荐校验器与合法的模型 / 规则解释存在不可消除冲突；
- 完整测试发现与本 Plan 无关的现有失败，无法区分回归。

## Todo

### P0

- [ ] 新增纯规则 ExecutionMode / ExecutionPlan 与计划矩阵。
- [ ] 为 Travel / Shopping / Generic 声明检索敏感字段和增量执行能力。
- [ ] 让 StageRunner 支持 full / refresh / rerank / explain-only / what-if。
- [ ] 让自然语言消息与结构化命令共用执行计划。
- [ ] 将 Demo 固定为 fixture + rules 确定性执行配置。
- [ ] 新增最终 Recommendation 不变量校验并接入 rollback / Trace。
- [ ] 完成 P0 专项测试、局部验证和行为验证。

### P1

- [ ] 明确 blocking clarification 与 optional decision question 的结构化语义。
- [ ] 统一 DecisionStatus、progress 和 Trace 阶段映射。
- [ ] Trace 增加 plannedPath / executedPath / skipReasons / candidatePool 使用摘要。
- [ ] 完成 P1 专项测试、流式验证和旧状态兼容验证。

### P2

- [ ] 让 Diet 复用 ExecutionMode、最终校验和 Trace path，同时保护领域特有分支。
- [ ] 在 characterization tests 证明安全后，选择性启用 Diet 增量执行。
- [ ] 为所有执行模式增加真实 Orchestrator Regression Cases 和确定性断言。
- [ ] 运行 core regression、fault injection 和 Baseline / Candidate 兼容检查。
- [ ] 更新 README、migration matrix 和 CHANGELOG。
- [ ] 执行完整测试、编译、JS 语法、diff 和真实行为验证。
- [ ] 检查最终 diff、逐项核对 Todo，并说明任何未验证项或剩余风险。