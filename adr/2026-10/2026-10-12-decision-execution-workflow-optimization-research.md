# 决策增量执行与工作流优化 Research

日期：2026-10-12

## 当前需求和研究范围

用户要求按照既定顺序完成当前决策流程的全部优化。本轮研究聚焦三个连续层级：

1. P0：让自然语言轮次按实际变化范围选择完整执行、候选刷新、候选池重排、只解释或 What-if，而不是默认重复完整流水线；固定 Demo 的确定性边界；补充最终推荐不变量校验。
2. P1：统一阻塞澄清、可选决策问题、DecisionStatus、流式 progress 和 Trace 的阶段语义，并让 Trace 显式记录计划路径与实际路径。
3. P2：在不破坏现有 API 的前提下，把上述执行规划、结果校验和阶段语义沉到 Diet / Generic 共用内核，并扩充真实 Orchestrator 回归评测。

本轮不直接合并 `/api/v1/diet/*` 与 `/api/v1/decisions/*`，不新增外部基础设施，不处理需要独立产品决策的分布式限流、服务端密钥托管或部署架构。这些属于生产运行环境与安全边界，不应混入本次工作流优化。

该改动会改变核心多轮执行路径、Trace 和评测，属于大改动。本 Research 阶段不修改产品代码。

## 成功标准

- 新建决策仍运行完整领域流水线。
- “为什么不选 A”只理解候选焦点并解释，不重新搜索或排序。
- 偏好、权重、硬约束、用户排除和候选事实变化优先复用 `candidatePool` 重排。
- 搜索边界变化、候选池缺失或用户明确刷新时才重新召回候选。
- What-if 只运行 shadow decision，不刷新或改写正式候选、Evidence、SearchRun、推荐与字段。
- Demo 固定 fixture 与规则路径，不因浏览器已有模型 / 搜索配置产生漂移。
- 任意推荐在提交前满足候选有效、未排除、硬约束通过、Evidence 引用合法等确定性不变量。
- `DecisionStatus`、progress 和 Trace 使用一致阶段语义，Trace 可解释为什么跳过某一步。
- Diet / Travel / Shopping / Generic 的现有行为、API、revision、receipt、fallback 和 Evaluation 保持兼容。
- 新增执行路径进入真实 Orchestrator Regression Dataset，不使用 `fixtureActual` 伪造结果。

## ADR / 历史方案检索

已按 execution mode、增量执行、rerank、refresh candidates、clarification、信息价值、Trace stage、Unified Orchestrator、Diet / Generic 等关键词检索 `adr/`、`docs/`、`src/`、`tests/`、`README.md` 和 `CHANGELOG.md`。

高度相关记录：

- `adr/2026-10/2026-10-09-decision-workflow-ux-optimization-research.md` / `plan.md`：已完成阶段摘要、AI / 规则边界、权重、排除原因、快捷交互和 Demo 说明。本次不重复前端展示优化。
- `adr/2026-10/2026-10-09-decision-workflow-correctness-hardening-research.md` / `plan.md`：已完成 What-if 隔离、偏好增量合并、状态展示一致性、结构化澄清和采用闭环。本次必须保留这些语义。
- `adr/2026-09/2026-09-19-decision-quality-p0-research.md` / `plan.md`：已实现质量摘要和排序后的信息价值问题选择。本次复用 `select_decision_question()`，不另建问题评分系统。
- `adr/2026-09/2026-09-05-candidate-search-productization-*`：已明确 clarification-only 不显示搜索进度、rerank-only 不重新搜索。
- `adr/2026-09/2026-09-05-decision-trace-observability-*`：已定义用户消息、理解、约束、召回、证据、过滤、排序、审查和解释主线。本次增量扩展 planned / executed path，不重写 Trace schema。
- `adr/2026-09/2026-09-05-evidence-presentation-*`：已要求搜索和 rerank 保持 Evidence 一致，本次不能在重排时刷新历史来源时间。
- `adr/2026-09/2026-09-22-diet-hybrid-db-web-recall-*` 与 `recommendation-feedback-loop-*`：已定义 Diet rerank、候选不足补充召回和负反馈路径，本次不能用通用规则覆盖 Diet 特有召回策略。
- `adr/2026-09/2026-09-04-generic-decision-evidence-workbench-*`：已明确 Diet 是共享 StageRunner 的完整业务来源，外部 Diet API 作为兼容层保留。

归档判断：新建本 Research / Plan。现有记录均已完成或解决展示、正确性、搜索、Evidence、质量等局部问题；本次解决的是“自然语言轮次如何选择最小必要执行路径”，追加旧文档会混淆历史范围。

## 当前工作区状态

Research 开始时 `git status --short` 无输出，工作区干净。后续实施仍需在每个批次开始前重新检查，避免覆盖用户的新修改。

## 核心文件与真实职责

### `src/choice_agent/agents/stages.py`

- `StageRunner.run()` 固定执行 Intent、Understanding、可选 Clarification、Candidate / Planning、Critic、Explanation、Risk。
- `StageRunner.recompute()` 已支持 `refresh_candidates=False` 时调用 `profile.rerank()`，为自然语言增量执行提供了现成能力。
- 当前缺少 explain-only、what-if-only 和统一执行计划输入。

### `src/choice_agent/orchestration/generic.py`

- `create()` 和 `message()` 最终都进入 `_run()`，而 `_run()` 对正常消息统一调用 `self.unified.run()`。
- `command()` 已根据 `apply_command()` 返回的 `full / refresh / rank` 选择完整运行或 `recompute()`。
- `message()` 在执行前保存 `official_baseline`，可用于比较字段、候选、约束、权重和推荐变化，无需另存数据库历史版本。
- revision、request receipt、事务、Trace 和持久化边界已经完整，应保持不变。

### `src/choice_agent/decision/assistance.py`

- `prepare_turn()` 已写入 `turn_intent=compare / explain / what_if`、`is_hypothetical`、候选焦点、事实和偏好变化。
- What-if 已在 `explain()` 中基于正式 baseline 创建 shadow decision，但在到达 Explanation 前，当前 StageRunner 仍可能对正式 decision 运行候选召回和排序。
- `assistance.changes` 是用户展示文本，不适合作为唯一机器路由依据。

### `src/choice_agent/decision/commands.py`

- 结构化命令已有成熟执行语义：刷新候选返回 `refresh`，权重 / 约束 / 排除 / 候选事实等返回 `rank`，少数回答返回 `full`。
- 这说明执行能力已经存在，缺口主要在自然语言轮次没有映射到相同语义。

### `src/choice_agent/domains/comparison.py`

- `source_and_rank()` 完成召回、Evidence 校验、Hard Filter、Ranking 和质量摘要。
- `rerank()` 复用 `domain_state.candidatePool`，保留来源与 Evidence。
- `critic()` 目前只检查候选 ID 重复和 score 范围，无法校验 Explanation 后的最终 Recommendation。
- `_update_decision_quality()` 已调用 `select_decision_question()` 产生排序后的信息价值问题。

### `src/choice_agent/decision/clarification.py`

- 已具备基于约束风险、证据缺失、前两名分差等信息选择单个高价值问题的能力。
- 它解决的是排序后的可选问题；领域 `needs_clarification()` 仍负责搜索前的阻塞字段，两者不应混为一类。

### `src/choice_agent/decision/state_machine.py`

- 已定义 `DRAFT / CLARIFYING / SEARCHING / COMPARING / DECIDED` 合法转换。
- 通用比较路径通常在完成召回和排序后才切到 `COMPARING`，`SEARCHING` 没有成为可观察的持久阶段。
- progress stage 和 Trace stage 另有字符串，存在语义漂移风险。

### `src/choice_agent/orchestration/diet.py`

- Diet 仍承担兼容 Session、旧响应、Meal 映射、反馈与计划能力，但核心阶段已复用 `UnifiedDecisionOrchestrator`。
- Diet 的 Adjustment、Composition、DB + Web hybrid recall 和负反馈补充召回是领域特性，不能由通用执行计划粗暴覆盖。

### `src/choice_agent/evaluation/runner.py`

- 每个 Case 在隔离 SQLite 中运行真实 Diet / Generic Orchestrator，收集多轮输出、related Trace 和确定性断言。
- 已有 core 与 fault-injection v2 case，可直接扩展执行路径断言。

## 当前关键调用链

### 自然语言消息

`GenericDecisionOrchestrator.message()` → 保存 baseline → `_run()` → `UnifiedDecisionOrchestrator.run()` → `StageRunner.run()` → 固定完整链路。

即使 `IntentAgent` 已识别 `turn_intent=explain`，或本轮只更新权重，后续仍会进入 `CandidateAgent`。

### 结构化命令

`GenericDecisionOrchestrator.command()` → `apply_command()` → `CommandMutation.mode`：

- `full` → `unified.run()`；
- `refresh` → `unified.recompute(refresh_candidates=True)`；
- `rank` → `unified.recompute(refresh_candidates=False)`。

这是本次自然语言执行规划应复用的行为基线。

### What-if

自然语言或显式 What-if → `prepare_turn(is_hypothetical=True)` → 当前仍经过 StageRunner 候选阶段 → `assistance.explain()` 再使用 baseline / shadow decision 生成 `whatIfAnalysis`。字段和正式推荐已有测试保护，但正式路径仍做了不必要工作，并可能增加 SearchRun、耗时和 Trace 噪音。

## 已有可复用能力

- `official_baseline`：可比较本轮前后结构化状态。
- `turn_intent`、`is_hypothetical`、`unhandled_turn`、候选焦点和 `assistance.changes`。
- `candidatePool`、`rerank()`、`source_and_rank()`。
- `CommandMutation` 的 `full / refresh / rank` 语义。
- `select_decision_question()` 与 `qualityAssessment`。
- Trace 的 timeline、state diff、fallback、recommendationChange 和 commitStatus。
- EvaluationRunner 的真实多轮 Orchestrator 与 fault injection。
- Demo 的 `demoMode` 与 `searchMode=fixture` 上下文。

## 主要问题和隐患

1. 解释、偏好变更和 What-if 仍可能触发搜索、Evidence 和完整排序。
2. 命令已有模式，自然语言只有 `turn_intent`；如果再在 Orchestrator 写关键词分支，会形成第二套语义。
3. 购物类别 / 用途、旅行出发地 / 天数等变化可能需要刷新；权重、预算上限、交通上限、排除和已有候选事实通常只需重排。
4. 旧状态或兼容数据没有 `candidatePool` 时，计划为 rerank 也必须安全升级为 refresh。
5. 现有 What-if 隔离主要保护 fields / recommendation，执行过度仍可能更新正式搜索相关状态。
6. 现有 Critic 在 Explanation 之前，无法统一校验最终 Recommendation。
7. DecisionStatus、progress、Trace stage 没有共同的执行计划来源。
8. `demoMode` 固定搜索 fixture，但请求头配置的模型仍可能参与理解 / 解释。
9. 直接合并 Diet / Generic Orchestrator 会扩大 API、Session、反馈和 Meal 映射影响，不符合最小修改原则。
10. 现有回归缺少“解释轮无 CandidateAgent / Search”“重排轮复用候选池”等执行路径断言。

## 设计结论

### 1. 新增纯规则执行计划器，而不是新增 Agent

新增内部模块 `decision/execution.py`，输出有限模式：`FULL`、`REFRESH`、`RERANK`、`EXPLAIN_ONLY`、`WHAT_IF`。阻塞性 `CLARIFY` 仍由领域规则决定。计划器只读取结构化状态差异、领域声明和现有上下文，不调用模型，不持久化状态。

### 2. 计划时机放在 Intent / Understanding 之后

自然语言的字段、事实、候选焦点和 turn intent 在 Intent / Understanding 阶段才完整。计划器应在这两个阶段后、候选召回前运行；阻塞性澄清优先于 RERANK / REFRESH。

### 3. 领域声明检索边界

避免在通用模块硬编码所有领域字段。`DomainProfile` 增加最小 hook，例如 `retrieval_sensitive_fields()`；Travel、Shopping、Generic、Diet 分别声明。通用计划器负责比较 baseline 字段和候选池状态。

### 4. 命令和自然语言共用执行模式

保留 `CommandMutation` 外部行为，但统一映射到内部 ExecutionMode，避免两套模式长期漂移。

### 5. 最终推荐使用独立确定性校验器

在 Explanation 后、持久化前运行 `validate_decision_result()`，检查推荐候选、排除状态、候选状态、硬约束、Evidence 引用和空候选语义。该校验器不是新 Agent，不调用模型；Trace 记录为 operation。

### 6. Demo 在请求级固定规则路径

当 `decision.context.demoMode=true` 时，搜索固定 fixture，Understanding / Explanation 使用 DisabledProvider，Trace 明确 `executionProfile=demo_deterministic`。普通决策不受影响。

### 7. 状态和可观测性由执行计划派生

- REFRESH 在 Provider 调用前进入 SEARCHING；
- RERANK 在过滤 / 排序前进入 COMPARING；
- 有合法正式推荐后进入 DECIDED；
- EXPLAIN_ONLY 不伪造 SEARCHING / COMPARING；
- WHAT_IF 不改变正式 status；
- Trace 记录 `plannedPath`、`executedPath`、`skipReasons`。

### 8. 不强制合并外部 Orchestrator

P2 的“收敛”定义为 Diet / Generic 共用 ExecutionMode、StageRunner 执行入口、结果校验和阶段语义；保留两个 API Facade 及 Diet 兼容持久化。只有发现可验证的重复事务代码且不影响兼容时，才做小范围抽取。

## 约束与风险

- 解释轮可能包含显式字段修改；只要 baseline diff 检测到业务状态变化，就必须升级为 RERANK 或 REFRESH。
- Web Search 的 departure / days / usage 变化可能影响查询；fixture 模式下也保持相同刷新语义。
- Generic 手工候选没有外部搜索，但目标或候选本身变化仍需重建 / 重排；由 Profile hook 决定。
- Diet 分支复杂，第一批默认保护 Diet 现有完整路径，再通过专项测试逐步接入共用模式。
- 最终结果校验不得把合法的“无推荐 + 澄清 / 顾虑”误判为失败。
- Demo 固定 DisabledProvider 会改变已配置模型用户在 Demo 中的行为，页面必须继续明确这是确定性演示；正式决策不受影响。
- 状态阶段变化可能影响前端和历史数据兼容；旧状态必须可读取，新增字段应放入现有 metadata / domainState 可选区。

## Plan 阶段边界

1. 首批只让 Travel / Shopping / Generic 自然语言接入执行计划；Diet 先共享类型、校验和可观测性，保持现有调度行为，待专项测试证明后再启用增量路由。
2. 外部 API、数据库 schema 和依赖保持不变。
3. 不在本 Plan 内实现分布式限流、服务端密钥存储或部署基础设施；它们需要单独安全与运行环境 ADR。
4. 按 P0 → P1 → P2 独立完成、验证和勾选 Todo；发现重要设计偏差时先更新 Plan。