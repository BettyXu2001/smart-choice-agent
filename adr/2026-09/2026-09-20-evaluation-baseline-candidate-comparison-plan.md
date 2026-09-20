# Evaluation Baseline / Candidate 真实版本对比 Plan

日期：2026-09-20。状态：已实施并验证。  
依据：同目录 `2026-09-20-evaluation-baseline-candidate-comparison-research.md`。

## 目标与成功标准

在保持现有五类 17 项指标定义和聚合口径不变的前提下，实现可追溯、可执行、可验证的 Baseline vs Candidate 版本对比。

完成后应满足：

1. 每个 Evaluation Run 都返回并持久化独立 `runConfiguration`，至少包含 `model`、`provider`、`promptVersion`、`ruleVersion`、`runLabel`。
2. `model` 和 `provider` 真正影响 Runner 执行；配置进入 request fingerprint，同 requestId 不得复用于不同配置。
3. 同一 Regression Dataset 可分别执行 baseline 和 candidate，两边的 `(caseId, caseRevision, repetition)` 集合一致，每个 Result 仍独立保存 output、assertions、metrics、error 和 Trace Snapshot。
4. 显式指定的两个 Run 可生成 `improved / regressed / unchanged / new_failure / fixed` 五类逐 Case Diff。
5. Comparison response 同时包含 baseline/candidate 的 overall score、category scores、17 项 metric 和 passed/failed/error/notEvaluated case counts，并给出分数差异与 Diff 计数。
6. 现有 Bad Case 生命周期、Dataset snapshot、Trace Snapshot、旧 Run 字段、CLI 和 Dashboard 基本行为保持兼容。
7. 新增配置、可比性、五类 Diff、聚合、API/CLI 和兼容路径有自动化测试；现有 evaluation 专项及合理可行的全量测试通过。

## 数据结构设计

### 类型化运行配置

在 `evaluation/schemas.py` 新增：

```python
class EvaluationRunConfiguration(EvaluationModel):
    model: str
    provider: Literal["configured", "disabled"]
    prompt_version: str
    rule_version: str
    run_label: Literal["baseline", "candidate"]
```

`EvaluationRunCreate` 新增 `run_configuration` / JSON alias `runConfiguration`。Service 在执行前解析为不含隐式空值的完整 effective configuration。

兼容策略：

- 保留 `versionLabel`、`modelName`、`config`、`mode`、`limit`、`repeat`；
- 旧请求未传新配置时，`modelName` 映射为 model，否则用 Settings 当前 model；provider 使用现有注入 provider；runLabel 默认 candidate；prompt/rule 使用当前版本常量；
- 新旧 model 同时存在且冲突时返回 422，不静默选值；
- Run response 新增完整 `runConfiguration`，同时保留 `modelName/versionLabel`。

### 持久化

完整 effective configuration 经 Pydantic 校验后写入 `EvaluationRunRecord.config_json["runConfiguration"]`，并保留现有 `model_name` 顶层列。`limit/repeat` 仍保存于 config JSON。

本轮不为 `evaluation_run` 加列：项目用 SQLAlchemy `create_all` 而非 migration tool，加列会让旧 SQLite 运行时缺列。类型化 schema + JSON 持久化可避免破坏旧库。旧 Run 读取时从 `model_name/version_label/config_json` 生成 legacy-compatible configuration，不回写历史数据。

### 比较响应

Comparison 包含：

- `baselineRun`、`candidateRun`：Run id、dataset/config/status 与完整 summary；
- `aggregateDelta`：overall、category、metric 的差异；metric 同时给出 raw delta 和按 direction 归一的 quality delta；
- `caseDiffCounts`：五类 Diff 数量；
- `caseDiffs`：每个 Case 的 id/title/revision、双方状态与得分、delta、classification 和 Result ids。

## Runner 执行设计

`EvaluationRunner.run_case()` 接收完整配置，并在创建隔离 Runner 前构造 effective Settings / Provider：

- model 同时覆盖 `main_model` 和 `light_model`，确保当前各 Agent 的模型参数都来自该 Run；
- provider=`configured` 使用 EvaluationService 注入 provider；provider=`disabled` 使用 `DisabledProvider`；
- Case 内 `mockModel` 故障注入保持更高优先级，维持 Fault Injection Dataset 行为；
- promptVersion/ruleVersion 写入 provenance 并校验当前支持版本；本轮不建立虚假的多版本 registry；
- 不在持久化结构、Trace 或 response 中保存 API key。

CLI 在 fixture/historical 默认沿用 disabled provider；`live_model + configured` 时用 Settings 构建 OpenAI-compatible provider，配置不完整时明确失败，不伪装成 live 运行。

## Comparison Logic

新建 `src/choice_agent/evaluation/comparison.py`，将可比性校验、Case 分组、得分提取、Diff 分类和 aggregate delta 实现为不依赖数据库的纯函数。Service 只负责 owner 边界和读取 Run/Result。

### 成对与聚合

1. 校验 baseline/candidate runLabel、Run 状态、datasetHash、evaluatorVersion 和 mode。
2. 建立 `(caseId, caseRevision, repetition)` 索引；key set 不一致时返回 409 和缺失摘要，不生成误导 Diff。
3. 按 `(caseId, caseRevision)` 分组，使用现有 `summarize_results()` 聚合该 Case 全部 repetition；Case 状态按最严重结果取 `error > failed > not_evaluated > passed`。
4. Run 级展示使用持久化 summary，同时从 Result 重算关键计数用于一致性检查，损坏或过时 summary 不静默展示。

### Diff 判定规则

按以下优先级执行，每个 Case 只属于一类：

1. `fixed`：baseline 为 `failed/error`，candidate 为 `passed`。
2. `new_failure`：baseline 为 `passed`，candidate 为 `failed/error`。
3. `improved`：未命中上述边界，且 candidate Case quality score 更高；若分数不可比，则候选状态质量级别更高。
4. `regressed`：candidate 分数或状态质量级别更低；`passed -> not_evaluated` 属于 regressed，不是 new_failure。
5. `unchanged`：状态与可比分数均无变化，或双方都无可评分证据且状态无变化。

状态质量级别仅用于无可比分数时的后备判断：`error < failed < not_evaluated < passed`。Case quality score 复用现有总分方法，不为空指标造 0 分。

### 聚合差异

- overall/category delta = candidate - baseline；任一边缺数据时为 null。
- metric `rawDelta` = candidate raw value - baseline raw value。
- metric `qualityDelta` 对 `lower_is_better` 取反，正数统一表示 candidate 更好。
- passed/failed/error/notEvaluated 分别展示双方原始计数，不合并 error 与 failed。

## Service、API 与 CLI

### Service

- `create_run()` 先解析 effective configuration，用它计算 fingerprint、保存 Run，并显式传给每个 `run_case()`。
- `compare_runs(owner_id, baseline_run_id, candidate_run_id)` 经 owner 过滤读取双方 Run/Result，再调用 comparison 纯函数。
- 保留 Bad Case `_sync_case_regression_status()`；“相对 baseline 变好”不等同于 Case verified，verified 仍要求该 Run 自身必需断言通过。
- Dashboard 旧 `comparison` 字段保留；仅在最近 baseline/candidate 严格可比时返回新摘要，不能配对时返回 null，不按日期猜测。

### API

新增只读接口：

```text
GET /api/v1/evaluations/comparisons?baselineRunId=...&candidateRunId=...
```

Run 不存在/越权为 404；存在但不可比为 409，并说明 dataset/evaluator/mode/result key 的具体不匹配原因。

### CLI

保留现有参数，新增：

- `--run-label baseline|candidate`
- `--model`
- `--provider configured|disabled`
- `--prompt-version`
- `--rule-version`
- `--compare-to-run-id`：新 Run 为 candidate 时指向 baseline，运行后输出 comparison；不传时仍只输出 Run JSON。

退出码保持：新 Run 有 failed/error 时为 1。Comparison 不默认因存在 regressed 改变 CI 退出码，避免计划外行为变化。

## 受影响文件

| 文件 | 计划修改 |
| --- | --- |
| `src/choice_agent/evaluation/schemas.py` | 新增类型化配置，扩展 Run create 契约并兼容旧字段。 |
| `src/choice_agent/evaluation/comparison.py` | 新增可比性、分组、五类 Diff 与 aggregate delta 纯逻辑。 |
| `src/choice_agent/evaluation/runner.py` | 接收配置，将 effective model/provider 作用于隔离 Orchestrator，保留 fault injection。 |
| `src/choice_agent/evaluation/service.py` | 解析/持久化配置、修正 fingerprint、调用 Runner、显式 Run 比较及兼容 response。 |
| `src/choice_agent/api/evaluations.py` | 新增 comparison GET API 及 404/409 映射。 |
| `src/choice_agent/evaluation/cli.py` | 新增配置/比较参数，按 mode/provider 选择实际 provider，保留旧用法。 |
| `tests/test_evaluation_comparison.py` | 覆盖五类 Diff、direction、空分数、repetition 聚合及不可比原因。 |
| `tests/test_evaluation_service.py` | 覆盖新旧配置、持久化、fingerprint、同 Dataset 双 Run 与 owner 边界。 |
| `tests/test_evaluation_runner.py` | 证明 model/provider 配置真正进入 Runner，回归 Trace/fault injection。 |
| `tests/test_evaluation_api.py`（新增或并入现有 API 测试） | 覆盖 comparison 成功、404、409 和旧 Run API。 |
| `tests/test_evaluation_cli.py` | 覆盖 CLI 旧参数和新配置解析，不调用真实网络。 |
| `README.md` | 小幅补充 baseline/candidate CLI/API 用法。 |
| `CHANGELOG.md` | 在当日标题精确追加新能力，保留用户现有未提交内容。 |

`db_models.py`、repository 和前端原则上不改；只有发现必要缺口时才做最小增量。

## 兼容性和破坏性变更评估

- 不修改 17 项指标 id、category、direction、scored 定义和汇总公式。
- 不修改 Case/Dataset/Result 表结构、Dataset snapshot 或 Result 唯一键。
- 不删除 `versionLabel/modelName/config`，旧 UI 可继续创建和读取 Run。
- 不改变 Bad Case verified/reopened 规则，不用相对改善替代绝对断言通过。
- 不改变 Trace Snapshot 格式或旧 diet evaluation 接口。
- 不新增依赖，不修改数据库迁移机制，不大改前端 UI。
- model/provider 从“仅记录”变为“真实执行”是预期变化；旧请求默认 effective 配置必须与当前 Runner 行为一致。

## 风险、边界与技术折衷

1. 单一 model 同时用于 main/light 是当前需求下最小清晰语义；后续需要双模型再扩展，本轮不提前抽象。
2. configured provider 是运行环境注入实例；Run 保存类型标识但不保存密钥。
3. prompt/rule 仅作 provenance 且校验当前支持版本，是为避免“标签不同但代码相同”的伪比较；本轮不重构全局提示词/规则为多版本注册表。
4. 含 error 的 partial Run 必须允许比较，否则 `new_failure` 会漏掉工程回归；但 Result key set 必须完整。
5. score delta 是描述性比较，不宣称统计显著性。
6. 不自动把“上一次运行”猜作 baseline；显式 run id 是完整比较的必要条件。

## 验证方案

1. Schema：新配置别名、枚举/长度、旧字段映射、冲突拒绝和默认值。
2. Runner：fake provider 记录 model；disabled 不调用 fake；mockModel 仍覆盖；双方 Trace 独立。
3. Service：同 Dataset 创建 baseline/candidate，配置、fingerprint、Result key set、outputs 与 Trace 均持久化；requestId 幂等保持。
4. Comparison：五类分类、高/低优 metric、空分数、repetition、overall/category/metric delta。
5. 不可比：owner、runLabel、Run 状态、dataset hash、evaluator version、mode、Case revision/repetition key set。
6. API：comparison 成功、404、409；旧 Run create/detail contract 可用。
7. CLI：旧命令无新参数仍执行；新参数生成 effective config；compare-to 不访问外网。
8. 回归：evaluation 专项、关联 API/CLI、全量 pytest、compileall、`git diff --check`。
9. Diff 复核：无前端大改、无指标口径变化、无用户现有修改被覆盖。

## 注意事项

- 所有新配置写入 JSON 前经 Pydantic 校验，旧 Run 通过明确 legacy adapter 读取。
- comparison/configuration 错误不得静默吞掉；API/CLI 给出可操作原因。
- 若实施中发现必须建立 prompt/rule 多版本 registry 才能继续，属于重要范围扩展，应暂停并更新 Plan，不擅自重构。
- 后端 API 和 CLI 完整可用即达到本轮范围目标，不以前端表单作为验收前提。

## Todo

- [x] 新增类型化 Evaluation Run Configuration、版本常量、旧请求/旧 Run 兼容映射和配置测试。
- [x] 让 effective model/provider 真正作用于每个隔离 Case，保留 fault injection 与 Trace Snapshot，补 Runner 测试。
- [x] 调整 EvaluationService 的指纹、持久化、response 和同 Dataset 双 Run 执行逻辑，保持 Bad Case 同步规则。
- [x] 实现 comparison 纯逻辑：严格可比性、Case/repetition 分组、五类 Diff、双版本 summary 和 aggregate delta。
- [x] 新增 comparison API，覆盖 owner、404、409 和成功响应测试。
- [x] 扩展 CLI 的 run configuration 与 compare-to 参数，保持旧命令和退出码兼容，补 CLI 测试。
- [x] 精确更新 README 和当日 CHANGELOG，不覆盖用户现有未提交修改。
- [x] 运行 evaluation 专项、关联 API/CLI、全量 pytest、compileall 和 `git diff --check`，复核最终 Diff 与所有 Todo。
## 实施与验证结果

- 已按 Plan 完成类型化 Run Configuration、真实 model/provider 执行、严格 Run comparison、API、CLI、兼容适配与自动化测试。
- 未修改 17 项指标定义、数据库表结构、Bad Case 生命周期或 Trace Snapshot 格式；未大改前端 UI。
- Evaluation 新旧专项：33 passed。
- 全量测试：195 passed，1173 warnings；warning 均为仓库既存 `datetime.utcnow()` 弃用提示。
- 最终检查：`python -m compileall -q src tests`、CLI `--help`、`git diff --check` 均通过。
