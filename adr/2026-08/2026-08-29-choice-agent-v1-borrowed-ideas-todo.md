# Choice Agent 可借鉴能力后续 Todo

## 文件目的

记录 `D:\Code\AI Coding\choice-agent` 中值得 `choice-agent-v2` 后续吸收、但不应塞进当前首页/模式入口改动的低优先级或较大范围事项。

当前首页 Plan 已纳入的高优先级借鉴项：开放式通用首页输入、跨领域示例、决策流程展示、当前能力状态提示和诚实降级。

## 后续 Todo

- [ ] 补强通用 `DecisionState` 字段：增加 `candidate_state`、`next_action`、结构化 `unanswered_questions`、`assumptions` 和更通用的 `trace` 表达。
- [ ] 抽出独立状态机：校验 `draft -> clarifying -> searching -> comparing -> decided` 等合法流转，避免 Agent 或 API 随意改状态。
- [ ] 使用 `revision` 做防陈旧写入：在异步搜索、推荐解释、多 Agent 并行或前端状态编辑时引入 `expected_revision` 校验。
- [ ] 增强证据质量模型：为 Evidence 增加稳定 ID、候选 ID、criterion key、freshness、publisher、published_at 等字段，并提供覆盖率、缺失、冲突、过期摘要。
- [ ] 增加推荐解释结构化校验：输出 reasons、tradeoffs、alternative 时引用 evidence IDs，并校验证据引用存在。
- [ ] 设计通用搜索 Provider 边界：保留 fixture provider / external provider 的接口，支持没有网络或密钥时完整演示。
- [ ] 建立通用决策创建 API：从一句自然语言创建 DecisionState，再逐步接入澄清、候选、比较和解释流程。
- [ ] 设计通用决策工作台：展示目标、硬约束、偏好权重、候选排序、证据状态和 Decision Trace；饮食模式可先作为领域化版本试点。
- [ ] 增加用户可编辑权重和候选排除能力：借鉴 `choice-agent` 工作台的实时重排体验，但要先评估饮食推荐业务是否需要暴露这些控件。
- [ ] 增加模式/领域注册机制：让饮食、旅行、职业、学习、消费等领域通过注册表接入首页，而不是硬编码导航和模式卡片。
- [ ] 明确 demo / rule / LLM 状态提示：在 UI 上区分规则模式、模型模式、演示数据和真实数据，避免用户误解结果来源。
- [ ] 扩展测试：为状态机、revision 冲突、证据摘要、推荐证据引用和通用首页入口增加单元或端到端测试。

## 暂不执行原因

这些事项会触及通用数据结构、API、状态流转、证据模型或工作台交互，属于跨模块或核心行为改动。应单独 Research / Plan / Review 后实施，避免当前首页入口调整演变成大范围重构。