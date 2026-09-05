# 决策过程可观测 Trace Plan

## 状态

2026-09-05：待用户审查，尚未批准实施。依据同目录 2026-09-05-decision-trace-observability-research.md。用户“继续”用于完成当前 Research / Plan 阶段，不据此提前修改产品代码。

## 目标与成功标准

以业务时间轴回答输入、意图、状态修改、Agent、证据、排除、推荐变化、降级；点击查看实际输入输出、Prompt、模型结果及 JSON。

可演示“上轮推荐 A → 收紧条件 → 字段旧值/新值 → A 命中具体排除规则 → 推荐 B”，关联可定位；准确显示未变、无候选、澄清、失败、降级、假设未落盘、历史信息缺失。

## 架构、逻辑和关键流程

### 1. 增量事件

保留 traceJson.events、AGENT_CALL 名称/输入输出/耗时、API、存储表；增加 schemaVersion=2、decisionId、domain、revisionBefore/revisionAfter、commitStatus、timeline、turnSummary。timeline 独立于旧 events，避免 Evaluation 重复统计。

节点包括 eventId、parentId、sequence（开始分配）、stage、kind（agent/operation/model）、status、startedAt、durationMs、summary、input/output、changes、引用 ID。区分 success/failed/fallback/skipped，历史缺失为 unknown。内存 collector 绑定 AgentContext 独立可选字段，不放进 data；无 collector 调用保持可用。AgentRuntime 包住实际调用，内部事件关联父 Agent。不重构调度、不重复执行、不额外调用模型生成摘要。

### 2. 状态差异及提交

Generic create/message/command、Diet _execute 第一次修改前采集基线；记录输入/命令、Agent 前后、最终结果。初次创建标无上一轮。

白名单包含 goal、intent、status/nextAction、constraints、criteria、字段值/确认/来源、候选/排除、证据、推荐、composition、facts/analysis、selection、必要业务 context。排除 agent_runs、trace_refs、历史消息/receipts、provider/repository/settings。按稳定 ID/key 比较 add/remove/replace，记录 path、before/after、origin、eventId；明确清空与确认变化。基线一次、节点差异，不保留可变对象引用。失败变化标 attempted/rolled_back，业务提交成功才标 committed，维持现有事务边界。

### 3. 真实检索、证据、过滤、排名

在 ComparisonProfile、DietProfile、三餐 composition 的实际操作处记录：

- Retrieval：provider/mode/query、候选 ID/数量、候选池复用；标明 fixture/数据库/用户来源。
- Evidence：ID 级新增/更新/移除、candidate/criterion、claim、source、verification；用户 facts/catalog 单列引用类型，不夸大验证含义。
- Hard Filter：GenericRankingEngine 增加可选诊断参数，返回值兼容。在原判断路径记录 candidateId、reasonCode、constraint key/operator/expected/actual、criterion/evidence；保持短路次序，只记录实际命中的原因，不复制筛选算法。
- Ranking：记录候选、scoreBreakdown、排序和可比前轮贡献。用户排除、缺值、硬约束分开；饮食低分、前十截取、避重/随机另记 Selection；三餐按 mealTime 分组，重复排除标真实原因。

### 4. 模型与 Fallback

轻量 ModelProvider 包装器保持 enabled/complete_json，记录实际 system/user Prompt、模型名、结构化返回、耗时、异常。OpenAICompatibleProvider 增加可选观测出口保留 content（含非法 JSON），不改解析抛错；测试 provider 仅返回 dict 时标原文未提供。Search 记录实际 input、尝试序号、结果/解析，关联 retrieval。

模型调用与业务校验/采用分层。agents/diet.py、assistance.py 现有 catch、ComparisonProfile auto fallback 处记录原因、from/to、采用结果。未捕获网络异常仍失败，不扩大降级策略；禁用模型为 rules mode。部分采用按现有行为记录。

仅记录业务 Prompt/结果；不记录 Authorization、API Key、headers、完整配置。递归脱敏并移除已知凭据；单段文本 32 KiB、模型原文 64 KiB 上限，标 truncated/originalLength，保留结构化引用。错误记录类型及脱敏原因。

### 5. 推荐变化

比较初始已保存 recommendation 与提交结果，分类 initial/changed/unchanged/cleared/no_recommendation；显示主选/备选、规则命中、分数贡献、Selection、顾虑、解释 sourceId，链接具体节点/候选/证据。

仅实际决策或引用链支持时表述因果，否则标“相关变化，归因信息不足”。仅文案改变不算主选变化。假设为 simulation 子组，注明未改变正式条件/推荐，模拟结果不能覆盖正式结果。

### 6. 页面

保留查询、标注、原始 JSON。页面命名“决策过程”，顶部显示输入、领域/revision、状态、耗时、推荐变化及降级摘要。

主线 User Message → Intent Understanding → Constraint Update → Candidate Retrieval → Hard Filter → Ranking → Critic Check → Explanation；Evidence 为检索后明确子节点；Clarification、Adjustment、Selection、Risk、Composition 按真实顺序插入。Intent/Understanding 视觉分组但保留独立 Agent 卡；Constraint Update 指向真实来源，不假定发生在 Understanding 后。

跳过显示原因，失败后为未执行；确认/场景提示不伪造调用；旧聚合事件标“历史记录未拆分”，缺失显示未记录。节点默认结论/数量/变化，details 展开输入、输出、差异、Evidence、Prompt/结果、JSON。HTML 转义、外链限 http/https、支持键盘、窄屏纵向、JSON 独立滚动。trace.js 隔离适配呈现，app.js 管查询路由；保留聊天入口，详情路由保留 traceId，处理加载/错误/快速切换竞态。

## 文件级范围

路径相对 src/choice_agent；tests、CHANGELOG 相对仓库根。

| 文件 | 计划修改 |
| --- | --- |
| services/trace.py | collector、快照/差异、引用、提交、摘要、脱敏；必要时辅助投影拆为 trace_projection.py。 |
| agents/base.py、agents/stages.py | collector、起止/失败/差异、跳过分支，保留旧事件。 |
| orchestration/generic.py、diet.py | mutation 前基线、请求命令、提交结果、模型作用域、直接 clarify 记录。 |
| domains/comparison.py、domains/diet/profile.py、domains/diet/composition.py | 检索/证据/排名/选择、fallback、餐次。 |
| decision/ranking.py | 可选过滤/评分诊断，不改算法返回值。 |
| providers/model.py、providers/search.py | 包装器、原文出口、搜索尝试。 |
| agents/diet.py、decision/assistance.py | 校验/降级/采用、事实引用、假设。 |
| static/assets/js/trace.js（新增）、app.js、static/assets/css/app.css、static/index.html | 时间轴、兼容、详情、脚本引入、布局路由。 |
| tests/test_trace_observability.py（新增） | 差异、顺序、引用、过滤、失败/降级、脱敏、提交、旧数据。 |
| tests/test_orchestrator.py、test_generic_orchestrator.py、test_diet_panel.py、test_general_conversation.py、test_decision_assistance.py、test_unified_decision.py、test_runtime_model_settings.py | 按需补两路径、命令、假设、选择、幂等、兼容断言。 |
| CHANGELOG.md | 实施验收后在同日期标题追加变化。 |

默认不改 schemas.py、db_models.py、routes.py、API JS、依赖和部署；若必须改变公开契约或事务设计，先更新 Plan 再审查。

## 兼容性、风险、技术折衷

- 增量 JSON，旧数据不迁移、不补造 Prompt；保留旧 Evaluation 口径，timeline 不参与旧耗时累计。
- 只采集现有结果，不加模型/搜索调用，不改候选/评分/排序；覆盖所有实际 rank 调用含 hypothetical。
- 不建设完整事件溯源、任意历史重放、实时推流、Agent 架构重构。
- 存储增加以本轮白名单基线/差异及有界原文控制；引用不因 UI 折叠丢失。
- 历史 Evaluation 将失败当 fallback 的口径保留；页面依据显式事件显示。
- 维持现有持久化边界，不声称业务与 Trace 原子提交；区分业务提交与 trace close 错误。

## 验证方案

1. 检查最终 diff/状态、意外格式化/调试代码；重要写入重新读取。
2. 专项 pytest：初次输入、续轮预算/权重/清空、命令修改/确认、证据/引用、硬约束/缺值/用户排除、无候选、无模型、合法/非法模型输出、搜索降级/失败、Critic 失败、rollback。
3. 饮食推荐/三餐/换一批结果与顺序不变；选择不误标硬过滤；幂等复用 traceId，两用户不互读。
4. facts/catalog 可解析，假设不成为正式变化；凭据、嵌套敏感字段、异常文本不泄漏，截断有标识。
5. 完整 pytest；Node 可用时 JS 语法检查。无既有 lint/typecheck/build 配置，不新增依赖制造检查。
6. 真实后端 fixture/数据库、受控 Provider 浏览器验收：聊天跳转、展开、Prompt/输出、引用、旧数据、失败/快速切换、标注、移动布局、键盘。外部模型联通未验证则明确报告。
7. 对照 Todo、diff、CHANGELOG；未能验证项说明环境原因、替代检查、剩余风险。

## Todo

- [ ] 实现 collector、差异、引用、脱敏，验证旧事件兼容。
- [ ] 接入请求命令、Agent 起止、提交，验证修改前基线与幂等。
- [ ] 接入检索、证据、过滤、排名、饮食选择/三餐/假设，验证原结果不变。
- [ ] 接入模型输入输出、采用、fallback，验证失败/规则模式区分。
- [ ] 实现推荐变化与关联，验证归因边界。
- [ ] 实现时间轴、展开、旧记录、错误、窄屏交互。
- [ ] 完成专项/全量自动验证、浏览器验收，记录未验证项。
- [ ] 检查 diff，更新 CHANGELOG 和验收记录。