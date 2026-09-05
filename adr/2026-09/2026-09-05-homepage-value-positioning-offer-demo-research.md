# 首页价值定位与 Offer 旗舰示例 Research

## 当前需求和研究范围

本次研究聚焦 Choice Agent 首页第一屏：强化相对普通聊天式 AI 的差异化价值，并把 Offer 选择提升为旗舰案例。目标是说明 Choice Agent 如何把模糊纠结转化为可检查、可修改、可解释的决策过程。

范围包括首页 Hero、输入提示、示例层级、价值说明、现有交互链路及响应式样式。后端 API、领域识别、决策状态、数据库、对话面板和模型配置能力不在改造范围内。

## ADR / 历史方案检索

已检索相关历史记录：

- `2026-08-29-home-general-decision-mode-*`：完成从饮食首页到通用决策首页的第一阶段迁移。
- `2026-08-30-unified-choice-entry-*`：统一用户入口并将饮食能力下沉到领域流程。
- `2026-08-30-generic-demo-mode-*`：建立旅行、Offer、学习和购物 Demo，但示例仍同权展示。
- `2026-09-04-general-conversation-panel-*`：把通用选择接入对话与可编辑结果侧栏。
- `2026-09-04-conversation-decision-assistance-*`：增强推荐依据、顾虑、代价、条件变化和假设比较。

这些记录均已完成。当前需求是上述能力完成后的首页定位升级，追加旧文件会混淆历史状态，因此新建本组 Research / Plan。

## 核心文件及职责

### `src/choice_agent/static/assets/js/app.js`

`renderGeneralHome()` 生成 Hero、模式提示、输入框、示例、流程卡和开发者入口。当前副标题仍以步骤为主；Hero 展示模型/演示状态与“配置 API”；placeholder 是饮食问题；五个示例同权；右侧出现“服务端决策工作台”；下方内容与右侧重复。

`submitGeneralDecision()` 调用 `conversation.startGeneral()`。`general-example` 只把示例写入输入框并聚焦，用户可编辑后提交。本次可以复用这条链路。

### `src/choice_agent/static/assets/js/conversation.js`

`startGeneral()` 先识别领域，再创建通用决策或进入饮食流程。通用侧栏已支持编辑目标、候选、偏好和条件，显示关键追问、当前倾向、推荐依据、需要接受的代价、本轮变化与不修改当前选择的假设比较。

### `src/choice_agent/decision/assistance.py`

决策辅助生成 `reasons`、`tradeoffs`、`question`、`changes` 和 `hypothetical`。依据不足时会追问或保留结论。因此首页可表达目标价值，但不应承诺首次回复一定给出确定答案。

### `src/choice_agent/static/assets/css/app.css`

现有 Hero、表单、示例按钮、卡片和响应式断点可复用。当前没有旗舰与次级案例的视觉层级，需要少量首页专用样式。

### `src/choice_agent/static/index.html`

标题与品牌已经是通用决策定位。本次聚焦 Hero 主体，暂不调整全局导航。

### `CHANGELOG.md`

首页定位和旗舰示例属于用户可感知变化，应追加到已有的 `2026-09-05` 标题下。

## 关键调用链

首页：进入 `#/` → `render()` → `renderGeneralHome()`。

Offer 示例：点击旗舰示例 → `general-example` → 问题写入输入框 → 用户编辑并提交 → `submitGeneralDecision()` → `conversation.startGeneral()`。

移除首页模式 banner 不改变设置页、模型配置持久化或请求行为。

## 当前差距

1. 首页讲了步骤，但没明确回答为什么不用一次普通聊天回答。
2. 工程状态和 API 配置进入 Hero，削弱用户价值表达。
3. 饮食 placeholder 与通用定位冲突。
4. 所有示例同权，不能展示复杂决策优势。
5. 页面没有突出推荐依据、代价和结论变化条件。

## 已有可复用能力

- 首页表单、状态、校验和 loading。
- `general-example` 示例填充事件。
- Offer 对话、条件编辑、取舍解释和假设分析。
- 现有响应式布局和独立设置页。

## 潜在问题和隐患

- “不会立即给答案”不能写成绝对承诺；应表述为“必要时先补齐真正影响结论的信息”。
- Offer 成为旗舰后仍需保留跨领域示例。
- 长副标题和旗舰卡增加首屏高度，需要删除重复卡和工程 banner。
- 次级按钮可显示短标签，但 `data-example` 应保留完整问题。
- 顶部开发者导航若要产品化，应单独规划，本次不顺带修改。

## 约束

- 不改后端 API、领域识别、数据库或核心决策结构。
- 不新增依赖。
- 不改变表单提交与示例进入对话的行为。
- 不删除设置、Trace 或评估能力。
- 修改集中在 `app.js`、必要的 `app.css`、ADR 和 `CHANGELOG.md`。

## Plan 阶段需要决策的问题

- Hero 文案如何覆盖输入门槛、澄清和输出价值。
- Offer 旗舰示例的层级和交互形式。
- 右侧展示系统步骤还是用户收益。
- 模型状态是否完全移出首页。
- 次级示例显示完整问题还是短标签。
