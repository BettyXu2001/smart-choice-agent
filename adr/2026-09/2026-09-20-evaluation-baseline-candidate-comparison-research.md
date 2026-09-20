# Evaluation Baseline / Candidate 真实版本对比 Research

日期：2026-09-20。状态：研究完成，未实施。

## 需求与研究范围

本次要在不重构现有 17 项指标的前提下，让同一个 Regression Dataset 可用独立 Baseline / Candidate 配置执行，持久化每个 Case 的结果，并基于两个真实 Run 生成逐 Case Diff 和双版本聚合结果。范围限于后端数据结构、service、runner、comparison logic、API / CLI 兼容与自动化测试；不大改前端 UI，不改动指标定义与评分公式。

这会修改运行配置契约、核心评测流程和版本对比语义，属于大改动。

## ADR / 历史方案检索

已按 evaluation、regression、dataset、run、baseline、candidate、comparison、Bad Case、Trace Snapshot 和相关模块路径检索 `adr/`、`src/`、`tests/`、README 与 CHANGELOG。

- `adr/2026-09/2026-09-05-evaluation-dashboard-research.md` / `plan.md`：高度相关且已完成。建立了 Case、Dataset、Run、Result、Bad Case 闭环、17 项指标、隔离回放、Trace Snapshot 和初步版本比较。
- `adr/2026-09/2026-09-06-evaluation-regression-dataset-research.md` / `plan.md`：高度相关且已完成。建立了 `core-regression/v1` 的 20 条固定 Case、真实 Orchestrator Runner、故障注入集和现有数据库幂等补 seed。
- `adr/2026-09/2026-09-09-browser-real-api-settings-research.md` / `plan.md`：相关。已实现请求头级的运行时 model/settings/provider 构造，可作为 evaluation 配置真实作用于 Runner 的参考。
- `adr/2026-09/2026-09-19-decision-quality-p0-*`：当前工作区存在用户未提交的进行中修改，与本轮 evaluation 文件不直接重叠；实施时必须保留并避免扩大范围。

归档决策：新建本 Research / Plan。原有 Dashboard 和 Dataset ADR 已完成，本次是对 Run 配置和成对比较语义的独立增量，追加到旧 Plan 会混淆历史边界。

## 核心文件及实际职责

| 文件 | 已确认的当前行为 |
| --- | --- |
| `src/choice_agent/evaluation/schemas.py` | `EvaluationRunCreate` 目前有 `versionLabel`、`mode`、`modelName`、`limit`、`repeat` 和无类型 `config`；没有 provider、promptVersion、ruleVersion 或 runLabel 契约。 |
| `src/choice_agent/db_models.py` | `EvaluationRunRecord` 已有 `model_name` 与 JSON `config_json`；`EvaluationResultRecord` 已按 `run_id + case_id + case_revision + repetition` 唯一，并保存 output、Trace Snapshot、assertions、metrics 和 error。 |
| `src/choice_agent/evaluation/service.py` | Dataset 使用不可变 Case snapshot；`create_run()` 顺序执行每个 snapshot 和 repetition；当前只把 `modelName` 写入 Run，没有交给 Runner。Dashboard comparison 只找最近两个“配置相同”Run 并返回 overall score delta，不读取 Result。 |
| `src/choice_agent/evaluation/runner.py` | 在每个 Case 的内存 SQLite 中跑真实 Diet / Generic Orchestrator并保存最终 Trace；默认使用构造 Runner 时的 Settings / Provider。Case 内白名单 fault injection 可覆盖 provider/search。 |
| `src/choice_agent/evaluation/metrics.py` | 定义五类 17 项指标，16 项进入评分，已支持 overall、category、metric、coverage 及 passed/failed/error/notEvaluated 聚合。本次无需改动定义。 |
| `src/choice_agent/evaluation/cli.py` | 已支持 dataset/version/mode/limit/repeat，但固定注入 `DisabledProvider`，没有 baseline/candidate 配置或指定两个 Run 比较。 |
| `src/choice_agent/api/evaluations.py` | 已有 Run 创建/列表/详情 API，没有显式 Run-to-Run comparison API。 |
| `src/choice_agent/providers/model.py` / `config.py` | 当前只有注入的 OpenAI-compatible provider 与 Disabled provider。Settings 保存 main/light model，provider 调用会使用每次传入的 model。 |
| `tests/test_evaluation_*.py` | 已覆盖 17 指标目录与聚合、Dataset snapshot、requestId 幂等、20 条 Core 真实回放、Trace Snapshot 和 6 条故障注入。 |

## 当前数据流与缺口

当前流程：`EvaluationRunCreate` → 计算 request fingerprint → 获取 Dataset Case snapshots → 创建 running Run → Runner 隔离执行每个 Case/repetition → 保存 Result → `summarize_results()` → 保存 Run summary。

主要缺口：

1. `modelName` 只是记录字段，没有真正改变 Runner 使用的 main/light model。
2. provider、promptVersion、ruleVersion 和 baseline/candidate 标签没有类型化、可指纹的运行配置。
3. 现有“版本对比”不读取两个 Run 的 Result，不能证明是同一批 Case，也不能生成逐 Case Diff。
4. 现有 `_comparable()` 要求 model 相同，反而阻止“仅切换 model 的 baseline/candidate”核心用例。
5. 没有对 Run 状态、Dataset hash、evaluator version、Case revision 和 repetition key set 的成对校验。
6. CLI 无法显式传入新配置或比较已完成的两个 Run。

## 可复用能力

- 继续使用 Dataset 的不可变 `case_snapshots` 和 `dataset_hash`，不引入新的 Case 复制机制。
- 继续使用 Result 的 Case/revision/repetition 唯一键，已满足“每 Case 独立结果”的持久化基础。
- 继续调用 `summarize_results()` 生成两个版本的 overall/category/metric/case counts，不复制或改写 17 项指标逻辑。
- 继续使用每 Case 内存 SQLite、fault injection、Trace Snapshot、Bad Case 状态同步和现有 API owner 边界。
- 继续使用 Run 的 `config_json` 保存类型化运行配置，避免 SQLite `create_all` 无法为已有表补列导致的隐式迁移风险。

## 配置真实性边界

- `model` 可作为真实执行参数：在 Case 隔离执行前生成 effective Settings，将 main/light model 都设为该 Run 的 model，确保模型差异真正进入 Orchestrator。
- `provider` 可在现有能力内真实选择 `configured` 或 `disabled`；不持久化 API key，不允许用未注册字符串伪装另一个 provider。
- 代码库当前没有可按 ID 切换的 prompt registry 或 rule registry。`promptVersion` / `ruleVersion` 必须定义为可追溯 provenance，纳入指纹和比较报告，但不能仅凭标签声称切换了不存在的实现。新 Run 使用当前支持的版本常量；历史 Run 可保留旧 provenance。
- 真实对比指两边都是已执行、已保存 Result 的 Run，而不是根据当前得分和人工 version label 推测旧版结果。当前进程不自动 checkout 旧代码。

## 比较可比性约束

两个 Run 只有同时满足以下条件才生成 Diff：

1. 归属同一 owner，分别标记为 baseline 和 candidate；
2. 都是 `completed`，或是已保存全部 Case 结果但含 error 的 `partial`；
3. `datasetHash` 相同；
4. `evaluatorVersion` 相同，保证 17 项指标口径一致；
5. mode 相同，避免把 fixture 和 live model 样本混为质量差异；
6. 两边 Result 的 `(caseId, caseRevision, repetition)` key set 完全一致。

model、provider、promptVersion 和 ruleVersion 允许不同，它们正是被比较的版本配置。

## 潜在问题和约束

1. 同一 Case 可有多个 repetition；逐 Case Diff 必须按 Case/revision 分组后聚合全部 repetition。
2. error 是执行异常，failed 是必需断言失败；Diff 需先处理 fixed/new_failure，再处理分数或状态改善。
3. 单 Case 可能没有可评分指标；不得构造分数，只能使用状态转换或 `unchanged`。
4. `partial` 当前表示全部 Case 已跑完但有 error；应允许比较，因为 error 是重要回归信号，但必须严格校验 Result key set。
5. 前端仍可能发送旧 `versionLabel/modelName/config`。新 schema/response 必须兼容，不强迫本轮 UI 大改。
6. 当前工作区不干净；不得覆盖或回滚用户现有修改。CHANGELOG 只能精确追加。

## 实施前基线

```text
.venv\Scripts\python.exe -m pytest tests/test_evaluation_service.py tests/test_evaluation_metrics.py tests/test_evaluation_runner.py
10 passed, 393 warnings in 65.10s
```

警告为既存的 `datetime.utcnow()` 弃用警告。本轮尚未修改产品代码。

## Plan 阶段需明确的事项

- 类型化 Run Configuration 的字段、默认值、旧请求映射和指纹口径；
- Runner 如何将 effective model/provider 作用于每个隔离 Case；
- comparison 的纯函数边界、可比性错误和五类 Diff 优先级；
- API / CLI 的最小增量与旧用法兼容；
- 不做数据库加列迁移时，如何让结构化配置仍是正式数据模型，而不是无约束字典。
