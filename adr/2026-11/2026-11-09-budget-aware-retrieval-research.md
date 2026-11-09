# 预算变化后的候选检索策略 Research

日期：2026-11-09
状态：研究完成；产品代码未修改。

## 需求和范围

复用现有 DecisionState、执行基线和增量流水线，根据预算变化方向与可证明的检索覆盖，决定刷新候选还是复用候选池。优先购物，检查旅行；保护命令、澄清、What-if、手工候选、排除、证据、revision、receipt 和事务。不新增 Agent，不重构 Orchestrator，不改变公开 API 或数据库 schema。

本次改变核心多轮执行和跨领域检索策略，属于大改动，需 Plan 明确批准后实施。

## ADR / 历史方案检索

先遍历 adr，再按预算/budget、candidatePool、增量、retrieval_sensitive、plan_execution 等内容检索，随后阅读相关实现。

直接相关候选：

- `adr/2026-10/2026-10-12-decision-execution-workflow-optimization-research.md` 和同名 plan：已完成执行规划、候选池复用、最终校验和 Trace；历史结论将预算上限视为通常可重排。本次细化其覆盖前提。
- `adr/2026-10/2026-10-13-multiturn-feedback-source-snapshot-research.md` 和同名 plan：已完成反馈分类和来源快照，保护显式刷新、排除与每轮来源语义。
- `adr/2026-09/2026-09-22-travel-clarification-web-search-research.md` 和同名 plan：旅行字段补全、阻塞澄清、auto 搜索和 fixture 回退边界。
- `adr/2026-09/2026-09-05-candidate-search-productization-research.md` 和同名 plan：Provider、证据、过滤与排序的复用边界。
- `adr/2026-10/2026-10-09-decision-workflow-correctness-hardening-*`：相关 What-if 隔离和结构化状态正确性记录。

上述历史主题已完成，追加会混淆原范围，因此新建本 Research / Plan，保留历史结论。

## 工作区和研究方法

起始工作区有 26 个已修改的 tracked 文件，以及 audit ADR、auth/http 和相关测试等未跟踪文件。包括 CHANGELOG、providers/search.py、repositories/decision_repository.py、tests/conftest.py 等，均为既有改动，本次不覆盖、不回滚。

默认沙箱执行持续无响应；沙箱外只读执行已恢复。环境无 rg，改用 Get-ChildItem / Select-String。读取源码并运行既有测试，不依据历史文档假定当前行为。

## 核心文件及真实职责

| 文件 | 当前职责与发现 |
| --- | --- |
| `decision/execution.py` | capture_execution_baseline 复制 fields/constraints/criteria/excluded/manualCandidates/facts；比较字段值和全部输入；无预算方向或覆盖判断。显式 requested_execution_mode 优先返回，可能绕过字段检查。 |
| `decision/conversation.py` | patch_fields 原子校验正有限数，更新来源/确认/cleared/revision 并清空 recommendation；sync_dependencies 替换 conversation_field 约束，保留其他来源。只有 category 变化分支清空池、手工候选和排除，预算不会触发该分支。 |
| `agents/conversation.py` | 规则识别预算及单位、取消预算，经 patch_fields 写入；反馈可指定 refresh 或 rerank。What-if 提前隔离。 |
| `decision/assistance.py` | 模型普通字段为未确认建议，带本轮原文证据的 explicit_fields 才作为确认修改；先在 shadow 校验，再由 Understanding 同步依赖。旅行人均预算需澄清。 |
| `decision/commands.py` | update_fields / confirm_fields / set_constraint / remove_constraint 返回 refresh，但 Generic Orchestrator 对多数命令不强制该 mode，而由实际差异规划。权重与候选操作返回 rank。 |
| `domains/profile.py` | 已有 retrieval_sensitive_fields / supports_incremental_execution 领域扩展点；没有预算策略扩展点。 |
| `domains/shopping.py` | 检索敏感字段为 category/usage。fixture 按类别及用途召回，未按 budget 截断；固定商品全集不是现实商品市场全集。 |
| `domains/travel.py` | 敏感字段为 departure/days。当前是目的地比较，不生成完整行程。fixture 为上海出发演示费用/交通；其他出发地删除相关属性及 Evidence，不能视为已核实费用。 |
| `domains/comparison.py` | source_and_rank 搜索、合并 manual、验证证据，将未硬筛选候选保存 candidatePool，再排序。rerank 从池恢复候选，保留来源并重算硬过滤。 |
| `providers/candidates.py` | CandidateSearchResult 只有候选、来源、证据、SearchRun、警告；无覆盖元数据。Fixture 返回声明集合全部条目，Manual 从 state 恢复，Composite 合并。 |
| `providers/search.py` | 每次构造请求，携带原目标、当前字段、最新消息、criteria、constraints，明确当前字段覆盖原目标。结果来自有次数限制的 Web 搜索，不能证明穷尽检索范围。 |
| `agents/stages.py` | 理解/澄清后规划；FULL/REFRESH 召回，RERANK 复用，EXPLAIN_ONLY/WHAT_IF 跳过正式候选执行。已有 Execution Plan Trace、候选池摘要与执行后数量。 |
| `orchestration/generic.py` | message/command 在变更前捕获执行基线；命令仅 diet/full/显式刷新/重新比较强制 mode；保存、receipt 和 revision 在既有事务中完成，异常 rollback。 |
| `decision/ranking.py`、`decision/validation.py` | 现有硬过滤拒绝非法数值/缺失预算，最终校验推荐引用和主推荐硬约束，失败上抛。可复用，不需要另建排序器或事务。 |
| `decision/source_snapshot.py`、`services/trace.py` | 每轮保存是否检索/复用及原因；Trace 保留执行模式、路径、候选数和失败回滚状态。 |

## 关键调用链与数据流

### 自然语言

message → load / replay / assert revision → capture_execution_baseline → 更新请求 context → StageRunner → Intent(规则及模型字段修改) → Understanding(sync_dependencies) → blocking clarification → plan_execution → source_and_rank 或 rerank → Critic → Explanation → validate_recommendation → persist / receipt / commit。

### 命令

command → 捕获基线 → apply_command → skip_interpretation（非 full）→ 必要领域澄清 → 同一 plan_execution → 相同执行与提交链。

预算来自：确认 conversationFields、已确认模型纠正、确认模型建议的命令、直接 set_constraint，以及兼容历史约束。仅比较字段无法发现直接修改 price/budget 硬约束；仅比较字段数值也无法区分建议与确认。不同来源的硬约束可能同时存在，实际有效上限应取有效数值上界交集，不能因字段清空而误删用户独立约束。

### 刷新与复用

REFRESH → _search 按 fixture/web/auto 调用 Provider → merge manual → EvidenceValidator → 保存完整 candidatePool → rank → sync evidence。

RERANK → 原 candidatePool → rank（最新 constraints）→ sync evidence。旧预算硬筛选不会直接删掉池内候选，因此固定全集可以安全复用；Web 请求本身可能只取旧预算附近商品，池内最高价不能证明覆盖。

Web 请求无旧查询缓存：刷新会重建当前字段和约束。原 user_goal 仍可能保留初始预算，已有 override 声明可复用，需 mock transport 断言最新条件进入真实请求体。

## 实测与现有测试

用内存 DecisionState（预算 5000、price 硬上限、非空候选池）运行实际 patch_fields + plan_execution：

| 修改 | 当前结果 | 目标差距 |
| --- | --- | --- |
| 5000 → 4000 | rerank，price=4000 | 路径符合购物收紧目标 |
| 5000 → 8000 | rerank，price=8000 | 覆盖未知时仍复用，可能漏掉新预算商品 |
| 5000 → None | rerank，预算字段约束已移除 | 覆盖未知时仍复用旧池 |

运行研究基线（禁用字节码与 pytest 缓存）：

`.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_execution_workflow.py tests/test_multiturn_replan_regression.py tests/test_general_conversation.py tests/test_decision_canvas.py tests/test_candidate_search_productization.py`

结果：45 passed，272 个既有 datetime.utcnow 弃用警告，耗时 92.71 秒。没有运行全量测试；未修改产品代码，未新增预算优化测试，不能据此宣称优化完成。

已有覆盖：最小执行路径、空池、类别刷新、权重复用、显式刷新、预算替换与取消、未确认模型建议、幂等/revision、持久化异常回滚、What-if 隔离、Travel 澄清和来源快照。

缺失覆盖：覆盖不足时的预算扩张、可信覆盖复用、首次设置预算、约束来源交集、同轮反馈 mode 绕过、实际新商品进入池、搜索/排序中途异常后的预算和结论一致性。

## 差距和风险

1. 规划器只判断 changed/not changed，没有方向或候选覆盖，预算放宽与撤销总是普通重排。
2. state.source、SearchRun、候选 Evidence 证明来源，不证明检索覆盖充分；当前没有可复用的覆盖字段。
3. requested rerank 早返回可能绕过同轮预算/类别变化；显式刷新和 What-if 的既有语义又必须保护。
4. 多来源约束和未确认建议不能与 conversationFields.budget 简单画等号；非法数值不应当成无限预算。
5. 旅行 Web 搜索携带总预算，可能按预算生成不同方案，收紧也可能需要新方案，不能套用购物固定商品过滤规则。
6. REFRESH 会更新 sources/evidence 为新候选集；RERANK 应保持原来源及时间，不为覆盖信息伪造新 Evidence。
7. 手工候选和排除记录必须经实际多轮测试保护；只断言 ExecutionMode 不足。
8. 既有未提交变更涉及检索与持久化，实施时需再次检查 diff，以当前工作区为基线。

## 可复用能力和约束

复用 execution baseline、字段同步、Provider 选择/回退、硬过滤、推荐校验、Trace 节点、来源快照、registry 注入、SQLite 测试 fixture 和事务，不增加新 Agent、网络依赖、表、UI 或公开请求/响应必填字段。

覆盖必须由受控 Provider 实现声明并与本次检索绑定；不接受模型返回的自称 complete、不接受候选最大价格推导、不接受仅有 source.mode=fixture 的旧状态。旧状态缺证据时保守刷新。

## Plan 需要决策的问题

- 预算字段变化与实际硬上限变化如何合并；非法和非普通上界约束如何保守处理。
- 可信覆盖的最小结构、作用域及失效条件；Provider 声明与 State 持久化放置点。
- Shopping 与 Travel 的刷新规则和安全优先级。
- 内部 ExecutionPlan 的诊断增量与 Trace 计划/结果数量区分。
- 回归矩阵、mock Search Provider 的真实性以及错误注入阶段。
