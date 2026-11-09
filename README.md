# Smart Choice Agent

**A structured, explainable, and evaluable AI decision agent.**
**一个结构化、可解释、可评估的 AI 多智能体决策助手。**

English | [中文](#中文)

Smart Choice Agent helps users make complex choices when requirements are vague, constraints conflict, and multiple options need to be compared.

Instead of directly generating a recommendation, it turns decision-making into a structured process:

**Understand → Clarify → Compare → Filter → Rank → Explain → Evaluate**

## Highlights

* **Structured Decision State** — models goals, hard/soft constraints, criteria, candidates, evidence, and recommendations.
* **LLM + Deterministic Engine** — LLMs handle understanding and explanation; deterministic code controls filtering, scoring, ranking, and state transitions.
* **Orchestrator + Specialized Agents** — separates intent, clarification, candidate preparation, review, explanation, and risk handling.
* **Evaluation & Regression** — supports multi-dimensional metrics, Bad Case analysis, Regression Dataset, and version comparison.
* **Trace & Fallback** — records Agent execution, state changes, latency, errors, and degraded execution paths.

## Architecture

```text
User Request
    ↓
Orchestrator
    ↓
Intent / Understanding / Blocking Clarification
    ↓
Execution Planner (full / refresh / rerank / explain-only / what-if)
    ↓
Candidate Retrieval + Evidence (only when required)
    ↓
Deterministic Filter & Ranking (reuses candidatePool when safe)
    ↓
Critic + Explanation + Final Validation + Risk
    ↓
Recommendation
    ↓
Trace → Evaluation → Bad Case → Regression
```

## Decision Domains

**Diet**
Demonstrates multi-turn clarification, domain rules, planning, and risk handling.

**Travel**
Demonstrates reusable decision modeling, candidate search, evidence, constraints, and multi-dimensional ranking.

Other scenarios may remain as demos.

## Evaluation

Evaluation follows a **rule-first** principle.

Whenever a metric can be verified from structured state or Trace, deterministic assertions are preferred over LLM-based judgment.

Each metric reports `evaluationMethod` as `deterministic`, `manual`, or `not_evaluated`. Regression PASS/FAIL is based only on explicit required deterministic assertions; Human Review is stored as a supplemental label and never changes the deterministic gate. `evaluation-v3` publishes 23 metrics (21 scored and 2 observational), with 20 deterministic target metrics. `core-regression/v3` adds real auto-routing, clarification, soft-preference, and safety cases while preserving v1/v2. Summaries include Case rates, domain/caseType/tag groups, and routing precision/recall/F1 plus a confusion matrix. Semantic judgments without reliable gold data remain manual. No LLM Judge is used.

The evaluation loop is:

```text
Regression Dataset
      ↓
Agent Run
      ↓
Metrics + Trace
      ↓
Bad Case
      ↓
Fix
      ↓
Regression Re-run
```

For a real Baseline/Candidate comparison, run the same Dataset twice with explicit run configuration, then compare the persisted Run IDs. `configured` uses the model API from the current environment; `disabled` keeps the deterministic offline path.

```bash
python -m choice_agent.evaluation.cli --dataset-id <dataset-id> --run-label baseline --model <baseline-model> --provider configured
python -m choice_agent.evaluation.cli --dataset-id <dataset-id> --run-label candidate --model <candidate-model> --provider configured --compare-to-run-id <baseline-run-id>
```

The comparison API is `GET /api/v1/evaluations/comparisons?baselineRunId=...&candidateRunId=...`. It requires identical Dataset hashes and Case/revision/repetition sets, and returns both aggregate summaries plus per-Case `improved`, `regressed`, `unchanged`, `new_failure`, or `fixed` results. It also reports `coverageDelta` and `coverageWarnings` when Candidate deterministic evaluation coverage drops versus Baseline.

`fault-injection-reliability/v2` runs eight controlled failure cases through the real EvaluationRunner and Orchestrator, covering LLM timeout/invalid JSON, Web Search transport/invalid response, and Agent execution failure. The v3 catalog also reports a Trace-derived, unscored fallback activation rate. See `docs/evaluation-v3-results-2026-10-17.md` for actual Core v3 and Fault v2 offline results.

`diet-travel-evaluation/v1` provides 20 balanced Diet/Travel cases for routing, clarification, constraints, correction, what-if, stability, safety, and controlled reliability failures. Its `repeat=2` offline result and all 23 metrics are documented in `docs/diet-travel-evaluation-results-2026-10-17.md`.

## Tech Stack

Python · FastAPI · Pydantic · SQLAlchemy · SQLite · OpenAI-compatible APIs

## Quick Start

Set a persistent `CHOICE_AGENT_SESSION_SECRET` of at least 32 bytes before starting the server. Generate it once with `python -c "import secrets; print(secrets.token_hex(32))"`; save and reuse that value across restarts. For local HTTP also set `CHOICE_AGENT_COOKIE_SECURE=false`. Public HTTPS deployments should keep it `true` (the default). The app does not automatically load `.env`.

PowerShell (set the secret in the shell once; do not regenerate it on every launch):

```powershell
$env:CHOICE_AGENT_SESSION_SECRET = "<your saved secret>"
$env:CHOICE_AGENT_COOKIE_SECURE = "false"
```

For Bash use `export CHOICE_AGENT_SESSION_SECRET='<your saved secret>'` and `export CHOICE_AGENT_COOKIE_SECURE=false`.

```bash
python -m pip install -e .
python scripts/init_db.py
python -m uvicorn choice_agent.main:app --host 127.0.0.1 --port 8000
```

App:

```text
http://127.0.0.1:8000/
```

API:

```text
http://127.0.0.1:8000/docs
```

The core deterministic workflow can run without an LLM API key.

Browser model/search Base URLs must be authorized by the deployment operator. Models support `https://api.deepseek.com` and `https://api.openai.com/v1` by default; search supports `https://api.openai.com/v1`. Each server-configured Base URL is also trusted. To authorize another gateway, set `CHOICE_AGENT_MODEL_BASE_URL_ALLOWLIST` or `CHOICE_AGENT_SEARCH_BASE_URL_ALLOWLIST` to a JSON array of exact HTTPS Base URLs. Provider requests do not follow redirects; use the final endpoint. See [deployment details](docs/deploy.md#provider-endpoint-authorization).

Each turn records its planned and executed path in Trace. Demo mode always uses fixture candidates and rule-based interpretation/explanation, even when model or Web Search credentials are configured.

## Documentation

For detailed architecture and design decisions, see:

* [`docs/deploy.md`](docs/deploy.md)
* [`docs/evaluation-v3-results-2026-10-17.md`](docs/evaluation-v3-results-2026-10-17.md)
* [`adr/`](adr/) — architecture and implementation decisions

---

# 中文

**一个结构化、可解释、可评估的 AI 多智能体决策助手。**

[English](#smart-choice-agent) | 中文

Smart Choice Agent 面向旅行、饮食等复杂选择场景，将用户的模糊需求转化为：

**理解需求 → 阻塞澄清 → 执行规划 → 按需检索 / 重排 / 解释 → 推荐校验 → 效果评估**

## 核心亮点

* **结构化决策状态**：显式建模目标、硬/软约束、评价维度、候选项、Evidence 和推荐结果。
* **LLM + 确定性引擎**：LLM 负责理解与解释，代码负责过滤、评分、排序和状态流转。
* **Orchestrator + 专职 Agent**：拆分意图理解、澄清、候选准备、审查、解释和风险处理。
* **评估与回归**：支持多维指标、Bad Case、Regression Dataset 和版本对比。
* **Trace 与 Fallback**：记录 Agent 执行、状态变化、耗时、异常和降级路径。
* **增量执行**：每轮按 `full / refresh / rerank / explain-only / what-if` 选择最小安全路径；Trace 记录计划、实际路径、跳过原因和候选池摘要。

## 整体架构

```text
用户请求
   ↓
Orchestrator
   ↓
Intent / Understanding / Clarification
   ↓
Candidate Retrieval + Evidence
   ↓
确定性过滤与排序
   ↓
Critic + Explanation + Risk
   ↓
Recommendation
   ↓
Trace → Evaluation → Bad Case → Regression
```

## 决策领域

**Diet 饮食决策**
用于验证多轮澄清、领域规则、规划与风险处理。

**Travel 旅行决策**
用于验证通用决策建模、候选检索、Evidence、约束与多维排序。

其他场景可作为 Demo 保留。

## Evaluation

评估采用 **规则优先** 原则。

只要能够通过结构化状态或 Trace 稳定判断，就优先使用确定性规则，而不是交给另一个 LLM 打分。

每个指标都返回 `evaluationMethod`：`deterministic`、`manual` 或 `not_evaluated`。Regression PASS/FAIL 只由明确标为 required 的 deterministic assertions 决定；Human Review 仅作为补充标签保存，不改变确定性 Gate。`evaluation-v3` 发布 23 项指标（21 项计分、2 项观测）和 20 项 deterministic target；`core-regression/v3` 新增真实自动路由、澄清、软偏好与安全 Case，并保留 v1/v2。Summary 新增 Case 比率、domain/caseType/tag 分组，以及路由 Precision/Recall/F1 和混淆矩阵。缺少可靠金标签的语义判断继续保留人工审阅。本版本未实现 LLM Judge。

```text
Regression Dataset
      ↓
Agent Run
      ↓
Metrics + Trace
      ↓
Bad Case
      ↓
Fix
      ↓
Regression Re-run
```

真实 Baseline/Candidate 对比需要对同一 Dataset 分别执行两次，并用已持久化的 Run ID 比较。`configured` 使用当前环境配置的模型 API，`disabled` 保持确定性的离线路径。

```bash
python -m choice_agent.evaluation.cli --dataset-id <dataset-id> --run-label baseline --model <baseline-model> --provider configured
python -m choice_agent.evaluation.cli --dataset-id <dataset-id> --run-label candidate --model <candidate-model> --provider configured --compare-to-run-id <baseline-run-id>
```

比较接口为 `GET /api/v1/evaluations/comparisons?baselineRunId=...&candidateRunId=...`。它要求双方 Dataset hash 及 Case/revision/repetition 集合完全一致，并返回两个版本的完整聚合结果与逐 Case 的 `improved`、`regressed`、`unchanged`、`new_failure`、`fixed` 判定。当 Candidate 的 deterministic evaluation coverage 低于 Baseline 时，接口会返回 `coverageDelta` 和 `coverageWarnings`。

`fault-injection-reliability/v2` 通过真实 EvaluationRunner 与 Orchestrator 运行 8 条受控故障 Case，覆盖 LLM timeout/invalid JSON、Web Search transport/invalid response 和 Agent execution failure。v3 指标目录还会报告 Trace 派生且不计分的 Fallback 激活率；Core v3 与 Fault v2 的实际离线结果见 `docs/evaluation-v3-results-2026-10-17.md`。

`diet-travel-evaluation/v1` 提供 20 条均衡的饮食/旅行专项 Case，覆盖路由、澄清、约束、纠正、what-if、稳定性、安全和受控可靠性故障；`repeat=2` 的离线结果及全部 23 项指标见 `docs/diet-travel-evaluation-results-2026-10-17.md`。

## 技术栈

Python · FastAPI · Pydantic · SQLAlchemy · SQLite · OpenAI-compatible APIs

## 快速启动

```bash
python -m pip install -e .
python scripts/init_db.py
python -m uvicorn choice_agent.main:app --host 127.0.0.1 --port 8000
```

应用：

```text
http://127.0.0.1:8000/
```

API：

```text
http://127.0.0.1:8000/docs
```

即使没有配置 LLM API Key，核心确定性链路也可以运行。

## 详细文档

完整架构与设计说明：

* [`docs/deploy.md`](docs/deploy.md)
* [`docs/evaluation-v3-results-2026-10-17.md`](docs/evaluation-v3-results-2026-10-17.md)
* [`adr/`](adr/) — 架构与实现决策记录

## 匿名会话与旧数据

公开访问使用服务端签名的 HttpOnly Cookie，每个浏览器自动建立独立身份。HTTP 客户端须先调用 `GET /api/v1/identity`，保存并在后续请求携带 Cookie；`X-User-Id` 不再选择身份。签名密钥必须至少 32 字节，并在重启和所有实例间保持一致。本地 HTTP 显式设置 `CHOICE_AGENT_COOKIE_SECURE=false`，公网 HTTPS 保持默认 `true`。应用不会自动读取 `.env`。

清除 Cookie、Cookie 到期、换设备或更换签名密钥后无法找回原匿名身份；旧数据仍保留，不会自动迁给新访客。既有演示用户的数据不会按旧 localStorage ID 自动认领。本轮未新增账户找回、配额或费用限制。
