# Deterministic Evaluation v2 P0 Plan

日期：2026-10-05。状态：已完成实施与验证。
依据：`adr/2026-10/2026-10-05-deterministic-evaluation-v2-p0-research.md`。

## 目标和成功标准

在不重做已完成 Deterministic Evaluation v2 主体能力的前提下，完成本次 P0 验收缺口：

1. Baseline / Candidate diff 严格符合用户指定状态转换语义：
   - `failed -> passed` = `fixed`
   - `passed -> failed` / `passed -> error` = `new_failure`
   - `not_evaluated -> passed` = `improved`
   - `passed -> not_evaluated` = `regressed`
   - `failed -> not_evaluated` 不能算 `improved`，本 Plan 定为 `regressed`
2. Comparison response 对 Evaluation coverage 下降给出明确结构化提示，而不是只暴露 summary 数字。
3. 自动化测试补齐 deterministic coverage：16 项目标 metric 的 auto evaluator 至少有明确可判定路径或不可判定/manual 边界测试。
4. 保持 manual 不参与自动得分、不参与 Regression Gate；没有可判定 required deterministic assertion 时仍为 `not_evaluated`。
5. `core-regression/v2` 默认发布且 v1 保留；弱文本匹配不被新增为 v2 的主判定方式；同一 Case 重复执行稳定性继续通过。
6. 不实现 LLM Judge，不新增模型裁判调用。

## 设计和修改范围

### 1. Comparison 状态转换

修改 `src/choice_agent/evaluation/comparison.py` 的 `classify_case_diff()`：

- 保留最高优先级：baseline `failed/error` 且 candidate `passed` -> `fixed`。
- 保留：baseline `passed` 且 candidate `failed/error` -> `new_failure`。
- 新增显式覆盖下降规则：baseline `failed/error` 且 candidate `not_evaluated` -> `regressed`。
- 保留：baseline `passed` 且 candidate `not_evaluated` -> `regressed`。
- 保留：baseline `not_evaluated` 且 candidate `passed` -> `improved`。
- 分数比较只在上述状态边界之后运行；避免 coverage 丢失被分数或状态排序误判为 improved。

不改变 run 可比性校验、result key 对齐、overall/category/metric delta 公式。

### 2. Coverage 下降提示

在 `compare_runs()` response 中新增结构化字段：

```json
{
  "coverageDelta": {
    "deterministicEvaluatedMetricCount": -1,
    "deterministicMetricRate": -0.0625,
    "catalogDeterministicEvaluatedMetricCount": -1,
    "deterministicEvaluatedAssertionCount": -3,
    "deterministicAssertionRate": -0.1
  },
  "coverageWarnings": [
    {
      "code": "evaluation_coverage_decreased",
      "message": "Candidate deterministic evaluation coverage decreased versus baseline.",
      "fields": ["deterministicEvaluatedMetricCount", "deterministicMetricRate"]
    }
  ]
}
```

字段名使用 camelCase，保持现有 response 风格。只在 candidate 对应 coverage 数值低于 baseline 时生成 warning；数值缺失时跳过，不构造假下降。

### 3. Deterministic evaluator 测试覆盖

扩展 `tests/test_deterministic_evaluation.py`：

- 直接调用 `evaluate_auto_assertion(metric_id, expected, outputs)`，使用小型结构化 `outputs` fixture 覆盖 16 项目标指标。
- 每类测试聚焦当前 evaluator 的稳定契约，不跑真实 Orchestrator：
  - 需求理解：`intent_accuracy`、`constraint_extraction_accuracy`。
  - 硬约束 / 排除候选：`hard_constraint_satisfaction`、`exclusion_correctness`、`excluded_candidate_recommend_rate`。
  - 多轮与纠正：`correction_update_accuracy`、`correction_coverage`、`multi_turn_state_retention`。
  - What-if 与条件变化：`what_if_isolation`、`sensitivity_to_condition_change`。
  - 解释与证据：`reason_recommendation_consistency`、`evidence_reference_validity`、`unsupported_fact_rate`。
  - Fallback / Agent：`llm_fallback_success`、`agent_execution_failure_rate`。
  - Repetition：`evaluate_repetition_stability()` 覆盖 `recommendation_stability`。
- 保留现有 Gate 和 missing path 测试；补充“只有 optional/manual 时 status not_evaluated 或 passed”的边界按现有函数契约校验。

### 4. Dataset / Service 覆盖

在现有 `tests/test_evaluation_service.py` 上做小幅补强：

- 明确默认 run 使用 `core-regression/v2`，而不是只按 name 找第一个 dataset。
- 断言 v1/v2 dataset hash 不同且 v1 case snapshots 仍存在。
- 保留 repeat stability 测试；不新增昂贵的全量重复真实 Orchestrator Run。

### 5. 文档与 CHANGELOG

`CHANGELOG.md` 当前 2026-10-05 条目已写了 deterministic-first 总结。本次实施后只在同日标题下精确追加：

- 修正 Baseline/Candidate coverage/status diff 语义；
- 补齐 deterministic evaluator coverage 测试；
- 如 response 新增 `coverageWarnings`，记录 API 行为变化。

如 README 已经准确描述 deterministic-first，不做大段改写；只有新增 `coverageWarnings` 需要时才补一句。

## 受影响文件

| 文件 | 修改内容 |
| --- | --- |
| `src/choice_agent/evaluation/comparison.py` | 修正状态转换优先级；新增 coverage delta/warnings 生成函数。 |
| `tests/test_evaluation_comparison.py` | 补全用户指定状态转换表、`failed -> not_evaluated`、coverage warning。 |
| `tests/test_deterministic_evaluation.py` | 补齐 16 项 deterministic evaluator 的结构化测试覆盖。 |
| `tests/test_evaluation_service.py` | 小幅补充默认 v2、v1 保留和 dataset hash 区分断言。 |
| `CHANGELOG.md` | 同日标题下精确追加实际变化。 |
| `README.md` | 仅当 API 新字段需要说明时做最小更新。 |

## 兼容性和破坏性变更评估

- API response 新增字段为向后兼容；不删除现有字段。
- `failed -> not_evaluated` 从 `improved` 改为 `regressed` 是语义修复，可能改变旧 comparison 结果，但符合用户要求。
- 不改变 metric id、dataset name/version、Run/Result 持久化结构或数据库表结构。
- 不改变 Regression Gate 本身，只补测试保护现有行为。
- 不改变 `core-regression/v1`，不覆盖用户自定义 Case 或 Dataset。

## 风险和边界情况

1. Coverage warning 只比较 summary 中存在的数值字段；历史 Run 若没有新 coverage 字段，不生成 warning，避免误报。
2. `failed -> not_evaluated` 定为 `regressed` 是本 Plan 的明确取舍；如果用户希望更温和地归为 `unchanged`，需要在实施前调整。
3. Deterministic evaluator 单测使用结构化最小 fixture，能保护 evaluator 规则，但不替代真实 Orchestrator 回归；真实路径仍由现有 service/runner 测试覆盖。
4. 不扩大范围去提升 evaluator 业务准确性；发现 evaluator 自身逻辑 bug 时，若是当前 P0 必要修复则纳入，否则记录后另开计划。

## 验证方案

1. 局部测试：
   - `python -m pytest tests/test_deterministic_evaluation.py tests/test_evaluation_comparison.py tests/test_evaluation_metrics.py -q`
2. Service/runner 相关测试：
   - `python -m pytest tests/test_evaluation_service.py tests/test_evaluation_runner.py tests/test_evaluation_api.py tests/test_evaluation_cli.py -q`
3. 合理全量验证：
   - `python -m pytest -q`
   - `python -m compileall -q src tests`
   - `git diff --check`
4. Diff 检查：确认只改 Plan 范围文件，无调试代码、无临时日志、无无关格式化。
5. Todo 对照：每项 Todo 完成并通过对应验证后再打勾。

## Todo

- [x] 修正 `classify_case_diff()` 状态转换，确保 `failed -> not_evaluated` 不再是 `improved`。
- [x] 为 comparison response 增加 coverage delta 和 coverage warning。
- [x] 补全 Baseline/Candidate 状态转换和 coverage warning 测试。
- [x] 补齐 16 项 deterministic evaluator 结构化测试覆盖。
- [x] 补充默认 `core-regression/v2`、v1 保留和重复稳定性相关断言。
- [x] 精确更新 CHANGELOG / README（如需要）。
- [x] 运行专项、合理全量验证、compileall、diff check，并复核最终 diff。