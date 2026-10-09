# 饮食 Demo 推荐正确性 Research

日期：2026-10-09

## 当前需求和研究范围

用户实际运行“今晚吃什么”网页 Demo 后，要求按观察顺序逐项修复七个问题：推荐理由与候选标签冲突、关键口味语义丢失、默认候选源质量不足、候选解释模板化、匹配分不可理解、快捷回复需要二次发送，以及切换餐食库后重复显示状态消息。

这些问题跨越自然语言理解、结构化饮食槽位、候选召回、排序口径、解释生成、对话持久化和前端交互，影响核心推荐流程，按大改动处理。本 Research 只确认真实代码行为、复用能力和约束，不修改产品代码。

## 成功标准

- 推荐理由只能引用候选真实命中的标签，不再把未命中的“清淡”等偏好写成已满足。
- “清淡但不寡淡”等明确表达同时保留清淡目标和可执行的有味道偏好。
- 首页饮食 Demo 默认能得到足够且相关的候选，同时保留用户显式切换个人餐食库的能力。
- 候选理由能说明各自命中的条件和主要差异，不再三项共用同一句模板。
- 饮食匹配分只以本轮实际提出的条件为分母，并向用户说明其语义。
- 点击饮食快捷回复后直接发送一次，不产生重复请求。
- 切换餐食库在对话中只出现一次确认，用户动作和系统回应的角色准确。
- 每项修复均有专项测试，并回归澄清、三餐、风险、反馈、个人/公共餐食库、Trace 和通用决策流程。

## ADR / 历史方案检索

已按 Diet、饮食、餐食、推荐理由、匹配分、候选源、快捷回复、反馈、澄清和数据源切换检索 `adr/`、`docs/`、`src/`、`tests/` 与 `CHANGELOG.md`。

相关记录：

- `adr/2026-09/2026-09-04-diet-conversation-panel-research.md` / `plan.md`：定义饮食对话、可编辑条件、来源切换、revision、恢复与面板交互；本次必须复用现有 `DietOrchestrator` 和版本化写路径。
- `adr/2026-09/2026-09-22-diet-hybrid-db-web-recall-research.md` / `plan.md`：定义餐食库优先、候选不足时补充 Web Search；当前未配置 Web Search 时只保留所选 DB 来源。
- `adr/2026-09/2026-09-22-recommendation-feedback-loop-research.md` / `plan.md`：定义“不合适”只排除当前候选、保留条件、复用重排且无候选时不自动放宽。
- `adr/2026-10/2026-10-09-decision-workflow-correctness-hardening-research.md` / `plan.md`：处理旅行/通用工作流正确性；与本次在前端文件和测试上重叠，实施时必须增量 patch，不能覆盖。

旧 Diet 方案均已完成且主题分别是面板、召回和反馈闭环；当前问题是一次真实饮食 Demo 验收暴露的推荐正确性集合。追加旧文档会混淆历史，因此新建本 Research / Plan。

## 当前工作区约束

工作区已有未提交的 README、CHANGELOG、Decision Assistance、Evaluation、前端工作流、测试和 `adr/2026-10/` 改动。其中 `app.js`、`conversation.js`、`app.css`、`tests/test_frontend_static.py` 与本次预计范围重叠。实施必须保留这些改动，禁止整体重写或格式化。

## 实际 Demo 观察

实际输入：“今晚不知道吃什么，想吃清淡一点，但又不想太寡淡，帮我推荐一下。”

1. 首轮正确追问餐次；点击“晚餐想吃清淡一点”只填入输入框，仍需再次点击发送。
2. 结构化详情得到 `mealTime=晚餐`、`healthGoal=清淡`，但 `taste` 仍显示尚未设置，“不想太寡淡”丢失。
3. 首页饮食入口把来源强制设为 `PERSONAL`，个人库只返回“土豆炖牛肉”，匹配 14%。
4. 土豆炖牛肉标签是“补能、湘菜、辣”，规则理由却写“比较符合清淡诉求”。
5. 点击“不合适”后，系统正确排除候选、保留条件且不自动放宽；个人库随后无结果。
6. 切换公共库后返回番茄鸡蛋面、清汤馄饨、鸡胸肉轻食碗，匹配分为 29%、29%、14%；三个理由仍是同一句“比较符合清淡诉求”。
7. 切换来源时“已切换为公共餐食库。”在对话中出现两次。

## 核心文件及真实职责

| 文件 | 当前职责与行为 |
| --- | --- |
| `src/choice_agent/domains/diet/rules.py` | `extract_slots()` 只按槽位字典字面匹配和少量别名提取；没有“清淡但不寡淡”一类平衡口味表达。 |
| `src/choice_agent/domains/diet/state.py` | `understand_fields()` 合并明确规则结果、模型推断、纠正和清空；明确规则值写成 `conversation + confirmed`，可复用。 |
| `src/choice_agent/agents/diet.py` | 规则理由只检查用户 slots 是否非空，不检查候选 attributes 是否命中；模型输入也没有标签或命中明细。 |
| `src/choice_agent/domains/diet/evaluator.py` | 七个 criterion 都返回 contribution；用户未提出的维度也以零分、权重 1 进入分母。 |
| `src/choice_agent/decision/ranking.py` | 通用排序按所有 contribution 的权重求平均；Diet evaluator 的行为导致两个命中仍只有约 29%。 |
| `src/choice_agent/domains/diet/profile.py` | `_database_search()` 只查当前 `source_mode`；无 Web Search 时个人库候选不足也不会补公共库。 |
| `src/choice_agent/static/assets/js/conversation.js` | `prepareChatFromHome()` 强制 `PERSONAL`；面板负责来源切换、快捷回复和版本化操作。 |
| `src/choice_agent/static/assets/js/app.js` | `quick-message` 只给 textarea 赋值，不调用现有 `submitChat()`。 |
| `src/choice_agent/orchestration/diet.py` | `set_source` 同一句完成态文案同时作为 user message 和 assistant 前缀持久化。 |
| 相关测试 | 已覆盖基础槽位、澄清、推荐、反馈、来源切换和静态接线；没有覆盖本次七个失败场景。 |

## 关键调用链和数据流

首页饮食入口：`general-example` → `prepareChatFromHome()` → `sourceMode=PERSONAL` → 自动 `sendChatMessage()` → `DietApi.chat()`。

理解链：`IntentAgent` → `extract_slots()` + 可选模型 slots → `UnderstandingAgent` → `understand_fields()` → `domainState.slots / dietFieldState / constraints`。

推荐链：`DietProfile._database_search()` → `DietMealProvider` → `EvidenceValidator` → `GenericRankingEngine + DietCriterionEvaluator` → `select_candidates()` → `ExplanationAgent` → `MealResponse`。

快捷回复：`quick-message` click → textarea/state draft 赋值 → 用户再次提交表单 → `sendChatMessage()`。当前第一次点击不发请求。

来源切换：`set_source` → `_panel_patch()` 返回“已切换为…” → `_execute()` 把该字符串保存成 user message → 重算后又把同一字符串前置到 assistant speech。

负反馈：`saveFeedback(DISLIKE)` → 排除 candidate → `recompute(refresh_candidates=False)` → 保留原 candidatePool；当前行为符合既有 ADR，不在本次重写。

## 已有可复用能力

- `understand_fields()` 的来源、确认、纠正和清空优先级。
- `Candidate.score_breakdown` 与 Diet 七维 attributes，可直接生成候选真实命中说明。
- `EvidenceValidator` 和数据库 Evidence，能够证明餐食标签来源。
- `DietOrchestrator` 的 revision、幂等、事务、Trace 和消息持久化。
- `sendChatMessage()` / `submitChat()` 的单一发送路径，可供快捷回复直接复用。
- 现有个人/公共来源切换，不需要新 API 或数据库字段。
- 反馈闭环已经正确处理排除、无候选和不自动放宽条件。

## 潜在问题和隐患

1. 只修改文案不能解决错误理由；规则理由和模型输入都必须包含候选真实标签/命中明细。
2. “不寡淡”不能泛化为任意重口味。首版只能保守映射到现有可执行标签“咸鲜”，并要求该选项真实存在。
3. 自动合并个人与公共候选会改变来源按钮的单来源语义。为保持最小改动，首页默认改为公共库，用户显式选择个人库时继续保持个人库边界。
4. 直接修改通用 RankingEngine 会影响其他领域；应只调整 Diet evaluator 对未请求维度的权重贡献。
5. 旧 `DecisionEngine` 仍有七维平均兼容测试，但主流程使用 `GenericRankingEngine`。本次不顺手重写旧引擎。
6. 快捷回复自动发送必须复用现有 pending/retry/revision 保护，不能自己再造请求逻辑。
7. 来源切换消息修复必须保留事件、Trace 和历史可读性，不能简单删除所有 command user message。

## 约束

- 不新增依赖、数据库表或 API 路径。
- 不改变“不合适”的排除、不自动放宽和 Trace 行为。
- 不扩大为完整中文饮食语义词典；仅覆盖本次明确表达及少量同义形式。
- 不把健康目标当作硬约束；低匹配个人候选仍可展示，但理由必须诚实说明未命中项。
- 不覆盖当前未提交的通用工作流修复。
- 用户可见行为变化需要写入现有 `CHANGELOG.md` 的 `2026-10-09` 小节。

## Plan 阶段结论

1. 建立候选真实命中/未命中摘要，并让规则理由不再虚构；模型路径也传入 attributes 和 score breakdown。
2. 将明确的“清淡但不寡淡”类表达保守映射为 `healthGoal=清淡 + taste=咸鲜`，仅在槽位字典支持“咸鲜”时应用。
3. 首页新饮食会话默认使用公共餐食库；历史会话和用户显式来源选择保持不变。
4. 基于真实命中摘要生成候选差异化理由，优先说明命中的餐次、健康目标和口味，并最多提示一个重要未命中项。
5. Diet evaluator 对未请求维度使用零权重，使百分比表示“本轮已表达条件匹配度”；前端同步改名并解释口径。
6. 快捷回复直接复用 `sendChatMessage()`，一次点击只发一次。
7. `set_source` 分离用户动作文本与系统确认文本，避免同一句完成态重复出现。

## 研究验证记录

- 已通过真实网页完成首页输入、餐次澄清、个人库推荐、负反馈、公共库切换和标签检查。
- 已运行现有饮食规则、旧评分、编排、面板、混合召回和前端静态测试，命令退出码为 0。
- 本阶段未修改产品代码；真实外部模型和 Web Search 未配置，不在本次基线中验证。