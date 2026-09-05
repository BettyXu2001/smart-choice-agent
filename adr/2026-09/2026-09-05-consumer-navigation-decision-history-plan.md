# Consumer Navigation and Decision History Plan

## 目标和成功标准

把 Choice Agent 的主信息架构从工程 Demo 调整为 C 端通用决策产品：顶部主导航只展示 `首页`、`历史决策`、`我的资料`；`首页` 负责开始新决策；`历史决策` 展示过去做过的选择、当时条件、推荐和最终选择；`我的资料` 保存长期偏好，并保留个人餐食库入口；`Trace`、`Evaluation`、`API / Model 设置`、`Debug 信息` 统一进入 `开发者工具`。

成功标准：普通用户首屏和主导航不再出现 `Trace`、`评估`、`设置` 等工程入口；`#/history` 能列出当前用户的真实决策记录；`#/history/:id` 能展示目标、候选、约束、用户偏好、最终推荐、关键理由、未确定信息和最终选择；`#/profile` 能查看和保存长期偏好；`#/developer/debug` 能查看用户 ID、当前路由、Developer Mode 状态和基础调试信息；旧路由和现有核心流程保持兼容。

## 架构和逻辑设计

第一阶段采用三层结构：

```text
主导航
  首页
  历史决策
  我的资料

右上角
  主题
  开发者工具
    Developer Mode 开关
    Trace
    Evaluation
    API / Model 设置
    Debug 信息
```

Developer Mode 使用 `localStorage` 保存开关状态。它只控制 UI 是否显性展示开发者入口，不作为权限控制。

## 历史决策 API

新增独立历史 API，避免改变现有 `GET /api/v1/decisions/{decision_id}` 的语义：

```text
GET /api/v1/decision-history
GET /api/v1/decision-history/{decision_id}
PUT /api/v1/decision-history/{decision_id}/outcome
DELETE /api/v1/decision-history/{decision_id}/outcome
```

列表 API 返回摘要：`decisionId`、`title`、`domain`、`createdAt`、`updatedAt`、`status`、`currentRecommendation`、`finalChoice`。详情 API 返回 `summary` 和完整 `DecisionState`。

## 最终选择数据结构

扩展 `DecisionState`，新增通用 `outcome` 字段：

```python
class DecisionOutcome(ApiModel):
    candidate_id: str | None = None
    label: str
    reason: str | None = None
    recorded_at: datetime | None = None
```

`DecisionState.outcome` 默认 `None`，保证旧记录兼容。保存时使用现有 `DecisionRepository.save()` 的 revision 机制，避免覆盖并发更新。用户可以选择已有候选，也可以输入自由文本；传入 `candidateId` 时必须存在于当前候选列表。

## 历史列表查询

在 `DecisionRepository` 增加 `list_for_user(user_id, limit)`：按 `DecisionRecord.updated_at desc` 读取最近记录，将 `state_json` 解析为 `DecisionState`，复用 owner 判断逻辑，仅返回当前用户可见记录。由于没有 owner column，第一版限制 `limit <= 100`，内部可多取一部分记录再过滤。后续如数据规模增长，再补数据库迁移。

## 我的资料

新增 `UserProfileRecord` 表，主键为 `user_id`，使用 `profile_json` 保存结构化资料，并包含 `created_at`、`updated_at`。新增 `UserProfile` Schema，字段包括 `budget_habit`、`preferred_cities`、`diet_preferences`、`notes`。新增 API：

```text
GET /api/v1/profile
PUT /api/v1/profile
```

第一版资料只保存和展示，不自动写入决策模型上下文，避免隐藏个性化影响推荐结果。

## 个人餐食库入口

保留现有 `#/diet/meals/personal` 和 `renderPersonalMeals()`，但从主导航移除。`#/profile` 中提供“个人餐食库”入口，让既有能力继续可用。

## 开发者工具

前端增加开发者工具菜单状态：`developerModeEnabled`，从 `localStorage.choiceAgentDeveloperMode` 初始化。菜单内提供 Developer Mode 开关、Trace、Evaluation、API / Model 设置、Debug 信息。

新增 `#/developer/debug`，展示当前用户 ID、当前路由、Developer Mode 状态、当前浏览器是否配置模型、当前决策 ID / session ID / revision，如果页面状态中存在；不展示 API Key 明文。

## 受影响文件列表

- `src/choice_agent/schemas.py`：新增历史摘要、历史详情、最终选择、用户资料相关 Schema；扩展 `DecisionState.outcome`。
- `src/choice_agent/db_models.py`：新增 `UserProfileRecord`。
- `src/choice_agent/repositories/decision_repository.py`：新增历史列表查询和摘要映射辅助逻辑。
- `src/choice_agent/repositories/profile_repository.py`：新增用户资料读写仓储。
- `src/choice_agent/api/routes.py`：新增历史决策和用户资料 API。
- `src/choice_agent/static/index.html`：调整顶部主导航，增加开发者工具菜单容器。
- `src/choice_agent/static/assets/js/api.js`：增加 `DecisionHistoryApi` 和 `ProfileApi`。
- `src/choice_agent/static/assets/js/app.js`：新增 `/history`、`/history/:id`、`/profile`、`/developer/debug` 路由和页面。
- `src/choice_agent/static/assets/js/conversation.js`：视需要调整个人餐食入口文案。
- `tests/test_decision_history.py`：新增历史列表、详情、最终选择记录和 owner 过滤测试。
- `tests/test_profile.py`：新增用户资料读写测试。
- `CHANGELOG.md`：记录导航、历史决策、我的资料、开发者工具和 API / 数据结构变化。

## 兼容性和破坏性变更评估

旧决策记录兼容：`DecisionState.outcome` 默认 `None`，旧 `state_json` 可继续解析。旧 API 兼容：不修改现有 `/api/v1/decisions/{decision_id}` 响应语义。旧路由兼容：`#/diet/meals/personal`、`#/admin/traces`、`#/admin/evaluations`、`#/settings`、`#/decisions/:id` 保留。数据库只新增 `user_profiles` 表，不修改既有表结构。Developer Mode 不是权限控制，Debug 页面不展示 API Key 明文。

## 风险和边界情况

- 历史列表第一版没有 `DecisionRecord.owner_user_id` 索引，Python 层过滤不适合大规模数据。
- 旧 owner 缺失记录继续只对 user 1 兼容可见。
- 推荐为空时列表展示“未形成推荐”。
- 最终选择为空时列表展示“未记录”。
- 我的资料第一版不自动影响推荐，页面文案必须准确。
- localStorage 被清除后 Developer Mode 回到普通模式。

## 验证方案

自动验证：

```text
python -m pytest tests/test_decision_history.py tests/test_profile.py
python -m pytest
python -m compileall -q src
node --check src/choice_agent/static/assets/js/api.js
node --check src/choice_agent/static/assets/js/app.js
node --check src/choice_agent/static/assets/js/conversation.js
git diff --check
```

行为验证：普通模式首页主导航只显示三项且无工程入口；创建通用决策后历史列表出现真实记录；历史详情能展示目标、候选、约束、偏好、推荐、理由和未确定信息；最终选择可保存并在列表和详情显示；我的资料可保存并刷新读取；开发者工具可切换 Developer Mode 并进入 Trace、Evaluation、设置和 Debug；旧路由仍可访问。

## 注意事项与技术折衷

第一版历史中心使用当前 `DecisionRecord` 最新状态，不做 revision 级时光回放。第一版用户资料保存但不参与推荐排序，后续可在新的 ADR 中设计“资料注入决策上下文”。第一版 Developer Mode 是前端显示控制，不承担鉴权。不修改 `DecisionRecord` 结构，避免在没有迁移体系的项目中引入数据库升级风险。最终选择放入 `DecisionState.outcome`，因为它是通用决策闭环的一部分，并且可以随现有 revision 机制保存。

## Todo

- [ ] 扩展 `DecisionState` 和新增历史、最终选择、用户资料 Schema。
- [ ] 新增 `UserProfileRecord` 和用户资料仓储。
- [ ] 扩展 `DecisionRepository`，支持按用户列出历史决策并生成摘要。
- [ ] 新增历史决策 API：列表、详情、保存最终选择、清除最终选择。
- [ ] 新增用户资料 API：读取和保存。
- [ ] 调整顶部主导航为 `首页 | 历史决策 | 我的资料`。
- [ ] 增加开发者工具菜单、Developer Mode 开关和 Debug 页面。
- [ ] 实现历史决策列表、历史详情和最终选择记录 UI。
- [ ] 实现我的资料页面，并保留个人餐食库入口。
- [ ] 调整首页普通模式，移除显性的工程入口。
- [ ] 增加历史决策和用户资料测试。
- [ ] 更新 `CHANGELOG.md`。
- [ ] 执行自动验证和关键行为验证。