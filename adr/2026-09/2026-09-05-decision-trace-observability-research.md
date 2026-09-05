# 决策过程可观测 Trace Research

## 范围与状态

2026-09-05。将 Trace 提升为每轮决策时间轴，回答输入、意图、状态变更、Agent 输入输出、证据、排除、推荐变化和降级。涉及运行时、领域执行与 UI，按大改动处理。本轮仅 Research / Plan，未实施。

## ADR 检索与归档

已按 Trace、AgentRuntime、Evidence、过滤、fallback、状态编辑检索 adr/2026-08 和 adr/2026-09 正文。

- 2026-09-04-generic-decision-evidence-workbench-plan.md：共享阶段、证据、TraceRepository 历史，未完成事项不自动续做。
- 2026-09-04-general-conversation-panel-research.md / plan.md、2026-09-04-diet-conversation-panel-research.md / plan.md：状态修改、回执、事务、轮次快照、聊天入口。
- 2026-09-04-conversation-decision-assistance-research.md / plan.md：事实引用、解释、假设分析。
- 2026-09-02-generic-decision-from-diet-foundation-research.md / plan.md：通用编排、兼容背景。
- 2026-08-31-diet-evaluation-parity-research.md / plan.md：评估消费者；2026-08-30-frontend-api-settings-research.md：模型设置和 Trace 边界。

未发现独立覆盖本次时间轴与逐步归因的 ADR。新建本组文档，保留历史主题及验收含义。研究开始及继续时 git status --short 均无输出。

## 核心代码及真实行为

以下路径相对 src/choice_agent。

| 文件 | 已核实行为 |
| --- | --- |
| services/trace.py、repositories/trace_repository.py | 内存 events 包含顺序、类型、phase、输入输出、时间；agent_run 同时写 AgentRunRecord；close 保存 trace_json 并提交。 |
| agents/base.py | AgentRuntime 采集 message/data、返回值、耗时、失败，没有显式 DecisionState 快照；复杂对象字符串化。 |
| agents/stages.py、orchestration/unified.py | 统一调度 Intent、Understanding、Clarification、Candidate/Planning、Critic、Explanation、Risk；存在调整、提前结束、重排。ProfileStage 外层 model_name 不代表内部实际调用。 |
| orchestration/generic.py | message 在 _run 前合并 context；command 在 Trace 前 apply_command；场景提示可不运行 Agent；部分 command 直接 profile.clarify。 |
| orchestration/diet.py | panel patch 在请求事件前执行；确认字段可不重算；失败 rollback 后保存失败 Trace；回执重放复用结果。 |
| domains/comparison.py | CandidateAgent 聚合搜索、手工候选合并、证据校验、rank；auto Web 失败回 fixture，显式 web 报错。 |
| domains/diet/profile.py、composition.py | 数据库检索、证据、rank、低分过滤、截取和选择；三餐按餐次重复 rank；部分路径覆盖 candidate_state，仅保留选中项。 |
| decision/ranking.py | 用户排除、缺值 EXCLUDE、硬约束筛除，只留笼统 reason；ScoreContribution 已有权重、得分、evidence_ids。 |
| decision/evidence.py、providers/candidates.py | 稳定 Evidence ID、候选/维度引用、来源校验；fixture/database/manual/web 可区分。 |
| decision/assistance.py、agents/conversation.py | Intent 即可改字段/事实；解释 sourceId 不全是 Evidence ID；假设在副本重排，不替换已保存推荐；模型校验失败 rules_fallback。 |
| agents/diet.py、providers/model.py、providers/search.py | 饮食模型校验失败主要记日志，网络错误未全部转降级；模型不保存 Prompt/原文；Search 两次尝试。 |
| schemas.py、db_models.py | State、AgentRun、Evidence、Recommendation、SearchRun 可复用；TraceRecord 已有 JSON。 |
| api/routes.py、repositories/diet_repository.py | 旧 diet/debug 路由按 user 查询并返回 traceJson；标注、Evaluation 消费旧事件。 |
| static/assets/js/app.js、conversation.js、static/index.html | 查询表格、元数据、整份 JSON、标注；消息已有 traceId 入口；原生 JS/CSS，无前端构建依赖。 |

## 调用链与数据流

聊天/面板 → API → GenericDecisionOrchestrator 或 DietOrchestrator → TraceScope → UnifiedDecisionOrchestrator → StageRunner → AgentRuntime(ProfileStage) → DomainProfile → Provider / EvidenceValidator / Ranking / Explanation → 保存 DecisionState 与轮次 → 保存 Trace → debug API → renderTraceDetail。

REQUEST_RECEIVED / COMMAND_RECEIVED 保存输入；AGENT_CALL 在执行完成后追加；失败保存 REQUEST_FAILED。没有开始/父子关系，不能据结束顺序推断嵌套阶段开始顺序。

## 可复用、隐患及约束

复用 trace_json、运行时、旧路由/用户边界/标注、Evidence、候选池、评分贡献、推荐、字段确认元数据、facts/catalog、selection、revision、回执以及原生 details。

1. 必须在 mutation 前抓基线；不能用最新 State 重建历史轮次。
2. 事后 candidate_state 会遗漏饮食排除；诊断必须在真实过滤点生成。缺值、用户排除、硬约束、低分/截取/选择分开。
3. Evidence 与解释 catalog 是不同引用空间；用户事实不能标成外部验证证据，URL 校验也不等于事实真伪审定。
4. 主选可能受 selection、定性顾虑、模型解释影响；不能仅凭权重变动编造唯一原因。
5. 澄清、安全、场景提示、确认、候选复用、三餐、假设不能伪装完整八步成功。
6. Prompt、原始返回、校验采用结果须分层；失败不等于降级，禁用模型属于规则模式。
7. EvaluationAgent 将 FAILED/error 视作 fallback，并依赖旧 Agent 名称；不能无意更改口径或重复累计耗时。
8. 不序列化 provider/settings/headers/凭据/收据历史；错误脱敏；旧数据缺失显示未记录。
9. rollback 后试算差异不能标已提交；幂等重放不能多造一轮 Trace。

## 待 Plan 决策

版本兼容、差异范围、父子关系、模型采集、过滤诊断、推荐引用、旧记录呈现和专项验收。

## 研究验证

完成代码、调用方、测试位置及配置静态检查。pyproject.toml 提供 pytest，未配置 lint/typecheck/前端 build。本阶段未跑产品测试或浏览器，不引用历史测试数作为本次结果。沙箱初始化失败后，通过获准的沙箱外只读命令完成研究。