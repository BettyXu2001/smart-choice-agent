# Diet / Travel Evaluation Batch Plan

日期：2026-10-17。状态：已完成并验证。

依据：`adr/2026-10/2026-10-17-diet-travel-evaluation-batch-research.md`。

## 目标与成功标准

在现有 Evaluation v3 上发布并实跑一个饮食/旅行专项批次，得到可复现、可分组、列全指标且不掩盖未评测项的结果。

成功标准：

1. 新增不可变 `diet-travel-evaluation/v1`，共 20 条：Diet 10 条、Travel 10 条。
2. 覆盖已确认的正常完整输入、信息不足需澄清、硬约束、约束冲突、边界/异常、多轮修改、同义改写/稳定性，并包含受控可靠性 Case。
3. 所有 Case 通过真实 EvaluationRunner 与对应 Orchestrator；禁止 `fixtureActual` 伪造结果。
4. 使用固定数据源、`DisabledProvider`、临时 SQLite 和 `repeat=2` 完成一次 Run，共 40 个 Result。
5. 报告逐项列出 Evaluation v3 的全部 23 项指标及分母、evaluationMethod、N/A/manual 原因；同时列出 Overall、分类分、Case rates、domain/caseType/tag 分组、路由诊断、平均/P95 延迟、Token/成本信息和失败明细。
6. 新 Dataset 的 seed、分布、关键 assertion 和实跑路径有自动化测试；现有 v1/v2/v3 与 Fault v2 保持不变。
7. 定向测试、全量测试、compileall、Diff 检查和实际 Run 完成；无法验证项明确记录。

## Dataset 设计

Dataset：`diet-travel-evaluation/v1`。

### Diet：10 条

1. `routing`：无显式 domain 的饮食表达正确路由到 diet。
2. `recommendation`：晚餐 + 清淡等完整输入产出候选、推荐、理由和 Evidence。
3. `clarification`：关键信息不足时进入真实澄清状态。
4. `hard_constraint`：可结构化的饮食硬限制得到提取并约束候选。
5. `soft_preference`：首选候选的 score breakdown 覆盖用户强调偏好。
6. `safety`：医疗承诺/特殊健康风险触发 risk flags，且不返回被禁止的推荐。
7. `correction`：多轮修改正式条件后，新值生效、旧值移除并覆盖相关状态。
8. `what_if`：假设变化不污染正式状态；如 Diet 当前链路不支持可靠 what-if，则改为已存在的多轮换一批隔离行为，并保留 `edge` tag，不伪造能力。
9. `stability`：同义表达或固定输入重复执行保持推荐稳定。
10. `reliability`：受控模型异常后规则/确定性路径正确降级并留下 Trace。

### Travel：10 条

1. `routing`：无显式 domain 的旅行表达正确路由到 travel。
2. `recommendation`：出发地、天数、预算和偏好充分时正常推荐。
3. `clarification`：缺 departure/days 时追问；完整时不多问由相邻 Case/断言覆盖。
4. `hard_constraint`：预算或行程硬限制过滤不合格候选。
5. `soft_preference`：轻松/人少等偏好进入首选候选评分。
6. `conflict`：互相冲突或不可满足的条件产生明确、结构化且不误推荐的结果。
7. `correction`：多轮修改预算/天数/偏好后正式状态与推荐按预期变化。
8. `what_if`：下雨等假设不污染正式状态，且无资料时不编造天气事实。
9. `reliability`：Search transport error 在 auto 模式回退 fixture，并记录 source warning 与 fallback Trace。
10. `edge`：非法 Search response 或 CandidateAgent 失败形成预期 error/rolled_back Trace，可定位失败 Agent，不中断整批 Run。

具体文案和 assertion path 以当前真实代码输出为准。允许在不改变上述目标的前提下，根据 dry run 修正字段路径或改用同等强度的结构化断言；不允许通过删除关键断言或只断言“请求成功”来制造通过。

## 指标覆盖策略

- 23 项指标全部进入结果表。
- `recommendation_stability` 通过 `repeat=2` 计算。
- 路由、澄清、约束、纠正、硬/软偏好、安全、排除、状态保持、纠正覆盖、what-if、Fallback、Agent failure、延迟优先使用确定性 assertion/Trace observation。
- `unsupported_fact_rate` 若只能人工判断，则保留 manual，并在结果报告中给出人工审阅结论，不改变 deterministic Regression Gate。
- Token/成本在 `DisabledProvider` 下预计为 N/A；报告 provider call、unreported usage、unknown price，解释为何不能给出伪 0。
- 故障注入导致的 fallback activation 和 Agent failure 按原始发生率展示；预期故障 Case 只要错误被正确观察，Case 可以通过。

## 实现方式

### Case 与 Dataset

在 `src/choice_agent/evaluation/fixtures.py` 中：

- 新增 `DIET_TRAVEL_DATASET = {"name": "diet-travel-evaluation", "version": "v1"}`。
- 新增独立 Case factory，避免改动已有四个 Dataset 的 Case snapshot。
- 将新 Dataset 加入 starter seed 列表；所有 seedId 稳定且带版本前缀。
- 复用现有 `_case`、`_auto`、`_manual` 和现有 fault setup，不新增重复 evaluator。

### 测试

- `tests/test_evaluation_service.py`：验证 Dataset seed、20 条数量、10/10 领域分布、类型/tags、旧 Dataset 不变。
- `tests/test_evaluation_runner.py`：覆盖新增批次的代表性 Diet/Travel 正常、澄清、可靠性和预期 error Case。
- 如 repeat/stability 汇总已有通用覆盖，仅补专项 Run 断言，不复制底层 metrics 单元测试。

### 实跑与报告

- 使用临时 SQLite 初始化固定 Diet 数据并 seed starter datasets。
- 定位新 Dataset id，按 fixture mode、provider disabled、repeat=2、limit=20 运行。
- 保存机器可读 Run JSON 到 `docs/diet-travel-evaluation-results-2026-10-17.json`。
- 整理人读报告到 `docs/diet-travel-evaluation-results-2026-10-17.md`，包含 20 条 Case 清单、全部 23 项指标、performance、分组、路由诊断、Bad Cases/错误、manual/N/A 和运行环境说明。

## 受影响文件

| 文件 | 计划修改 |
| --- | --- |
| `src/choice_agent/evaluation/fixtures.py` | 追加专项 Dataset 与 20 条 Case；不改已有 snapshots。 |
| `tests/test_evaluation_service.py` | 验证 seed、版本、数量和领域/类型分布。 |
| `tests/test_evaluation_runner.py` | 验证代表性专项 Case 真实执行和故障语义。 |
| `docs/diet-travel-evaluation-results-2026-10-17.json` | 保存一次实际 Run 的机器可读结果。 |
| `docs/diet-travel-evaluation-results-2026-10-17.md` | 整理全部指标和 Case 结果。 |
| `README.md` | 在 Evaluation 数据集说明中增加专项批次及复现命令。 |
| `CHANGELOG.md` | 追加到现有 `2026-10-17` 标题，记录新 Dataset 与实跑报告。 |
| 本 Plan | 实施和验证完成后逐项勾选 Todo。 |

不计划修改指标定义、deterministic evaluator、Runner 架构、数据库 schema、生产领域逻辑或 API。

## 兼容性与风险

- 仅新增 Dataset；旧 `core-regression/v1/v2/v3` 和 `fault-injection-reliability/v2` 保持不可变。
- starter seed 会新增数据，但不改变旧 Dataset hash；使用稳定 seedId 保持幂等。
- 当前工作区已有未提交 v3 改动，实施必须基于现有内容做小范围追加，并在最终 diff 中区分本次变化。
- 若某个计划 Case 暴露真实产品缺陷，本任务只如实记录 Bad Case，不未经批准修改生产逻辑；若需要修复，另行 Research/Plan。
- 若现有 Runner 不支持某个受控 Diet/Travel 故障路径，优先换用同领域、同指标且已有白名单支持的 Case；不扩展 Runner，除非更新 Plan 并重新获批。
- 结果耗时受本机影响，只作为本次基线；不设未经确认的性能阈值。

## 验证方案

1. 实施前复查 `git status` 和相关 diff，保护现有未提交 v3 修改。
2. 每次重要写入后回读对应片段确认落盘。
3. Case 定义静态检查：总数 20、Diet 10、Travel 10、seedId 唯一、无 `fixtureActual`、type/tag 分布符合计划。
4. 定向测试：

```text
.venv\Scripts\python.exe -m pytest \
  tests\test_evaluation_service.py \
  tests\test_evaluation_runner.py \
  tests\test_evaluation_metrics.py \
  tests\test_deterministic_evaluation.py -q
```

5. 实际临时数据库 Run：fixture + disabled provider + limit 20 + repeat 2。
6. 校验 Run：40 Results；无非预期 error；预期 error Case 的 Regression Gate 通过；23 项指标全部出现在 summary；各 N/A/manual 有原因。
7. 全量测试：`.venv\Scripts\python.exe -m pytest`。
8. 编译：`.venv\Scripts\python.exe -m compileall -q src scripts`。
9. 检查 `git diff --check`、最终 diff、重复日期标题、调试输出、占位符和 Todo。

## Todo

- [x] 复查当前工作区 diff 与专项 Case 所依赖的真实输出路径。
- [x] 新增不可变 `diet-travel-evaluation/v1` 和 20 条平衡 Case。
- [x] 补充 seed、分布、代表性真实执行与可靠性测试。
- [x] 运行定向测试并修正 Case/assertion 定义问题，不修改产品行为。
- [x] 在临时数据库以 `repeat=2` 实跑专项 Dataset。
- [x] 保存 Run JSON，整理包含全部 23 项指标的结果报告。
- [x] 更新 README 和同日 CHANGELOG 条目。
- [x] 执行全量测试、compileall、diff 检查和最终 Todo 对照。
