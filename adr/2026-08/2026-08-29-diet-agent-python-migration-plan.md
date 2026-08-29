# Choice Agent V2 迁移实施计划

## 1. 项目目标

在 D:\Code\AI Coding\choice-agent-v2 新建一个 Python 多 Agent 项目：

- 完整迁移 diet-agent 的现有架构、业务功能和数据。
- 将 Java、Spring Boot、MyBatis 实现改写为 Python。
- 保留多 Agent 设计、编排流程、Trace、反馈和评估能力。
- 在不改变饮食业务范围的前提下，引入 choice-agent 的通用决策思想。
- 将饮食实现为通用决策系统的第一个领域模块。
- 不修改 diet-agent 和 choice-agent 中的任何文件。

## 2. 成功标准

- 原 diet-agent 的主要用户流程在 V2 中全部可用。
- 所有后端业务由 Python 实现，不依赖原 Java 服务运行。
- 多 Agent 分工、编排和调用轨迹真实存在。
- 推荐排序可重复、可解释、可追踪。
- 饮食模块与通用决策内核分离。
- 两个原项目没有任何文件变化。
- 所有新增内容仅位于 choice-agent-v2。

## 3. 第一阶段范围

必须迁移：

- 饮食意图识别；
- 多轮会话与会话状态；
- 槽位提取、合并与澄清；
- 单餐推荐；
- 多餐计划；
- “换一个”“排除刚才结果”等推荐调整；
- 个人餐食库和公共餐食库；
- 餐食增删改查；
- 候选项搜索、过滤、评分和排序；
- 健康风险识别与保护回复；
- 推荐结果生成；
- 用户反馈；
- 请求 Trace、运行记录和标签；
- Agent 评估；
- 原数据库结构、种子数据和提示词表达的业务规则；
- 原前端全部主要使用页面。

第一阶段不做：

- 旅行、购物、职业等新领域；
- 用户系统、付费、部署和生产级权限体系；
- 与迁移无关的 UI 重做；
- 对原项目进行清理、重构或提交；
- 无必要的新业务功能。

## 4. 技术架构

建议基线：

- API：FastAPI；
- 数据模型：Pydantic；
- 数据访问：SQLAlchemy；
- 数据迁移：Alembic；
- 默认数据库：SQLite；
- 可切换数据库：MySQL 或 PostgreSQL；
- 测试：Pytest；
- 前端：优先保持原功能和交互，不把界面重设计作为迁移目标；
- Agent 框架：先验证 AgentScope Python 的适配性，业务协议不与具体框架绑定。

系统分层：

~~~text
API / Web UI
    ↓
Application Services
    ↓
Multi-Agent Orchestrator
    ↓
Agents + Deterministic Decision Engine
    ↓
Domain Plugins
    ↓
Repositories / Database / Model Providers
~~~

## 5. 多 Agent 设计

核心 Agent：

- IntentAgent：识别领域、请求类型和当前用户意图。
- UnderstandingAgent：提取目标、候选项、约束、偏好和评价标准。
- ClarificationAgent：判断信息是否充分并生成必要追问。
- CandidateAgent：从个人库、公共库等数据源获取候选项。
- PlanningAgent：处理多餐计划和组合型决策。
- AdjustmentAgent：处理换一个、排除、修改条件等请求。
- CriticAgent：检查候选、证据、约束和结果是否存在问题。
- ExplanationAgent：生成首选、备选及权衡解释。
- RiskAgent：处理过敏、疾病、极端饮食等风险。
- EvaluationAgent：离线或人工触发评估 Agent 运行质量。

Orchestrator 负责：

- 根据意图选择 Agent；
- 维护共享决策状态；
- 控制执行顺序、分支、重试和回退；
- 防止 Agent 越权修改状态；
- 记录每次执行的输入、输出、耗时、错误和模型信息。

多 Agent 不代表每个步骤都调用大模型。普通 Python 服务负责数据库访问、规则判断、硬约束、数值计算、排序和状态持久化。

## 6. 通用决策模型

引入统一的 DecisionState：

~~~text
decision_id
session_id
domain
intent
user_goal
constraints
criteria
candidates
evidence
clarifying_questions
recommendation
risk_flags
excluded_candidates
agent_runs
revision
status
~~~

Choice Agent 思想映射：

- 饮食槽位 → 决策偏好或领域属性；
- 忌口、过敏、健康限制 → 硬约束；
- 口味、菜系、心情 → 软偏好；
- 健康、便利、匹配度 → 评价标准；
- 餐食 → 候选项；
- 餐食信息及来源 → 证据；
- 匹配评分 → 多标准确定性评分；
- 推荐回复 → 首选、备选、排除原因和权衡解释。

Agent 状态写入边界：

- Understanding Agent 可以补充结构化理解，不能直接决定排名；
- Research/Candidate Agent 可以增加候选和证据，不能覆盖用户硬约束；
- Critic Agent 只能提出问题或修正建议，不能静默替换最终结果；
- Decision Engine 负责过滤和排序，不能生成不存在的候选及证据；
- Explanation Agent 只能解释已确认的排序和证据。

## 7. 饮食领域插件

DietDomain 独立提供：

- 饮食槽位模型；
- 饮食意图扩展；
- 餐食候选数据源；
- 饮食约束规则；
- 饮食评分标准；
- 健康风险规则；
- 饮食提示词；
- 单餐推荐和多餐计划工具；
- 饮食领域评估数据。

保留现有槽位：

~~~text
meal_time
mood
scene
health_goal
cuisine
taste
convenience
~~~

未来新增领域时，不修改决策内核，只增加新的领域插件。第一阶段不会实际创建其他领域。

## 8. 确定性决策引擎

推荐流程：

1. 应用硬约束，排除明确不符合的候选项。
2. 对候选项进行领域规则检查。
3. 根据软偏好和评价标准计算得分。
4. 计算数据或证据完整度。
5. 应用排除历史和本轮调整条件。
6. 生成稳定排序、首选和备选。
7. 交给 Critic Agent 检查。
8. 由 Explanation Agent 解释已有结果。

大模型不得直接覆盖硬约束或篡改计算排名。迁移初期保留旧槽位匹配结果作为兼容基线，再通过显式配置启用新的多标准评分，避免无法定位推荐差异。

## 9. 数据迁移

迁移以下表对应的业务数据：

- 会话；
- 消息；
- 餐食；
- 槽位选项；
- 推荐反馈；
- 请求 Trace；
- Trace 标签；
- 评估记录。

实施方式：

- 在 V2 中建立新的 Python ORM 模型；
- 保留旧字段的业务含义；
- 增加通用决策状态、Agent Run 和 Evidence 表；
- 编写一次性导入工具读取旧数据库导出数据；
- 种子数据独立存放，可重复初始化；
- 不直接修改旧数据库。

## 10. API 与前端兼容

第一阶段优先保持旧接口语义：

- 会话创建；
- 饮食聊天；
- 个人餐食管理；
- 公共餐食查询；
- 槽位选项；
- 推荐反馈；
- Trace 查询与标记；
- Agent 评估。

可以在内部增加通用决策 API，但旧饮食流程不能因通用化而失效。是否完全保留旧 URL 和响应字段，需要在实施前通过接口清单确认。

前端保留：

- 首页；
- 饮食聊天；
- 推荐卡片；
- 个人餐食库；
- 公共餐食库；
- Trace 管理；
- 评估页面。

## 11. 计划目录和受影响文件

以下为计划结构。具体文件可在骨架阶段按已批准技术选型微调；任何重大变化需要先更新本 Plan。

~~~text
choice-agent-v2/
├── AGENTS.md
├── README.md
├── CHANGELOG.md
├── pyproject.toml
├── .env.example
├── alembic.ini
├── adr/2026-08/
├── src/choice_agent/
│   ├── main.py
│   ├── config.py
│   ├── api/
│   ├── agents/
│   ├── orchestration/
│   ├── decision/
│   ├── domains/diet/
│   ├── models/
│   ├── repositories/
│   ├── services/
│   ├── providers/
│   ├── prompts/
│   └── web/
├── migrations/
├── scripts/
└── tests/
~~~

计划文件职责：

- pyproject.toml：Python 版本、运行依赖、开发依赖和工具配置。
- .env.example、config.py：数据库、模型、日志和运行参数。
- main.py、api/：应用入口、错误处理和兼容 API。
- agents/：各 Agent 的结构化输入输出、提示词绑定和执行器。
- orchestration/：状态图、分支、重试、回退和 Agent 调度。
- decision/：约束、标准、候选、证据、评分和稳定排序。
- domains/diet/：饮食模型、规则、数据源、评分、风险和领域工具。
- models/、repositories/：ORM 模型和持久化边界。
- services/：会话、聊天、餐食、反馈、Trace 和评估业务服务。
- providers/：模型供应商及外部能力的可替换接口。
- prompts/：从旧项目迁移并结构化管理的提示词。
- web/：迁移后的前端资源或服务端页面。
- migrations/：数据库版本迁移。
- scripts/：种子初始化和旧数据导入工具。
- tests/：单元、集成、API、编排和端到端测试。
- README.md：本地运行、配置和架构说明。
- CHANGELOG.md：按 AGENTS.md 记录实际完成的重要变化。

两个原项目的任何文件均不在受影响文件列表中。

## 12. 实施阶段

### 阶段 A：冻结基线

- 清点两个原项目的功能、接口、数据表、页面和提示词；
- 建立迁移对照表和验收清单；
- 记录现有关键请求及响应，作为行为基线；
- 确认 Agent 框架、前端承载方式、数据库默认值和 API 兼容级别。

### 阶段 B：创建 Python 骨架

- 建立配置、日志、数据库、API 和测试结构；
- 定义模型供应商接口；
- 定义 Agent、工具、领域插件和编排器协议。

### 阶段 C：迁移数据层

- 实现 ORM 模型、Repository 和数据库迁移；
- 导入餐食及槽位种子数据；
- 验证个人库、公共库、消息和 Trace 数据。

### 阶段 D：迁移决策内核

- 实现约束、标准、候选项、证据和排序模型；
- 复刻现有槽位匹配结果；
- 加入硬约束、软偏好和可解释评分。

### 阶段 E：迁移多 Agent 流程

- 依次实现意图、理解、澄清、推荐、调整、计划、风险和回复 Agent；
- 实现 Orchestrator 分支、重试和回退；
- 实现完整 Agent Run Trace。

### 阶段 F：迁移 API 和前端

- 对齐原接口行为；
- 迁移全部主要页面；
- 接通聊天、餐食库、Trace、反馈和评估流程。

### 阶段 G：验证与收尾

- 运行单元、集成、API 和端到端测试；
- 对比新旧项目关键场景结果；
- 验证多轮会话、排除、风险和失败回退；
- 补充运行文档、环境变量示例和迁移说明。

## 13. 兼容性和破坏性变更评估

- 原项目保持不变，因此不会对旧系统产生代码级破坏。
- V2 是独立运行的新系统，不与旧 Java 进程共享运行状态。
- Python ORM 与旧 MySQL Schema 不保证物理结构完全一致，但业务字段应可映射。
- 新的通用决策状态和证据模型会扩展旧数据结构。
- 新评分模式可能改变候选排序，因此必须保留旧算法对照和回归样例。
- 模型输出可能因供应商或模型变化而不同，结构化状态和确定性排序必须降低这种差异。
- 旧 API 的兼容程度需要在阶段 A 固化；未确认前不删除或更名任何拟迁移能力。

## 14. 风险和边界情况

- 个人餐食库为空时，应提示补充或允许切换公共库。
- 候选项全部被硬约束排除时，不得强行推荐。
- 用户条件互相冲突时，应澄清或说明无解。
- “换一个”必须排除本会话已展示结果，并处理候选耗尽。
- 多餐计划需要避免重复并检查组合约束。
- 健康风险场景必须保守，不生成医疗诊断或危险饮食建议。
- 模型超时、限流、无密钥或结构化输出失败时，需要显式错误、重试或可解释降级。
- Agent 之间的状态并发更新必须使用 revision 或等价机制防止覆盖。
- Trace 不应记录模型密钥或其他敏感配置。
- 导入脚本必须幂等或能够检测重复数据，且不得写回旧数据库。

## 15. 验证方案

必须覆盖：

- 普通饮食推荐；
- 信息不足时的澄清；
- 个人库为空；
- 个人库和公共库切换；
- 换一个及排除历史结果；
- 多餐计划；
- 硬约束过滤；
- 健康风险请求；
- Agent 调用失败与回退；
- 会话恢复；
- Trace 完整性；
- 用户反馈；
- 评估执行；
- 数据导入；
- 相同状态下排序稳定。

验证层级：

- 单元测试：领域规则、约束、评分、状态转换和解析；
- Agent 合约测试：每个 Agent 的输入输出 Schema 和越权保护；
- 集成测试：数据库、Repository、Orchestrator 和模型替身；
- API 测试：成功、错误、空状态和兼容响应；
- 端到端测试：聊天、餐食库、Trace、反馈和评估主要页面；
- 新旧对照测试：使用固定样例比较意图、槽位、候选和推荐排序；
- 最终检查：git diff、静态检查、测试、构建和 Todo 对照。

## 16. 注意事项与技术折衷

- 迁移优先于扩展。
- 业务等价优先于界面重做。
- 多 Agent 保留，但确定性逻辑不交给大模型。
- 通用化不能破坏饮食业务。
- Agent 框架可以替换，业务协议必须稳定。
- 先以旧算法建立兼容基线，再引入新的评分维度。
- SQLite 便于本地启动，但生产数据库兼容需要单独验证。
- 每完成一个独立模块进行局部验证，最终再执行完整验证。
- 实施中若发现重大设计变化，暂停实现并更新本 Plan 重新 Review。

## 17. 交付物

- 完整的 choice-agent-v2 Python 项目；
- 饮食领域插件；
- 多 Agent 编排系统；
- 通用决策引擎；
- 数据库模型与初始化数据；
- 旧数据导入工具；
- API 和前端；
- 单元、集成及端到端测试；
- Trace 和评估功能；
- 开发运行说明；
- 新旧功能迁移对照表；
- 已知差异与后续扩展说明。

## Todo

- [x] 冻结 diet-agent 功能、API、数据、页面和提示词基线。
- [x] 确认 Agent 框架、前端方案、默认数据库和 API 兼容级别。
- [x] 创建 Python 项目骨架、配置、日志和测试基础设施。
- [x] 定义通用 DecisionState、Agent 合约和领域插件协议。
- [x] 迁移数据库模型、Repository、种子数据和旧数据导入工具。
- [x] 实现兼容旧行为的饮食槽位匹配与排序。
- [x] 实现硬约束、软偏好、评价标准、证据和确定性决策引擎。
- [x] 实现 Intent、Understanding、Clarification 和 Candidate Agent。
- [x] 实现 Planning、Adjustment、Critic、Explanation 和 Risk Agent。
- [x] 实现 Orchestrator 的分支、重试、回退、revision 和 Trace。
- [x] 迁移会话、聊天、餐食、反馈、Trace 和评估 API。
- [x] 迁移首页、聊天、餐食库、Trace 和评估前端页面。
- [x] 完成单元、合约、集成、API 和端到端测试。
- [x] 完成新旧行为对照、数据导入及风险场景验证。
- [x] 检查最终文件范围、更新 README 和 CHANGELOG，并逐项关闭 Todo。

## 实施结果

- 采用项目内类型化多 Agent 运行协议，并通过 OpenAI-compatible Provider 保留模型接入能力。
- 默认 SQLite，启动时幂等创建 Schema 并导入打包的旧饮食 SQL 数据。
- 保持原饮食 API 和静态前端主要行为兼容，新增通用 DecisionState 查询。
- 自动测试 12 项全部通过；真实 HTTP 主流程验证通过。
- 浏览器视觉验收因本机浏览器控制沙箱初始化失败未执行，HTTP 页面入口已验证可访问。
