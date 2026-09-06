# Evaluation Regression Dataset Plan

日期：2026-09-06。状态：待用户审查与明确实施批准。
依据：同目录 `2026-09-06-evaluation-regression-dataset-research.md`。

## 目标与成功标准

把当前 starter evaluation 从“少量 fixture 展示样例”升级为“固定数据集 + 真实链路 + 可重复 pass/fail + 指标 + Trace Snapshot”的可信回归基线。

成功标准：

1. 自动 seed 出 20 条 Core Regression Cases，核心 Case 不依赖 `fixtureActual`。
2. 自动 seed 出约 6 条 Fault Injection / Reliability Cases，单独 dataset 和 run。
3. 保留 `EvaluationRunCreate.limit <= 20`，Core 与 Fault Injection 拆成两个 Dataset / Run。
4. 现有数据库也能幂等补齐新增 seed case 和 dataset，不只对新库生效。
5. 每条 Case 运行后有明确 passed / failed / error / not_evaluated、指标结果和 Trace Snapshot。
6. 文档明确口径：Core Regression 验证固定数据源下的确定性 Orchestrator 产品行为，不代表真实 LLM / Web Search 完整质量。

## Case 分类与数量

### Core Regression Dataset

Dataset：`core-regression`，version：`v1`，数量：20。

全部优先跑真实 Orchestrator + fixture source，不使用 `fixtureActual`。

| 类别 | 数量 | 目标 |
| --- | ---: | --- |
| 多轮纠正 | 4 | 新值生效、旧值移除、候选归属正确、短回答能承接问题 |
| Hard Constraint | 4 | 硬约束过滤、用户排除、缺失必要数据、推荐不选被排除候选 |
| What-if | 3 | 假设分析不污染正式字段、正式推荐和正式 analysis |
| Recommendation / Explanation | 3 | 推荐候选、理由、追问解释和 tradeoff 一致 |
| Evidence | 3 | evidenceIds 可回溯、数值比较引用多候选、用户来源不能伪造 trusted evidence |
| Candidate Search | 2 | shopping / travel fixture 候选、Evidence、ranking 和 source mode 可观察 |
| Fallback | 1 | 模型解释不可用时 rules fallback 产出可用结论 |

候选 Case：

1. Offer：稳定优先后推荐 B。
2. Offer：追问为什么不选 A，解释包含 A 的 tradeoff。
3. Offer：B 通勤两小时后，该事实正确挂载到 B，并进入当前分析/顾虑；不要求一定改变最终推荐。
4. Offer：纠正 B 通勤半小时后旧“两小时”事实移除。
5. Offer：每天最多 1 小时通勤后 B 被 hard constraint eliminate。
6. Offer：确认 B 通勤不能妥协后 B 进入 excluded candidates。
7. Shopping：预算 8000 初始化候选和推荐。
8. Shopping：预算改成 7000 后候选价格不超过 7000。
9. Shopping：如果预算改成 6000，不污染正式预算 8000。
10. Shopping：what-if 后正式改预算 7000，正式状态才更新。
11. Shopping：预算 9000 数值比较理由引用至少两个候选 Evidence。
12. Shopping：硬约束排除超预算候选。
13. Learning：输入中显式提供结构化在线课程、开源项目实战、文档与论文路线三条 Manual Candidates；零基础每周三小时推荐结构化课程。
14. Learning：沿用显式 Manual Candidates；已有 Python 且想实践后推荐开源项目实战。
15. Learning：沿用显式 Manual Candidates；短回答“有”能承接上一轮问题，不重复澄清。
16. Travel：上海两天一夜 fixture search 产生候选和推荐。
17. Travel：如果下雨但无天气资料，不编造天气且不污染正式推荐。
18. Generic：未知自由文本不被静默当成有效约束。
19. Evidence：推荐理由 evidenceIds 均存在于 decision evidence。
20. Fallback：解释模型不可用时 analysis mode 为 `rules_fallback`，且 warning 可观察。

### Fault Injection / Reliability Dataset

Dataset：`fault-injection-reliability`，version：`v1`，数量：约 6。

这些不是 Runtime Bad Cases。它们是受控故障注入，用于验证可靠性和降级路径。

候选 Case：

1. 模型 timeout，期望 rules fallback。
2. 模型返回 unknown candidate id，期望 fallback 且不推荐未知候选。
3. 模型返回 false quote，期望 fallback。
4. 模型生成 unsupported number，期望 fallback / warning。
5. Search Provider 缺 API Key，受控进入 `searchMode=web`，期望 search_provider_failed error event 或 case error 可观察。
6. Search Provider transport error / invalid response，受控进入 `searchMode=web`，期望 run 不中断且 result error 可记录。

## 真实链路与 Mock 边界

Core Regression：

- `generic`、`shopping`、`travel` 走 `GenericDecisionOrchestrator`；
- `diet` 如后续纳入，走 `DietOrchestrator`；
- 默认 context 使用 `{"searchMode": "fixture"}`；
- provider 默认 `DisabledProvider`，需要模型路径时使用确定性 stub；
- 不使用真实 Web Search；
- 不使用真实外部 LLM 作为稳定基线；
- 不使用 `fixtureActual`。

Fault Injection / Reliability：

- 模型故障使用本地 stub provider；
- 搜索故障使用白名单 setup 或 mock provider，并显式让 Case 进入受控 `searchMode=web`，避免 Runner 默认 `searchMode=fixture` 导致未覆盖 Web Search 路径；
- 结果必须标明 mock / injected fault；
- run 失败不能中断整批，单 case 记录 error 或 fallback 断言。

## Versioned Seed / Dataset 初始化

现状问题：`ensure_starter_cases()` 当前只要已有任意 Case 就跳过，导致现有数据库不会获得新增 starter cases。

最小幂等方案：

1. 为每条 starter case 增加稳定 seed id，例如：
   - `caseData.setup.seedId = "core-regression-v1.offer-stability"`
   - `caseData.setup.seedDataset = "core-regression"`
   - `caseData.setup.seedVersion = "v1"`
2. `ensure_starter_cases(owner_id)` 不再用“有任意 case 就返回”的逻辑，而是：
   - 读取当前 owner 的所有 cases；
   - 从 `case_data.setup.seedId` 建索引；
   - 对缺失 seed id 创建新 case；
   - 已存在 seed id 不覆盖、不更新，保护用户手工编辑。
3. seed 补齐后创建两个 dataset：
   - `core-regression` / `v1`：包含 20 条 Core seed case snapshot；
   - `fault-injection-reliability` / `v1`：包含约 6 条 Fault Injection seed case snapshot。
4. Dataset 创建保持幂等：
   - 同 owner/name/version 已存在则跳过；
   - 不静默修改已存在 dataset snapshot；
   - 如果 seed 内容未来变化，使用新 version，例如 `v2`。
5. 如果某些 seed case 已存在但 dataset 缺失，dataset 从当前 case response 生成 snapshot。
6. 如果用户删除部分 seed case，下一次 dashboard / run 入口可补齐缺失 case。

该方案无需数据库 schema 变更，复用现有 JSON `case_data.setup`。

## Runner 修改

保持最小增强：

1. 保留 `limit <= 20`。
2. Core case 没有 `fixtureActual` 时继续走隔离 DB + Orchestrator。
3. 支持 `case_data.commands`：
   - create 后按顺序调用 `GenericDecisionOrchestrator.command()`；
   - command 使用上一轮 revision；
   - 暂不支持 diet command，遇到不支持时显式 error。
4. 支持白名单 fault injection setup：
   - `setup.mockModel = "timeout" | "unknown_candidate" | "false_quote" | "invented_number"`；
   - `setup.mockSearch = "missing_key" | "transport_error" | "invalid_response"`；
   - mockSearch case 必须同时显式启用受控 `searchMode=web` 或由 Runner 等价设置，确保真正走到 Web Search provider；
   - 不支持任意代码、任意模块路径或 URL。
5. `outputs` 中保留：
   - `mode`；
   - `domain`；
   - `traceId`；
   - `speechText`；
   - `displayBlocks`；
   - `decisionState`；
   - 必要时增加 `turns` 以便多轮断言定位。

## 需要修改的文件

| 文件 | 修改内容 |
| --- | --- |
| `src/choice_agent/evaluation/fixtures.py` | 扩充 20 条 Core + 约 6 条 Fault Injection seed cases；添加稳定 seed id / dataset / version tags；Core 不使用 `fixtureActual`。 |
| `src/choice_agent/evaluation/service.py` | 将 `ensure_starter_cases()` 改为 versioned seed 补齐；幂等创建两个 starter datasets；不覆盖已有 seed case。 |
| `src/choice_agent/evaluation/runner.py` | 支持 commands 和白名单 fault injection setup；保留隔离 DB 和 trace snapshot。 |
| `tests/test_evaluation_service.py` | 覆盖现有数据库补 seed、dataset 幂等、limit 20 不变、重复调用不重复创建。 |
| `tests/test_evaluation_runner.py` | 覆盖 Core 真实链路、无 `fixtureActual`、fault injection mock、pass/fail/error 和 trace snapshot。 |
| `CHANGELOG.md` | 记录新增固定 Regression Dataset、Fault Injection Dataset 和 versioned seed。 |
| 可选文档 | 如 README 或 docs 已有评估说明，则补充稳定回归与真实 LLM/Web Search 口径边界。 |

## 兼容性

- 不改 `EvaluationRunCreate.limit <= 20`。
- 不新增数据库表或列。
- 不删除旧 starter cases；如旧 case 缺 seed id，可作为普通历史 case 保留。
- 不修改旧 `/api/v1/diet/evaluations`。
- 不改变 Dashboard / Runner / Dataset API 的已有响应结构。
- 不把 Fault Injection 样例称为 Runtime Bad Cases。
- 不把 fixed fixture regression 的分数包装成真实 LLM / Web Search 质量。

## 风险与边界

1. 20 条 Core case 全部真实链路后，当前 main 可能暴露实际失败；这是本需求期望的可信结果，不应通过复制当前输出为金标签掩盖。
2. Learning 没有内置稳定候选数据；相关推荐 Case 必须显式提供 Manual Candidates，不为了 Regression Case 新增学习推荐规则。
3. Search fault injection 如果未切换到 Web Search 路径，会误测 fixture 路径；测试需覆盖 mockSearch 确实进入 web provider。
4. 某些断言路径可能过脆，需要优先断言稳定业务投影，不比较完整 state。
5. Mock provider 必须小而明确，避免变成第二套模型运行框架。
6. Dataset snapshot 不会自动随 seed case 更新；后续 seed 变化要升 dataset version。
7. 真实模型和真实搜索质量另行评估，本次只建立稳定 regression baseline。

## 验证方案

1. 运行 `python -m pytest tests/test_evaluation_service.py tests/test_evaluation_metrics.py tests/test_evaluation_runner.py`。
2. 运行相关业务回归：
   - `python -m pytest tests/test_decision_assistance.py`
   - `python -m pytest tests/test_decision_canvas.py`
   - `python -m pytest tests/test_evidence_presentation.py`
   - `python -m pytest tests/test_candidate_search_productization.py`
   - `python -m pytest tests/test_trace_observability.py`
3. 验证 starter seed：
   - 空库 seed 后有 20 条 Core + 约 6 条 Fault Injection；
   - 已有任意 case 的库也会补齐缺失 seed；
   - 重复调用不会重复创建；
   - 用户编辑过的 seed case 不被覆盖。
4. 验证 dataset：
   - `core-regression/v1` caseCount 为 20；
   - `fault-injection-reliability/v1` caseCount 约 6；
   - 同名同版本 dataset 不重复创建；
   - dataset hash 稳定。
5. 验证 run：
   - Core run 在 `limit <= 20` 下完整运行；
   - Fault Injection 单独运行；
   - result 包含 pass/fail/error、assertions、metrics、traceSnapshot；
   - 批量 run 中单 case error 不中断其他 case。
6. 执行 `python -m compileall -q src`、`git diff --check` 和最终 diff 范围复核。

## Todo

- [x] 调整 starter case 定义，补齐 20 条 Core Regression 和约 6 条 Fault Injection / Reliability seed cases。
- [x] 实现 versioned seed 补齐和两个 starter dataset 的幂等初始化。
- [x] 最小增强 Runner，支持 commands 和白名单 fault injection setup。
- [x] 补充 service / runner 测试，覆盖现有库 seed、dataset、真实链路和 mock 故障。
- [x] 运行相关业务回归与基础验证。
- [x] 更新 CHANGELOG 和必要文档，明确稳定回归与真实 LLM/Web Search 口径边界。
