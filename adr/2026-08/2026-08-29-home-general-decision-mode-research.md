# 首页通用决策形态与饮食模式入口 Research

## 当前需求和研究范围

用户反馈 Choice Agent V2 当前看上去仍偏向饮食推荐，希望：

- 首页默认进入通用决策形态；
- 当前饮食能力作为一个可点击进入的模式保留；
- 找到合适位置增加饮食模式入口；
- 不破坏现有饮食聊天、餐食库、Trace 和评估能力。

本次研究范围限定在静态前端首页、导航、默认路由和模式入口。后端饮食 API、通用决策引擎、数据库结构和多 Agent 编排暂不纳入实现范围。

## 相关历史记录

- `adr/2026-08/2026-08-29-diet-agent-python-migration-research.md`
  - 记录了 V2 的整体定位：以 diet-agent 为功能基线，同时吸收 choice-agent 的通用决策思想。
  - 明确饮食是第一个完整领域，而不是系统唯一定位。
- `adr/2026-08/2026-08-29-diet-agent-python-migration-plan.md`
  - 计划中包含“通用决策模型”“饮食领域插件”“未来新增领域时不修改决策内核”等设计。
  - 实施结果完成了饮食完整迁移，但前端首页仍以饮食为默认呈现。

本次更适合新建独立 Research / Plan，而不是改写已完成的迁移 ADR。

## 核心文件及职责

### `src/choice_agent/static/index.html`

静态页面壳层，负责：

- 页面标题；
- 顶部品牌区；
- 主导航；
- 用户 ID 输入；
- 挂载 `app.css`、`api.js` 和 `app.js`。

当前标题和品牌副标题为饮食语义：

- `<title>Choice Agent V2 · 饮食决策</title>`
- `<small>饮食决策 · 首个领域</small>`

顶部品牌链接指向 `#/diet`，主导航也把饮食聊天、个人餐食、公共餐食作为一级入口。

### `src/choice_agent/static/assets/js/app.js`

静态应用核心逻辑，负责：

- hash 路由解析；
- 页面渲染；
- 首页数据加载；
- 饮食聊天；
- 个人餐食和公共餐食管理；
- Trace 与评估页面；
- 点击和表单事件绑定。

当前默认路由：

```js
function currentRoute() {
    return (location.hash || "#/diet").slice(1).split("?")[0] || "/diet";
}
```

启动时若没有 hash，会执行：

```js
if (!location.hash) {
    navigate("/diet");
} else {
    render();
}
```

`render()` 中 `"/diet"` 直接渲染 `renderHome()`。因此首页和饮食模式目前是同一个路由。

### `src/choice_agent/static/assets/css/app.css`

提供页面布局与组件样式：

- `.hero` / `.hero-panel` / `.stats` 可用于首页；
- `.grid.two` / `.grid.three` 可用于模式卡片；
- `.card` / `.section` / `.stat-card` 可复用；
- `.btn`、`.badge`、`.chips` 等控件可复用。

当前视觉主题偏绿色、轻食感较强。若只做入口和文案调整，可先不改整体配色；但如果要进一步弱化饮食联想，后续可单独规划视觉主题调整。

### `src/choice_agent/static/assets/js/api.js`

饮食 API 客户端，当前使用：

- `const API_BASE = "/api/v1/diet";`
- `const USER_ID_KEY = "diet.userId";`

首页统计调用 `DietApi.listPersonalMeals()` 和 `DietApi.listPublicMeals()`。如果首页改为通用决策形态，饮食统计仍可作为“饮食模式卡片”的状态信息保留，但不应成为主 Hero 的核心卖点。

## 关键调用链和数据流

### 默认进入首页

浏览器打开 `/`
→ `index.html`
→ 加载 `app.js`
→ 无 hash 时 `navigate("/diet")`
→ hash 变为 `#/diet`
→ `render()`
→ `renderHome()`
→ `loadHomeStats()`
→ 调用饮食餐食库 API
→ 回写首页统计。

### 进入饮食聊天

点击 `#/diet/chat`
→ `renderChat()`
→ 若首次发送消息则 `DietApi.createSession()`
→ `DietApi.chat()`
→ 后端 `POST /api/v1/diet/chat`
→ 返回推荐、澄清问题、Trace 等。

### 切换饮食数据来源

饮食聊天页通过 `data-action="set-source"` 修改：

- `state.chat.sourceMode = "PERSONAL"`
- `state.chat.sourceMode = "PUBLIC"`

这里的“模式”是饮食推荐内部的数据源模式，不是用户当前提出的“饮食模式入口”。本次需要避免混淆：入口应表达为“饮食决策模式”或“吃什么模式”，而不是复用 sourceMode 概念。

## 当前实现逻辑

- 应用默认首页与饮食模式共用 `#/diet`。
- 首页 Hero 标题是“用更轻松的方式决定今天吃什么”。
- 首页 badge 是“多 Agent 饮食推荐”。
- 首页主按钮是“开始聊天推荐”“管理个人餐食”“查看 Trace”。
- 首页统计展示个人餐食、公共餐食、当前用户。
- 顶部导航把饮食相关页面直接作为一级导航。
- 未知路由会跳回 `"/diet"`。

因此用户感知上，Choice Agent V2 更像 diet-agent 的新 UI，而不是通用决策系统。

## 已有可复用能力

- Hash 路由可低成本新增 `"/"` 或 `"/home"` 路由。
- `featureCard()`、`statCard()`、`.hero`、`.grid.three` 等可以复用来展示模式入口。
- 当前饮食能力已经完整挂在 `#/diet/chat`、`#/diet/meals/personal`、`#/diet/meals/public`。
- 通用 DecisionState API 已存在 `GET /api/v1/decisions/{decision_id}`，但没有通用决策创建或交互前端。首页只能展示通用决策系统定位和现有领域入口，不能伪装已有完整通用决策工作台。

## 潜在问题和隐患

- 如果直接把 `#/diet` 文案改成通用首页，会导致饮食入口和首页路由语义混在一起。
- 如果把顶部饮食子页面全部保留为一级导航，首页即使改了 Hero，也仍会显得以饮食为中心。
- 如果新增 `#/home` 但品牌和无 hash 默认仍指向 `#/diet`，用户首次进入仍看不到通用形态。
- 如果首页继续强依赖饮食统计加载，网络或后端错误会影响通用首页观感。
- 当前 CSS 使用绿色主题和较大的圆角，仍有轻食/健康应用联想；本次若只调结构和文案，视觉联想可能只会部分改善。

## 约束

- 不改后端 API、数据库和多 Agent 编排。
- 保留现有饮食页面路径，避免破坏已有书签和调试流程。
- 不新增依赖。
- 不引入尚不存在的通用决策聊天功能。
- 首页应诚实表达当前能力：通用决策系统底座已经存在，饮食是当前可用的完整模式。
- 修改范围应集中在 `index.html`、`app.js`、必要的 `app.css` 和 `CHANGELOG.md`。

## Plan 阶段需要决策的问题

- 默认首页路由使用 `"/"` 还是 `"/home"`。
- `#/diet` 是否保留为饮食模式介绍页，还是直接重定向到 `#/diet/chat`。
- 顶部导航是否把饮食子页面收拢，只保留“饮食模式”一级入口。
- 首页是否继续展示饮食统计，若展示，应弱化为模式卡片的辅助信息。
- 是否对视觉主题做轻量调整，还是只做文案和信息架构调整。