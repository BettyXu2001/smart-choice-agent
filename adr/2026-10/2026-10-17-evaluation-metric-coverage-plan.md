# Evaluation Metric Coverage Plan

日期：2026-10-17。状态：已完成并验证。

## 目标与成功标准

在现有 Evaluation 架构内发布 `evaluation-v3`，新增 5 项必要指标和分组/路由诊断汇总，使自动评测能够真实覆盖领域路由、是否应追问、软偏好排序、安全违规和降级频率。

成功标准：

1. 指标目录从 18 项扩展到 23 项；21 项 scored、2 项 unscored。
2. `domain_routing_accuracy` Case 不显式注入正确领域，真实经过 `DomainRegistry.identify()`。
3. 澄清、软偏好和安全指标均有结构化 auto evaluator，缺少判定条件时返回 `not_evaluated`。
4. `fallback_activation_rate` 从真实 Trace 派生，按可观测 Case 聚合且不进入总分。
5. summary 输出 Case 比率、分 domain/caseType/tag 统计和路由 Precision/Recall/F1/混淆矩阵。
6. 旧 Dataset/Run 数据保持可读；新旧 evaluator version 不可比较；无数据库迁移。
7. 发布不可变 `core-regression/v3`，新增指标在真实 Runner/Orchestrator 链路中有分母。
8. 定向测试、完整测试、编译、Diff 检查和一次实际 v3 Run 均通过；实际结果如实记录。

## 总体设计

```text
core-regression/v3 Case snapshot
  -> caseData.domain = expected domain
  -> caseData.caseType / tags = grouping metadata
  -> setup.autoRoute ? request.domain=None : request.domain=expected domain
  -> real Orchestrator + Trace
  -> v3 deterministic assertions + trace observations
  -> Result
  -> summary core
       -> overall/category/metrics/coverage
       -> case counts/rates
       -> performance
       -> grouped summaries
       -> routing diagnostics
```

不修改生产 Registry 规则、DecisionState、推荐算法或数据库表。

## 指标设计

### 1. `domain_routing_accuracy`

- 分类：需求理解；higher-is-better；scored。
- Auto expected：`{"domain": "travel", "needsClarification": false}`，其中 `needsClarification` 可选。
- Actual：最终 `decisionState.domain`、`domainState.sceneResolution`。
- `domain` 缺失或输出无 DecisionState 时 `not_evaluated`。
- `setup.autoRoute=true` 时 Runner 不向请求传 domain；期望领域仍取 `caseData.domain`。
- 自动路由 Case 一律走 GenericDecisionOrchestrator，使 diet 也经过 Registry。

### 2. `clarification_decision_accuracy`

- 分类：需求理解；higher-is-better；scored。
- Auto expected：`{"shouldClarify": true, "turn": -1}`；`turn` 可选，默认最终状态。
- Actual clarification：`status=clarifying`、`nextAction=ask_clarify` 或存在 clarifying/unanswered question 任一成立。
- 同时覆盖需要追问与不应追问，避免只优化召回率。

### 3. `soft_preference_satisfaction`

- 分类：决策质量；higher-is-better；scored。
- Auto expected：

```json
{
  "turn": -1,
  "criteria": [
    {"key": "relaxation", "minimumNormalizedScore": 60, "minimumWeight": 1}
  ]
}
```

- 定位 Primary Candidate，在 `scoreBreakdown` 中逐项检查 criterion、weight 和 normalized score。
- 没有 recommendation、Primary Candidate、目标 criteria 或 scoreBreakdown 时 `not_evaluated`，不造失败分母。

### 4. `safety_constraint_violation_rate`

- 分类：决策质量；lower-is-better；scored。
- Auto expected 支持：`requireRiskFlags`、`forbidRecommendation`、`forbidCandidates` 和通用 `checks`。
- evaluator 返回 `passed=true` 表示安全策略满足；聚合时 lower-is-better 使用失败断言数作为违规 numerator。
- 首批只覆盖已有可观察的 Diet 风险/特殊人群/极端节食路径，不扩写生产安全规则。

### 5. `fallback_activation_rate`

- 分类：工程可靠性；lower-is-better；`scored=false`。
- 从 related Trace 的 timeline fallback node 或 event `fallbackUsed=true` 判断本 Case 是否激活过 Fallback。
- 每个有 Trace 的 Case denominator=1，激活时 numerator=1；无 Trace 为 `not_applicable`。
- 加入 Trace observation metric 集合，不允许 assertion 与 observation 双重聚合。

### 评分与 Coverage

- `EVALUATOR_VERSION = evaluation-v3`。
- `QUALITY_METRIC_IDS` 随 scored 定义扩展为 21 项。
- `DETERMINISTIC_TARGET_METRIC_IDS` 加入前四项，从 16 扩展为 20；Fallback 激活率不加入。
- 保持 category 先平均、overall 再对 category 平均的既有公式。
- 新增低优指标继续使用 `1 - value` 参与分类分数。

## Summary 设计

### Case 比率

在现有 `caseCounts` 旁新增：

```json
"caseRates": {
  "passRate": 0.0,
  "failureRate": 0.0,
  "errorRate": 0.0,
  "notEvaluatedRate": 0.0
}
```

分母为 Result 数；空 Run 全部返回 `null`，不返回虚假的 0%。

### Case metadata

- `EvaluationCaseData` 新增 `caseType: str = "general"`，限制非空和合理长度。
- Service 从本次不可变 snapshots 构造 `{caseId: {domain, caseType, tags}}`。
- `summarize_results(results, case_metadata=...)` 使用该 map；历史调用未传 metadata 时 groups 返回空对象。
- 不把 metadata 重复写入 Result 表。

### 分组统计

新增：

```json
"groups": {
  "byDomain": {},
  "byCaseType": {},
  "byTag": {}
}
```

每组值包含：`caseCounts/caseRates/overallScore/categoryScores/metrics/coverage`。抽取内部 `_summarize_core()` 复用现有公式；分组不再包含 `groups/performance`，避免递归和冗余 Trace 聚合。

### 路由诊断

从 eligible deterministic `domain_routing_accuracy` assertion 的 expected/actual 构建：

- `sampleCount`
- `accuracy`
- `macroPrecision`
- `macroRecall`
- `macroF1`
- `perDomain`
- `confusionMatrix`

未出现的类别不参与 macro 平均；没有样本时 count=0，其余为空值/空对象。

## Dataset 与 Case

发布 `core-regression/v3`，保留 v1/v2 不变。v3 以 v2 行为覆盖为基础，增加 10 条定向 Case，总数控制在现有 Run `limit=20` 约束内，因此不直接复制全部 20 条 v2；选择 10 条现有核心 Case加 10 条新 Case，共 20 条。

新增 Case 计划：

1. 四个单领域自动路由：diet、travel、shopping、generic。
2. 一个多领域歧义路由：期望 generic 且 `needsClarification=true`。
3. 两个澄清决策：应追问、不应追问。
4. 一个 Travel/Shopping 软偏好排序 Case。
5. 一个 Diet 软偏好排序 Case。
6. 一个 Diet 安全风险 Case。

每个 Case 设置稳定 `caseType` 与 tags。Fallback activation 复用 `fault-injection-reliability/v2` 真实 Trace，不新增重复 fault Case。

## 受影响文件

| 文件 | 计划修改 |
| --- | --- |
| `src/choice_agent/evaluation/schemas.py` | 新增向后兼容的 `caseType`。 |
| `src/choice_agent/evaluation/metrics.py` | 注册 5 项指标、v3 version、Trace observation、Case rates、分组和路由诊断。 |
| `src/choice_agent/evaluation/deterministic.py` | 实现 routing/clarification/soft preference/safety 四个 auto evaluator。 |
| `src/choice_agent/evaluation/runner.py` | 支持白名单 `setup.autoRoute`，自动路由 Case 不显式传 domain；采集 fallback observation。 |
| `src/choice_agent/evaluation/service.py` | 从 snapshot 构造 metadata map 并传给 summary。 |
| `src/choice_agent/evaluation/fixtures.py` | 发布 `core-regression/v3` 与新增定向 Case。 |
| `src/choice_agent/evaluation/comparison.py` | 保持现有 delta，必要时补新 summary 字段/coverage warning 的兼容测试，不改比较原则。 |
| `src/choice_agent/static/assets/js/evaluation.js` | 移除 deterministic count 写死值；最小展示 Case rates、分组和路由诊断。 |
| `tests/test_deterministic_evaluation.py` | 覆盖四个 auto evaluator 的通过、失败、not_evaluated 边界。 |
| `tests/test_evaluation_metrics.py` | 覆盖 23 项目录、评分、Fallback observation、比率、分组、路由诊断。 |
| `tests/test_evaluation_runner.py` | 证明 autoRoute 未注入 domain，并真实执行四领域/歧义 Case。 |
| `tests/test_evaluation_service.py` | 覆盖 v3 seed、旧版本共存、metadata summary。 |
| `tests/test_evaluation_comparison.py` | 覆盖 evaluator-v3 同版本比较与新 summary 兼容。 |
| `tests/test_evaluation_api.py`、`tests/test_evaluation_cli.py` | 验证新增字段通过既有接口输出。 |
| `README.md` | 更新 evaluator-v3、23 项指标和 summary 字段。 |
| `CHANGELOG.md` | 在 `2026-10-17` 唯一标题记录用户可感知的评测扩展。 |

## 兼容性与破坏性评估

- API 仅新增字段与指标定义，没有删除字段；旧客户端按动态 definitions 可继续工作。
- Overall score 口径变化，因此 evaluator version 必须升级；这是有意的评测版本边界。
- 不修改数据库 schema；旧 Case snapshot 默认 `caseType=general`。
- 不修改生产路由、澄清、排序、安全或 Fallback 行为。
- 默认 Dataset 改为 `core-regression/v3` 后，新 Run 与旧 v2 Run 不可直接比较；用户可显式选择旧 Dataset 复现历史结果。

## 风险与边界情况

- 路由 cue 是规则实现，Case 必须包含正例、generic 负例和多领域歧义，不能只测明显关键词。
- clarification actual 使用多个结构字段时必须统一判定函数，避免 status 与 nextAction 短暂不一致造成随机结果。
- 软偏好只在有正式 ranking breakdown 时评测；自然语言主观质量留给后续人工/LLM Review。
- safety 指标只衡量 Case 声明的可观察规则，不宣称覆盖全部现实安全风险。
- Fault Dataset 的 fallback activation 预计较高，因该指标 unscored，不会惩罚故障注入成功。
- 分组小样本只如实展示，不额外做置信区间。
- 指标新增会影响测试中写死的目录长度、coverage denominator 和 Dashboard fallback，需要全仓搜索更新。

## 验证方案

1. 修改前再次检查 `git status` 和所有指标/summary 调用方。
2. 每次重要写入后回读相应片段，确认真实落盘。
3. 定向测试：

```text
.venv\Scripts\python.exe -m pytest \
  tests\test_deterministic_evaluation.py \
  tests\test_evaluation_metrics.py \
  tests\test_evaluation_runner.py \
  tests\test_evaluation_service.py \
  tests\test_evaluation_comparison.py \
  tests\test_evaluation_api.py \
  tests\test_evaluation_cli.py -q
```

4. 可靠性专项：`tests/test_trace_observability.py` 与现有 Fault v2 Runner 测试。
5. 完整测试：`.venv\Scripts\python.exe -m pytest`。
6. 编译：`.venv\Scripts\python.exe -m compileall -q src scripts`。
7. 实际运行 `core-regression/v3`，核对 23 项目录、20 项 deterministic target、Case rates、三种 groups 和 routing diagnostics。
8. 实际运行 `fault-injection-reliability/v2`，核对 fallback activation 与既有 fallback success 不冲突。
9. 检查 `git diff --check`、最终 diff、无临时日志/占位符/无关格式化，并逐项关闭 Todo。

## 注意事项与技术折衷

- 只新增 5 项已确认 P0 指标；P50/max latency、输入输出 Token、semantic judge、timeout/retry/provider failure 暂不纳入本次，避免扩大范围。
- 路由 Precision/Recall/F1 是诊断字段，不作为额外 scored metric，避免同一问题被重复计权。
- Case 分组复用 snapshot metadata，不为查询便利引入数据库迁移。
- Fallback activation 保留原始发生率，不转换成阈值式 score。

## Todo

- [x] 检查工作区和所有指标/summary/fixture 调用方，确认无用户改动冲突。
- [x] 扩展 Case schema，发布 `evaluation-v3` 的 23 项指标目录。
- [x] 实现四个新增 deterministic auto evaluator 及边界语义。
- [x] 实现 autoRoute 真实路由执行和 Fallback 激活 Trace observation。
- [x] 实现 Case rates、分组 summary 和路由诊断。
- [x] 发布不可变 `core-regression/v3` 及 10 条新增定向 Case。
- [x] 更新 Dashboard、README 和 CHANGELOG。
- [x] 补齐并验证 deterministic、metrics、runner、service、comparison、API、CLI 测试。
- [x] 实际运行 Core v3 与 Fault v2，整理所有指标和诊断结果。
- [x] 完成定向测试、全量测试、compileall、diff 检查和 Todo 对照。
