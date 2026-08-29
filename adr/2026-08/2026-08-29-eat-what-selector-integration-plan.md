# eat-what 选择器整合 Plan

## 目标和成功标准

目标是在不重构整体架构的前提下，把 `eat-what` 中已验证的推荐策略、近期冷却和选择洞察，整合为 `choice-agent-v2` 的通用候选选择能力，并先接入饮食推荐流程。

成功标准：

- 新增一个领域无关的选择器模块，支持 `weighted`、`random`、`least_recent` 三种策略。
- 饮食推荐继续使用现有槽位匹配和硬约束过滤生成候选。
- 选择器只在候选列表生成后决定主推荐与备选顺序，不接管饮食槽位逻辑。
- 第一版不新增依赖、不新增前端构建体系、不引入饮品领域。
- 旧 `/api/v1/diet/*` 路径保持兼容。
- 默认行为尽量接近现有稳定排序；新策略可通过请求上下文启用。
- 新增单元测试和编排测试覆盖策略、历史冷却、洞察和兼容路径。

## 架构或逻辑设计

采用三层分工：

```text
Diet domain
  负责餐食数据、槽位匹配、健康风险、饮食展示

Decision selector
  负责候选选择策略、会话级近期冷却、概率和解释标签

Diet orchestration
  负责在 CandidateAgent 之后调用选择器，并把结果交给 ExplanationAgent
```

新增通用选择器不依赖 `MealRecord`，只依赖轻量输入结构：

```python
SelectionCandidate(
    candidate_id: str,
    name: str,
    score: float,
    attributes: dict[str, Any],
)
```

选择器输出：

```python
SelectionResult(
    selected_id: str | None,
    ordered_ids: list[str],
    insights: SelectionInsights,
)
```

策略定义：

- `ranked`：保持现有排序顺序，作为默认兼容策略。
- `random`：有效候选中均匀随机。
- `weighted`：按候选 `score` 作为权重随机；当总权重为 0 时退化为随机。
- `least_recent`：优先选择会话历史中最久未展示或从未展示的候选。

说明：`eat-what` 只有三种策略，但 `choice-agent-v2` 需要一个兼容默认策略，所以新增 `ranked` 作为系统默认值，避免上线后推荐顺序突然随机化。

## 关键流程

普通推荐：

```text
CandidateAgent
  -> DecisionEngine.rank 生成 ranked meals
  -> DecisionSelector.select 根据策略和历史生成 ordered_ids
  -> context.data["ranked"] 按 ordered_ids 重排
  -> context.decision.domain_state["selection"] 写入洞察
  -> CriticAgent
  -> ExplanationAgent 使用重排后的前 3 个候选生成回复
```

换一批：

```text
AdjustmentAgent
  -> 继续把 session.last_recommendations 放入 exclude_ids
  -> CandidateAgent 排除已展示候选
  -> DecisionSelector 在剩余候选中选择
```

策略传入：

- 第一版从 `ChatRequest.context.selectionStrategy` 读取；
- 允许值为 `ranked`、`random`、`weighted`、`least_recent`；
- 缺失或非法时使用 `ranked`；
- `avoidRecentCount` 从 `ChatRequest.context.avoidRecentCount` 读取，缺失时为 0；
- 第一版不持久化用户默认策略。

历史来源：

- 第一版使用 `session.last_recommendations` 作为会话级历史；
- `avoidRecentCount` 只排除最近 N 个已展示候选；
- 不新增选择历史表；
- 不从反馈表推导偏好，避免把“喜欢/不喜欢”和“展示过”混为一谈。

洞察输出：

- 写入 `DecisionState.domain_state["selection"]`；
- 包含策略、候选数、有效候选数、选中概率、解释标签、近期排除数；
- 第一版不扩展 `MealResponse` 顶层字段，避免影响旧前端。

## 受影响文件列表

- `src/choice_agent/schemas.py`
  - 增加 `SelectionStrategy` 枚举和必要的选择洞察模型，或使用内部 dataclass 时仅补充对 `ChatRequest.context` 的说明性约束。
- `src/choice_agent/decision/selector.py`
  - 新增通用候选选择器、候选过滤、策略实现和洞察计算。
- `src/choice_agent/agents/diet.py`
  - 在 `CandidateAgent` 中接入选择器，对 `ranked` 重排并写入 `domain_state["selection"]`。
  - 保持 `PlanningAgent` 暂不接入随机策略，避免三餐计划失去稳定性。
- `src/choice_agent/orchestration/diet.py`
  - 将 `selectionStrategy` 和 `avoidRecentCount` 从请求上下文传入 AgentContext。
- `tests/test_selector.py`
  - 新增通用选择器单元测试。
- `tests/test_orchestrator.py`
  - 增加饮食编排接入测试，覆盖默认兼容、策略上下文和近期冷却。
- `README.md`
  - 如对外说明请求上下文策略，需要补充简短用法。
- `CHANGELOG.md`
  - 若实施完成，记录新增推荐策略和选择洞察。

## 每个文件计划修改的内容

### `src/choice_agent/decision/selector.py`

新增纯函数模块：

- `SelectionStrategy` 或字符串归一化函数；
- `SelectionCandidate`；
- `SelectionInsights`；
- `SelectionResult`；
- `select_candidates(candidates, strategy, recent_ids, avoid_recent_count, random=None)`；
- 内部函数：随机选择、加权选择、最久未选排序、概率计算、标签生成。

设计要求：

- 不依赖数据库；
- 不依赖饮食模型；
- 支持注入 `random` 函数，方便测试；
- 空候选返回空结果，不抛异常；
- 非法策略退回 `ranked`。

### `src/choice_agent/agents/diet.py`

在 `CandidateAgent.execute()` 中：

- 将 `RankedMeal` 转换为 `SelectionCandidate`；
- 读取 `context.data["selection_strategy"]` 和 `context.data["avoid_recent_count"]`；
- 读取 `context.data["recent_recommendation_ids"]`；
- 调用选择器；
- 按 `ordered_ids` 重排 `ranked`；
- 把洞察写入 `context.decision.domain_state["selection"]`。

`ExplanationAgent` 不直接理解策略，只继续解释 `context.data["ranked"]` 的前 3 个，降低改动面。

### `src/choice_agent/orchestration/diet.py`

构造 `AgentContext.data` 时增加：

- `selection_strategy`：来自 `request.context.selectionStrategy`，默认 `ranked`；
- `avoid_recent_count`：来自 `request.context.avoidRecentCount`，默认 0；
- `recent_recommendation_ids`：来自 `session.last_recommendations`。

对 `avoidRecentCount` 做保守归一化：

- 非整数、负数或异常值归零；
- 设置上限，例如 20，避免请求传入过大值导致意外排空候选。

### `tests/test_selector.py`

覆盖：

- 默认 `ranked` 保持顺序；
- `random` 可通过注入随机函数确定；
- `weighted` 按 score 权重选择；
- score 全 0 时退化为随机；
- `least_recent` 优先从未展示或最久未展示；
- `avoid_recent_count` 排除最近 N 个；
- 空候选返回空结果；
- 非法策略回退。

### `tests/test_orchestrator.py`

新增或扩展测试：

- 默认不传策略时，现有推荐流程仍返回稳定前 3 个；
- 传入 `selectionStrategy="least_recent"` 且 `avoidRecentCount` 时，不推荐最近展示项；
- `decision_state.domain_state["selection"]` 包含策略、候选数和解释标签。

## 兼容性和破坏性变更评估

- API 路径不变。
- `ChatRequest.context` 已存在，新增约定字段不会破坏旧客户端。
- 默认策略为 `ranked`，现有请求不应出现随机化行为。
- `DecisionState.domain_state` 已是扩展字段，新增 `selection` 子对象对旧读取方兼容。
- 不修改数据库 schema，避免迁移成本。
- 不改变 `MealResponse` 顶层结构，旧前端不需要同步改造。
- `PlanningAgent` 暂不接入选择器，三餐计划继续保持稳定。

## 风险和边界情况

- 如果候选很少且 `avoidRecentCount` 较大，可能排空候选。第一版应允许选择器返回空结果，并由现有 `ExplanationAgent` 给出无匹配提示。
- `weighted` 使用匹配分而非用户星级，因此它表达的是“匹配度加权”，不是 `eat-what` 的“偏好星级加权”。文案必须避免误导。
- 会话历史只记录已展示推荐，不等同于用户真正吃过或接受过。
- 随机策略会降低可复现性，测试必须通过注入随机函数覆盖，生产 Trace 中应记录策略和洞察。
- 当前 `CriticAgent` 只检查重复、分数范围和排除项；如果选择器重排后出现空结果，应继续由解释层处理。

## 验证方案

自动验证：

- 运行 `python -m pytest tests/test_selector.py`。
- 运行 `python -m pytest tests/test_engine.py tests/test_orchestrator.py tests/test_rules.py`。
- 运行 `python -m compileall src tests`。

行为验证：

- 默认聊天请求 `晚餐想吃清淡一点` 仍能返回推荐。
- 带上下文的请求可以启用 `weighted` 或 `least_recent`。
- 设置 `avoidRecentCount` 后，最近展示项不会进入有效候选。
- 返回的 `decision_state.domain_state.selection` 能解释当前策略和候选情况。

Diff 检查：

- 确认只修改计划内文件；
- 确认没有引入前端构建依赖；
- 确认没有新增数据库迁移；
- 确认没有调试输出或临时日志。

## 注意事项与技术折衷

- 本次选择器是通用能力，但只先接入饮食领域，避免一次性改造通用 Orchestrator。
- 用 `score` 作为权重是最小可行方案；用户级偏好 rating 可以后续在单独计划中设计。
- 不把 `eat-what` 的 UI 直接搬入当前项目，避免引入 React 技术栈。
- 不把饮品模式并入本次范围，因为它会牵涉领域建模和 API 命名。
- 选择洞察先放 `domain_state`，后续通用工作台稳定后再决定是否升级为顶层模型。

## Todo

- [x] 新增通用选择器模块，支持 `ranked`、`random`、`weighted`、`least_recent`。
- [x] 为选择器实现候选冷却、概率计算和解释标签。
- [x] 在饮食推荐 CandidateAgent 后接入选择器并重排候选。
- [x] 从 ChatRequest.context 读取 `selectionStrategy` 和 `avoidRecentCount`。
- [x] 将选择洞察写入 `DecisionState.domain_state["selection"]`。
- [x] 补充选择器单元测试。
- [x] 补充饮食编排集成测试。
- [x] 运行 compileall 和 pytest 验证。
- [x] 检查 git diff，确认无计划外改动。
- [x] 按 CHANGELOG 规则记录用户可感知变化。