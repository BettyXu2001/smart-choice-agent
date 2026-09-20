# 模型调用 Trace、成本与 Fallback Plan

## 状态

2026-09-20：用户已明确批准实施。实施前已复核当前工作区；Evaluation 的确定性 runConfiguration / baseline-candidate 并行改动与本方案可增量兼容，实施不得覆盖其签名、配置或比较逻辑。

2026-09-20：已完成实现与验证。Provider/Trace/AgentRun/Evaluation 链路、旧表补列、模型与 Search Fallback、专项测试和全量测试均已完成；未修改 Trace 前端。

验证边界：未使用真实外部 API Key 发起计费请求；已使用符合 Chat Completions / Responses 标准结构的响应夹具覆盖真实 usage 读取、缺失 usage、未知价格、解析失败和 Search 重试。

## 目标与成功标准

在不重做 Trace 前端、不伪造 Token/价格、不破坏旧数据的前提下，完成统一 Provider → Trace → AgentRun → Evaluation 可观测链路。

1. 新 AgentRun 可查询 `provider`、`promptVersion`、`inputTokens`、`outputTokens`、`totalTokens`、`estimatedCost`、`retryCount`、`fallbackUsed`、`fallbackReason`。
2. Chat Completions 和 Responses Search 读取真实 usage；无 usage 时 Token 为 null。
3. 只在精确命中配置价格且有 input/output Token 时计算成本；未知模型返回 null。
4. 降级 Trace 同时包含 failed Provider 节点、标准 fallback 节点和 `fallbackUsed=true` 的 AgentRun，并明确 reason 与 from/to 路径。
5. Evaluation Run summary 提供 average latency、P95、total tokens、average tokens/case、estimated total cost 和覆盖信息。
6. 旧 SQLite 表可幂等补列；旧 JSON 缺字段仍可加载且不补造历史数据。
7. 专项与现有测试通过，最终 diff 无前端重做和计划外修改。

## 设计

### 1. 统一 Provider metadata

新增 `providers/observability.py`：

- `ProviderCallMetadata`：provider、model、prompt_version、input/output/total tokens、estimated_cost、retry_count。
- dict-compatible 的模型完成结果：业务层仍可 `.get()` / Pydantic validate；Trace 可读取 metadata；普通 dict stub 继续可用。
- 携带 metadata 的 Provider response error：响应已返回但 JSON/结构解析失败时仍保留 usage；传输失败 usage 为 null。
- usage 只接受响应整数；total 优先取响应值，仅在响应给出 input/output 时允许相加，不做 tokenizer 推算。

`OpenAICompatibleProvider` 从 chat usage 的 `prompt_tokens`、`completion_tokens`、`total_tokens` 读取；Search 从 Responses usage 的 `input_tokens`、`output_tokens`、`total_tokens` 读取。Provider label 显式配置，不从 URL 猜厂商。

### 2. Prompt 版本与价格

统一工具对稳定 Prompt 模板计算 SHA-256 指纹，如 `sha256:<摘要>`。只对 system/static instruction 指纹，不把动态用户内容作为版本，避免各 Agent 手工维护。

新增 `CHOICE_AGENT_MODEL_PRICING_JSON`，按精确模型名配置每百万 input/output Token 单价：

```json
{"model-name":{"inputPer1MTokens":1.25,"outputPer1MTokens":10.0}}
```

价格非负；使用 Decimal 中间计算并稳定序列化。未知模型、usage 缺失或无 input/output 拆分时 `estimatedCost=null`，不内置假价格。运行时 Settings 改用 `dataclasses.replace()`，避免漏传新增字段。

### 3. TraceScope 与 AgentRun

Trace schema 升到 v3，但保留 v2 timeline/events 字段。AgentRuntime 在 handler 前开启当前 Agent 上下文，结束时消费 TraceScope 聚合并统一创建 AgentRun。

统一 Provider 调用入口负责：

- 每个 model/Search attempt 的节点、耗时、metadata 与异常；
- 失败响应仍记录可得 usage；
- 当前 Agent 内 Token和已知成本求和，retryCount 记录额外尝试；
- timeline 保留逐次调用，不压扁原始失败。

AgentRun 新字段均可空以兼容旧记录。新运行无重试写 0、未降级写 false；旧记录缺字段保持 null。若多次调用的 provider/model/prompt 无法无歧义汇总，对应单值为 null，细节仍在 timeline。

### 4. 统一 Fallback

TraceScope 提供统一 fallback API，接收 reason、from_path、to_path 和详情；同时写 fallback timeline 节点、标记当前 Agent `fallbackUsed=true`、填充 `fallbackReason`。

迁移以下手写点：

- 通用模型理解 → 已确认条件/规则；
- 通用解释/校验失败 → rules explanation；
- Diet 意图/解释调用或输出失败 → 既有规则结果；
- Search auto 的 Web → fixture。

原 Provider 节点先 failed，再写 fallback。降级成功时 AgentRun status 仍为 SUCCESS。显式 web 模式继续报错，不新增隐式降级。

### 5. 持久化与旧库

AgentRun schema 和 `agent_run` 表新增九个可空列。旧 AGENT_CALL event 增量输出同名 camelCase 字段。

`Database.create_all()` 后使用 SQLAlchemy inspector 检查明确列集合，仅为缺失列执行 dialect 编译的 `ALTER TABLE ADD COLUMN`。旧行不回填。测试覆盖旧表升级、旧行读取和重复执行幂等；不实现通用迁移框架。

### 6. Evaluation 聚合

EvaluationRunner 收集一个 Case 的全部唯一 traceId；保留现有 `traceSnapshot` 顶层最后 Trace，并增加 related traces 与 case observability。

口径：

- Case latency：该 Case 所有唯一 Trace 的 `durationMs` 之和。
- average latency：有样本 Case 均值。
- P95：Case latency 的 nearest-rank P95。
- total tokens：真实已观测 `totalTokens` 之和；无任何 usage 时 null。
- average tokens/case：已观测 Token / 至少一个调用有 usage 的 Case 数；无样本时 null。
- estimated total cost：所有带 usage 的计费调用均可精确定价时才返回；否则 null，同时返回 knownEstimatedCost 与未知数。

`summary.performance` 至少包含 caseCount、latencySampleCount、averageLatencyMs、p95LatencyMs、totalTokens、averageTokensPerCase、estimatedTotalCost、knownEstimatedCost、tokenUsageCaseCount、providerCallCount、unreportedUsageCallCount、unknownPriceCallCount。旧 Result 没 observability 时跳过并反映 coverage，不视为 0。

### 7. 查询与前端边界

现有 Trace API、DecisionState API 和 Evaluation Run API 直接返回新增 JSON，不加新路由。本次不修改 Trace/Evaluation 页面布局；现有 JSON 详情可查询底层数据。

## 受影响文件

| 文件 | 计划修改 |
| --- | --- |
| `providers/observability.py`（新增）、`providers/model.py`、`providers/search.py` | metadata、usage、价格、错误与重试。 |
| `config.py`、`.env.example`、`api/routes.py` | Provider/价格配置与 Settings 安全透传。 |
| `schemas.py`、`db_models.py`、`database.py` | AgentRun 字段和旧表补列。 |
| `agents/base.py`、`services/trace.py` | 当前 Agent 聚合、Trace v3、统一 Provider/fallback。 |
| `agents/diet.py`、`decision/assistance.py`、`domains/comparison.py` | 使用统一 fallback；精确保留现有未提交改动。 |
| `evaluation/runner.py`、`metrics.py`、`service.py` | 多轮 Trace 与 performance summary。 |
| 新增/扩展 Provider、Trace、Search、数据库兼容、Evaluation 测试 | 覆盖成功、失败、缺失和兼容路径。 |
| `CHANGELOG.md` | 按同日标题规则记录能力变化。 |

## 兼容性、风险与折衷

- API 只增字段；旧前端忽略新增 JSON。
- 普通 dict Provider stub 继续工作。
- 旧 JSON 新字段为 null；旧 DB 启动时 additive migration，不回填。
- Evaluation 原 metrics/caseCounts 保持；只新增 performance。
- 部分调用缺 usage 时 Token 是“已观测值”并带 missing count；完整成本更保守，任何必要价格未知即为 null。
- Prompt 内容指纹不是语义化版本，但统一、不可漂移且无需 Agent 重复维护。
- 不新建 ProviderCall 数据表；AgentRun 保持 Stage 级，逐次细节留在 timeline。
- additive DDL 只覆盖本次九列；未来复杂迁移另立方案。
- 当前工作区有重叠的用户修改，实施不得格式化、回滚或覆盖相邻逻辑。

## 验证方案

1. Provider：usage 映射、无 usage、解析失败 metadata、精确价格、未知模型。
2. Trace：模型 timeout/非法响应 failed；fallback 含 from/to/reason；同 AgentRun 的 fallback/retry/token/cost。
3. Search：两次 attempt retry、auto fallback、显式 web 不降级、Responses usage。
4. 数据库：旧表/旧行升级、重复 create_all、旧 JSON AgentRun 加载。
5. Evaluation：average/P95、多轮去重、Token/cost 与 coverage。
6. 局部运行新增测试及 `test_candidate_search_productization.py`。
7. 完整运行 `python -m pytest`、`python -m compileall -q src scripts`、`git diff --check`。
8. 最终检查无密钥、假 Token/价格、前端重做、占位符或计划外文件。

## Todo

- [x] 实现统一 Provider metadata、真实 usage、Prompt 指纹和配置价格计算。
- [x] 扩展 TraceScope / AgentRuntime / AgentRun 聚合与持久化。
- [x] 统一模型和 Search Fallback，记录失败、原因、路径与 retry。
- [x] 实现并验证旧 `agent_run` 表幂等补列。
- [x] 扩展 Evaluation 多轮 Trace 和 latency/P95/Token/cost 聚合。
- [x] 补充 Provider、Trace、Search、数据库兼容和 Evaluation 测试。
- [x] 更新配置示例与 CHANGELOG，检查最终 diff。
- [x] 执行局部与完整验证，记录未验证项和剩余风险。
