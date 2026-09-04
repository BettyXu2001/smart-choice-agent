# 对话决策辅助能力修复 Research

## 范围与 ADR 检索

用户反馈 Demo 输入后仍笨、无法辅助决策。属于跨理解、状态和解释阶段的核心流程改动。正式研究前检索已有 ADR：

- `2026-09-04-general-conversation-panel-research.md` / `plan.md`：直接相关，已实现共享界面、结构化字段、请求恢复和 Demo 入口补漏；其验收不足以证明决策质量。
- `2026-09-04-diet-conversation-panel-research.md` / `plan.md`：共享交互与字段保护来源，本次保护其既有行为。
- `2026-09-04-generic-decision-evidence-workbench-plan.md`：结构化候选、证据和比较能力的既有基础。

已有推广已完成，本次重点是语义理解与决策推进，另建记录，避免修改既有已完成验收含义。本轮不改产品代码。

## 实际调用链

Demo 示例 → app.js/startDemoChat → conversation.js/startGeneral（context.demoMode、fixture）→ routes 的 runtime_model → GenericDecisionOrchestrator → StageRunner → ComparisonProfile.intent / understand / clarify / source_and_rank / explain → Recommendation / 历史快照 → 共享对话和侧栏。

`agents/conversation.py` 提取固定字段、少数格式的候选和排除/恢复操作。仅在没有规则 patch 且 operation=compare 时调用模型。模型请求只有本轮 message、domain、fields，没有候选、近期对话或上一轮追问。

`prompts/conversation.py` 和 Interpretation 只允许 fields/question，没有候选信息更新、比较解释或建议。

`domains/generic.py` 无数值评分时拼接候选说明，再复述 priority；不根据文本事实分析取舍，不生成条件性建议。`domains/comparison.py` 的有分数回复主要是排名第一的名字，缺少本轮变动的因果说明。

`orchestration/generic.py` 的 _stage_data 已有近期消息与 provider，理解器却没有将近期消息传给模型；解释器完全未调用模型。每轮重新运行排序，表面上已响应，但未理解的内容没有进入持久化决策。

`static/assets/js/app.js` 把 Offer/学习示例作为描述文字送进 Generic，原先演示数值未导入（此前有意避免伪装真实评分）。因此兜底复述问题在这两类 Demo 最明显。候选描述里的“稳定”等词还可能被关键词规则误当成用户偏好。

## 可重复证据

使用独立临时 SQLite、RecordingProvider（不访问外部服务）重放示例：A 公司 AI 方向匹配、成长大、业务早期；B 公司平台成熟、薪酬稳定、传统岗位。

1. “更看重稳定”：规则设置 priority，模型调用 0 次；回复复述 A/B 并让用户继续补充，primary 为空。
2. “那为什么不选 A 公司？”：模型调用 1 次，但仅收到 message/domain/fields；返回仍与上轮相同。
3. “B 公司通勤每天要两小时，我不太能接受”：没有更新 B 的候选事实，也没有记录该限制，回复仍与前两轮相同。

问题不仅是是否配置模型；当前模型入口本身不具备足够上下文与决策职责。现有 98 项测试及浏览器通过证明了状态/交互兼容，未覆盖这些对话质量失败。

## 可复用、约束与待决策

复用现有 ModelProvider、runtime_model、StageRunner、Recommendation/RecommendationPoint、candidatePool/manualCandidates、revision/收据/快照和共享 UI。不引入新模型 SDK、搜索接口或数据库表。

已有数值筛选/排序不得被无依据文字建议推翻；候选事实必须来自用户、标明的演示数据或已有来源。优先级、推测、事实分别记录。用户明确的新补充应能覆盖旧信息；模糊指代/语义冲突先追问，清空字段不可由旧上下文复活。

Plan 需决定：每轮理解与解释的模型职责、候选补充/指代处理、无模型时的有限辅助方式、可审阅的理由结构、质量验收、故障回退和成本边界。
