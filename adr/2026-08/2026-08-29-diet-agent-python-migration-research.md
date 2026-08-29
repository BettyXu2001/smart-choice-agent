# Diet Agent Python 迁移 Research

## 1. 当前需求与研究范围

目标是在全新目录 `choice-agent-v2` 中，用 Python 重写现有 `diet-agent`，完整保留其业务能力和多 Agent 设计，并吸收 `choice-agent` 的通用决策思想。

本阶段只记录现状和约束，不实施产品代码。以下两个项目保持只读：

- `D:\Code\AI Coding\diet-agent\diet-agent`
- `D:\Code\AI Coding\choice-agent`

所有未来新增产品代码仅允许写入 `D:\Code\AI Coding\choice-agent-v2`。

## 2. 已研究项目

### 2.1 diet-agent

当前项目采用 Java 21、Spring Boot、MyBatis、MySQL 和 AgentScope Java Starter。静态前端由 HTML、CSS 和 JavaScript 实现，并由 Spring Boot 同一服务托管。

核心能力包括：

- 饮食意图识别；
- 多轮会话和槽位合并；
- 信息不足时的澄清；
- 单餐推荐与多餐计划；
- “换一个”等推荐调整；
- 个人餐食库和公共餐食库；
- 槽位匹配、候选过滤与排序；
- 健康风险保护；
- 消息、会话、反馈和 Trace 持久化；
- Trace 管理和评估页面；
- 基于数据库脚本初始化的餐食及槽位数据。

### 2.2 choice-agent

当前项目采用 Next.js、React、TypeScript、Zod 和 OpenAI SDK，核心定位是通用决策 Agent。

可复用的设计思想包括：

- 通用 `DecisionState`；
- 候选项、硬约束和软偏好；
- 评价标准及权重；
- 证据、来源、置信度和时效性；
- 确定性的约束检查与排序；
- 理解、澄清、搜索、比较和决定的状态流程；
- 推荐、备选、排除原因和权衡解释；
- LLM 理解与普通代码决策相结合。

`choice-agent` 当前主要使用浏览器本地存储，持久化和领域业务能力弱于 `diet-agent`，因此不适合作为直接复制的后端实现。

## 3. diet-agent 核心文件及职责

### 后端与配置

- `pom.xml`：Java、Spring Boot、MyBatis、MySQL 和 AgentScope 依赖。
- `src/main/resources/application.yml`：数据库、服务端口、模型及 AgentScope 配置。
- `DietOrchestratorService.java`：会话锁、意图分流、多 Agent 调用、澄清、推荐、计划、调整、风险和 Trace 的核心编排。
- `DietChatController.java`：饮食对话 API 入口。
- `MealRankService.java`：根据饮食槽位重合度计算并排序候选餐食。
- `SlotBundle.java`：餐时、心情、场景、健康目标、菜系、口味和便利性槽位模型。
- MyBatis Mapper、Service 和 Model：会话、消息、餐食、反馈、Trace 和评估的数据访问及业务封装。

### 提示词

- `diet/prompts/intent.txt`：意图识别。
- `diet/prompts/clarify.txt`：澄清判断与问题生成。
- `diet/prompts/recommend-response.txt`：单餐推荐回复。
- `diet/prompts/plan-response.txt`：多餐计划回复。
- `diet/prompts/evaluation-judge.txt`：评估判断。

### 数据和前端

- `db/diet_db.sql`：数据表、槽位选项和餐食种子数据。
- `static/index.html`：静态应用入口。
- `static/assets/js/api.js`：饮食 API 客户端。
- `static/assets/js/app.js`：聊天、餐食库、Trace 和评估等页面逻辑。
- `static/assets/css/app.css`：当前界面样式。

## 4. 关键调用链和数据流

普通推荐流程：

```text
POST /api/v1/diet/chat
  -> DietChatController
  -> DietOrchestratorService.dietChat
  -> 加载或创建会话并加锁
  -> 记录用户消息和 Trace
  -> Intent Agent 识别意图
  -> 合并历史槽位和当前槽位
  -> Clarification Agent 判断是否需要追问
  -> 从个人库或公共库搜索候选餐食
  -> MealRankService 计算槽位匹配分
  -> Response Agent 生成推荐说明
  -> Risk Guard 检查健康风险
  -> 保存助手消息、会话状态和 Trace
  -> 返回 ChatResponse
```

推荐调整流程会读取上一轮推荐，排除已推荐候选项后重新检索和排序。多餐计划流程使用独立的计划提示词和生成逻辑。健康风险意图走保守回复分支，不进入普通推荐。

## 5. 当前数据模型

主要持久化对象包括：

- `diet_sessions`：会话和当前状态；
- `diet_messages`：用户与助手消息；
- `meal_item`：个人或公共餐食及其槽位属性；
- `diet_slot_option`：槽位可选值；
- `recommend_feedback`：推荐反馈；
- `diet_request_trace`：一次请求中的运行轨迹。

饮食槽位包括：

```text
meal_time
mood
scene
health_goal
cuisine
taste
convenience
```

## 6. 已有可复用能力

### 可直接迁移的业务资产

- 数据库种子数据和字段语义；
- 提示词中的意图、澄清、推荐、计划和评估规则；
- API 的业务语义；
- 会话、反馈、Trace 和评估流程；
- 前端页面的信息架构和主要用户流程；
- 推荐调整、来源模式和空个人库等边界行为。

### 需要重写的实现

- Java、Spring Boot 和 MyBatis 代码；
- AgentScope Java 调用方式；
- Java DTO、Entity、Service 和 Controller；
- 与 Java 枚举及异常体系绑定的逻辑；
- 静态前端与后端的耦合方式。

### 可吸收的 choice-agent 设计

- 将饮食槽位映射为约束、偏好和评价标准；
- 将餐食映射为通用候选项；
- 引入证据对象和来源信息；
- 使用确定性引擎执行硬约束过滤和多标准评分；
- 将推荐解释限制在已计算的排名和证据范围内；
- 建立可扩展的领域插件协议。

## 7. 潜在问题和隐患

- “完整迁移”涉及后端、前端、数据、提示词和管理能力，范围较大，必须使用功能对照表防止遗漏。
- Java AgentScope 与 Python Agent 框架的接口和行为未必一一对应，不能机械翻译。
- 现有槽位重合度算法简单；升级评分逻辑时可能改变推荐顺序，需要定义兼容基线。
- 旧数据主要面向 MySQL；新项目若默认 SQLite，需要处理 JSON、时间和主键差异。
- 健康风险属于高风险输出，不能只依赖生成模型，需保留明确的规则和保护路径。
- 多 Agent 调用可能增加延迟、成本和失败点，需要按意图动态选择 Agent，而不是每次调用全部 Agent。
- `choice-agent` 中部分页面和决策逻辑存在未提交改动，只能读取理解，不能复制覆盖或修改。
- 两个原项目的测试覆盖不完全，迁移前需要用代表性请求建立行为基线。

## 8. 与需求相关的约束

- 必须使用 Python 重写后端及 Agent 编排。
- 必须保留真实的多 Agent 设计。
- 饮食是第一个完整领域，第一阶段不实现其他业务领域。
- 多 Agent 负责理解、澄清、研究、审查和解释；硬约束与数值排名由确定性代码负责。
- 旧项目和旧数据库保持只读。
- 所有新代码、文档和数据文件只能放在 `choice-agent-v2`。
- 进入实施前必须完成 Plan Review，并获得用户明确的实施授权。

## 9. Plan 阶段需要确定的问题

- Python Agent 编排采用 AgentScope Python、状态图框架还是轻量自研编排层。
- 前端是迁移为 Python 模板应用，还是采用独立 Web 前端；第一阶段需以功能等价为准。
- 新数据库默认使用 SQLite 还是 MySQL，以及旧数据导入的目标格式。
- 旧 API 是否要求路径和响应结构完全兼容，还是只要求业务能力兼容。
- 推荐算法第一版采用旧算法兼容模式，还是立即切换为新的多标准评分。
- 模型供应商第一版支持范围及无模型密钥时的降级行为。

## 10. Research 结论

本次工作属于架构、技术栈、核心数据结构、数据迁移和业务流程均发生变化的大改动。可行路径是以 `diet-agent` 为功能基线进行 Python 等价重写，同时在内部引入 `choice-agent` 的通用决策状态和确定性决策引擎。饮食能力应通过领域插件接入通用内核，多 Agent 协作和 Trace 应作为系统一级能力保留。