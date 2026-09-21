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
Intent / Understanding / Clarification
    ↓
Candidate Retrieval + Evidence
    ↓
Deterministic Filter & Ranking
    ↓
Critic + Explanation + Risk
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

Each metric reports `evaluationMethod` as `deterministic`, `manual`, or `not_evaluated`. Regression PASS/FAIL is based only on explicit required deterministic assertions; Human Review is stored as a supplemental label and never changes the deterministic gate. `core-regression/v2` provides structured assertions for the 16 target quality metrics. Semantic judgments without reliable gold data remain manual. No LLM Judge is used.

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

The comparison API is `GET /api/v1/evaluations/comparisons?baselineRunId=...&candidateRunId=...`. It requires identical Dataset hashes and Case/revision/repetition sets, and returns both aggregate summaries plus per-Case `improved`, `regressed`, `unchanged`, `new_failure`, or `fixed` results.

`fault-injection-reliability/v2` runs eight controlled failure cases through the real EvaluationRunner and Orchestrator, covering LLM timeout/invalid JSON, Web Search transport/invalid response, and Agent execution failure. It reports 18 metrics, including LLM/Search fallback success, Trace-derived Agent failure rate, and response latency. See `docs/reliability-regression-example.json` for an actual offline run.

## Tech Stack

Python · FastAPI · Pydantic · SQLAlchemy · SQLite · OpenAI-compatible APIs

## Quick Start

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

## Documentation

For detailed architecture and design decisions, see:

* [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md)
* [`docs/EVALUATION.md`](docs/EVALUATION.md)
* [`adr/`](adr/) — architecture and implementation decisions

---

# 中文

**一个结构化、可解释、可评估的 AI 多智能体决策助手。**

[English](#smart-choice-agent) | 中文

Smart Choice Agent 面向旅行、饮食等复杂选择场景，将用户的模糊需求转化为：

**理解需求 → 澄清信息 → 比较候选 → 约束过滤 → 多维排序 → 权衡解释 → 效果评估**

## 核心亮点

* **结构化决策状态**：显式建模目标、硬/软约束、评价维度、候选项、Evidence 和推荐结果。
* **LLM + 确定性引擎**：LLM 负责理解与解释，代码负责过滤、评分、排序和状态流转。
* **Orchestrator + 专职 Agent**：拆分意图理解、澄清、候选准备、审查、解释和风险处理。
* **评估与回归**：支持多维指标、Bad Case、Regression Dataset 和版本对比。
* **Trace 与 Fallback**：记录 Agent 执行、状态变化、耗时、异常和降级路径。

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

每个指标都返回 `evaluationMethod`：`deterministic`、`manual` 或 `not_evaluated`。Regression PASS/FAIL 只由明确标为 required 的 deterministic assertions 决定；Human Review 仅作为补充标签保存，不改变确定性 Gate。`core-regression/v2` 为 16 项目标质量指标提供结构化断言；缺少可靠金标签的语义判断继续保留人工审阅。本版本未实现 LLM Judge。

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

比较接口为 `GET /api/v1/evaluations/comparisons?baselineRunId=...&candidateRunId=...`。它要求双方 Dataset hash 及 Case/revision/repetition 集合完全一致，并返回两个版本的完整聚合结果与逐 Case 的 `improved`、`regressed`、`unchanged`、`new_failure`、`fixed` 判定。

`fault-injection-reliability/v2` 通过真实 EvaluationRunner 与 Orchestrator 运行 8 条受控故障 Case，覆盖 LLM timeout/invalid JSON、Web Search transport/invalid response 和 Agent execution failure。当前共 18 项指标，包括 LLM/Search fallback 成功率、Trace 派生的 Agent 失败率和响应延迟；实际离线运行示例见 `docs/reliability-regression-example.json`。

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

* [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md)
* [`docs/EVALUATION.md`](docs/EVALUATION.md)
* [`adr/`](adr/) — 架构与实现决策记录
