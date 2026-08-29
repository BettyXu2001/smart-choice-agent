# Smart Choice Agent 通用架构后续 Todo

## 文件目的

记录 `D:\Code\AI Coding\choice-agent` 中值得 `choice-agent-v2` 后续吸收的通用决策能力，并把它们整理为 Smart Choice Agent 的架构推进计划。

当前判断：

- `diet-agent` 的优势是多 Agent 业务闭环更完整，已经覆盖意图、理解、澄清、候选、计划、风险、解释、Trace 和评估。
- `choice-agent` 的优势是通用决策抽象更清晰，包含 DecisionState、约束、标准、候选、证据、稳定排序、状态机和工作台思路。
- `choice-agent-v2` 当前应以 `diet-agent` 的完整 Agent 编排作为主骨架，把 `choice-agent` 的通用决策能力补齐到可复用架构中。

本文件不等同于已批准实施计划。涉及核心类型、API、状态流转、证据模型和前端工作台，正式实施前仍需单独 Research / Plan / Review。

## 目标

- 把当前饮食专用编排升级为 Smart Choice Agent 的通用多领域决策架构。
- 保留饮食领域作为第一个完整可用领域，避免通用化破坏现有饮食能力。
- 把通用决策能力沉淀到核心层，让旅行、职业、学习、消费等新领域可以复用同一套 Agent Pipeline。
- 让通用首页不只是入口提示，而是能创建、推进和展示真实 DecisionState。
- 保持无模型密钥时可用规则/fixture 模式完整演示。

## 架构方向

建议采用分层推进：

```text
Static UI / API
  -> Domain Router
    -> Generic Decision Orchestrator
      -> Agent Pipeline
        -> Decision Engine
          -> Domain Plugin
            -> Repository / Search Provider / Model Provider
```

关键原则：

- 通用 Orchestrator 负责状态流转、Agent 调度、revision 校验、Trace 和错误边界。
- Domain Plugin 负责领域槽位、领域候选、领域规则、风险规则、提示词和展示适配。
- Decision Engine 负责硬约束过滤、软偏好评分、稳定排序和推荐结构化结果。
- Explanation Agent 只能解释已确认候选、证据和排序，不能生成不存在的候选或覆盖硬约束。
- 模型输出必须进入结构化校验后才能写入 DecisionState。

## 分阶段计划

### 阶段 1：通用核心补强

- 补强 `DecisionState`，加入候选状态、下一步动作、未回答问题、假设、结构化 trace 引用和领域无关扩展字段。
- 抽出独立状态机，集中校验 `draft -> clarifying -> searching -> comparing -> decided` 等合法流转。
- 引入 `expected_revision`，防止异步搜索、推荐解释、多 Agent 写入或前端编辑覆盖旧状态。
- 把当前饮食编排中可复用的 Agent 运行协议、Trace、错误处理和回退逻辑移到通用层。

### 阶段 2：领域插件化

- 定义 Domain Plugin 协议，包含领域识别、槽位 Schema、候选 Provider、评分标准、风险规则、提示词、展示转换和评估样例。
- 将现有饮食能力改造成 `DietDomain` 插件，而不是让通用 Orchestrator 直接依赖饮食 Repository 和 SlotBundle。
- 保留现有 `/api/v1/diet/*` 兼容接口，内部转发到通用编排，降低迁移风险。
- 建立领域注册表，让首页和 API 从注册表读取可用领域，而不是硬编码饮食入口。

### 阶段 3：证据和搜索边界

- 增强 Evidence 模型，增加稳定 ID、候选 ID、criterion key、publisher、source url、published_at、freshness 和 confidence。
- 增加证据质量摘要，覆盖缺失证据、冲突值、过期证据和低置信度来源。
- 设计通用 Search Provider 边界，支持 fixture provider、领域本地数据源和外部搜索 Provider。
- 对推荐解释增加 evidence ID 引用校验，确保 reasons、tradeoffs 和 alternatives 都能追溯到真实证据。

### 阶段 4：通用决策 API

- 增加通用决策创建 API：从自然语言创建 DecisionState，并自动识别领域或进入领域选择。
- 增加通用推进 API：回答澄清、刷新候选、调整权重、排除候选、重新排序、生成推荐。
- 增加状态查询和历史恢复 API，保持与现有 `/api/v1/decisions/{decision_id}` 兼容。
- 为饮食旧接口提供适配层，确保旧前端和现有测试不因通用 API 引入而失效。

### 阶段 5：通用工作台

- 将首页开放式输入接入真实通用决策创建 API。
- 增加通用决策工作台，展示目标、硬约束、软偏好、候选、评分、证据状态、推荐和 Trace。
- 支持用户编辑权重、补充候选、排除候选、回答澄清并触发稳定重排。
- 饮食模式先作为领域化工作台试点，确认体验后再扩展其他领域。

### 阶段 6：新领域试点

- 优先选择一个低风险新领域作为第二个插件，例如学习路径、消费选择或旅行方案。
- 只接入 fixture/local provider，先验证通用 Agent Pipeline、状态机、证据模型和工作台是否足够复用。
- 第二领域通过后，再决定是否接入外部搜索或更多复杂领域。

## 成功标准

- 饮食现有主流程、API、Trace、反馈和评估继续通过。
- 通用首页可以创建真实 DecisionState，而不是只显示能力提示。
- 通用 Orchestrator 不直接依赖饮食字段、饮食 Repository 或饮食提示词。
- 饮食领域以插件形式接入通用流程。
- 至少一个非饮食领域可以复用同一套状态机、候选、证据、排序和解释流程。
- 所有候选推荐都有可追踪证据或明确说明证据缺口。
- 相同 DecisionState 下排序稳定可复现。
- 无模型密钥时仍能通过规则和 fixture 完成演示。

## 风险和约束

- 通用化过早可能破坏饮食已稳定流程，应先加适配层和回归测试，再逐步替换内部依赖。
- `DecisionState` 扩字段会影响持久化、API 和前端渲染，需要版本兼容策略。
- revision 校验引入后，旧接口如果没有传 revision，需要明确由适配层处理。
- 证据模型增强会扩大数据结构和 UI 复杂度，第一版应先做最小可用字段。
- 新领域不应一开始接外部实时搜索，否则会把 Provider 不确定性和架构验证混在一起。
- 健康、金融、法律等高风险领域不适合作为第二领域试点。

## 验证方案

- 单元测试：状态机合法流转、revision 冲突、硬约束过滤、稳定排序、证据摘要。
- 合约测试：每个 Agent 的输入输出 Schema、越权写入保护、错误降级。
- 集成测试：通用 Orchestrator + DietDomain + fixture provider。
- 兼容测试：现有 `/api/v1/diet/*` 行为和响应字段不回归。
- 前端测试：通用首页创建决策、工作台展示、编辑权重、排除候选、饮食模式入口。
- 回归测试：现有 `python -m pytest` 必须保持通过，并补充第二领域 fixture 场景。

## 后续 Todo

- [ ] 补强通用 `DecisionState` 字段：增加 `candidate_state`、`next_action`、结构化 `unanswered_questions`、`assumptions` 和更通用的 `trace` 表达。
- [ ] 抽出独立状态机：校验 `draft -> clarifying -> searching -> comparing -> decided` 等合法流转，避免 Agent 或 API 随意改状态。
- [ ] 使用 `revision` 做防陈旧写入：在异步搜索、推荐解释、多 Agent 并行或前端状态编辑时引入 `expected_revision` 校验。
- [ ] 抽出通用 Orchestrator：把 Agent 调度、Trace、错误边界和回退从饮食编排中沉淀到核心层。
- [ ] 定义 Domain Plugin 协议：覆盖领域识别、槽位、候选、标准、风险、提示词、展示转换和评估样例。
- [ ] 将饮食能力改造成 `DietDomain` 插件，并通过兼容适配层保留现有 `/api/v1/diet/*` 行为。
- [ ] 增加模式/领域注册机制：让饮食、旅行、职业、学习、消费等领域通过注册表接入首页，而不是硬编码导航和模式卡片。
- [ ] 增强证据质量模型：为 Evidence 增加稳定 ID、候选 ID、criterion key、freshness、publisher、published_at 等字段，并提供覆盖率、缺失、冲突、过期摘要。
- [ ] 增加推荐解释结构化校验：输出 reasons、tradeoffs、alternative 时引用 evidence IDs，并校验证据引用存在。
- [ ] 设计通用搜索 Provider 边界：保留 fixture provider / external provider 的接口，支持没有网络或密钥时完整演示。
- [ ] 建立通用决策创建 API：从一句自然语言创建 DecisionState，再逐步接入澄清、候选、比较和解释流程。
- [ ] 建立通用决策推进 API：支持回答澄清、调整条件、编辑权重、排除候选、刷新候选和生成推荐。
- [ ] 设计通用决策工作台：展示目标、硬约束、偏好权重、候选排序、证据状态和 Decision Trace；饮食模式可先作为领域化版本试点。
- [ ] 增加用户可编辑权重和候选排除能力：借鉴 `choice-agent` 工作台的实时重排体验，但要先评估饮食推荐业务是否需要暴露这些控件。
- [ ] 接入一个低风险非饮食领域试点，优先使用 fixture/local provider 验证通用架构复用能力。
- [ ] 明确 demo / rule / LLM 状态提示：在 UI 上区分规则模式、模型模式、演示数据和真实数据，避免用户误解结果来源。
- [ ] 扩展测试：为状态机、revision 冲突、证据摘要、推荐证据引用、通用 Orchestrator、Domain Plugin 和通用首页入口增加单元或端到端测试。

## 暂不执行原因

这些事项会触及通用数据结构、API、状态流转、证据模型、领域插件和工作台交互，属于跨模块或核心行为改动。应单独 Research / Plan / Review 后实施，避免在没有批准的情况下把当前系统演变成大范围重构。

## 阶段 1 执行 Research / Plan

### Research

当前代码现状：

- `src/choice_agent/schemas.py` 已定义通用 `DecisionState`、`Candidate`、`Evidence`、`Constraint`、`Criterion` 和 `DecisionStatus`，但还缺少 `next_action`、候选状态、未回答问题、假设和结构化 trace 引用。
- `src/choice_agent/agents/base.py` 已有 `AgentContext` 和 `AgentRuntime`，负责记录 Agent 输入、输出、耗时和失败，但不负责状态流转校验。
- `src/choice_agent/orchestration/diet.py` 当前直接创建 `DecisionState`，并在保存时按 session revision 写入 decision revision。
- `src/choice_agent/agents/diet.py` 里多个 Agent 直接设置 `context.decision.status`，状态变化分散在 Agent 内部。
- `src/choice_agent/repositories/diet_repository.py` 保存 `DecisionRecord` 时已经持久化 `status`、`revision` 和完整 `state_json`，因此扩展 Pydantic 字段不需要立即改数据库 schema。
- 现有测试覆盖饮食推荐、澄清、换一批、三餐计划、健康风险、餐食 CRUD、评估和基础排序，但没有覆盖通用状态机或 revision 冲突。

主要约束：

- 本阶段不能破坏现有 `/api/v1/diet/*` 兼容行为。
- `ChatRequest` 新增字段必须保持可选，旧前端不传时不能失败。
- 状态机第一版应先覆盖现有饮食流程实际需要的状态转换，避免过度设计。
- `DecisionState` 扩字段应有默认值，避免旧 `state_json` 读取失败。

### Plan

本阶段只实施通用核心补强：

- 在 `schemas.py` 中补充通用字段：`candidate_state`、`next_action`、`unanswered_questions`、`assumptions`、`trace_refs`，并增加必要的小型结构模型。
- 新增 `src/choice_agent/decision/state_machine.py`，集中提供状态转换校验和 revision 校验函数。
- 修改饮食 Agent，把直接设置 `decision.status` 的位置改为调用状态机函数。
- 在 `DietOrchestrator.chat()` 中支持可选 `expected_revision`，传入且不匹配当前 session revision 时返回 400。
- 在关键响应中填充 `next_action`，让通用工作台后续可以直接复用。
- 补充测试覆盖状态机合法/非法流转、chat revision 冲突和新字段默认兼容。
- 保持数据库 schema、旧 API 路径和前端不变。

### 阶段 1 Todo

- [x] 扩展 `DecisionState` 的通用字段并保持默认兼容。
- [x] 新增通用状态机和 revision 校验能力。
- [x] 将饮食 Agent 状态写入迁移到状态机函数。
- [x] 为饮食聊天请求增加可选 `expected_revision` 校验。
- [x] 补充状态机、revision 和字段兼容测试。
- [x] 运行 diff、compileall 和 pytest 验证。
