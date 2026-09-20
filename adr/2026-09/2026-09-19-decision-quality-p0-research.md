# 决策质量 P0 改进 Research

日期：2026-09-19

## 当前需求和研究范围

本次覆盖三个 P0：选择后的结果闭环、推荐质量与不确定性表达、只询问可能影响结论的问题。它们共同修改 DecisionState、通用比较流程、历史 API 与 Decision Canvas，属于大改动。本阶段只记录 Research 和 Plan，不修改产品代码。

## ADR / 历史方案检索

已按最终选择、反馈闭环、Evidence、置信度、What-if、敏感性、追问和评估检索 adr/。相关记录：

- 2026-09-05-consumer-navigation-decision-history-*：已实现历史中心和 DecisionState.outcome，并预留决策复盘。
- 2026-09-05-evidence-presentation-*：已区分来源、引用和 claim 状态，但没有结论级质量摘要。
- 2026-09-04-conversation-decision-assistance-*：已支持上下文理解、最多一个问题、理由与代价，但模型问题仍可在排序前触发。
- 2026-09-05-decision-canvas-what-if-*：已有正式状态与假设状态隔离，可复用重排思路。
- 2026-09-06-evaluation-regression-dataset-*：已有稳定性、敏感性和多轮回归框架。
- 2026-08-29-choice-agent-v1-borrowed-ideas-todo.md：提出过证据质量摘要，尚未完成产品化。

这些记录均已完成或主题边界不同，因此新建本组 Research / Plan，并复用既有类型、排序、What-if、历史与测试能力。

## 核心文件及职责

- src/choice_agent/schemas.py：DecisionState、Candidate、ScoreContribution、Evidence、Recommendation、DecisionOutcome。Outcome 当前只有候选、标签、原因和时间。
- src/choice_agent/decision/ranking.py：硬约束过滤和加权排序；候选保存 raw value、标准化分、权重和 evidence IDs。
- src/choice_agent/decision/evidence.py：校验来源和引用；链接有效不等于事实已独立核实。
- src/choice_agent/domains/comparison.py：排序前 clarify，随后检索、Evidence 校验、排序与解释。
- src/choice_agent/domains/generic.py、travel.py、shopping.py：定义候选、出发地/天数、类别等前置条件。
- src/choice_agent/decision/assistance.py：生成当前分析、理由、代价与问题。
- src/choice_agent/decision/what_if.py：生成缺失信息和假设场景；Generic 仍含固定 Offer 启发式。
- src/choice_agent/agents/stages.py、orchestration/generic.py：控制 Clarification 到 Ranking 再到 Explanation 的顺序。
- src/choice_agent/api/routes.py：历史详情和 outcome 保存/清除，包含 owner 与 revision 校验。
- src/choice_agent/repositories/decision_repository.py、db_models.py：完整状态保存在 DecisionRecord.state_json。
- src/choice_agent/static/assets/js/conversation.js：Decision Canvas。
- src/choice_agent/static/assets/js/app.js、api.js：历史详情和 outcome 表单/API。
- src/choice_agent/evaluation/*：17 项离线指标，暂无真实结果满意度。

## 关键调用链和数据流

通用决策：

用户消息 → GenericDecisionOrchestrator → conversation understanding → ComparisonProfile.needs_clarification / clarify → CandidateProvider + EvidenceValidator → GenericRankingEngine → assistance.explain → what_if.missing_info / scenarios → state_json → Decision Canvas。

阻塞追问发生在候选检索和排序之前，无法利用前两名差距和敏感性判断问题价值。

最终选择：

历史详情 → PUT outcome → owner / revision / candidate 校验 → DecisionState.outcome → DecisionRepository.save → state_json。

保存后没有 review、满意度、实际结果或待复盘状态。

## 当前实现逻辑

候选 score 是 criterion 标准化分的加权平均，表达当前规则下的相对匹配程度，不是推荐正确概率。它没有单独反映缺失字段、排名差距、权重扰动是否换榜、来源类型或是否依赖单一 criterion。

领域 needs_clarification 负责前置必需信息，conversation_question 也可触发 clarify。进入 clarifying 后会清空推荐并停止候选阶段。排序后的 missing_info 只展示提示，其中部分是 Offer 固定启发式。

DecisionOutcome 是 DecisionState 的可选嵌套字段。新增带默认值的 review 可以沿用 JSON 持久化和 revision，不需要数据库列迁移。

## 已有可复用能力

- ScoreContribution 和 ranking diagnostics 足以计算数据覆盖、分差和有限敏感性。
- rerank 与 What-if 的隔离原则可以复用。
- Evidence 能区分数据已提供与来源可追溯，但不能证明事实正确。
- JSON 持久化和 revision 可复用到 outcome review。
- 历史详情与 Decision Canvas 已有入口。
- 回归数据可覆盖换榜、无效追问和旧状态兼容。

## 潜在问题和隐患

- 稳健度不能叫准确率或 AI 置信度，只表示指定扰动下的排名稳定性。
- 单独看分差不够；权重和缺失值变化可能换榜。
- 大量随机扰动会制造虚假精度，应使用有限、可解释、确定性的场景。
- 用户输入和 fixture 可作为数据，但不等于外部事实核验。
- 前置必需信息仍要阻塞；信息价值策略适用于初步排序之后。
- 排序后问题若设置 clarifying 会清空推荐。
- 改选时旧复盘不能继续挂在新 outcome 上。
- 没有后台调度或通知基础设施，第一版只能在历史页面显示待复盘。
- 工作区已有 CHANGELOG.md、app.js、demo.js 和 test_frontend_static.py 的未提交修改，实施时必须精确合并。

## 与需求相关的约束

- 旧 state_json 必须继续读取，新增字段必须有默认值。
- 不新增依赖和数据库列。
- 保留 API、owner 与 revision 语义。
- 前置必需问题与排序后可选问题必须分开。
- 质量摘要由确定性逻辑计算，LLM 不得自报稳健度。
- 复盘不能自动改写用户资料或权重。
- Diet 现有必填追问、安全和反馈流程保持兼容；第一阶段只接入通用 ComparisonProfile。

## Plan 阶段需要决策的问题

- 单次最新复盘还是多次时间序列。
- 稳健度的有限扰动集合和产品阈值。
- 排序后问题如何进入 currentAnalysis 而不触发 clarifying。
- 无后台任务时如何提示待复盘。
- 离线指标与未来线上结果指标的边界。

## Research 结论

三个 P0 作为同一项决策质量闭环改动，分成结果复盘、确定性质量摘要、信息价值追问三个可独立验证的单元。第一版采用单次最新复盘、有限扰动稳健度、排序后非阻塞关键问题，并保留领域必需追问，不引入依赖、后台任务或数据库迁移。