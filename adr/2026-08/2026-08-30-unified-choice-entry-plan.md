# 统一 Choice Agent 用户入口 Plan

## 目标和成功标准

目标：

- 用户侧只看到一个 Choice Agent 决策入口。
- 首页不再把“通用决策”和“饮食模式”表达成两套并列产品。
- 饮食问题从首页输入后自动进入现有饮食聊天页，并自动发起第一轮。
- 现有 Diet Chat、餐食库、Trace、Evaluation 基本不重写。
- `/diet/*` 路由继续保留兼容。
- 不改后端核心架构、不引入 `DecisionApi`、不实现真正后端 Domain Router。

成功标准：

- 顶部用户侧导航不再出现“饮食模式”。
- 首页只保留“开始决策”主操作，不再有并列的“进入饮食模式”按钮。
- 首页示例混合 Offer、学习路线、出行、饮食等场景；点击示例后仍走统一输入框。
- 输入饮食类问题后，页面直接进入 `#/diet/chat`，聊天页显示用户原始问题并自动请求现有 `DietApi.chat()`。
- 从首页带 prompt 进入聊天页时，不重复显示原有欢迎语。
- 聊天页标题从“聊天推荐”改为“决策助手”，并用小标签展示“已识别：饮食决策”。
- `/diet` 不再承担第二个产品首页角色，作为兼容路由跳转到 `#/diet/chat`。
- 餐食库作为辅助能力，通过“我的数据”或聊天页辅助入口进入。
- Trace 和评估继续可访问，作为开发者入口保留。
- `#/diet/chat`、`#/diet/meals/personal`、`#/diet/meals/public`、`#/admin/traces`、`#/admin/evaluations` 原路径继续可用。

## 本轮范围

纳入：

- P0：统一首页定位。
- P0：删除首页“进入饮食模式”并列按钮。
- P0：修改顶部导航，用户侧不再出现“饮食模式”。
- P0：改造 `submitGeneralDecision()`，饮食类问题直达聊天并自动发起第一轮。
- P0：首页示例统一走同一决策入口。
- P0：弱化 `/diet` 独立首页。
- P0：统一聊天页标题。
- P1：将饮食 Domain 表达为上下文状态标签，而不是用户可见模式。
- P1：餐食库降级为辅助能力，放入“我的数据”入口。
- P1：优化从首页带 prompt 进入时的聊天初始状态。
- P1：弱化用户可感知的 `PERSONAL / PUBLIC` 模式感，保留高级切换但不作为主标题控件。
- P1：调整“使用提示”文案。
- P1：首页统计卡和 Feature Card 重做。

暂不纳入：

- P2：新增统一后端 Domain 状态。
- P2：新增 `/decision` 或 `/chat` 路由并迁移所有内部链接。
- P2：抽 `DecisionApi`。
- P2：后端 Intent / Domain Router。
- P2：统一 General 与 Diet 的后端决策状态。

## 设计方案

采用“产品入口统一、底层路由兼容”的方案。

用户层：

```text
首页
  -> 输入选择问题
  -> 前端轻量识别饮食场景
  -> 决策助手
  -> 追问 / 推荐
```

代码层：

```text
#/
  -> submitGeneralDecision()
  -> 检测为 Diet
  -> state.chat.pendingPrompt = prompt
  -> #/diet/chat
  -> 复用 DietApi.createSession + DietApi.chat
```

非饮食问题：

- 保持在首页。
- 展示“这个场景还在接入中；现在可以先把目标、约束和候选整理出来，饮食场景已可直接进入对话”这类诚实提示。
- 不创建后端数据，不调用不存在的通用 API。

## 关键流程

### 首页提交饮食问题

1. 用户在首页输入 `今晚不知道吃什么，想要清淡一点`。
2. `submitGeneralDecision()` 保存原始 prompt。
3. 前端通过现有关键词增强版判断为饮食场景。
4. 设置 `state.chat.pendingPrompt = prompt`、`state.chat.domain = "DIET"`，并清理当前聊天会话和消息，避免上一轮上下文污染。
5. `navigate("/diet/chat")`。
6. `renderChat()` 检测到 pending prompt，渲染用户问题和“正在分析...”状态。
7. 调用抽出的 `sendChatMessage(prompt, { source: "home" })`。
8. 成功后显示澄清问题或推荐。
9. 失败时保留用户消息，并显示失败提示。

### 首页提交非饮食问题

1. 用户输入 Offer / 学习路线 / 旅行等问题。
2. 前端判断不属于当前完整饮食场景。
3. 首页展示轻量提示，不跳转。
4. 示例和输入仍保留，避免用户输入丢失。

### `/diet` 兼容路由

本轮采用直接重定向：

```js
} else if (route === "/diet") {
    navigate("/diet/chat");
}
```

理由：用户不再需要第二个产品首页；旧书签 `#/diet` 仍可用；饮食说明和数据入口可以放进聊天页侧栏。

### 我的数据

顶部导航改为：

- 首页；
- 我的数据；
- Trace；
- 评估。

其中：“我的数据”指向 `#/diet/meals/personal`；公共餐食保留在个人餐食页、聊天页侧栏或页面内按钮中；`setActiveNav()` 把 `/diet/meals/*` 归组到“我的数据”。

### 聊天页

标题和状态：标题改为 `决策助手`；会话说明保持自然；增加小标签 `已识别：饮食决策`。

数据源：默认仍使用 `PERSONAL`，避免改后端；顶部不再突出 `个人库 / 公共库` 两个模式按钮；侧栏展示当前数据来源说明和辅助切换，文案使用 `优先用我的数据` / `使用公共数据`，不出现 `PERSONAL / PUBLIC`。

## 受影响文件列表

### `src/choice_agent/static/index.html`

计划修改：

- 顶部导航移除 `饮食模式`。
- 新增 `我的数据`，指向 `#/diet/meals/personal`。
- `Trace`、`评估` 继续保留为开发者入口。
- title 和品牌副标题保持现状。

### `src/choice_agent/static/assets/js/app.js`

计划修改：

- 扩展 `state.chat`：`domain: "DIET"`、`pendingPrompt: ""`、`autoSending: false`。
- 新增 `isDietPrompt(prompt)`，集中当前关键词识别，保留轻量前端判断。
- 新增 `startDecisionFromHome(prompt)`：判断饮食场景、准备聊天状态、导航到 `#/diet/chat`。
- 抽出 `sendChatMessage(message)`，让 `submitChat()` 和首页自动发送复用同一请求逻辑。
- `renderChat()`：标题改为 `决策助手`；展示 `已识别：饮食决策` 状态标签；从首页 pending prompt 进入时不显示原欢迎语；渲染后触发一次自动发送，避免重复触发。
- `resetChat()` 更新欢迎语，避免“餐食库 / 公共库推荐今天吃什么”成为首屏主语。
- `submitGeneralDecision()`：空输入仍提示补充问题；饮食问题不再显示“进入饮食模式”，而是直接进入聊天；非饮食问题显示当前可接入能力提示。
- `renderGeneralHome()`：badge 从 `通用决策入口` 改为更产品化的 `Choice Agent` 或 `决策入口`；删除 `进入饮食模式` 并列按钮；文案不再强调“当前完整可用的领域模式是饮食决策”；右侧统计改为“描述选择 / 澄清条件 / 比较取舍 / 当前增强场景”等；下方 Feature Card 改为用户流程：`描述选择`、`澄清条件`、`比较取舍`；Developer 入口单独放一行小区域：Trace / 评估。
- `/diet` 路由改为重定向到 `/diet/chat`。
- `setActiveNav()`：`/diet/meals/*` 高亮到“我的数据”；`/diet/chat` 推荐高亮首页，因为它是统一入口流出的主决策体验。
- `loadHomeStats()`：不再服务首页 Hero；只在数据页或需要侧栏数据说明时调用。

### `src/choice_agent/static/assets/css/app.css`

计划修改：

- 调整首页统计卡和 Feature Card 的少量样式，支持流程表达。
- 增加或复用状态标签样式，如 `.domain-label`、`.developer-links`、`.source-panel`。
- 调整聊天页侧栏数据源切换样式，弱化模式感。
- 保持响应式规则，重点检查按钮和长文本不溢出。

### `CHANGELOG.md`

计划修改：

- 在 `2026-08-30` 下记录用户可感知变化：统一首页入口、饮食问题从首页直达决策助手、餐食库改为辅助数据入口。

## 兼容性和破坏性变更评估

- 后端 API 不变。
- 数据库不变。
- `DietApi` 命名不变。
- `/diet/chat`、`/diet/meals/personal`、`/diet/meals/public` 继续可直接访问。
- `#/diet` 会从原独立饮食首页变成兼容跳转，这是用户流程变化，但不删除路径。
- 顶部导航不再直达 `#/diet`，符合本轮目标。
- 个人库 / 公共库切换仍保留，但不作为主流程入口。
- 自动发送首页 prompt 会创建真实饮食 session，这是预期行为；需要防重复发送。

## 风险和边界情况

- 前端关键词识别可能误判，例如“饭局地点怎么选”可能被识别为饮食；本轮可接受，但文案应避免称为最终 Domain Router。
- 自动发送可能因后端服务未启动失败；需要把用户原文保留在聊天中。
- 如果用户从已有会话返回首页再提交新问题，需要清理旧 session，避免上下文串线。
- 如果用户直接打开 `#/diet/chat`，仍应显示正常初始欢迎语。
- 如果 `renderChat()` 每次渲染都触发自动发送，会造成重复请求；必须用状态锁或清空 pending。
- 如果 `set-source` 调用 `resetChat()`，需要避免清掉正在自动发送的首页 prompt。
- 首页非饮食提示不能让用户误解 Offer / 学习路线已经能完整执行。
- 移除“饮食模式”导航后，开发者可能少一个快捷入口；旧路由和聊天入口仍保留。

## 验证方案

静态检查：

- 重读 `index.html`、`app.js`、`app.css` 关键片段，确认修改真实落盘。
- 搜索确认首页不再出现 `进入饮食模式`。
- 搜索确认顶部导航不再出现 `饮食模式`。
- 搜索确认用户可见区域不再出现 `PERSONAL 模式` / `PUBLIC 模式`。
- 搜索确认 `submitGeneralDecision()` 饮食分支会进入聊天而不是只设置 notice。

自动验证：

- `python -m compileall -q src scripts`
- `python -m pytest`
- 如项目具备 JS 语法检查，执行可用的前端静态检查；否则使用浏览器加载验证 JS。

行为验证：

- 启动本地服务。
- 打开 `/`，确认首页是唯一决策入口，只有“开始决策”主操作。
- 点击饮食示例，确认填入统一输入框。
- 提交饮食问题，确认进入 `#/diet/chat` 并自动发起第一轮。
- 直接打开 `#/diet`，确认兼容跳转到聊天页。
- 打开 `#/diet/chat`，确认直接访问时有正常初始状态。
- 打开 `#/diet/meals/personal` 和 `#/diet/meals/public`，确认餐食库仍可用。
- 打开 Trace 和评估，确认开发者入口仍可用。
- 窄屏检查导航、首页和聊天侧栏不出现明显重叠。

## 技术折衷

- 本轮继续使用 `DietApi` 和 `/diet/chat`，用前端入口统一解决产品割裂，避免扩大到后端重构。
- 饮食识别仍用关键词，作为过渡方案；真正 Domain Router 放到后续大阶段。
- `/diet` 用跳转而不是删除，保护旧链接。
- 数据源切换不删除，只从主标题区域下沉到侧栏辅助操作。
- 非饮食问题不进入伪聊天，避免制造假能力。

## Todo

- [x] 调整顶部导航：移除“饮食模式”，新增“我的数据”，保留 Trace 和评估。
- [x] 重做首页文案和按钮：统一为 Choice Agent 唯一入口，只保留“开始决策”主操作。
- [x] 重做首页统计和 Feature Card：展示决策流程、已增强场景和开发者入口分层。
- [x] 抽出聊天发送逻辑，让表单提交和首页自动发送复用同一请求路径。
- [x] 改造 `submitGeneralDecision()`：饮食类 prompt 直接进入聊天并自动发起第一轮。
- [x] 优化聊天页标题、领域状态标签和从首页带 prompt 进入时的初始状态。
- [x] 弱化用户可见的个人库 / 公共库模式感，改为数据源辅助说明和切换。
- [x] 将 `/diet` 降级为兼容跳转到 `/diet/chat`。
- [x] 调整必要 CSS，保证首页、聊天页和数据源辅助区响应式稳定。
- [x] 更新 `CHANGELOG.md`。
- [x] 执行 diff 检查、自动验证和可行的页面行为验证。浏览器控制因本地启动器错误不可用，已用 HTTP 静态资源检查、饮食 API 请求和前端静态断言替代。