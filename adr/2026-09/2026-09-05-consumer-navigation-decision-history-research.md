# Consumer Navigation and Decision History Research

## 当前需求和研究范围

本次需求要求把 Choice Agent 从工程 Demo 信息架构调整为更像 C 端 AI 产品的结构：顶部主导航调整为 `首页 | 历史决策 | 我的资料`；`首页` 负责开始新的决策；`历史决策` 负责查看过去做过的选择、当时条件、推荐和最终选择；`我的资料` 存放长期偏好，例如预算习惯、城市偏好、饮食偏好等；`Trace`、`Evaluation`、模型设置和 Debug 信息保留，但收拢到 `开发者工具` 或 Developer Mode；后续可继续扩展“决策复盘”和长期 Evaluation 数据闭环。

这属于大改动，因为它会影响核心导航、用户主流程、公开 API、核心数据结构、持久化模型和前端路由。按照 `AGENTS.md`，必须先完成 ADR lookup、Research 和 Plan，获得用户明确批准后才能修改产品代码。

## ADR lookup

已检索 `adr/` 中与导航、通用决策、历史恢复、Trace、Evaluation、设置、个人数据和 `DecisionState` 相关的记录。

相关记录：

- `adr/2026-08/2026-08-30-unified-choice-entry-research.md` 和 `plan.md`：覆盖首页从饮食入口升级为通用决策入口，并将餐食库下沉为辅助入口。本次继续推进该方向，但新增历史决策中心、我的资料和开发者模式，边界更大。
- `adr/2026-08/2026-08-30-frontend-api-settings-research.md` 和 `plan.md`：覆盖浏览器侧 API / Model 设置。本次保留设置页，只调整入口。
- `adr/2026-09/2026-09-02-generic-decision-from-diet-foundation-research.md` 和 `plan.md`：覆盖通用 `DecisionState`、通用决策 API 和领域插件。本次历史中心应复用这些能力。
- `adr/2026-09/2026-09-04-general-conversation-panel-research.md` 和 `plan.md`：覆盖统一对话面板，已让饮食、旅行、购物和通用决策共用一套体验。本次历史详情可借鉴展示字段，但需要独立只读页面。

结论：已有 ADR 相关但没有同类完整方案。由于相关计划已完成，且本次主题是新的信息架构和数据闭环，选择新建 Research / Plan。

## 核心文件及职责

- `src/choice_agent/static/index.html`：定义顶部导航和右上角用户 ID / 主题入口。当前顶部直接展示 `首页`、`我的数据`、`Trace`、`评估`、`设置`，其中 `我的数据` 链接到 `#/diet/meals/personal`。
- `src/choice_agent/static/assets/js/app.js`：管理 hash router、导航激活、首页、设置页、demo 页、Trace 页、Evaluation 页和个人餐食页。当前路由包括 `/`、`/diet/chat`、`/demo`、`/demo/:id`、`/decisions/:id`、`/diet/meals/personal`、`/diet/meals/public`、`/admin/traces`、`/admin/evaluations`、`/settings`。`setActiveNav()` 将餐食页面映射到 `/data`。首页仍有 `Trace`、`评估` 和 `配置模型` 等显性开发入口。
- `src/choice_agent/static/assets/js/conversation.js`：管理统一对话式决策面板。已能展示目标、条件、推荐候选、候选事实、来源、详细对比和未回答问题。`renderPersonalMeals()` 仍是个人餐食 CRUD 页面，概念偏饮食 Agent。
- `src/choice_agent/static/assets/js/api.js`：封装前端请求。`DecisionApi` 当前只支持 `resolve`、`create`、`message`、`command` 和 `get`。没有历史列表、历史详情、最终选择记录或用户资料 API。
- `src/choice_agent/api/routes.py`：当前通用决策 API 包括创建、消息、命令和单条读取。饮食反馈 API 存在，但绑定饮食会话和餐食项，不适合作为通用最终选择记录。没有决策历史 collection API。
- `src/choice_agent/schemas.py`：`DecisionState` 已包含 `decision_id`、`session_id`、`domain`、`user_goal`、`constraints`、`criteria`、`candidates`、`unanswered_questions`、`assumptions`、`recommendation`、`revision`、`status`、`domain_state`、`owner_user_id`、`messages` 等字段。`Recommendation.primary_candidate_id` 和 `Candidate.id/name` 可用于推导“当前推荐”。当前没有通用 `outcome` / `final_choice` 字段，也没有历史摘要、历史详情或用户资料 Schema。
- `src/choice_agent/db_models.py`：`DecisionRecord` 包含 `id`、`session_id`、`domain`、`status`、`revision`、`state_json`、`created_at`、`updated_at`。没有独立 owner column，owner 当前只存在于 `state_json.owner_user_id`。没有用户资料表。
- `src/choice_agent/repositories/decision_repository.py`：当前有 `get()`、`get_for_user()`、`latest_for_session()`、`save()`。`get_for_user()` 会读取 `state_json.owner_user_id` 做权限过滤，并兼容 user 1 读取 owner 缺失的旧数据。没有按用户列出历史决策的方法。

## 当前实现逻辑

当前信息架构仍偏工程展示：用户打开首页可以开始决策，但顶部同时看到 `我的数据`、`Trace`、`评估`、`设置`；`我的数据` 实际进入个人餐食库；通用决策创建后，数据保存在 `DecisionRecord.state_json`；用户无法从产品侧查看过去所有通用决策；用户无法记录“最后实际选择”；长期偏好没有独立资料中心；Trace、Evaluation 和设置入口直接暴露在主导航。

## 关键调用链和数据流

```text
首页输入
  -> DecisionApi.create()
  -> POST /api/v1/decisions
  -> GenericDecisionOrchestrator
  -> DecisionRepository.save()
  -> DecisionRecord.state_json
  -> 前端进入决策详情或对话页
```

```text
前端 #/decisions/:id
  -> DecisionApi.get(id)
  -> GET /api/v1/decisions/{id}
  -> DecisionRepository.get_for_user(id, current_user_id)
  -> DecisionState
  -> app.js 渲染工作台详情
```

```text
前端 #/diet/meals/personal
  -> renderPersonalMeals()
  -> DietApi.listMeals({ sourceMode: PERSONAL })
  -> 饮食餐食仓储按 owner_user_id 过滤
  -> 前端展示餐食 CRUD
```

## 已有可复用能力

`DecisionRecord.state_json` 已持久化完整 `DecisionState`，历史详情第一版可以不新建复杂快照表。`DecisionState.user_goal`、`constraints`、`criteria`、`candidates`、`recommendation`、`unanswered_questions`、`assumptions` 已覆盖历史详情的大部分字段。`Recommendation.primary_candidate_id` 可映射候选名，用于列表中的“当前推荐”。`owner_user_id` 和前端用户 ID 请求头机制可复用做用户隔离。当前 settings 页、Trace 页和 Evaluation 页可以保留，主要修改入口和分组。`Base.metadata.create_all()` 支持新增表自动创建，适合新增用户资料表；但不适合安全修改已有表字段。

## 潜在问题和隐患

- `DecisionRecord` 没有独立 `owner_user_id` column。第一版如果按 `state_json.owner_user_id` 在 Python 层过滤，数据量大时性能有限。短期可限制列表数量，后续再补 indexed owner 迁移。
- 当前只保存最新 `DecisionState`，没有每一轮 revision 的历史快照。第一版历史详情展示的是该决策记录的当前保存状态，不做 revision 级时光回放。
- 用户最后实际选择是通用决策闭环数据，不适合复用饮食 `FeedbackRecord`。更合适的是扩展 `DecisionState` 增加通用 `outcome` 字段。
- 长期偏好第一版不应隐式影响推荐，避免引入难以解释的个性化行为和测试风险。
- Developer Mode 只能降低普通用户视觉复杂度，不能作为安全边界。
- 当前无登录体系依赖右上角用户 ID 进行本地多用户测试。它应移入开发者工具或 Debug，但不能删除。

## 与需求相关的约束

必须保留 Trace、Evaluation、API / Model 设置和 Debug 能力；必须保持旧路由兼容；新增字段必须提供默认值，保证旧 `state_json` 可以读取；新增 API 应复用现有用户 ID 请求头；不应在 API response 或 Debug 页面中泄露 API Key 明文；`CHANGELOG.md` 需要记录用户可感知的新功能、API 或数据结构变化。

## 尚未确定、需要 Plan 阶段决策的问题

- 历史列表 API 是独立为 `/api/v1/decision-history`，还是扩展 `/api/v1/decisions` 的 GET collection。
- 最终选择记录字段是直接放在 `DecisionState.outcome`，还是新建独立 outcome 表。
- 我的资料第一版是 JSON 表，还是建立更细的结构化偏好表。
- 开发者工具使用右上角菜单、Developer Mode 开关，还是独立页面。
- 个人餐食库在新信息架构中的入口位置。