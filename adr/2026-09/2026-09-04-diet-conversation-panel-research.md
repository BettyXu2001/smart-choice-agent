# 饮食对话与可编辑决策面板 Research

## 范围与状态

2026-09-04：先将饮食版改为对话主导、右侧可编辑决策面板，用户验收稳定后再考虑通用推广。本轮只写 Research / Plan，未获新方案实施批准。涉及关键交互、状态与接口，按大改动处理。

当前工作区已有大量未提交的统一内核改动，研究以实际代码为准，不回滚、覆盖或归为本轮成果。

## ADR 检索与归档决定

已按对话、面板、槽位、编辑、ChatResponse、renderChat 检索历史内容：

- ../2026-08/2026-08-29-diet-agent-python-migration-research.md 及同名 Plan：饮食槽位、澄清和推荐基础。
- ../2026-08/2026-08-29-eat-what-selector-integration-plan.md：推荐选择与换一批边界。
- ../2026-08/2026-08-30-unified-choice-entry-plan.md：首页分流和饮食入口。
- 2026-09-02-generic-decision-from-diet-foundation-plan.md：早期通用抽取。
- 2026-09-04-generic-decision-evidence-workbench-plan.md：共享阶段、状态和命令，仍记录饮食专用页未对齐。

本轮边界为饮食产品交互，新建文档引用旧记录，不覆盖历史。用户最新决定优先于旧工作台扩展方向，旧方案其他未完成事项不因此视为完成。

## 关键文件、调用链与真实行为

以下路径均相对仓库根目录。

| 文件 | 职责与当前行为 |
| --- | --- |
| src/choice_agent/static/assets/js/app.js | 首页饮食关键词分流到 /diet/chat；renderChat 右侧是快捷问题和数据源。sendChatMessage 未保存 decisionState，也未发送 expectedRevision。 |
| src/choice_agent/static/assets/css/app.css | 已有主列加 320px 侧栏，980px 以下单列，两套主题可以复用。 |
| src/choice_agent/static/assets/js/api.js | DietApi 聊天/餐食/反馈，DecisionApi 查询/命令；错误只保留普通 message。 |
| src/choice_agent/api/routes.py | 饮食与通用 API 入口、错误与版本冲突处理。 |
| src/choice_agent/orchestration/diet.py | 加载 session / DecisionState，运行统一阶段，保存消息、槽位和版本，返回饮食响应。 |
| src/choice_agent/orchestration/unified.py、agents/stages.py | 共享阶段：意图、理解、澄清、推荐/三餐、审查、解释、风险。 |
| src/choice_agent/agents/diet.py、domains/diet/rules.py | 规则与模型提取，槽位累加，澄清与换一批。 |
| src/choice_agent/domains/diet/profile.py | 根据槽位重建条件，合并旧约束并保留权重，执行领域策略。 |
| src/choice_agent/domains/diet/composition.py | 三餐组合，composition.items 保留餐次归属。 |
| src/choice_agent/presenters/diet.py、schemas.py | ChatResponse 已有 decisionState，后者含 domainState.slots、constraints、assumptions、messages、revision、composition。 |
| src/choice_agent/decision/commands.py、orchestration/generic.py | 已有命令和幂等事件，但无槽位替换/清空；通用写入不等同于饮食消息持久化。 |
| src/choice_agent/repositories/diet_repository.py、repositories/decision_repository.py | 保存 session/message 镜像与 Decision JSON；有条件版本更新，但多个方法自行 commit。 |

调用链：首页 → renderChat → DietApi.chat → DietOrchestrator.chat → DietProfile / StageRunner → DietPresenter → 聊天文字和卡片。服务端已有完整决策状态，页面只保存文字、卡片、澄清字段与 sessionId，刷新没有当前会话恢复。

## 可复用能力

聊天布局、主题、SLOT_LABELS、slot-options、现有多选控件模式、餐食卡片、反馈；DietProfile 与统一阶段；DecisionState / revision / EditEvent；现有 tests/test_orchestrator.py、test_rules.py、test_unified_decision.py。

已读用例包含跨 API 调权后继续饮食聊天、三餐重算及风险保护。这些用例不能证明槽位编辑、来源或刷新已实现。

## 问题和隐患

1. SlotBundle.merged_with 去重累加，晚餐改午餐不会替换，空数组无法清除历史值。
2. UnderstandingAgent 重建 constraints，DietProfile 合并旧约束。只改面板 constraints 会与 slots 分离，删除项可能恢复。
3. 规则和模型提取合并；Constraint.source 默认 user，不能据此宣称每项已获用户确认。
4. hard_exclusions 依赖已有槽位选项，未证明任意食材过滤。不能将“不吃鱼”展示成已可靠执行。
5. 前端不持有 revision，编辑和聊天可能竞态；重渲染可能丢输入及滚动位置。
6. 直接混用通用 command 与饮食 chat 会涉及两套消息保存及响应细节。
7. repository 分段提交，需在本轮饮食写入边界解决消息、事件、状态的一致性。
8. 澄清、风险、条件改变后旧结果需要失效，历史卡片不能冒充当前推荐。

## 约束与 Plan 决策点

不换技术栈、不增依赖、不改通用版 UI 或场景识别、不建设内部 Trace 面板。尽量保持现有排序，必要修复明确纠正、清空和来源。

Plan 需决定编辑接口、字段权威来源、推断优先级、未支持忌口的表达、恢复机制及验收门槛。

本次为静态代码研究，未运行未来功能或真实模型验证；历史 ADR 测试结果不作为本轮验证结果。
