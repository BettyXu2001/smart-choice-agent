# 基于 Diet Agent 骨架升级通用决策 Plan

## 目标

将 `choice-agent-v2` 从“饮食 Agent + 通用 demo”升级为“通用决策 Agent 框架 + 饮食作为第一个完整领域”。

本轮以当前更完整的 diet-agent 多 Agent 闭环为基础，抽出通用编排、通用领域协议和通用 API。旧 `choice-agent` 只作为通用决策抽象和工作台体验参考，不迁回 Next.js 技术栈。

## 成功标准

- 现有 `/api/v1/diet/*` 行为和测试不回归。
- 新增后端通用决策 API，非饮食决策不再只能走纯前端 demo。
- 至少一个非饮食领域 `travel` 可以通过后端创建真实 `DecisionState`，生成 fixture 候选、排序、解释并持久化。
- 通用 Orchestrator 不直接依赖 `SlotBundle`、`MealRecord` 或 `DietRepository.list_meals()`。
- `DietDomain` 作为领域插件接入通用协议，先允许内部复用现有 diet agents/repository，避免一次性重写饮食闭环。
- 无模型 API Key 时通用决策仍可使用本地规则/fixture 跑通。
- Research / Plan / CHANGELOG 与实现同步。

## 架构设计

采用渐进式抽象，不推倒 diet-agent。

```text
FastAPI / Static UI
  -> Generic Decision API
    -> GenericDecisionOrchestrator
      -> DomainRegistry
        -> DomainPlugin
          -> Domain Agents / Candidate Provider / Scorer / Explainer
      -> AgentRuntime
      -> DecisionRepository
      -> DecisionState

Compatibility:
  /api/v1/diet/chat
    -> 保留 DietOrchestrator
    -> 后续逐步包装为 DietDomain
```

第一阶段重点是把“通用后端闭环”立起来。饮食 API 暂不强行迁到通用 Orchestrator 内部，以降低回归风险；但会定义 `DietDomain` 适配层，让后续替换路径明确。

## 关键流程

### 通用创建决策

```text
POST /api/v1/decisions
  -> GenericDecisionRequest
  -> DomainRegistry.resolve(domain/message)
  -> DecisionRepository.create_decision
  -> DecisionState 初始化
  -> GenericDecisionOrchestrator.run
  -> DomainPlugin.understand
  -> DomainPlugin.clarify
  -> DomainPlugin.candidates
  -> generic/domain ranking
  -> DomainPlugin.explain
  -> save DecisionState
  -> GenericDecisionResponse
```

### 通用推进决策

```text
POST /api/v1/decisions/{decision_id}/messages
  -> 读取 DecisionState
  -> 校验 expected_revision
  -> 追加用户输入到 domain_state/history
  -> 重新运行 DomainPlugin 对应阶段
  -> 保存新 revision
```

第一阶段可以只支持单轮创建和再次发送文本推进，不实现所有编辑操作。

### Diet 兼容路径

```text
POST /api/v1/diet/chat
  -> 继续使用 DietOrchestrator
  -> 保持 ChatResponse / MealResponse / Trace / Evaluation 兼容
```

同时新增 `DietDomain`，声明 domain key、criteria、风险描述、展示转换能力。后续再逐步把 `DietOrchestrator` 内部依赖迁入插件协议。

## 受影响文件

### 新增文件

- `src/choice_agent/domains/base.py`：定义 `DomainPlugin`、`DomainRunResult` 等最小协议。
- `src/choice_agent/domains/registry.py`：领域注册和简单识别逻辑。
- `src/choice_agent/domains/travel.py`：第一版 fixture travel domain，实现理解、候选、排序、解释。
- `src/choice_agent/domains/diet/domain.py`：diet 插件适配层，先暴露元数据、criteria 和 compatibility 标记。
- `src/choice_agent/repositories/decision_repository.py`：抽出通用 DecisionState 保存、读取能力。
- `src/choice_agent/orchestration/generic.py`：通用 Orchestrator。
- `tests/test_domain_registry.py`：领域识别和注册测试。
- `tests/test_generic_orchestrator.py`：通用创建、travel fixture、revision、保存读取测试。
- `tests/test_generic_api.py`：通用 API 合约测试。

### 修改文件

- `src/choice_agent/schemas.py`
  - 新增通用请求/响应模型；
  - 避免破坏现有 diet models；
  - 如需要，新增通用 intent/action 字段，不移除 diet `Intent`。
- `src/choice_agent/api/routes.py`
  - 新增 `POST /api/v1/decisions`；
  - 新增 `POST /api/v1/decisions/{decision_id}/messages`；
  - 保留现有 `GET /api/v1/decisions/{decision_id}`；
  - 保持 `/api/v1/diet/*` 不变。
- `src/choice_agent/decision/engine.py`
  - 保留现有 meal ranking；
  - 如需通用评分，优先新增通用函数或新文件，避免把 meal ranking 改坏。
- `src/choice_agent/static/assets/js/api.js`
  - 增加 `DecisionApi` 客户端。
- `src/choice_agent/static/assets/js/app.js`
  - 首页非饮食输入优先调用通用 API；
  - API 不可用时保留现有 demo fallback；
  - 增加通用后端 decision 的基础展示。
- `src/choice_agent/static/assets/js/demo.js`
  - 保留作为 fallback 和 fixture 参考，不作为后端真实链路。
- `docs/migration-matrix.md`
  - 更新通用决策能力状态。
- `CHANGELOG.md`
  - 记录用户可感知的新通用决策 API 和 travel 后端 fixture。

## 兼容性和破坏性变更评估

- 不删除或重命名现有 diet API。
- 不改变 `ChatRequest`、`ChatResponse`、`MealResponse` 的必填字段。
- 不迁移数据库 schema；使用现有 `decision_state.state_json` 保存通用状态。
- `DecisionState.intent` 暂不改类型，避免影响 diet 测试；通用领域使用 `domain_state["intent"]` 或新增可选字段。
- 前端保留 demo fallback，降低通用 API 初版不完整导致页面不可用的风险。

## 风险和边界情况

- 如果第一轮就强行让 `/api/v1/diet/chat` 改走通用 Orchestrator，回归风险高。本轮不这么做。
- `DecisionRepository` 如果复用 diet session 表，会留下命名债务；如果新增表，会引入迁移。本轮先只抽 DecisionState 保存读取，session/message 仍最小化处理。
- travel fixture 不能伪装实时搜索结果，UI 和响应中必须标注 fixture/local source。
- 通用解释不能编造 evidence 之外的事实；第一版解释只基于候选 attributes/evidence。
- 前端通用工作台如果一次性替换现有 demo，范围会过大；本轮只接入基础真实后端流程。

## 技术取舍

- 以 diet 为骨架，不迁回 Next.js：保留 FastAPI/Python 架构，复用当前更完整的 Trace、评估和 AgentRuntime 能力。
- 先插件协议，后深度改造 diet：先建立 `DomainPlugin`，让 travel 走真实通用后端；diet 兼容 API 下一阶段再逐步内部迁移。
- 先 fixture domain，不接外部搜索：先验证通用 pipeline，避免外部搜索不确定性干扰架构落地。
- 保留 demo fallback：保证无网络、无模型、API 初版异常时仍可演示。

## 验证方案

- `python -m compileall -q src scripts`
- `python -m pytest`
- 新增测试覆盖 domain registry resolve、generic orchestrator 创建 travel decision、expected_revision 冲突、persisted `DecisionState` 查询、`/api/v1/decisions` API 合约和 `/api/v1/diet/chat` 既有回归。
- 前端静态检查：
  - `node --check src/choice_agent/static/assets/js/api.js`
  - `node --check src/choice_agent/static/assets/js/app.js`
  - `node --check src/choice_agent/static/assets/js/demo.js`

## 注意事项

- 实施前必须获得用户明确批准。
- 若实施中发现必须改数据库 schema、删除 diet 兼容接口或重写大段前端，需要暂停并更新 Plan。
- 不把旧 `choice-agent` 的 Supabase/Vercel/Next.js 部署方案纳入本轮。
- 不在本轮接入健康、金融、法律等高风险通用领域。

## Todo

- [x] 新增通用 DomainPlugin 协议和 DomainRegistry。
- [x] 新增通用 DecisionRepository，抽出 DecisionState 保存和读取能力。
- [x] 新增 GenericDecisionOrchestrator，复用 AgentRuntime、状态机、Trace 和 DecisionState。
- [x] 新增 travel fixture domain，支持理解、候选、排序、解释和 evidence。
- [x] 新增通用决策创建 API 和文本推进 API。
- [x] 增加 DietDomain 适配层，声明 diet 作为第一个完整领域但不破坏现有 DietOrchestrator。
- [x] 前端增加 DecisionApi，非饮食输入优先走通用后端，失败时回退 demo。
- [x] 更新通用后端 decision 的基础展示和 demo/source 标识。
- [x] 补充 domain registry、generic orchestrator、generic API 和 diet 回归测试。
- [x] 更新 docs/migration-matrix.md 和 CHANGELOG.md。
- [x] 执行 diff、compileall、pytest 和 JS 语法检查。