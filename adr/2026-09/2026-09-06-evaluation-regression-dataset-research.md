# Evaluation Regression Dataset Research

日期：2026-09-06。状态：研究完成，待 Plan 审查。

## 需求与范围

本次目标是完善 Evaluation Regression Dataset，把现有“评估系统”升级为“有可信评测结果”。重点是建设固定、可重复运行、可比较版本的核心回归 Case，而不是重复开发已存在的 Evaluation Dashboard / Runner / API 能力。

范围包括：

- 扩充约 20 条 Core Regression Cases；
- 增加约 6 条 Fault Injection / Reliability Cases；
- 优先使用真实 Orchestrator 链路和固定数据源，减少 `fixtureActual`；
- 覆盖多轮纠正、Hard Constraint、What-if、Recommendation / Explanation、Evidence、Candidate Search、Fallback；
- 补齐现有数据库的 starter seed 兼容路径，避免只对新库生效；
- 明确稳定回归口径，不宣称覆盖真实 LLM / Web Search 完整质量。

本次属于评估数据集和回归质量口径建设，影响核心评测可信度与数据初始化行为，按大改动处理。当前阶段只做 Research / Plan，不修改产品代码。

## ADR 检索

已按 evaluation、regression、dataset、case、fixtureActual、orchestrator、trace、what-if、evidence、candidate search 等关键词检索 `adr/`、`src/`、`tests/`、`docs/`。

相关记录：

- `adr/2026-09/2026-09-05-evaluation-dashboard-research.md` / `plan.md`：高度相关，已设计并实现 Dashboard、Case、Dataset、Run、Result、版本对比、Bad Case Center 和 Runner 闭环。本次不重复开发这些能力。
- `adr/2026-09/2026-09-04-conversation-decision-assistance-research.md` / `plan.md`：候选事实纠正、模型校验、rules fallback、what-if 隔离等能力来源，可转化为 Regression Case。
- `adr/2026-09/2026-09-05-candidate-search-productization-research.md` / `plan.md`：固定来源、fixture/web 搜索模式和错误路径相关。
- `adr/2026-09/2026-09-05-decision-canvas-what-if-research.md` / `plan.md`：正式 analysis 与假设 analysis 隔离相关。
- `adr/2026-09/2026-09-05-decision-trace-observability-research.md` / `plan.md`：Trace v2、推荐变化、fallback 观测相关。
- `adr/2026-09/2026-09-05-evidence-presentation-research.md` / `plan.md`：Evidence 引用、来源状态和解释一致性相关。

归档决策：新建本 Research / Plan，原因是本次主题是数据集内容、seed 兼容和评测口径，和 2026-09-05 的 Dashboard / Bad Case 闭环不是同一改动边界。

## 当前真实现状

`src/choice_agent/evaluation/schemas.py` 已定义 Case、Dataset、Run、Review schema。`EvaluationRunCreate.limit` 当前最大为 20，与既有 ADR 中“同步 Run 最多 20 Case”的约束一致，本次不修改。

`src/choice_agent/evaluation/runner.py` 已支持真实 Orchestrator 链路：没有 `fixtureActual` 时会在临时 SQLite 中运行 `DietOrchestrator` 或 `GenericDecisionOrchestrator`，并复制输出、断言、指标和 Trace Snapshot。当前 Runner 尚未执行 `case_data.commands`，也没有受控 fault injection setup。

`src/choice_agent/evaluation/fixtures.py` 当前只有 3 条 starter cases，且全部使用 `fixtureActual`。它们能展示指标计算，但不能证明当前真实 Orchestrator 链路仍满足行为。

`src/choice_agent/evaluation/service.py` 已支持 starter seed、Case、Dataset immutable snapshot、Run、Result、summary、版本对比和 Case regression status 自动同步。关键限制是 `ensure_starter_cases()` 只要当前 owner 已有任意 Case 就直接返回，因此只扩充 `fixtures.py` 只会影响新数据库，现有数据库不会补齐新增 starter cases 或固定 dataset。

`src/choice_agent/db_models.py` 已有 `evaluation_case`、`evaluation_dataset`、`evaluation_run`、`evaluation_result` 四张表；`src/choice_agent/api/evaluations.py` 已有 dashboard、cases、datasets、runs、result review API。本次无需新增 Dashboard / Runner 管理面的大能力。

`src/choice_agent/evaluation/metrics.py` 已有 17 项指标和汇总逻辑，能区分 `not_applicable`、`not_evaluated`、低优错误率方向和覆盖率。本次主要通过 Case 断言让指标有真实分母。

## 可复用真实链路场景

现有测试已经沉淀了可转化为 Regression Case 的真实行为：

- `tests/test_decision_assistance.py`：Offer 三轮、多轮纠正、学习路径纠正、What-if、未知自由文本、雨天假设、模型非法输出 fallback、排除候选保护。
- `tests/test_decision_canvas.py`：正式 analysis 与 what-if analysis 分离、Hard Constraint 排除 B 公司。
- `tests/test_evidence_presentation.py`：推荐理由引用 evidence snapshot、数值比较引用多候选、手工候选不能伪造可信 Evidence、非法 URL rejected。
- `tests/test_candidate_search_productization.py`：fixture 搜索进度、web 缺 key 错误、ranking hard/missing/user exclusion diagnostics。
- `tests/test_trace_observability.py`：Trace timeline、fallback 节点、ranking diagnostics。
- `tests/test_generic_orchestrator.py`：travel fixture 决策、revision 校验和多轮消息保存。

这些测试不是 Dataset，但它们提供了可靠输入、期望和路径，可作为 starter cases 的来源。

补充确认：当前没有独立的 Learning fixture/provider 或学习推荐规则。Learning 相关测试之所以稳定，是因为测试输入显式提供了三条演示候选，由 `GenericProfile` 的 `ManualCandidateProvider` 解析为手工候选。因此 Learning Regression Case 不应新增学习推荐规则；若要验证推荐，只能在 Case 输入中显式提供 Manual Candidates。否则仅验证背景信息更新、纠正和短回答承接。

## 术语边界

- Core Regression Cases：固定数据源下验证真实 Orchestrator 产品行为的稳定回归样例。
- Fault Injection / Reliability Cases：使用受控 mock / stub 注入模型或搜索故障，验证 fallback、错误记录和批量运行不中断。
- Runtime Bad Cases：真实测试、真实运行或用户反馈中发现的问题，进入 Bad Case Center 后由人工诊断、修复、回归验证。本次 starter seed 不伪造 Runtime Bad Case。

## 评测口径约束

Core Regression 主要验证真实 Orchestrator、固定 fixture 数据源、可控或禁用模型 provider、稳定确定性的产品行为，以及 pass/fail、指标结果和 Trace Snapshot 是否可重复比较。

Core Regression 不宣称覆盖真实 LLM 的完整质量、真实 Web Search 的召回质量、外部搜索结果随时间变化的稳定性、模型服务或搜索服务 SLA、真实线上用户分布。

真实模型和真实搜索应作为单独 `live_model` / web run 或持续观测处理，不能混入稳定 Regression 基线结论。

## 潜在问题

1. `ensure_starter_cases()` 当前不是 versioned seed，现有数据库不会获得新增 starter cases。
2. Core cases 如果继续使用 `fixtureActual`，会让指标看起来通过但无法证明当前链路。
3. `commands` schema 已存在但 Runner 未执行，命令类 Case 需要最小补齐或暂时只用消息 Case。
4. Fault injection 需要白名单 setup，不能允许任意代码、任意路径或外部 URL。
5. `limit <= 20` 不能改；Core 与 Fault Injection 必须拆成两个 Dataset / Run。
6. Dataset snapshot 是 immutable，seed 版本更新应新建 version，不应静默修改已存在 dataset。
7. 现有 Case 可能被用户编辑；seed 补齐不能覆盖用户编辑内容。

## Plan 决策项

- Core Regression 精确控制为 20 条；
- Fault Injection / Reliability 约 6 条，单独 dataset；
- versioned seed 使用稳定 seed id 幂等补齐；
- 自动创建或补齐两个 starter dataset；
- Core 不使用 `fixtureActual`；
- 只对 fault injection 使用 mock / stub；
- 保留 `limit <= 20`；
- 文档和界面口径明确“固定数据源稳定回归”。

## 验证边界

本 Research 基于只读文件检查和现有测试阅读；未修改产品代码，未运行测试。初始确认当前分支为 `main...origin/main`。