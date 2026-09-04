# 通用对话与决策面板推广 Research

## 范围与状态

2026-09-04：饮食版已完成并记录 80 项测试及浏览器验证，用户进一步明确要求“推广到通用”。这是进入推广阶段的决定，不代表未经审查的具体方案已获实施批准。本轮按跨模块/核心交互大改动完成 Research / Plan，尚不修改产品代码。

## ADR 检索与归档

按场景识别、DomainRegistry、对话、工作台、状态编辑检索历史内容，相关记录：

- 2026-09-04-diet-conversation-panel-research.md / plan.md：直接复用来源，包含字段确认、双侧同步、幂等恢复、移动抽屉。
- 2026-09-04-generic-decision-evidence-workbench-plan.md：现有共享阶段、通用命令和证据能力；其工作台主导方向已被本次对话主导需求取代，不自动续做其他未完成项。
- 2026-09-02-generic-decision-from-diet-foundation-research.md / plan.md：后端通用接口与领域协议历史。
- ../2026-08/2026-08-30-unified-choice-entry-plan.md：前端关键词分流的历史边界。

新建本组文档，保留饮食已完成记录和旧方案历史，不把“推广到通用”写成已完成通用验收。工作区已有大量未提交修改，后续应以实施前快照区分本轮范围。

## 代码与调用链

下列路径相对 src/choice_agent。

| 文件 | 实际职责及观察 |
| --- | --- |
| static/assets/js/app.js | 饮食已有 renderChat/renderDietPanel/runDietOperation、草稿/版本/恢复；非饮食仍 renderGenericDecisionState 工作台。首页 isDietPrompt 先按“吃、饭、餐”等词分流。 |
| static/assets/js/api.js | 饮食 chat/state/command 与通用 create/message/command/get 均已有封装；错误已有 status/detail。 |
| orchestration/diet.py、domains/diet/state.py | 饮食已具备来源、清空保护、事务、轮次快照和请求回执，是交互推广基线。 |
| domains/registry.py | 显式 domain 优先，否则按 profiles 注册顺序返回首个匹配，最后 generic；无多匹配/歧义结果。 |
| domains/diet/profile.py、domains/diet/rules.py | Diet matches 依赖旧意图规则，“推荐”等泛词也可能命中，不能直接作为跨领域高置信证据。 |
| domains/comparison.py | intent 固定 compare_<domain>_options，confidence 固定 1；没有每轮操作意图分类。understand 重写 assumptions，仅记 provider。 |
| domains/travel.py | 关键词识别；预算只生成“预算友好”软文本，不解析数值；下一轮删除此前 source=inferred 的偏好。澄清继承长度启发式。 |
| domains/shopping.py | 同样丢失此前 inferred 偏好；类别由原 goal 与当前 message 拼接匹配，缺持久化类别字段。 |
| domains/generic.py | 手工候选不足两个就澄清，要求填写 fit/cost/risk 0–100 分；constraints 原样返回，不从自然语言录入候选。 |
| orchestration/generic.py | create 解析领域；message 固定使用既有 domain；command 支持 revision/事件，普通 create/message 无请求幂等。_stage_data 无条件加载饮食槽位。 |
| decision/commands.py、decision/ranking.py | 已有约束、权重、候选、排除/恢复等命令；硬约束与数值 criteria 参与排序，普通软文本不会自动改变 AttributeCriterionEvaluator 权重。 |
| providers/search.py、providers/candidates.py | 旅行/购物可用 fixture 或现有 Web Search；搜索包含 goal、当前 message、criteria、constraints，但未包含新结构化场景字段。 |
| api/routes.py | 饮食接入 runtime_model；通用 create/message/command 仍取基础 settings/provider，浏览器模型设置尚未真正接入通用理解流程。 |
| schemas.py、repositories/decision_repository.py | 通用状态已有 messages、assumptions、revision、domainState 等；repository 已支持不立即提交和版本条件更新。 |

当前非饮食链路：主页 → DecisionApi.create → DomainRegistry.resolve → GenericDecisionOrchestrator → StageRunner → ComparisonProfile → Provider/Ranking → DecisionState → 工作台。

续聊接口存在，但界面主要通过 command 表单操作；answer_question 进入完整阶段，不能自动让通用 profile 理解自由对话中的候选、预算或纠正。

## 可复用与问题

可复用：饮食页面交互壳、移动抽屉、请求串行/重试与旧回包隔离；现有消息/状态/command；领域注册表、共享调度器、候选来源与排序；既有来源显示与详细比较。

主要缺口：

1. 双重领域识别（前端关键词＋后端首个命中）导致“推荐电脑”“周末买耳机”等误路由风险。
2. “操作意图”只是固定标签；换一批、补充偏好和修改候选未统一到结构化变更。
3. 非饮食没有字段来源和清空保护，旧 inferred 偏好会消失；UI 展示变化不代表排序变化。
4. 通用兜底依赖用户先懂评分表，不能承接大众对话需求。
5. generic 普通创建/消息缺幂等，失败 Trace 提交可能保留部分运行记录；需应用已有饮食事务做法。
6. 直接复制饮食页面会形成多套请求/草稿/恢复逻辑；直接把所有领域都变成饮食槽位则会误用标签和结果类型。
7. 旅行 fixture 没有真实出发地/日期依据；购物 fixture 是模拟商品。不能把新增面板字段解释为已验证实时适配。
8. 原工作台已有候选编辑/权重/证据能力，需要按需展开保留，而不是删除后只剩聊天文字。

## 约束与待 Plan 决策

本轮不新增外部搜索服务、专业 Offer/学习领域或替换技术栈；不修改饮食评分/食材数据能力。已有 provider 可继续使用，模型输出不得捏造候选事实或主观分数。

Plan 决定共享页面层边界、服务端路由策略、每轮操作意图、各领域字段语义、旧链接/状态兼容、普通消息幂等、刷新与推广验收。

本轮仅静态研究；80 项测试是饮食阶段既有结果，不是通用推广的验证结果。
