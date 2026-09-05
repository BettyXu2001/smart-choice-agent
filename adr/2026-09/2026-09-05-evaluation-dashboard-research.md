# Evaluation Dashboard / Bad Case 闭环 Research

日期：2026-09-05。状态：研究完成，尚未实施。

## 需求与研究范围

将 /admin/evaluations 升级为覆盖五类 17 项指标的跨领域 Dashboard，关联版本差异、失败 Case、Trace、归因、修复版本、Regression Dataset 与持续观测。涉及持久化、API、真实链路回放和核心观测，按大改动处理。

## ADR 检索与归档决策

已对 adr 内容按 evaluation、评测、回归、grounding、what-if、trace 和核心模块路径进行语义检索。

- `adr/2026-08/2026-08-31-diet-evaluation-parity-research.md` / `plan.md`：旧饮食指标迁移，已完成；无标签视作通过是当时明确的兼容口径。
- `adr/2026-09/2026-09-04-generic-decision-evidence-workbench-plan.md`：统一阶段、TraceRepository、Evidence 边界，保留旧 Evaluation；不能假定其中未完成的设计已有实现。
- `adr/2026-09/2026-09-04-conversation-decision-assistance-research.md` / `plan.md`：候选事实纠正、引用校验、假设副本及降级。Plan 标记 2026-09-05 完成，有 Offer 通勤案例。
- `adr/2026-09/2026-09-02-generic-decision-from-diet-foundation-research.md`：通用状态和旧饮食表共存的历史。
- `adr/2026-09/2026-09-04-general-conversation-panel-plan.md`：共享页面、owner/revision 与幂等约束。

本轮是新的评估体系，选择新建 Research / Plan，避免改写已完成的兼容结论。

## 核心文件及实际行为

| 文件 | 已确认职责和行为 |
| --- | --- |
| src/choice_agent/static/assets/js/app.js | hash 路由 /admin/evaluations；时间、limit、Judge 表单；报告仅存在 state.evaluation.report；另有 Trace 查询、JSON 详情、标注表单。 |
| src/choice_agent/static/assets/js/api.js | 共享 fetch、身份/模型请求头及错误处理；DietApi.evaluate 调旧评估接口。 |
| src/choice_agent/api/routes.py | POST /api/v1/diet/evaluations 查询历史 Trace，直接执行 EvaluationAgent，按 session 近似关联反馈；结果仅返回，无 run/dataset/case 表。 |
| src/choice_agent/agents/diet.py | EvaluationAgent 依赖 Agent 名和输出抽取；缺 intent/slots 标签默认 1；空候选 hallucinationControl 默认 1；FAILED 当作 fallback；优先累计 Agent 耗时。 |
| src/choice_agent/db_models.py、database.py、main.py | SQLAlchemy，默认 SQLite，启动 create_all；现有 TraceRecord、AgentRunRecord、DecisionRecord，没有评估表。create_all 不迁移旧表列。 |
| src/choice_agent/services/trace.py、repositories/trace_repository.py | TraceScope 保存请求状态、durationMs、events，AgentRun 单独入表；close 经 repository commit。 |
| src/choice_agent/agents/base.py、agents/stages.py、orchestration/unified.py | 统一阶段调度；AgentRuntime 记录失败并重抛；重算可使用 RankAgent，旧评估器主要识别 CandidateAgent。 |
| src/choice_agent/orchestration/generic.py | create/message/command 校验 owner/revision/receipt，运行统一阶段，再 _persist；conversationTurns 保存当轮 analysis/displayBlocks；DecisionRecord 保存当前完整状态。 |
| src/choice_agent/orchestration/diet.py | 饮食独立 facade 和持久化出口，复用 TraceScope 和统一阶段；观测需覆盖此入口。 |
| src/choice_agent/agents/conversation.py、decision/assistance.py | 本轮事实归属、字段纠正、模型 patch 原文校验；what-if 在深副本上重算，保留正式推荐；理解失败存 warning，解释降级为 rules_fallback。 |
| src/choice_agent/decision/evidence.py | 检查来源 URL 和候选关联；verified 不等于现实事实已证实。 |
| tests/test_decision_assistance.py | 已有 B 公司通勤两小时、半小时纠正、确认硬约束后的排除；学习背景纠正；What-if；非法引用/数值/候选及超时降级测试。 |
| tests/test_orchestrator.py、tests/conftest.py | 旧评估聚合及失败 Trace 测试，临时 SQLite + 饮食 seed 可复用。 |

## 调用链与数据流

历史评估：表单 → DietApi.evaluate → evaluate → DietRepository.traces/feedbacks → EvaluationAgent.execute → 聚合 → 内存报告。仅评价历史输出，不重新运行当前实现，不能证明修复。

通用决策：create/message/command → owner/revision → TraceScope → UnifiedDecisionOrchestrator → StageRunner → AgentRuntime → DomainProfile → assistance/evidence/ranking → _persist → DecisionRecord/conversationTurns/Trace。饮食 facade 使用同一阶段但有独立出口。

多轮：interpret/prepare_turn → 字段/事实更新 → model_understand 校验 → rule_analysis → 模型解释和引用校验 → model 或 rules_fallback → 保存 analysis/正式 recommendation。What-if 的消息、revision、Trace、假设 analysis 正常变化，不能比较整个 DecisionState 是否相同。

## 复用能力

沿用 FastAPI/SQLAlchemy、现有 provider/DomainRegistry/orchestrator 和原生 JS/CSS 主题；复用 Trace 展示与身份过滤、错误提示；复用临时 DB/seed 和多轮测试场景。无需新建决策引擎或引入 Agent 框架。

## 潜在问题与约束

1. 缺标注默认满分会虚高；新口径必须与旧接口分开版本化。
2. 无构建版本/数据集版本/评估器版本，不能按时间猜版本；不能用当前 DecisionRecord 反推历史状态。
3. 错误不等于降级成功，业务捕获错误后 AgentRun 可能 SUCCESS；需显式区分调用失败、输出校验拒绝、模型禁用和降级结果。
4. 旧 Trace 缺完整正式状态前后快照；多轮指标需新增精简投影或隔离回放。
5. 数字和引用结构校验不足以计算全面无依据事实率，需人工 claim 标注或独立明确的 Judge；缺数据为未评测。
6. session 反馈不能自动作为单 Case 金标签；缺输入历史 Trace 只能诊断。
7. X-User-Id 是当前演示身份，非生产认证；新增对象沿用同 owner 边界，本轮不重构认证。
8. 回放必须隔离正式数据库；故障注入不能提供任意代码执行能力；配置/结果不持久化密钥。
9. 新增评估表优于修改既有列，避免隐式数据库迁移。

## Plan 决策项

17 项指标分母/缺失/总分；规则和人工边界；可比版本条件；隔离回放；Case 生命周期和数据集快照；观测与 CLI 范围；增量埋点和旧接口兼容。

## 验证边界

已读取上述代码、主要调用方和相关测试；未运行应用/测试，未修改产品代码或项目数据库。研究初始及写入前 git status --short 均为空。默认沙箱初始化故障，通过获准的备用执行完成读取；此前 ADR 写入因额度限制被拒绝，重试前确认目标文件不存在。历史 ADR 的测试通过记录不是本轮测试结果。