# Smart Choice Agent

**A Python multi-agent decision system for structured, explainable choices.**

Smart Choice Agent turns vague user intent into ranked options, trade-off analysis,
clarifying questions, evidence records, and auditable decision traces. The first
complete domain is diet recommendation, but the core engine is designed as a
general decision framework for future domains.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

English | [中文](#中文)

## Why It Exists

Most recommendation apps jump straight to an answer. Smart Choice Agent makes the
decision process visible:

- What did the user ask for?
- What constraints are hard requirements?
- Which candidates were considered?
- Why did one option outrank another?
- What evidence and agent runs produced the final answer?

This makes it useful for building AI products where recommendations need to be
debuggable, explainable, and stable.

## Highlights

- **Multi-agent workflow**: intent, understanding, clarification, candidate generation, adjustment, planning, review, explanation, risk, and evaluation agents.
- **Deterministic ranking engine**: hard-constraint filtering plus seven-dimension scoring for stable, testable recommendations.
- **Candidate selection strategies**: diet chat can opt into ranked, random, weighted, or least-recent selection with session-level recent-item cooldown.
- **Works without an API key**: local rule agents can run the full flow when LLM mode is disabled.
- **Optional LLM integration**: supports OpenAI-compatible Chat Completions through environment configuration.
- **Auditable traces**: sessions, messages, recommendations, feedback, `DecisionState`, `Evidence`, and agent runs are persisted.
- **Diet domain included**: single-meal recommendations, multi-turn clarification, refresh suggestions, three-meal planning, personal meals, and public meals.
- **FastAPI + static web UI**: run locally and inspect the API at `/docs`.

## Architecture

```text
FastAPI / Static Web
  -> DietOrchestrator
    -> Specialized Agents
      -> Deterministic Decision Engine
        -> Diet Domain Plugin
          -> SQLAlchemy / SQLite
```

The agents handle language, clarification, planning, review, and explanation.
The deterministic engine handles filtering, scoring, ranking, data isolation, and
repeatable decision behavior.

## Quick Start

Requirements:

- Python 3.10+

Install and run:

```powershell
python -m pip install -e .
python scripts/init_db.py
python -m uvicorn choice_agent.main:app --host 127.0.0.1 --port 8000
```

Open:

- App: http://127.0.0.1:8000/
- API docs: http://127.0.0.1:8000/docs

If the package is not installed, run with `PYTHONPATH`:

```powershell
$env:PYTHONPATH = "src"
python scripts/init_db.py
python -m uvicorn choice_agent.main:app --host 127.0.0.1 --port 8000
```

## Configuration

By default, LLM mode is disabled and the system runs with deterministic rule
agents.

Copy `.env.example` and configure the values you need:

```env
CHOICE_AGENT_DATABASE_URL=sqlite:///./choice_agent.db
CHOICE_AGENT_MODEL_API_KEY=
CHOICE_AGENT_MODEL_BASE_URL=https://api.openai.com/v1
CHOICE_AGENT_MAIN_MODEL=gpt-5
CHOICE_AGENT_LIGHT_MODEL=gpt-5-mini
CHOICE_AGENT_MODEL_TIMEOUT_SECONDS=30
CHOICE_AGENT_ENABLE_LLM=false
CHOICE_AGENT_DEBUG=true
```

When model calls fail, intent and explanation agents fall back to local rule
behavior so the deterministic decision engine can continue to work.

The web UI also has a Settings page at `#/settings` for browser-side model
configuration. Values saved there are stored in the current browser's
localStorage and sent to the local backend as request headers for diet chat and
evaluation requests. If no browser API key is configured, the home page shows demo
mode and generic non-diet decisions continue to use the local demo workbench.

## Demo Mode

The web UI includes a generic demo workbench for travel, career offer, learning path,
and shopping decisions. These demo decisions use local fixture data and are labeled as
non-real-time examples so the general Choice Agent workflow can be shown without API
keys, network access, or extra database setup. New demo decisions start with an editable
candidate-preparation step, so users can add, remove, or confirm options before ranking
and generating a recommendation.

Diet requests still use the real local rule-agent flow and seeded meal data instead of
the generic fixture workbench.

## Data

The default database is `choice_agent.db` in the project root. The first startup
creates the tables and idempotently imports legacy diet slot options and meal data
from `legacy_diet_db.sql`.

The local database is ignored by Git and should not be committed.

## Diet Selection Context

Diet chat requests can pass optional selector controls in `context`:

```json
{
  "context": {
    "selectionStrategy": "weighted",
    "avoidRecentCount": 3
  }
}
```

Supported strategies are `ranked`, `random`, `weighted`, and `least_recent`. The default is `ranked` to preserve stable existing behavior.

## Testing

```powershell
python -m pytest
python -m compileall -q src scripts
```

## Project Structure

```text
src/choice_agent/
  agents/              Agent protocol and specialized agents
  api/                 FastAPI routes
  decision/            Generic deterministic decision engine
  domains/diet/        Diet-specific rules, seed data, and domain logic
  orchestration/       Multi-agent state machine
  providers/           Optional model provider integration
  repositories/        Persistence access layer
  services/            Trace and supporting services
  static/              Local web interface
tests/                 Engine, rules, orchestration, and API behavior tests
docs/                  Migration and implementation notes
adr/                   Research and planning records
```

## Roadmap

- Add more decision domains beyond diet.
- Improve evaluation datasets and regression scoring.
- Add richer comparison views for candidate trade-offs.
- Expand provider support for search, retrieval, and external evidence.
- Package reusable decision-domain templates.

## License

MIT

---

# 中文

**一个用于结构化、可解释决策的 Python 多 Agent 系统。**

Smart Choice Agent 可以把模糊需求转成候选项排序、约束分析、权衡解释、澄清问题、
证据记录和可审计 Trace。当前第一个完整领域是饮食推荐，但核心引擎按通用决策框架
设计，后续可以扩展到更多决策场景。

[English](#smart-choice-agent) | 中文

## 为什么做它

很多推荐系统会直接给答案，但很难解释“为什么是这个结果”。Smart Choice Agent 关注
完整决策过程：

- 用户到底想要什么？
- 哪些条件是必须满足的硬约束？
- 系统考虑过哪些候选项？
- 为什么一个选项排在另一个前面？
- 最终答案来自哪些证据和 Agent 运行记录？

这让它适合用于构建需要可调试、可解释、结果稳定的 AI 推荐和决策类产品。

## 核心亮点

- **多 Agent 流程**：意图、理解、澄清、候选、调整、计划、审查、解释、风险和评估 Agent。
- **确定性排序引擎**：硬约束过滤 + 七维评分，推荐结果稳定、可测试、可复现。
- **候选选择策略**：饮食聊天可通过上下文启用稳定排序、随机、匹配度加权或很久未推荐优先，并支持会话级近期冷却。
- **无 API Key 也能运行**：默认关闭 LLM，使用本地规则 Agent 完成完整流程。
- **可选 LLM 集成**：通过环境变量接入 OpenAI-compatible Chat Completions 接口。
- **完整可审计 Trace**：持久化会话、消息、推荐历史、反馈、`DecisionState`、`Evidence` 和 Agent Run。
- **内置饮食领域**：支持单餐推荐、多轮澄清、换一批、三餐计划、个人餐食库和公共餐食库。
- **FastAPI + 本地 Web UI**：本地即可启动，API 文档位于 `/docs`。

## 技术架构

```text
FastAPI / Static Web
  -> DietOrchestrator
    -> Specialized Agents
      -> Deterministic Decision Engine
        -> Diet Domain Plugin
          -> SQLAlchemy / SQLite
```

Agent 负责自然语言理解、澄清、计划、审查和解释；确定性引擎负责过滤、评分、排序、
数据隔离和可复现的决策行为。

## 快速开始

环境要求：

- Python 3.10+

安装并启动：

```powershell
python -m pip install -e .
python scripts/init_db.py
python -m uvicorn choice_agent.main:app --host 127.0.0.1 --port 8000
```

打开：

- 应用首页：http://127.0.0.1:8000/
- API 文档：http://127.0.0.1:8000/docs

如果尚未安装项目包，也可以直接指定源码路径：

```powershell
$env:PYTHONPATH = "src"
python scripts/init_db.py
python -m uvicorn choice_agent.main:app --host 127.0.0.1 --port 8000
```

## 配置

默认 `CHOICE_AGENT_ENABLE_LLM=false`，系统使用确定性规则 Agent 运行。

复制 `.env.example` 并按需配置：

```env
CHOICE_AGENT_DATABASE_URL=sqlite:///./choice_agent.db
CHOICE_AGENT_MODEL_API_KEY=
CHOICE_AGENT_MODEL_BASE_URL=https://api.openai.com/v1
CHOICE_AGENT_MAIN_MODEL=gpt-5
CHOICE_AGENT_LIGHT_MODEL=gpt-5-mini
CHOICE_AGENT_MODEL_TIMEOUT_SECONDS=30
CHOICE_AGENT_ENABLE_LLM=false
CHOICE_AGENT_DEBUG=true
```

模型调用失败时，意图和解释 Agent 会回退到本地规则结果，不影响确定性决策引擎运行。
Web UI 也提供 `#/settings` 设置页，可配置浏览器侧模型 API。该设置保存在当前浏览器的 `localStorage`，并随饮食聊天和评估请求通过请求头发送给本地后端。未配置浏览器 API Key 时，首页会显示演示模式，通用非饮食决策继续使用本地演示工作台。

## 演示模式

Web UI 内置通用演示工作台，覆盖旅行、职业 Offer、学习路径和购物决策。通用 demo 使用本地 fixture 数据，并在页面中标注“演示数据 / 非实时”，用于在没有 API Key、网络或额外数据库配置时展示 Choice Agent 的通用决策流程。新建演示会先进入可编辑的约束准备和候选项准备步骤，用户可以新增、删除或确认约束与候选项，再进入排序和结论生成。

饮食类请求仍然使用真实的本地规则 Agent 链路和种子餐食数据，不会被通用 fixture 工作台替代。

## 数据

默认数据库是项目根目录下的 `choice_agent.db`。首次启动会创建全部表，并从
`legacy_diet_db.sql` 幂等导入旧饮食项目的槽位选项和餐食数据。

本地数据库已加入 `.gitignore`，不应提交到 GitHub。

## 饮食选择上下文

饮食聊天请求可以在 `context` 中传入可选选择器参数：

```json
{
  "context": {
    "selectionStrategy": "weighted",
    "avoidRecentCount": 3
  }
}
```

支持的策略包括 `ranked`、`random`、`weighted` 和 `least_recent`。默认使用 `ranked`，保持现有稳定推荐行为。

## 测试

```powershell
python -m pytest
python -m compileall -q src scripts
```

## 项目结构

```text
src/choice_agent/
  agents/              Agent 协议和专用 Agent
  api/                 FastAPI 路由
  decision/            通用确定性决策引擎
  domains/diet/        饮食领域规则、种子数据和领域逻辑
  orchestration/       多 Agent 状态机
  providers/           可选模型服务集成
  repositories/        持久化访问层
  services/            Trace 和辅助服务
  static/              本地 Web 界面
tests/                 引擎、规则、编排和 API 行为测试
docs/                  迁移和实现说明
adr/                   Research 和 Plan 记录
```

## 路线图

- 扩展饮食以外的更多决策领域。
- 增强评估数据集和回归评分。
- 增加更清晰的候选项权衡对比视图。
- 扩展搜索、检索和外部证据的 provider 支持。
- 沉淀可复用的决策领域模板。

## 许可证

MIT
