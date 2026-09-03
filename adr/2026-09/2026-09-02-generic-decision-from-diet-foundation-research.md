# 基于 Diet Agent 骨架升级通用决策 Research

## 当前需求和范围

用户希望将 `choice-agent-v2` 升级为真正的通用决策系统，同时明确倾向于以当前更完整的 `diet-agent` 多 Agent 闭环为基础，而不是简单迁回旧版 `choice-agent` 的 Next.js 架构。

本 Research 聚焦当前 v2 中 diet 流程的真实调用链、通用决策能力已经具备的基础、仍然绑定饮食领域的部分、旧 `choice-agent` 可借鉴但不应硬搬的能力，以及第一阶段升级到通用决策的边界和风险。本阶段不修改产品代码。

## ADR / 历史方案检索

已检索 `adr/`、`docs/`、`src/choice_agent/`、`tests/` 中与 `choice-agent`、`diet-agent`、`DecisionState`、`Domain Plugin`、`generic demo`、`orchestrator`、`search provider` 相关的记录。

相关记录：

- `adr/2026-08/2026-08-29-choice-agent-v1-borrowed-ideas-todo.md`：高度相关。该文件已经判断旧 `choice-agent` 的优势是通用决策抽象，`diet-agent` 的优势是多 Agent 业务闭环，并列出了 Domain Plugin、通用 Orchestrator、通用 API、证据模型和工作台路线。
- `adr/2026-08/2026-08-29-diet-agent-python-migration-research.md`：高度相关。记录了 Java `diet-agent` 的多 Agent、会话、Trace、反馈、评估和饮食数据能力如何迁移到 Python。
- `adr/2026-08/2026-08-29-diet-agent-python-migration-plan.md`：高度相关。该计划已完成饮食闭环迁移，并曾提到领域插件协议，但当前代码仍没有真正插件化。
- `adr/2026-08/2026-08-29-home-general-decision-mode-research.md`：相关。明确当时通用 DecisionState 查询已存在，但没有通用决策创建或交互前端。
- `adr/2026-08/2026-08-30-generic-demo-mode-research.md`：相关。确认非饮食通用决策当前是纯前端 fixture demo，不是后端通用 Agent API。
- `adr/2026-08/2026-08-30-frontend-api-settings-plan.md`：相关。明确配置模型后，非饮食决策仍进入 demo，因为当时没有通用后端 API。
- `docs/migration-matrix.md`：相关。显示 diet-agent 核心能力基本已迁移，通用能力当前只到 `DecisionState / Candidate / Evidence` 和查询接口。

判断：本需求会改变核心架构边界，应新建本 Research / Plan。旧记录已完成或是长期 Todo，继续追加会混淆历史上下文。

## 核心文件及职责

### `src/choice_agent/orchestration/diet.py`

当前最完整的业务编排入口。它创建或恢复 diet session，校验 `expected_revision`，创建 `DecisionState` 和 trace id，读取近期消息、slot options、last recommendations，按顺序调用 `IntentAgent`、`UnderstandingAgent`、`ClarificationAgent`、`AdjustmentAgent`、`CandidateAgent`、`PlanningAgent`、`CriticAgent`、`ExplanationAgent`、`RiskAgent`，保存 session、message 和 decision state，并返回兼容旧 diet API 的 `ChatResponse`。

关键问题：类名、请求类型、session 字段、repository、engine、source mode、slot options、display blocks 都直接绑定 diet。

### `src/choice_agent/agents/base.py`

已有通用 Agent 运行协议。`AgentContext` 携带 session、trace、user、message、decision 和临时 data；`BaseAgent` 定义 `execute()`；`AgentRuntime` 统一记录输入、输出、耗时、失败和 trace agent run。

可复用：这是通用 Orchestrator 的良好基础，不需要推倒重来。限制是 `AgentContext.data` 是自由 dict，没有领域协议，Agent 输入输出没有阶段级 schema。

### `src/choice_agent/agents/diet.py`

当前饮食领域 Agent 的集中实现。它覆盖意图识别、slot 合并、澄清、候选检索、调整、三餐计划、候选审查、解释、风险和评估。可复用的是完整领域 Agent pipeline 样板，限制是大多数 Agent 的输入输出都是饮食 slots、meal records、meal ids、source mode。

### `src/choice_agent/decision/engine.py`

当前文件名看似通用，但实际是饮食专用引擎。它定义七个饮食 criteria，根据 `SlotBundle` 和 `MealRecord` 计算匹配，支持硬排除，并转换 `MealRecord` 为通用 `Candidate` 和 `Evidence`。

关键问题：`DecisionEngine.rank()` 直接依赖 `MealRecord`、`SlotBundle` 和 `SLOT_FIELDS`，不能直接用于旅行、购物、学习等领域。

### `src/choice_agent/decision/state_machine.py`

已有可复用状态机，负责校验 `draft / clarifying / searching / comparing / decided` 合法状态转换和 `expected_revision`。可作为通用 Orchestrator 的状态边界。

### `src/choice_agent/schemas.py`

同时包含通用模型和 diet API 模型。已有通用模型包括 `DecisionState`、`Constraint`、`Criterion`、`Evidence`、`Candidate`、`CandidateState`、`UnansweredQuestion`、`Assumption`、`TraceReference`、`Recommendation`、`AgentRun`。已有 diet 模型包括 `SlotBundle`、`ChatRequest`、`ChatResponse`、`MealRequest`、`MealResponse`、`FeedbackRequest`、`TraceLabelRequest`、`EvaluationRequest` 和 diet enums。

关键问题：通用和 diet schema 混在一个文件中，短期可以接受，但继续通用化时需要小心不要让通用接口依赖 `SlotBundle` 或 `MealResponse`。此外 `DecisionState.intent` 使用 diet `Intent` enum，不适合非饮食领域。

### `src/choice_agent/repositories/diet_repository.py`

当前持久化入口，负责 diet session/message、meal CRUD、slot options、feedback、trace 查询与标注、decision state 保存。可复用部分是 `DecisionRecord` 的保存/查询已经是通用表 `decision_state`。限制是 repository 名称和大量方法绑定 diet。通用 decision 保存最好抽出 `DecisionRepository`，避免通用 API 依赖 `DietRepository`。

### `src/choice_agent/db_models.py`

已有 `decision_state`、`agent_run`、`decision_evidence` 这些通用表，也有 `diet_sessions`、`diet_messages`、`meal_item`、`diet_slot_option`、`recommend_feedback`、`diet_request_trace` 这些饮食命名表。第一阶段可以复用 `decision_state.state_json`，避免数据库迁移；中长期再抽通用 session/message/feedback。

### `src/choice_agent/api/routes.py`

当前 API 覆盖 `/api/v1/diet/*`、Trace、Evaluation，以及 `GET /api/v1/decisions/{decision_id}` 查询。关键缺口是没有通用 `POST /api/v1/decisions`，没有通用推进 API，没有通用 recommend / candidate update API。

### `src/choice_agent/static/assets/js/demo.js`

当前非饮食通用决策是纯前端 demo，覆盖 travel、career、learning、shopping、generic，支持 localStorage、候选准备、约束准备、权重调整、候选排除、本地排序和解释。限制是完全不经过后端、数据库、Trace、AgentRuntime 或真实 `DecisionState` API。

## 当前调用链和数据流

饮食真实链路：

```text
POST /api/v1/diet/chat
  -> routes.chat
  -> DietOrchestrator.chat
  -> _session / assert_expected_revision
  -> TraceScope
  -> repository.add_message(user)
  -> AgentContext
  -> AgentRuntime.run(IntentAgent)
  -> AgentRuntime.run(UnderstandingAgent)
  -> branch:
       HEALTH_RISK -> RiskAgent
       OTHER -> fixed text
       MEAL_ADJUST -> AdjustmentAgent
       normal -> ClarificationAgent
       MEAL_PLAN -> PlanningAgent
       otherwise -> CandidateAgent
  -> CriticAgent
  -> ExplanationAgent
  -> RiskAgent
  -> _save_state
  -> repository.save_decision
  -> repository.add_message(assistant)
  -> ChatResponse
```

通用 demo 链路：

```text
Home input
  -> static app.js 判断非饮食
  -> ChoiceAgentDemo.createDecision(prompt, domain)
  -> localStorage
  -> #/demo/decision/:id
  -> ChoiceAgentDemo.rank / explain
```

该链路没有后端 trace、没有通用 session、没有 AgentRuntime，也不使用 `DecisionRecord`。

## 已有可复用能力

- `AgentRuntime` 已能统一记录 Agent run 和失败。
- `DecisionState` 已经具备大部分通用字段。
- `state_machine.py` 可复用为通用状态边界。
- `DecisionRecord` 可保存完整 JSON state，无需第一阶段数据库迁移。
- diet flow 具备完整业务闭环，可作为第一个 Domain 的参考实现。
- 静态 demo 已有 travel/career/learning/shopping fixture，可作为第二领域或通用 fixture provider 的数据来源。
- 模型 provider 已支持 OpenAI-compatible Chat Completions 和运行时 header 覆盖。

## 关键问题和隐患

- `DecisionEngine` 名称通用但实现饮食专用。继续在其中加旅行/购物逻辑会扩大混乱。
- `DietOrchestrator` 是完整骨架，但直接依赖 diet repository、diet request/response 和 diet agents。
- `DecisionState` 虽然通用，但 `intent` 字段使用 diet `Intent` enum，不适合非饮食领域。
- 通用 demo 的状态字段命名和后端 `DecisionState` 不完全一致，例如 `id` vs `decision_id`、`candidateState` vs `candidate_state`。
- 通用前端 demo 与真实后端链路分叉，用户会感觉“通用决策只是演示，diet 才是真的”。
- 旧 `choice-agent` 的 evidence quality、expectedRevision、search/recommend API 值得借鉴，但技术栈不同，不应照搬文件。
- 健康风险 guard 是 diet 特有能力，抽到通用层时需要保持领域边界，避免所有领域都套健康文案。
- Trace/evaluation 当前按 diet 标签设计，通用化时第一阶段不应强行统一评估后台，否则范围过大。

## 约束

- 必须保留现有 `/api/v1/diet/*` 兼容 API。
- 不能破坏当前饮食聊天、餐食库、反馈、Trace、评估流程。
- 第一阶段应避免数据库 schema 迁移，优先复用 `decision_state.state_json`。
- 通用化要以 diet-agent 的完整闭环为骨架，而不是迁回旧 Next.js。
- 无模型 key 时必须仍可运行，通过本地规则/fixture 完成通用演示。
- 新领域第一版应选低风险 fixture/local provider，避免外部搜索和高风险建议混在架构迁移中。

## Research 结论

推荐路线：以当前 `DietOrchestrator` 的多 Agent 顺序和 Trace 保存方式为模板，抽出一个 `GenericDecisionOrchestrator`，再把 diet 包装成 `DietDomain` 插件。第一阶段不追求完整替换所有 diet 内部实现，而是建立通用 API 和 Domain 协议，让非饮食领域也能走后端 `DecisionState + AgentRuntime + Trace + Repository` 链路。

第一阶段应该选择一个低风险 `travel` fixture domain，验证通用创建、澄清、候选、比较、推荐、保存和查询闭环。饮食继续保留当前 `/api/v1/diet/chat`，同时逐步让内部能力符合 Domain 协议。