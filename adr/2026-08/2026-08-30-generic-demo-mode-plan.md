# 通用演示模式 Plan

## 目标和成功标准

目标：让 `choice-agent-v2` 新版也具备类似旧版 `choice-agent` 的通用 demo 展示能力。用户在首页选择或输入旅行、Offer、学习、购物等非饮食决策问题时，可以进入一个通用决策演示工作台，看到目标、约束、偏好权重、候选比较、证据标注、推荐结论和演示数据来源。

成功标准：

- 首页非饮食示例不再只显示“场景接入中”，而是可以进入通用 demo。
- 通用 demo 至少支持旅行、职业 Offer、学习路径、购物四类 fixture。
- 无 API Key、无网络、无数据库额外配置时 demo 可稳定运行。
- 页面明确标注“演示数据 / 非实时”，不承诺真实搜索或后端 Agent 已接入。
- 饮食问题仍进入现有真实饮食聊天链路，不被 demo fixture 替代。
- 现有饮食 API、餐食库、Trace、评估和测试不回归。

## 方案选择

采用 Research 中的方案 A：纯前端通用 Demo 工作台。

本阶段不做：不新增通用后端 Orchestrator；不把 `DecisionEngine` 泛化为所有领域的评分引擎；不新增数据库表或迁移；不把旅行、职业、学习、购物伪装成真实在线搜索；不引入新前端框架或构建链。

这样可以用最小风险恢复通用 demo 展示，同时保留后续通用后端架构空间。

## 架构和逻辑设计

新增前端 demo 层：

```text
static app
  -> 首页 submitGeneralDecision()
    -> 饮食类：沿用现有 /diet/chat 真实链路
    -> demo 类：createDemoDecision(prompt)
      -> demo fixtures
      -> demo ranking
      -> localStorage
      -> #/demo/decision/:id
        -> demo workbench
        -> 调整权重 / 排除候选 / 生成结论
```

### Demo 数据模型

前端新增轻量 demo state，字段贴近旧版通用 `DecisionState`：`id`、`status`、`domain`、`candidateState`、`nextAction`、`goal`、`constraints`、`criteria`、`unansweredQuestions`、`candidates`、`recommendation`、`assumptions`、`trace`、`revision`、`createdAt`、`updatedAt`。

不要求与后端 Pydantic `DecisionState` 完全同名，因为本阶段不写入后端 `DecisionRecord`。

### Demo 场景识别

在首页提交时：

- 饮食关键词继续走 `isDietPrompt()`。
- 旅行关键词匹配旅行 fixture。
- Offer / 公司 / 工作 / 职业关键词匹配职业 fixture。
- 学 AI / 学习路径 / 入门 / 课程关键词匹配学习 fixture。
- 电脑 / 笔记本 / 买 / 购物关键词匹配购物 fixture。
- 若用户输入包含 2 个以上明显候选名，可进入 generic fixture。
- 其余场景进入 generic demo，并标注“仅演示结构化比较”。

### Demo 排序

新增通用前端排序函数：根据每个 criterion 的 `weight` 和 candidate attributes 计算加权分；支持 `higher_better`、`lower_better`、`target` 三种方向；已排除候选不参与主推荐排序，但仍可显示为已排除；分数稳定可复现，相同分数按候选原始顺序或 id 排序。

### Demo 推荐解释

新增前端解释函数：取排序第一作为主推荐；取排序第二作为替代项；从主推荐 evidence 中抽取 1-2 条作为 reasons；若 evidence 不足，则用最高权重 criterion 和 attributes 生成“基于演示属性”的解释；recommendation 明确带上 demo 语义，不暗示实时搜索。

### Demo 工作台 UI

新增 hash 路由：

- `#/demo`：默认打开旅行 fixture 或首页最新创建的 demo。
- `#/demo/decision/:id`：打开指定 demo decision。

工作台布局：顶部显示 `Choice Agent Demo`、领域标签、`演示数据 · 非实时` 标签、返回首页；内容展示目标、约束、开放问题、假设、候选比较、偏好权重、证据摘要和结论区。

## 关键流程

首页示例进入 demo：用户点击旅行示例并提交 → 识别为 `travel` → 创建 `travelFixture` 副本 → 写入 `localStorage` → 导航 `#/demo/decision/<id>` → 工作台展示旅行通用决策。

自由输入进入 demo：用户输入“我在 A 公司和 B 公司 Offer 之间纠结” → 识别为 `career` → 基于职业 fixture 创建 demo state → 如果能抽取候选名，则替换 fixture 中候选名称 → 进入工作台。

饮食输入保持真实链路：用户输入“今晚不知道吃什么” → `isDietPrompt()` 命中 → 沿用 `prepareChatFromHome(prompt)` → 进入 `#/diet/chat` → 调用真实 `/api/v1/diet/chat`。

权重调整：用户拖动 criterion slider → 更新 demo state criteria weight → `revision + 1` → 清空旧 recommendation → 重新计算排名 → 保存 localStorage → UI 即时更新。

生成结论：用户点击“生成结论” → 根据当前排序和 evidence 生成 recommendation → `status = decided` → `revision + 1` → 保存 localStorage → 展示结论。

## 受影响文件

### `src/choice_agent/static/assets/js/demo.js`（新增）

定义 demo fixtures、领域识别、候选名抽取、localStorage 存取、通用排序和解释函数。如当前静态页面引入新 JS 文件不方便，也可以先放入 `app.js`，但优先新增 `demo.js` 保持边界清楚。

### `src/choice_agent/static/index.html`

引入 `assets/js/demo.js`，确保在 `app.js` 之前加载。

### `src/choice_agent/static/assets/js/app.js`

扩展 `state`，增加 demo 当前状态；扩展 `render()` 支持 `#/demo` 和 `#/demo/decision/:id`；修改首页示例元数据；修改 `submitGeneralDecision()`，让非饮食通用问题进入 demo，饮食继续真实链路；新增 `renderDemoWorkbench()`、demo 权重调整、排除候选、生成结论、返回首页等事件处理。

### `src/choice_agent/static/assets/css/app.css`

增加 demo workbench 必要样式，复用现有 `.card`、`.section`、`.badge`、`.grid`、`.button-row` 等类，新增样式控制权重 slider、候选排名、证据摘要、结论区域和排除状态。

### `README.md`

增加 Demo Mode 说明：通用 demo 使用本地 fixture；饮食场景使用真实规则 Agent；非实时数据标识；无 API Key / 无网络可运行。

### `.env.example`

第一版不新增 `CHOICE_AGENT_DEMO_MODE`，避免出现“配置存在但后端不消费”的假能力。只在 README 和 UI 中说明通用 demo 为静态 fixture。

### `tests/`

不新增 JS 测试依赖。保留并运行现有 `python -m pytest`，确认后端不回归；运行 `python -m compileall -q src scripts`。如实现中新增可由 Python 静态检查验证的关键标识，可补一个轻量测试，但不强制。

## 兼容性和破坏性变更

- 饮食 API 不变。
- 饮食聊天、餐食库、Trace、评估路径不变。
- 首页饮食问题行为不变。
- 新增 demo 路由，不影响旧 hash 路由。
- 非饮食首页提交行为会从“只提示接入中”变为“进入通用 demo”。这是用户可感知增强，但必须通过文案说明是演示数据。
- 不新增依赖，不修改构建/部署方式。

## 风险和边界情况

- 用户可能误解非饮食 demo 为真实 Agent 能力：通过 `演示数据 · 非实时`、说明文案和 evidence source 解决。
- 前端 `app.js` 已较大，继续扩展会增加维护成本：用 `demo.js` 分离纯 demo 数据和算法。
- 纯前端 demo 与后端 `DecisionState` 字段不完全一致：本阶段不跨边界持久化，避免 schema 适配复杂化。
- Generic 输入的候选抽取可能不准：只做保守抽取，抽不到则使用“方案 A / 方案 B”。
- 当前没有前端自动化测试：需要通过本地浏览器或静态页面手动验证主要交互，并跑后端测试确保不回归。

## 验证方案

自动验证：

- `python -m compileall -q src scripts`
- `python -m pytest`

手动行为验证：

- 打开首页。
- 点击旅行示例，提交后进入通用 demo 工作台。
- 点击 Offer 示例，进入职业 demo。
- 点击学习示例，进入学习 demo。
- 点击购物示例或输入电脑选择问题，进入购物 demo。
- 输入饮食问题，仍进入 `#/diet/chat` 并调用真实饮食链路。
- 在 demo 工作台调整权重，候选排名即时变化且 revision 增加。
- 排除候选后主推荐不再选择该候选。
- 生成结论后展示推荐理由和替代项。
- 刷新页面后 demo state 能从 localStorage 恢复。
- Trace、评估、餐食库页面仍可打开。

Diff 检查：确认只修改 demo 相关前端、README、CHANGELOG 和 ADR；确认没有临时日志、调试输出或无意义格式化。

CHANGELOG：需要在 `CHANGELOG.md` 的 `2026-08-30` 下追加一条用户可感知变化：新增通用演示模式/工作台。

## 技术折衷

- 第一版选择纯前端 demo，是为了快速恢复通用展示能力，不把需求扩大为通用后端架构重构。
- 不新增 `CHOICE_AGENT_DEMO_MODE`，避免出现“配置存在但后端不消费”的假能力。演示模式由 UI 和 fixture 明确表达。
- Demo fixture 可借鉴旧版内容，但在 V2 中以静态 JS 结构重新实现，避免引入 TypeScript/Next.js 源码依赖。
- 饮食继续真实后端规则链路，保留 V2 当前最强的实际业务闭环。

## Todo

- [ ] 新增前端 demo fixture、领域识别、localStorage、排序和解释工具。
- [ ] 在静态页面引入 demo 工具脚本。
- [ ] 扩展首页示例和提交逻辑，让非饮食通用问题进入 demo 工作台，饮食问题保持真实链路。
- [ ] 新增通用 demo 工作台渲染和交互：权重调整、排除候选、生成结论、返回首页。
- [ ] 补充 demo 工作台样式并保持现有主题兼容。
- [ ] 更新 README，说明通用 demo 与饮食真实规则链路的区别。
- [ ] 更新 CHANGELOG。
- [ ] 执行 diff 检查、compileall、pytest 和手动页面验证。