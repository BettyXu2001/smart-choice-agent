# Evaluation Dashboard / Bad Case 闭环 Plan

日期：2026-09-05。状态：待用户审查与明确实施批准。
依据：同目录 2026-09-05-evaluation-dashboard-research.md。

## 目标与成功标准

现有评估页升级为五类 17 项指标、整体得分/覆盖率、可比版本差异、失败 Case/Trace、归因、修复版本和 Regression Dataset 的持久化评估中心。

核心验收链：失败结果 → Case → 归因/方案 → 加入固定数据集版本 → 隔离运行当前实现 → 修复版本与回归结果 → 后续失败重新打开。刷新恢复；无数据不造分；示例和真实运行清楚区分。

## 页面设计

沿用原生 JS/CSS 和 mint/pop 主题，保留 /admin/evaluations。

- 总览：版本/数据集选择、运行评估；总分、覆盖率、基线差值、失败/未评测 Case 数；五组指标显示值、方向、分母和定义。
- 运行记录：版本、模式、数据集 hash、配置、状态、通过/失败/错误/未评测；逐轮 expected/actual 和 Trace。
- Bad Case Center：按错误类型、状态、模块筛选和问题搜索；详情含原问题、完整轮次、预期/实际、归因、模块、修改方案、修复版本、回归结果、审计历史。
- Regression Dataset：成员、版本、覆盖指标、可执行性、最近运行；加入前校验输入/断言，修改生成新版本。
- 持续观测：真实历史 Trace 时间窗的请求/Agent 失败、延迟、显式降级；标明来源和样本量，与离线回归分开。提供手动刷新和回归 CLI/失败退出码，可供 CI 或外部定时器调用；本轮不部署常驻调度或外部通知。

保留“旧版 Trace 报告”入口及其口径说明。复用 Trace 详情，支持准确 ID 深链接；隔离回放的 Trace 从结果快照读取。桌面列表/详情并排，移动端顺序布局，支持键盘与焦点恢复。

## 指标 v1

每项保存 id、category、direction、unit、numerator/denominator、value、eligibleCount/evaluatedCount、missingReason、method、失败断言与轮次来源。无适用样本为 not_applicable，证据不足为 not_evaluated，null 不等于 0。金标签人工审核，不能复制当前输出当标准。

| 类别 | 指标 | 分子 / 分母及边界 |
| --- | --- | --- |
| 需求理解 | Intent 准确率 | 匹配金标签操作意图的轮次 / 已标注意图轮次；领域路由另记。 |
| 需求理解 | 约束抽取准确率 | 正确约束断言 / 标注约束断言；检查字段、值、硬软属性、候选归属和额外约束。 |
| 需求理解 | 纠正后状态更新准确率 | 新值生效、旧值移除且归属正确的轮次 / 标注纠正轮次。 |
| 决策质量 | 硬约束满足率 | 满足全部硬约束的推荐 / 可判定推荐；应推荐却为空由金标签断言判失败。 |
| 决策质量 | 排除候选正确率 | 排除集合匹配的轮次 / 有预期集合轮次，检查误排和漏排。 |
| 决策质量 | 推荐稳定性 | 满足稳定断言的重复配对 / 相同输入状态及固定来源配对；稳定样例默认重复 3 次，记录配置。 |
| 决策质量 | 条件变化后的结论敏感性 | 满足预期变化或维持结论的配对 / 标注条件变化配对；不奖励无条件改变推荐。 |
| 解释质量 | 推荐与理由一致率 | 通过关联和已审阅语义断言的回答 / 可完整判定回答；仅结构检查时注明范围，语义未知不记全面通过。 |
| 解释质量 | Evidence 引用有效率 | 存在、归属及原文引用符合来源的引用 / 已检查引用；用户/fixture/web 分明，URL 合法不代表事实真实。 |
| 解释质量 | 无依据事实生成率（低优） | 判为无依据的 claim / 完成来源支持性标注的 claim；默认人工审阅，数字/保证性表述规则仅作辅助。 |
| 解释质量 | 已排除候选误推荐率（低优） | 误推荐已排除候选的轮次 / 有排除记录且最终输出可观察的轮次。 |
| 多轮交互 | 状态保持率 | 无合法编辑且正确保留的断言 / 标注保持断言，含清空保护、事实、排除集合。 |
| 多轮交互 | 用户纠正覆盖率 | 被更新流程处理的纠正目标 / 所有金标签纠正目标；和更新内容正确性区分。 |
| 多轮交互 | What-if 不污染成功率 | 正式业务投影不变的假设轮次 / 可检查假设轮次；忽略消息/revision/Trace/假设 analysis。 |
| 工程可靠性 | LLM 调用失败 Fallback 成功率 | 调用失败后返回有效降级结果且通过状态断言的请求 / 发生模型调用失败的请求；校验拒绝单列，禁用模型不算失败。 |
| 工程可靠性 | Agent 执行失败率（低优） | FAILED AgentRun / 全部实际 AgentRun；另显请求失败率。 |
| 工程可靠性 | 平均响应时间（低优） | 请求 durationMs 总和 / 有耗时请求；标明模式与失败样本，不能累加阶段耗时代替。 |

总分：成功率直接使用，错误率取 1-rate；类别内可评测质量指标等权，再对有数据类别等权，乘 100。延迟单独展示，不引入任意 SLA 分。强制附已评测指标数/16、类别覆盖和样本量；覆盖不满标“部分评估”，全空为 null。版本差值要求相同有效样本集合，不宣称统计显著。

新评估器独立于旧 EvaluationAgent，旧字段和兼容测试保持。v1 不新增通用 LLM Judge；保留旧版 Judge，新的自由文本语义/claim 用人工审阅并绑定输出 hash，重新执行输出变化后旧标注失效。

## 执行、版本与隔离

历史诊断读取已有输出，regression 调当前 Generic/Diet orchestrator 在独立临时 SQLite 中运行。Case 含 setup、messages/commands、逐轮断言、领域、固定来源和故障场景；严格 schema 和白名单解释执行，禁止 eval/exec、任意代码/路径或 URL。

默认离线 provider + fixture；固定 stub 支持 timeout、非法引用/候选等故障，结果明确标 mock。真实模型是单独显式选择，使用现有 provider、固定数据源；密钥只留内存，不写 Trace/配置/报告。

每个 run 保存 versionLabel、可获取的 build/commit（否则 unknown）、datasetVersion/hash、evaluatorVersion、配置指纹、模式/model、起止时间和状态。不按日期猜版本。比较允许构建不同，但数据集、评估器、模式/model/来源配置及指标有效样本必须相同；否则给出不可比原因。上一版本为最近不同 versionLabel 且可比的完成记录，也可手动选择。数据集扩充后需重跑基线。

v1 有上限同步运行：默认最多 20 Case、每 Case 10 轮、重复至多 3 次；总体时长预算和 provider 超时有效。先保存 running，再逐 Case 保存；error 显式记录并继续其他 Case。中断保留未完成状态，不展示完整得分；进程恢复时识别遗留运行。requestId + fingerprint 防重复，冲突返回 409。CLI 支持分批并标明范围，不引入队列。

临时 DB 的 Trace/AgentRun/状态投影在清理前复制到结果快照，finally 清理。业务投影含条件、候选事实、排除、权重、正式推荐，排除无关历史；在 mutation 前捕获 before，成功持久化后记录 after。失败路径保留明确事件，不改变业务事务。版本对比不自动 checkout 旧代码。

## 存储与 API

新增四表，保留旧列和接口：

- evaluation_case：owner/revision、原问题/轮次、expected/actual 快照、来源 run/trace、错误类型、归因/模块/方案、修复版本、状态及审计事件。
- evaluation_dataset：owner、名称、版本、hash、不可变 Case 输入/断言快照，owner/name/version 唯一。
- evaluation_run：owner、requestId/fingerprint、构建/配置/数据集快照、状态/汇总/时间。
- evaluation_result：run/case/version/repetition、逐轮输出/Trace/断言/人工审阅、指标和 error，run/case/repetition 唯一；审阅有 revision 并触发汇总更新。

启动 create_all 新建表，测试已有库无损兼容。手动导入明确标识的示例数据集，实际运行后才产生得分；历史归因援引 ADR，缺历史失败 Trace 显示不可用，不构造虚假历史结果。

新增独立 router /api/v1/evaluations：dashboard；runs 创建/列表/详情/结果；cases 创建/列表/详情/更新；datasets 创建版本/列表/详情；results/{id}/review。复用既有身份、DB、runtime model 依赖。所有关联对象检查同 owner，分页限额；422 不合法，404 不存在或越权，409 revision/幂等冲突。保留 /api/v1/diet/evaluations。

Case 错误类型：理解、约束处理、候选获取、Evidence、排序、解释不一致、多轮状态丢失、Fallback 异常。

生命周期：open → diagnosed → fix_pending → awaiting_regression → verified；只有已加入数据集且同 Case 版本/修复版本的全部必需断言可判定并通过才能 verified。修改版本是声明，不能凭填写即认证已修复。后续同一 Case 版本失败可 reopened，旧结果不能覆盖更新结果；保留各版本历史。重复加入去重。归因和代码修复由人审查，页面不自动改代码。

## 受影响文件

路径相对仓库根目录。

| 文件 | 修改内容 |
| --- | --- |
| src/choice_agent/evaluation/schemas.py、metrics.py（新增） | 断言/指标类型、17 项计算、缺失/覆盖/可比性。 |
| src/choice_agent/evaluation/runner.py、fixtures.py、cli.py（新增） | 隔离回放、固定故障 provider、初始多轮样例、CLI 和预算。 |
| src/choice_agent/evaluation/service.py（新增） | 运行/Case/数据集/人工审阅生命周期编排。 |
| src/choice_agent/repositories/evaluation_repository.py（新增）、db_models.py | 新表、owner 过滤、事务/唯一性/revision。 |
| src/choice_agent/api/evaluations.py（新增）、main.py | 新路由和注册，复用 routes.py 依赖，旧 evaluate 不改。 |
| src/choice_agent/evaluation/observations.py（新增）、services/trace.py | 精简版本化业务投影及显式降级观测，避免嵌套历史/密钥。 |
| src/choice_agent/orchestration/generic.py、orchestration/diet.py | create/message/command 的前后投影，保持事务/幂等。 |
| src/choice_agent/decision/assistance.py、agents/diet.py | 在既有模型分支补调用成功/失败/校验拒绝/降级事件，不改业务策略或旧评估器。 |
| src/choice_agent/static/assets/js/evaluation.js（新增）、api.js、app.js、static/index.html | Dashboard/Case/数据集界面、API、路由/事件桥接、脚本注册、旧报告入口；切换身份清空状态并忽略过期响应。 |
| src/choice_agent/static/assets/css/app.css | 作用域内页面样式，复用主题变量和移动布局。 |
| tests/test_evaluation_metrics.py、test_evaluation_runner.py、test_evaluation_api.py（新增） | 指标、回放隔离、版本/权限/生命周期测试。 |
| tests/test_decision_assistance.py、test_orchestrator.py | 原业务和观测事件兼容回归。 |
| README.md、docs/migration-matrix.md、CHANGELOG.md | 使用方法、指标边界和实际变化。 |

## 兼容、风险与折衷

新增表/API，无新增依赖、不换框架；旧报告口径不变，新页明确区分。标注内容转义、JSON 体积有上限。人工语义评测不能伪装成自动事实核验。回归成功不证明历史版本失败。新发现业务 Bug 记录为 Case，不顺手扩大修复范围。同步运行有时长与中断限制，持久化部分结果并通过 CLI 分批。缺资料历史 Case 需补输入才可回放。不重构现有演示身份系统。

## 验证方案

1. 实施前记录 git 状态并运行全量 pytest 基线，使用临时 DB，不操作 choice_agent.db。
2. 各指标正/负/缺数据/零分母；误排、空推荐、配对、人工标注失效、相反方向及覆盖聚合。
3. 真实多轮回放：Offer 稳定→解释 A→B 两小时→半小时纠正；硬约束排除；学习背景纠正；购物 What-if 后正式编辑；非法引用/候选/数字/超时。
4. 正式库 session/decision/trace 不变；错误、中断、重复请求、部分结果、资源清理正确。
5. API：失败转 Case→归因→数据集→修复版本回放→verified→失败 reopened；缺断言不能 verified；跨 owner、revision、幂等冲突验证。
6. 旧饮食评估、聊天/命令/反馈/Trace 与 Generic API；旧 SQLite 新增表后旧数据不变。
7. 浏览器：空/加载/错误/刷新；版本不可比；指标→失败→准确 Trace；Case 保存和加入回归；双主题、390px/桌面、键盘/焦点、无溢出或 JS error；身份切换不泄露旧异步结果。
8. 全量 pytest、compileall、node --check、git diff --check 和范围复核；更新同日 CHANGELOG。真实模型未实测明确说明，mock 不当线上质量证明。

## Todo

- [ ] 记录基线，新增 schema/表/repository，验证旧库和 owner/revision。
- [ ] 补齐状态投影、模型失败/降级观测并回归原业务。
- [ ] 完成 17 项指标、人工审阅、缺失/总分/覆盖/版本对比及测试。
- [ ] 完成隔离回放、样例数据集和 CLI，验证正式库隔离及多轮故障场景。
- [ ] 完成 run/Case/dataset API，验证幂等/权限/修复验证/重开。
- [ ] 完成 Dashboard、Bad Case Center、数据集管理、Trace 联动和旧报告入口。
- [ ] 完成浏览器和全量自动验证，复查 diff，更新文档与 CHANGELOG，说明剩余边界。