# Deterministic Evaluation Runner Plan

日期：2026-09-20。状态：原 Plan 已获批准；实施前发现重要重叠改动，已更新并等待重新批准。
依据：同目录 `2026-09-20-deterministic-evaluation-runner-research.md`。

## 实施前冲突审计与 Plan 调整

实施前检查确认，原 Plan 形成后已有 Baseline/Candidate comparison、Fault Injection v2、模型/Search Trace observability 和成本/性能聚合完成实施，且相关专项测试 42 passed。为保留这些用户改动，本 Plan 调整如下：

- 保留当前 18 项目录，不删除或改名 `search_fallback_success`；用户指定的 16 项单独计算 deterministic coverage，同时报告完整 scored catalog coverage。
- 直接复用 Runner 已有 `relatedTraces` 和 `observability`，不再新设计每轮 Trace 容器；确定性 evaluator 从该结构读取 Trace、AgentRun、Fallback 和 revision。
- 保留 `EvaluationRunConfiguration`、fingerprint、Baseline/Candidate comparison、API/CLI 和 performance summary。新的 summary 字段只能增量添加。
- 不再发布或改写 `fault-injection-reliability/v2`；只在不改变其 Case 行为的前提下补 `evaluationMethod` 和 Gate 兼容。
- 仍发布 `core-regression/v2`，因为 immutable v1 不能安全承载新的结构化 deterministic/manual assertion 语义。
- 将 `EVALUATOR_VERSION` 从 `evaluation-v1` 升为 `evaluation-v2`。现有 comparison 必须因 evaluator version 不同而拒绝 v1/v2 误比较。
- README 和 CHANGELOG 只做精确追加，不覆盖当前大幅未提交改动。

这些调整改变了原 Plan 的集成基础和部分 Todo，必须重新获得用户明确批准后再修改产品代码。
## 目标与成功标准

把现有“通用 path assertion + 模糊聚合”升级为确定性优先的 Evaluation Runner，同时保留人工语义标签但完全隔离 Regression Gate。

成功标准：

1. 16 项目标指标的每个聚合结果都明确记录 `evaluationMethod`，取值仅为 `deterministic`、`manual`、`not_evaluated`。
2. 可由 DecisionState/Candidate/Constraint/Evidence/Recommendation/Trace/revision 判断的指标使用规则 evaluator；需要金标签的指标只在 Case 提供结构化期望时确定性判定。
3. 自由文本语义质量不被弱文本匹配强行包装为完整自动评分；缺可靠规则时标记 manual。
4. Run summary 输出 deterministic coverage、manual review 指标和 not evaluated 指标。
5. Regression Case 的 passed/failed 只由显式 `required=true`、`evaluationMethod=deterministic` 且已判定的 assertion 决定；没有可判定 required deterministic assertion 时为 `not_evaluated`。
6. Human Review 可保存并返回，但更新 review 前后 Run deterministic summary、Result status 和 Case verified/reopened 状态不变。
7. 不实现 LLM Judge；不调用模型做评测；未来 auxiliary evaluator 不能满足 required assertion。
8. 相同 Case snapshot、固定 fixture/provider/config 重复运行，忽略 ID、时间和 latency 等非业务字段后，assertion、metric method/value、Gate status 与规范化输出一致。

## 设计原则

### 评测来源与 Gate

在 assertion result 与 metric result 中使用 `evaluationMethod`：

- `deterministic`：由白名单规则、结构化金标签和实际状态/Trace 计算；可以参与指标值和 Gate。
- `manual`：需要人工语义判断；自动运行时 `passed=null`，只进入 manual review 列表，不参与自动得分或 Gate。
- `not_evaluated`：不适用、缺少所需状态/Trace/金标签，或没有样本；`value=null`，不造 0 分。

兼容规则：旧 assertion 未写方法时，`operator=manual` 推断为 manual，其余现有白名单 operator 推断为 deterministic。拒绝 `required=true + manual`；`not_evaluated` 只能是运行结果，不能用来伪装 required assertion。

Case Gate：

1. 执行异常为 `error`。
2. 任一 required deterministic assertion 为 false，则 `failed`。
3. 所有 required deterministic assertions 均已判定且为 true，则 `passed`。
4. 没有 required deterministic assertion，或任一 required assertion 无法判定，则 `not_evaluated`。
5. optional deterministic assertion 可进入指标覆盖和诊断，但不决定 PASS / FAIL。
6. manual review 永远不改变以上状态；Bad Case `verified/reopened` 继续只跟随确定性 Result status。

### 确定性 evaluator

新增纯函数 evaluator 层，输入只包含 Case assertion/结构化期望、规范化 outputs、每轮 Trace snapshots 和必要的 repetition peers，不访问网络、不调用 LLM、不读取正式数据库。

保留现有通用 path operators作为低层确定性断言，并增加 `operator="auto"`：按 `metricId` 路由到白名单 metric evaluator。`expected` 承载结构化金标签和 turn/repetition 选择；不允许动态代码、模块路径或表达式执行。

主要规则：

- intent/constraint/correction/exclusion：与 Case 的结构化金标签做规范化精确比较；纠正同时检查 revision 递增、新值生效、旧值移除和归属。
- hard constraint：检查推荐与 excluded/eliminated 集合无交集；对支持的结构化 operator 检查候选属性，不认识的 operator 返回 not_evaluated。
- stability：由 Service 在同 `(caseId, caseRevision)` 的 repetition 完成后，比较规范化 Recommendation/关键业务投影，再回写每个 Result 的稳定性 assertion/metric。
- sensitivity/retention/what-if：对 Case 指定的 before/after turn 进行配对；使用 `decision_projection()` 衍生的稳定投影，分别应用“应改变”“应保持”“正式状态隔离”规则。
- reason consistency：只自动判断 candidate/evidence/recommendation 的结构一致性；文本充分性和说服力保留 manual。
- evidence validity：校验 evidence/source/candidate/revision/quote 的引用链；不把 URL 存在等同于现实真实性。
- unsupported facts：普通 speechText 默认 manual；只有结构化 claim status 或受控 Case 明确给出的禁止事实才能 deterministic。
- excluded recommendation：检查 primary 和 alternatives 与 excluded/eliminated 集合交集。
- fallback：要求 Trace 中真实 failed model node、最终 request/commit 成功、规则降级标志和有效状态/Recommendation。
- agent failure rate：从所有 turn Trace 中精确聚合 AgentRun/AGENT_CALL 的 FAILED / total；缺 Trace 为 not_evaluated。

### 多轮 Trace 和规范化

Runner 已通过 `traceSnapshot.relatedTraces` 保存 Case 全部轮次 Trace；本次直接复用该结构，并建立按 traceId/turn 顺序的只读索引，不新增重复容器。规范化比较明确忽略 UUID、trace/session/decision id、createdAt、durationMs、检索时间等非业务字段，保留 domain、intent、约束、候选业务属性、排除、Recommendation、正式 domain state 和 revision 关系。

`average_response_time_ms` 保持现有展示指标，不属于用户列出的 16 项质量指标；本次只确保其不进入 deterministic quality coverage/Gate，不顺带重做 SLA 语义。

## 每个指标的目标评测方式

| 指标 | 默认 evaluationMethod | 自动判定条件 | 人工边界 |
| --- | --- | --- | --- |
| `intent_accuracy` | deterministic / not_evaluated | 有结构化 intent/domain 金标签 | 无金标签时 manual review 可补充，但不自动打分 |
| `constraint_extraction_accuracy` | deterministic / not_evaluated | 有结构化 constraint 金标签 | 隐含/语义等价约束 manual |
| `correction_update_accuracy` | deterministic / not_evaluated | 有纠正目标和 turn pair | 纠正意图本身不明确时 manual |
| `hard_constraint_satisfaction` | deterministic / not_evaluated | operator 可解释、候选属性/状态齐全 | 未知领域规则 manual |
| `exclusion_correctness` | deterministic / not_evaluated | 有期望集合或可验证排除不变量 | 是否应排除但无金标签时 manual |
| `recommendation_stability` | deterministic / not_evaluated | repetition >= 2 且 config/source 相同 | 非确定来源不评分 |
| `sensitivity_to_condition_change` | deterministic / not_evaluated | 有 before/after 和 expected change mode | “应该怎样变化”未标注时 manual |
| `reason_recommendation_consistency` | deterministic 或 manual | 结构引用一致时 deterministic 子判断 | 文本语义质量 manual |
| `evidence_reference_validity` | deterministic / not_evaluated | 引用链和来源快照齐全 | 来源真实性/权威性 manual |
| `unsupported_fact_rate` | manual 为默认；受控样本可 deterministic | 结构化 claim status 或显式禁止事实 | 普通自然语言 claim 支持性 manual |
| `excluded_candidate_recommend_rate` | deterministic / not_evaluated | 有推荐和排除/淘汰集合 | 无额外人工要求 |
| `multi_turn_state_retention` | deterministic / not_evaluated | 有标注的无正式编辑 turn pair | 轮次意图不明确时 manual |
| `correction_coverage` | deterministic / not_evaluated | 有结构化纠正目标和 Trace/state diff | 无目标分母时不评测 |
| `what_if_isolation` | deterministic / not_evaluated | 有 What-if turn 标记和 before/after | 隐晦假设未标注时 manual |
| `llm_fallback_success` | deterministic / not_evaluated | Trace 证明真实 model failure | disabled model 不适用 |
| `agent_execution_failure_rate` | deterministic / not_evaluated | Trace 含 AgentRun/AGENT_CALL | 历史缺 Trace 不评测 |

聚合 metric 不能表示 mixed，因此只要该 metric 有确定性样本，就输出 deterministic 的自动值；manual labels 单独保存在 `manualReviews`/现有 `reviews` 中并在 summary 的 `manualReviewMetricIds` 报告。只有 manual 样本而无确定性样本时，metric `evaluationMethod=manual`、`value=null`；完全无样本时为 not_evaluated。

## Deterministic Coverage

Run summary 的 `coverage` 保留旧字段、18 项目录与 performance summary，以兼容现有 Dashboard/Comparison，并新增：

- `deterministicEvaluatedMetricCount` / `deterministicMetricCount`（用户指定目标指标固定为 16）；`catalogDeterministicEvaluatedMetricCount` / `catalogQualityMetricCount`（当前完整 scored 目录为 17，包含 `search_fallback_success`）；
- `deterministicMetricRate`；
- `deterministicEvaluatedAssertionCount` / `deterministicEligibleAssertionCount`；
- `deterministicAssertionRate`；
- `manualReviewMetricIds`；
- `notEvaluatedMetricIds`。

`overallScore` 和 `categoryScores` 只聚合 deterministic 且有值的质量指标；manual 与 not_evaluated 不作为 0，也不提高 coverage。

## Fixtures / Dataset 版本

不改写不可变的 `core-regression/v1` 与 `fault-injection-reliability/v1` snapshot。发布 `core-regression/v2`，复用原 20 个真实 Orchestrator 场景并把弱代理断言升级为结构化 `auto`/deterministic assertions；补齐 `correction_coverage`，并让 reason/unsupported semantic 部分显式 manual。

现有 `fault-injection-reliability/v2`、`search_fallback_success`、execution envelope、失败 Trace 和 observation metrics 全部保留；本次只补 `evaluationMethod` 与 deterministic-only Gate 兼容，不改变其场景数量或既有行为。

Starter seed 继续按稳定 seedId 幂等补齐，不覆盖用户已存在的 Case 或历史 Dataset。

## Human Review

沿用 `reviews_json`，在 review payload 中保存 metricId、label/value、note、reviewer（若现有身份可用）、reviewedAt 和 output fingerprint。输出 fingerprint 变化时旧 review 在展示上标记 stale。

`update_review()` 可以更新 review 展示摘要，但必须断言以下字段不变：Result status、deterministic assertions、deterministic metrics、Run Gate case counts、overall/category deterministic score、Case regression lifecycle。Human Review 不是 required assertion 的替代品。

## 受影响文件

| 文件 | 计划修改 |
| --- | --- |
| `src/choice_agent/evaluation/schemas.py` | 增加 evaluationMethod 类型、`auto` operator、结构化 assertion 校验；兼容旧 snapshot 推断。 |
| `src/choice_agent/evaluation/deterministic.py`（新增） | 实现白名单 metric evaluator、业务投影规范化、Trace/Recommendation/Evidence 检查和无副作用纯函数。 |
| `src/choice_agent/evaluation/runner.py` | 复用 `relatedTraces`/observability，调用确定性 evaluator、生成 assertion method，按 required deterministic assertions 判 Case status；保留 Run configuration、fault v2 和 execution envelope，不加入 LLM Judge。 |
| `src/choice_agent/evaluation/metrics.py` | 升级 `EVALUATOR_VERSION= evaluation-v2`；按评测来源聚合、只用 deterministic 计分、输出三态 method 与双口径 coverage；保留 search fallback、Trace observation 和 performance。 |
| `src/choice_agent/evaluation/service.py` | repetition 完成后计算稳定性并持久化一致结果；保证 review 不改变 Gate；保留 Run configuration/comparison，Bad Case 生命周期只信任确定性 status。 |
| `src/choice_agent/evaluation/fixtures.py` | 新增 `core-regression/v2` 结构化断言和 manual 边界，不修改 core v1 或既有 fault v2 snapshot。 |
| `src/choice_agent/static/assets/js/evaluation.js` | 最小展示 evaluationMethod、deterministic coverage 和 manual review 指标；不新增 Judge UI。 |
| `tests/test_evaluation_metrics.py` | 覆盖三态方法、低优指标方向、manual 隔离、coverage 和零样本。 |
| `tests/test_evaluation_runner.py` | 覆盖 16 项规则路径、required Gate、每轮 Trace、同输入确定性与 unsupported semantic manual。 |
| `tests/test_evaluation_service.py` | 覆盖跨 repetition stability、Human Review 不改变 Gate、v2 seed/dataset 幂等和生命周期。 |
| `tests/test_evaluation_api.py` / 前端静态测试 | 覆盖响应字段兼容和最小展示；优先并入现有文件。 |
| `README.md`、`CHANGELOG.md` | 精确记录 deterministic-first 口径、覆盖率、人工边界和本轮实际变化；合并到现有同日标题。 |

原则上不改 `db_models.py` 或 repository：新增信息进入现有 JSON 字段。若实施发现必须迁移表结构，属于重要设计变化，暂停并更新 Plan。

## 兼容性与破坏性评估

- 保留当前全部 18 个 metric id、category/direction/scored 语义：用户指定的 16 项、`search_fallback_success` 和 latency。
- 旧 path assertions 继续可运行，并按 operator 推断 method；旧历史 Result 原样可读。
- 新 Run 的分数可能下降或 coverage 变得更诚实，因为 manual/不可判定样本不再被当作自动通过。这是预期口径修正。
- `core-regression/v1` 不变；默认 dataset 是否切换到 v2 会在实施时显式更新并测试，Dashboard 同时可查看历史 v1。
- 不新增依赖、不访问网络、不调用真实 LLM、不改旧 `/api/v1/diet/evaluations` 的可选 Judge。
- 保留已实现的 baseline/candidate comparison；通过 `evaluation-v2` 阻止新口径与历史 `evaluation-v1` 被误判为可比。

## 风险与边界情况

1. 自动结构一致性不能代表完整语义质量；UI/报告必须显示方法和范围。
2. repetition 配对必须在所有 Result 产生后统一计算，避免先保存的 Result 缺稳定性；中途 error 时只对可比完整样本评测。
3. Trace 内时间、ID、latency 非确定；一致性测试必须使用规范化结果，不能断言原始 JSON 字节完全相同。
4. `unsupported_fact_rate` 不能通过简单数字/关键词扫描宣称完整覆盖；普通回答保留 manual。
5. hard constraint 只支持白名单 operator；未知 operator 返回 not_evaluated，不猜测。
6. v2 seed 不覆盖用户编辑；旧数据库幂等补齐时保持历史 Case/Dataset 不变。
7. 当前工作树有用户未提交改动。实施前后按文件检查 diff，不覆盖 `schemas.py` 等已有修改；如冲突无法安全合并，暂停请求方向。

## 验证方案

1. 单元测试每个 metric evaluator 的 positive/negative/missing/manual 分支，尤其是 Evidence 引用、排除推荐、revision、What-if 投影和 Trace fallback/AgentRun。
2. Gate 测试 required deterministic pass/fail、只有 manual、required 缺数据、optional failure、execution error；证明 manual review 不能改变 status。
3. 聚合测试三态 evaluationMethod、deterministic-only score、错误率方向、16 项 coverage 和 manual/not-evaluated 列表。
4. repetition 测试同一 Case 固定输入运行至少两次，比较规范化 outputs、assertions、metrics 和 status；另造有差异样本验证 stability 失败。
5. Service/API 测试 v2 dataset 幂等、旧 v1 保留、Result JSON 持久化、review fingerprint/stale 与 Bad Case lifecycle。
6. 真实 Core v2 Run：确认 20 个 Case 全部走 Orchestrator、每轮 Trace 可用、报告输出每项方法和 coverage；对 manual 项不宣称自动分数。
7. 回归：evaluation 专项、相关 API/前端静态测试、全量 pytest、compileall、node --check、`git diff --check`。
8. 最终检查 diff、Plan Todo、同日 CHANGELOG 合并和未验证项；不得以 mock/fixed fixture 结果证明真实 LLM/Web Search 质量。

## Todo

- [x] 完成实施前冲突审计，确认 Baseline/Candidate、Fault v2 与 Trace observability 为必须保留的有效基线。
- [ ] 增加 evaluationMethod/auto assertion 契约和兼容校验，完成三态与 required/manual 单元测试。
- [ ] 实现纯确定性 evaluator 与规范化投影，覆盖 16 项指标的可靠规则边界。
- [ ] 增强 Runner 的逐轮 Trace 捕获和 deterministic-only Gate，不加入 LLM Judge。
- [ ] 增强 metrics summary 的 deterministic-only 分数、coverage、manual/not-evaluated 报告。
- [ ] 在 Service 中实现跨 repetition stability，并证明 Human Review 不影响 Gate 与 Bad Case lifecycle。
- [ ] 发布并幂等 seed `core-regression/v2`，保留 v1，不用弱文本代理冒充全面语义评分。
- [ ] 最小更新 Evaluation Dashboard、README 和同日 CHANGELOG，展示评测方式与人工边界。
- [ ] 运行专项与全量验证、重复运行一致性测试、compileall/node check/diff check，复核全部 Todo。