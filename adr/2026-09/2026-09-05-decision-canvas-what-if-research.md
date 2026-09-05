# Decision Canvas 与 What-if 产品化 Research

日期：2026-09-05

## 当前需求和研究范围

本次需求是把 Choice Agent 的产品重心从“聊天窗口”调整为“持续演化的决策结果面板”。左侧聊天继续负责收集、澄清和修正信息，右侧 Decision Canvas 成为用户判断当前结论的主界面。

需求包含两部分：

- Decision Canvas 固定呈现当前建议、为什么、选择它的代价、当前结论为什么发生变化、还缺什么关键信息。
- 将 What-if 能力产品化，展示“什么会改变我的决定”，支持点击或输入假设进行分析，并明确假设比较不会修改正式决策条件。

该改动影响核心业务流程、前端主布局、正式状态与假设状态的数据边界、解释结构和测试覆盖，按大改动处理。

## ADR lookup 结果

已检索 `adr/` 中与 conversation、decision assistance、generic decision、panel、what-if、evidence、workbench 相关的历史记录。相关记录包括：

- `adr/2026-09/2026-09-04-conversation-decision-assistance-research.md` 与 `plan.md`：覆盖对话式决策辅助、理由、代价、假设分析基础能力。
- `adr/2026-09/2026-09-04-general-conversation-panel-research.md` 与 `plan.md`：覆盖通用对话面板和共享 UI 状态。
- `adr/2026-09/2026-09-02-generic-decision-evidence-workbench-research.md` 与 `plan.md`：覆盖通用候选事实、证据和决策状态。

这些记录与本次需求相关，但主题已经完成。本次需求要重新定义页面主次关系，并分离正式分析与假设分析，追加到旧记录会混淆历史语义，因此新建本组 Research / Plan。

## 核心文件及职责

前端：

- `src/choice_agent/static/assets/js/conversation.js`：`window.createConversation` 的共享对话实现，管理消息、草稿、发送状态、通用面板渲染和面板打开状态。当前 `renderGeneralPanel` 直接消费 `assistance.analysis`、`recommendation` 和 `displayBlocks`。
- `src/choice_agent/static/assets/js/app.js`：路由、demo 初始化、消息渲染和通用详情渲染。
- `src/choice_agent/static/assets/js/api.js`：通用决策 message/get/command API wrapper，当前无需新增 endpoint。
- `src/choice_agent/static/assets/css/main.css`：`.diet-conversation` 同时服务饮食和通用决策，当前桌面布局偏聊天优先，小屏使用抽屉。新 Canvas 样式必须用通用决策专用 class，避免饮食回归。

后端：

- `src/choice_agent/decision/assistance.py`：核心解释逻辑。当前普通轮和假设轮都会写 `domain_state["assistance"]["analysis"]`；假设轮不更新 `Recommendation`，但会覆盖前端展示使用的 analysis。
- `src/choice_agent/agents/conversation.py`：用户输入解释和操作生成。`simulation=True` 用于假设链路，但通用领域目前没有结构化通勤字段。
- `src/choice_agent/decision/conversation.py`：DecisionState 字段定义、字段校验和 criteria 同步。通用字段目前是 `background`、`weeklyHours`、`target`、`priority`。
- `src/choice_agent/domains/comparison.py`：通用比较领域的 interpret、understand、rank、clarify、explain 调用链。假设分析基于当前 candidate pool dry-run。
- `src/choice_agent/orchestration/generic.py`：创建、消息、命令、运行阶段、持久化和 receipt。`command` 先 mutation 再 stage，若要解释结论变化，必须在 mutation 前捕获 baseline。
- `src/choice_agent/ranking.py`：weighted ranking、hard constraints、missing policy 和候选状态。不能为通勤全局改变 missing policy。
- `src/choice_agent/schemas.py`：`DecisionState.domain_state` 是开放 dict，`Recommendation` 和 `AssistanceExplanation` 已承载部分解释字段。

## 当前调用链和数据流

普通消息：前端 `DecisionApi.message` 发送 message、expectedRevision、context，后端 `GenericDecisionService.message` 校验 receipt/revision 后写 context 与消息，再经领域 plugin 执行 interpret、understand、rank、explain。`assistance.explain` 写入 `assistance.analysis`，非假设轮更新 `Recommendation`，最后 `_persist` 保存 snapshot、display blocks、conversation turns 和 receipt。

假设消息：`prepare_turn` 用 `如果|假如|假设|要是` 识别假设，正式理解链路早返回，`explain_hypothesis` 使用深拷贝状态和 `simulation=True` dry-run。正式 `Recommendation` 不更新，但 `assistance.analysis` 会被假设结果覆盖，前端无法明确区分右侧展示的是正式结论还是假设比较。

## 已有可复用能力

- `assistance.explain_hypothesis` 的深拷贝 dry-run 思路。
- `conversation.interpret(..., simulation=True)` 避免正式写入的机制。
- `ranking.rank_candidates` 的权重、硬约束和候选状态。
- `domain_state["assistance"]` 作为解释和面板数据容器。
- receipt / expectedRevision 机制。
- `createConversation` 的消息、重试、草稿和 demo 初始化能力。

## 主要问题和隐患

- `assistance.analysis` 是单槽位，假设分析会覆盖正式展示，容易让用户误以为正式条件被修改。
- “当前结论为什么发生变化”缺少结构化 old/new recommendation 对照，必须在 service mutation 前捕获基线。
- 通勤需求目前不够结构化。旅行有 `maxTransitHours`，但通用求职/公司比较没有 `maxCommuteMinutes` 或单程/每日口径。
- 不能全局修改 `ranking.py` 的缺失策略，否则会影响其他领域。
- What-if 建议不能编造阈值；只有已有可计算事实时才能展示类似“薪资高出 30%”。
- `.diet-conversation` 是共享布局，通用 Canvas 改版必须保护饮食页面。
- `_safe_context` 会保留任意 context key，what-if 的 request-only 字段必须过滤，避免下一轮正式消息被污染。

## 约束

- 不新增依赖，优先复用现有 Python、vanilla JS 和 CSS。
- API 路径保持兼容，优先通过现有 message 上下文承载 What-if 入口。
- 假设比较可以写入聊天历史，但不能修改正式 fields、facts、candidate states、recommendation。
- 旧 snapshot 必须兼容，没有新 Canvas 字段时从旧 `analysis` 和 `recommendation` 降级渲染。
- 移动端通用决策应让 Canvas 可见，不能继续把核心结果藏在难发现的抽屉里。

## 已执行验证

Research 阶段执行了：

```powershell
python -B -m pytest -p no:cacheprovider tests/test_decision_assistance.py
```

结果：17 passed。

该验证只确认当前 baseline 的 decision assistance 行为可运行，尚未覆盖本次计划中的新 Canvas 和 What-if 产品化行为。

## Plan 阶段需要决策的问题

- 如何在兼容旧 `assistance.analysis` 的同时分离正式分析和假设分析。
- 结论变化说明应在哪一层捕获和生成。
- 通用领域通勤约束是否需要结构化字段。
- What-if 建议应规则生成还是允许模型补充后校验。
- 移动端通用决策采用 tabs 还是沿用抽屉。