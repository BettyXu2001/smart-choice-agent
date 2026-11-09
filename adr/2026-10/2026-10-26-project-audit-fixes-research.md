# 项目检查问题修复 Research

## 需求和范围

逐项修复 2026-10-26 整体检查确认的五个问题，以及同轮发现的失效文档链接和 VPS 安装指令。用户已选择：公开多人使用，采用匿名签名会话，每个浏览器独立身份，无需注册。

身份边界、部署配置、跨前后端调用链和并发更新均涉及重要设计决策，按大改动执行。本阶段只写 Research / Plan，不修改产品代码。

## ADR 检索与归档选择

- `adr/2026-09/2026-09-05-consumer-navigation-decision-history-research.md` / `plan.md`：定义历史列表、旧 owner 兼容、前端用户 ID 切换。历史 Plan 明确使用多取后过滤的临时方案，是本轮漏查的来源；其用户 ID 请求头约定需要被本轮公开部署安全边界取代。
- `adr/2026-09/2026-09-04-web-deployment-research.md` / `plan.md`：定义 Docker、Render 和 VPS 发布路径。原方案不修改认证或应用逻辑，本轮补充数据库排除和新会话配置。
- `adr/2026-09/2026-09-05-evaluation-dashboard-research.md` / `plan.md`：定义 Evaluation Case、owner、revision 和 API；Research 明确 X-User-Id 只是演示身份，并非生产认证。
- `adr/2026-09/2026-09-04-general-conversation-panel-plan.md`：现有决策命令的 owner、revision 与事务约束，可用于对照 Case 并发更新。

上述记录均属于已完成的历史功能，追加本轮跨主题修复会混淆原决策。新建本轮 Research / Plan，保留历史文档。

## 核心文件和职责

| 文件 | 当前职责及相关行为 |
| --- | --- |
| `src/choice_agent/main.py` | 应用 lifespan、路由挂载、异常响应。校验错误直接交给 JSONResponse。 |
| `src/choice_agent/config.py` | 不可变 Settings 和环境变量读取；尚无签名密钥或 Cookie 配置。 |
| `src/choice_agent/api/routes.py` | 全部业务 API 依赖共用 user_id；当前直接读取可伪造的 X-User-Id。 |
| `src/choice_agent/api/evaluations.py` | 复用 routes.user_id；Case 冲突已有 HTTP 409 映射。 |
| `src/choice_agent/api/decision_stream.py` | 在线程创建独立数据库会话；uid 已由路由传入，可继续复用。 |
| `src/choice_agent/db_models.py` / `database.py` | owner 为整数；create_all 可新增表，已有升级仅补 agent_run 列。 |
| `src/choice_agent/repositories/decision_repository.py` | owner 位于 state_json；先 limit*3 全局截取，再做可见性过滤。Decision 保存已有数据库条件更新。 |
| `src/choice_agent/repositories/evaluation_repository.py` | Case 只在内存比较 revision，ORM 更新不带数据库 revision 条件。 |
| `src/choice_agent/evaluation/service.py` | 用户编辑和回归状态自动同步均调用 update_case。 |
| `src/choice_agent/static/assets/js/api.js` | 普通及流式 fetch 均发送 localStorage 中的用户 ID；可复用两处统一请求封装。 |
| `src/choice_agent/static/assets/js/app.js` / `conversation.js` | 初始化可编辑 ID；会话缓存和异步过期保护依赖 getUserId。 |
| `.dockerignore` / `Dockerfile` | COPY 整个工作目录；未排除运行数据库。 |
| `scripts/verify_main_flow.py` | urllib 主流程验证，固定发送 X-User-Id=7001。 |

## 调用链和数据流

1. 浏览器启动 → initUserField → localStorage 用户 ID → API request/streamRequest → X-User-Id → user_id → Repository owner 条件。
2. 决策创建/消息/命令 → GenericDecisionOrchestrator → DecisionRepository → state_json.ownerUserId；流式入口同样先解析 uid。
3. 历史列表 → list_for_user → 全局按时间取最多 limit*3 → Pydantic 解析 → visible_to_user → 返回。旧 owner 缺失记录只允许内部 user 1。
4. Case 编辑 → EvaluationService.update_case → 读取 Case → 内存校验 → 普通 ORM UPDATE → commit；自动回归同步复用相同仓库函数。
5. 请求校验 → RequestValidationError → error.errors() → JSONResponse；模型 validator 的 ctx.error 可以是异常对象。
6. docker build → .dockerignore 过滤 → COPY → 默认 sqlite:///./choice_agent.db，因而本地运行数据可成为镜像初始数据。

## 已复现问题

- 只指定他人的 X-User-Id 即可读取其 UserProfile；无凭证请求默认访问 user 1。
- 非法 required manual EvaluationAssertion 触发 ValueError；错误处理器再抛 TypeError，HTTP 返回 500 而非 422。
- 一个用户的历史比其他用户最新 150 条记录更旧时，默认 limit=50 返回空，但详情仍可读取。
- 两个 Session 都读到 Case revision=1，先后提交不同 title；两次都成功，最终 title 被覆盖，revision 仍是 2。
- 本地存在 choice_agent.db，Docker ignore 没有匹配它的规则；Git ignore 不控制 Docker build context。
- README 中 PROJECT_OVERVIEW.md 和 EVALUATION.md 不存在；VPS 指令引用的 requirements.txt 不存在。

## 已有可复用能力

- 所有用户业务 API 已统一依赖 user_id；改身份入口即可保留业务 owner 检查。
- 前端 request 和 streamRequest、getUserId、会话缓存命名和异步 generation 保护可继续使用。
- DecisionRepository.save 已用 WHERE id/revision + rowcount 实现冲突控制，可复用其模式。
- EvaluationConflictError 和 API 409 映射已存在。
- JSON owner 字段通过 SQLAlchemy JSON 表达式可在数据库筛选，无需给 DecisionRecord 迁移加列。
- 标准库 hmac、hashlib、secrets、time 可支持签名 Cookie，无需引入认证依赖。
- Base.metadata.create_all 可新增匿名身份保留表，已有业务表无需结构迁移。

## 约束、风险和待决策点

- Cookie 必须由服务端签发；客户端提交的 ID、旧 localStorage、伪造请求头均不能用于认领旧数据。
- 匿名身份不是账户系统：清 Cookie/换设备不能恢复历史；用户已选择无需注册，本轮不实现找回或跨设备同步。
- 必须避免新匿名 ID 与旧用户 owner 冲突。旧 owner 分布在 session、meal、feedback、trace、profile、evaluation 三表和 Decision JSON；不能直接从 1 开始自增。
- 签名密钥需持久稳定，跨进程一致；随机临时密钥会导致重启丢身份，不能作为默认降级。
- 前端必须先完成身份初始化，再使用 getUserId 计算缓存键和请求指纹；初始化失败应显示错误并可重试。
- 自动 Case 状态同步也会遇到真实并发冲突，不能覆盖编辑或静默吞错。
- 不新增登录/注册、管理员角色、配额或限流系统；匿名隔离不限制公开接口对服务端模型额度的使用。
- 检查基线：300 tests passed；1474 条 datetime.utcnow 弃用警告。弃用告警不在本轮修复范围。
- 当前没有 httpx、lint/typecheck 配置或 Docker 可执行文件。HTTP 回归可使用标准库/轻量 ASGI 测试辅助；Docker 实际构建需在可用环境补验证。

Plan 需要明确 Cookie 协议、密钥配置、旧数据边界、新身份分配、前端启动顺序，以及 Case 自动同步遇到冲突时的显式处理。
