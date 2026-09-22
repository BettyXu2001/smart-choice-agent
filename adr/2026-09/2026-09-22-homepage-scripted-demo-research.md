# 首页固定剧本 Demo Research

## 当前需求和研究范围

本次研究聚焦首页预设示例和 #/demo 演示入口。目标是让 Demo 不依赖真实 LLM、后端 Orchestrator 或搜索服务，以固定 fixture 和确定性状态机稳定完成至少一轮：分析候选差异、提出澄清问题、用户点击固定回答、更新偏好并展示推荐结果。

真实自由输入、领域识别、饮食聊天、通用决策 API、历史决策和后端数据结构不在本次改造范围内。本阶段只研究与规划，不修改产品代码。

## ADR / 历史方案检索

已按首页、Demo、fixture、状态机、多轮澄清、推荐结果和流程可视化检索 adr/、src/choice_agent/static/、tests/、docs/ 和 CHANGELOG.md。

直接相关记录：

- 2026-09-05-homepage-value-positioning-offer-demo-research.md / plan.md：建立首页旗舰示例与普通示例层级，示例点击仅填充输入框并沿用真实提交链路；当前需求改变了预设示例的交互边界。
- 2026-09-04-general-conversation-panel-research.md / plan.md：建立真实自由输入的通用对话与 Decision Canvas。本次必须与该链路隔离，不能用固定剧本替换真实会话。
- 2026-09-12-decision-process-visualization-research.md / plan.md：已有“理由、代价、什么会改变结论”的用户侧结果结构，可复用于 Demo 呈现。
- 2026-09-04-conversation-decision-assistance-research.md / plan.md：定义多轮偏好更新和解释结构，但属于真实 Orchestrator 能力，不应成为固定 Demo 的运行依赖。
- 2026-09-02-generic-decision-from-diet-foundation-research.md / plan.md：确认 fixture 可作为无模型 key 时的稳定能力，但当时仍通过后端通用决策链路运行。

上述记录均为已完成的历史方案，且当前需求新增“预设示例直接进入纯前端确定性剧本”的独立边界。追加旧文件会混淆真实链路与 Demo 链路，因此新建本组 Research / Plan。

## 核心文件及职责

### src/choice_agent/static/assets/js/app.js

- renderGeneralHome() 渲染顶部推荐示例和四个普通示例。当前所有按钮使用 general-example action。
- handleClick() 对 general-example 的处理只是把文案写入 textarea、记录 demo domain 并聚焦输入框，没有进入 Demo。
- submitGeneralDecision() 无论内容是否来自示例，都会调用 conversation.startGeneral()。它是自由输入主链路，必须保持不变。
- renderDemoWorkbench() 当前展示示例卡；startDemoChat() 最终仍调用 conversation.startGeneral()，因此依赖后端领域解析、API 和 Orchestrator。
- 文件中仍保留旧本地 Demo 的候选、权重、约束和结论渲染函数，但现行页面没有把这些函数组织成可见的轻量闭环。

### src/choice_agent/static/assets/js/demo.js

- 已有 travel、career、learning、shopping fixture，包含候选、criteria、attributes 和 evidence。
- 已有 localStorage 保存、候选排序、权重调整、澄清回答和推荐生成等能力。
- 当前状态机围绕 constraint_input → candidate_input → compare → decided，偏向可编辑工作台；不是需求要求的轻量固定剧本。
- explain() 主要由加权排序动态生成通用结论，代价和变化条件较泛；不能保证每个用户回答都有明确、稳定、可读的专属结果。
- 当前 fixture 没有 diet 场景，而首页推荐示例已经是 diet。

### src/choice_agent/static/assets/js/conversation.js

- startGeneral() 负责真实领域解析、diet 分流、后端创建和路由进入 /diet/chat 或 /decisions/:id。
- renderGeneralPanel() 展示真实 Decision Canvas，其中已有推荐理由、代价、变化原因和变化边界。
- 固定 Demo 不应调用或修改该模块；这是保证真实自由输入不受影响的主要隔离边界。

### src/choice_agent/static/assets/css/app.css

已有 example-grid、demo-workbench、demo-candidate、chips、decision-result-card、result-grid、demo-trace 等样式可复用。新增样式应限定在固定剧本容器下，避免影响真实 Decision Canvas 和饮食页面。

### tests/test_frontend_static.py

当前只做前端源码静态断言，没有执行 Demo 状态转换。要证明固定剧本稳定，需要增加可执行的 JavaScript 状态机测试，而不仅检查函数名或文案存在。

## 关键调用链和数据流

### 当前首页预设示例

renderGeneralHome() → 点击 general-example → 写入 textarea → 用户提交 generalDecisionForm → submitGeneralDecision() → conversation.startGeneral() → 领域解析/API/Orchestrator → /diet/chat 或 /decisions/:id。

### 当前 #/demo

renderDemoWorkbench() → 点击 start-demo-chat → startDemoChat() → conversation.startGeneral(demoMode:true) → 后端 fixture/Orchestrator → 真实通用对话页。

### 目标隔离边界

预设 Demo 示例 → 本地 script id → ChoiceAgentDemo 创建固定初始状态 → /demo/script/:id 渲染第一轮候选差异和固定澄清选项 → 用户选择 option id → 本地状态机返回对应固定推荐 → 同页展示偏好更新、理由、代价和变化边界。

自由输入表单继续保持：textarea → submitGeneralDecision() → conversation.startGeneral()。两条链路不共享请求函数，也不以 demoMode 参数伪装隔离。

## 当前实现的主要问题

1. 首页“示例”与真实自由输入共用提交流程，后端或模型行为会使体验不稳定。
2. demoMode:true 只是后端请求上下文，不代表纯本地或固定输出。
3. #/demo 文案声称演示数据，但运行仍依赖 API；服务不可用时无法完整体验。
4. 旧本地 Demo 的步骤较重，需要先编辑约束和候选，不符合“一次点击即可体验核心闭环”。
5. 旧澄清回答只记录 assumption，不保证重新计算出与回答对应的专属推荐。
6. 结果中的代价与变化条件偏通用，不能稳定证明 Choice Agent 的核心解释价值。
7. 首页推荐场景已改为 diet，但本地 fixture 尚无 diet 剧本。

## 已有可复用能力

- demo.js 独立于后端，可作为固定剧本状态机归属模块。
- ChoiceAgentDemo.domainLabels 和现有场景 fixture 可复用部分候选文案。
- 首页示例已经携带明确文案和 domain，可改为稳定的 script id 映射。
- app.js 的事件委托适合增加少量 start-scripted-demo / demo-script-answer action。
- 现有候选卡、chips、结果卡和流程样式可复用。
- 首页 textarea 提交和 conversation.js 可以完全不动，从结构上保护真实链路。

## 约束和边界

- Demo 必须明确标注“固定演示数据 / 非实时建议”，不能伪装为 LLM 或实时搜索输出。
- 固定回答每个问题控制在 2～3 个；每个回答必须映射到确定的偏好更新和结果。
- 推荐结果至少包含：当前推荐、推荐理由、需要接受的代价、什么变化会改变结论。
- 第一轮必须先展示候选差异，再让用户选择，不能直接给最终结论。
- 预设示例和 #/demo 不发起网络请求。
- 自由输入继续使用真实链路，不改变 API、路由语义和 DecisionState。
- 不新增前端框架或依赖，不把 Demo 状态写入真实历史决策。
- 旧 /demo/decision/:id 本地链接应有兼容处理，不能出现空白页或异常。

## 潜在问题和隐患

- demo.js 已包含一套较大的旧工作台状态机；新 scripted session 必须使用独立、很小的数据结构和明确函数名。
- 若一次为所有场景编写大量分支，内容维护成本会快速上升；应采用统一 schema，每个选项只携带自己的结果快照。
- localStorage 中存在旧 Decision 数据，不能让新版脚本误读旧 shape。
- 只做 DOM 静态测试无法验证状态转换；需用 Node 加载 demo.js 并执行每个 option。
- 首页示例点击行为会从“填入可编辑文本”改为“立即进入 Demo”，需要保留明确的自由输入入口。
- 当前工作区已有其他未提交修改，实施时必须限定 diff，避免覆盖 evaluation 等无关文件。

## Plan 阶段需明确的决策

- 为保证所有预设按钮语义一致，建议首页全部预设示例进入固定 Demo；textarea 提交仍走真实链路。
- scripted 状态机应有独立 schema、路由和旧 Demo 兼容策略。
- 首批覆盖当前首页五个预设场景（diet、travel、shopping、learning、career），至少完整验收 diet 推荐场景。
- 自动化测试应遍历每个回答分支并证明输出字段完整和结果确定。