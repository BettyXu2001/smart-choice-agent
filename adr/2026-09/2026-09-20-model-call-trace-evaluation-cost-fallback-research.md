# 模型调用 Trace、成本与 Fallback Research

## 需求与范围

增强统一 Provider → Trace → AgentRun → Evaluation 链路，真实记录 Provider、Prompt 版本、Token、成本、重试和 Fallback；兼容旧数据库/旧 JSON，不重做 Trace 前端。该改动跨核心链路，按大改动处理。本文件只记录研究结论，不修改产品代码。

## ADR / 历史方案检索

已按 AgentRun、ModelProvider、Trace、usage、token、cost、fallback、search、evaluation 和模块路径检索 `adr/`：

- `2026-09-05-decision-trace-observability-*`：Trace v2、模型失败节点和 fallback 展示，是本次直接基础。
- `2026-09-05-evaluation-dashboard-*`：已有 Evaluation Case / Dataset / Run / Result 与 summary，本次应增量扩展。
- `2026-09-06-evaluation-regression-dataset-*`：已有真实链路回放、模型/Search fault injection 和 Trace Snapshot。
- `2026-09-05-candidate-search-productization-*`：定义 Search auto 的 Web → fixture fallback，要求不能隐藏降级。
- `2026-08-30-frontend-api-settings-research.md`：约束运行时模型配置和密钥边界。

这些记录已完成且主题不同，追加会混淆历史，因此新建本次专属 Research/Plan。

## 核心实现与调用链

| 文件 | 当前实现与发现 |
| --- | --- |
| `providers/model.py` | `complete_json()` 返回普通 dict；OpenAI-compatible 只保留 content，响应 `usage` 被丢弃。 |
| `providers/search.py` | Responses Web Search 最多两次尝试；有 attempt 节点但丢弃 usage，retry 不进入 AgentRun。 |
| `agents/base.py`、`agents/stages.py` | AgentRuntime 统一创建 AgentRun；ProfileStage 只带 name。模型/Search 在 handler 内发生，外层 AgentRun 不知道调用 metadata，modelName 通常为空。 |
| `services/trace.py` | Trace v2 写旧 events 和 timeline；`model_call()` 只记 Prompt、结果、耗时、异常；`agent_run()` 写 JSON event 和数据库。 |
| `schemas.py`、`db_models.py` | AgentRun 仅有 agent/model/status/latency/input/output/error。 |
| `database.py` | `create_all()` 不会给旧表新增列；只改 ORM 会使旧 SQLite 失败。 |
| `decision/assistance.py`、`agents/diet.py` | 通用链路捕获多类调用异常并规则降级；Diet 只捕获输出校验异常，网络/timeout 可能直接失败；fallback 节点均手写。 |
| `domains/comparison.py` | Search auto 在 Web 失败后回退 fixture，但 fallback 字段不统一。 |
| `config.py` | 无价格表、Provider label 或 Prompt 版本；运行时配置手工重建 Settings。 |
| `evaluation/runner.py` | 一个 Case 只复制最后一条 Trace，多轮前序调用会漏算。 |
| `evaluation/metrics.py`、`service.py` | summary 只聚合质量断言和 Case 数；没有 latency/P95/Token/cost 汇总。 |

真实链路是：

`Orchestrator → TraceScope → StageRunner → AgentRuntime → ProfileStage/Domain handler → model_call/SearchProvider → fallback → AgentRuntime 写 AgentRun → Trace/DB`。

Provider usage 在到达 Trace 前已丢失，外层 AgentRun 与内部 Provider 节点没有聚合关系。Evaluation 又只读取单个 Trace Snapshot，所以无法形成完整评测成本。

## 可复用能力

- 每请求独立 TraceScope、timeline、旧 events 和 AgentRun 双写。
- AgentRuntime 是统一 AgentRun 创建点。
- timeline 已支持 model/operation、failed/fallback、耗时和脱敏。
- Search 已有 attempt 循环和 auto fallback。
- Evaluation 的 `trace_snapshot`、`summary_json` 是 JSON，可兼容增加字段。
- Pydantic alias 可输出要求的 camelCase。
- 已有 fault injection 与临时数据库测试。

## 关键问题与约束

1. 只扩展 ORM 会破坏旧库，必须做幂等 additive migration。
2. 在各 Agent 重复赋值无法覆盖 Search；需要 TraceScope 的当前 Agent 聚合。
3. usage 缺失时不能通过字符数、tokenizer 或模型猜测伪造 Token。
4. 响应已产生但 JSON/业务校验失败时仍可能有 usage；异常需携带已取得的 metadata。
5. 未知模型或缺 input/output 拆分时 cost 必须为 null；Evaluation 要暴露覆盖率。
6. Prompt version 应由统一层对稳定模板生成指纹，不能由各 Agent 重复维护。
7. Agent 内可能有多次 attempt；Token/成本需汇总，timeline 保留逐次细节。
8. 模型失败但规则降级成功时，AgentRun 保持 SUCCESS 且 `fallbackUsed=true`；原模型节点仍为 failed。
9. 旧记录缺新增事实时保持 null/unknown，不能回填 0 Token、0 cost 或 false fallback。
10. Evaluation 多轮需收集全部唯一 traceId。
11. 保持 `complete_json()` 的 dict 使用体验与简单测试 Provider。
12. 密钥不得进入 Trace；价格显式配置并精确模型名匹配；不内置假价格。
13. 不扩大 Search 语义：显式 web 仍失败，只有既有 auto 降级。
14. 当前工作区有未提交修改，且 `schemas.py`、`decision/assistance.py`、`domains/comparison.py` 重叠，实施必须精确合并。

## Plan 阶段决策

需要明确 metadata success/error 载体、Agent 聚合、价格精度、旧表补列、P95 与缺失覆盖口径、Trace schema 版本。