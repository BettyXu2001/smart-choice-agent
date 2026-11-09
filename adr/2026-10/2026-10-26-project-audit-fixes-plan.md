# 项目检查问题修复 Plan

## 状态

2026-10-26 用户明确回复“执行”，已批准本 Plan。实施与可执行验证已完成；Docker 实构建和真实外部 Provider 验证受环境限制，详见下方结果。

## 目标和成功标准

依次解决身份冒用、Docker 数据库泄漏、校验错误 500、历史漏查、Case 并发覆盖，并修复两处文档问题。

1. 两个独立浏览器自动获得不同身份；篡改 Cookie、X-User-Id 或 localStorage 均不能读取/写入对方数据。
2. 同一浏览器刷新/重启后，在 Cookie 有效且密钥不变时仍能访问自己的数据；普通和流式 API 行为一致。
3. Docker 构建上下文排除运行数据库、SQLite sidecar 和测试运行数据。
4. 普通字段校验和模型 validator 错误均返回可解析的 422 JSON。
5. 历史记录按用户筛选后才应用 limit；其他用户新增任意数量记录不影响当前用户可见条数和排序。
6. 两个请求编辑同一 Case revision 时仅一个成功，另一个得到 409，成功更新的内容及审计记录保留。
7. README 本地链接有效，VPS 安装方式匹配 pyproject.toml。

## 1. 匿名签名会话

### 服务端协议

- 新增 `GET /api/v1/identity`：有效 Cookie 返回当前 userId；缺失、过期或无效 Cookie 时分配全新匿名身份并 Set-Cookie。响应标记 Cache-Control: no-store。
- Cookie 使用版本、userId、签发时间和 HMAC-SHA256 签名；使用 compare_digest 验签，检查格式、时间和有效期。签名有效仍需检查身份保留表存在。
- Cookie 为 HttpOnly、SameSite=Lax、Path=/、host-only；有效期 365 天。默认 Secure=true；本地 HTTP 通过显式配置 Secure=false。
- 业务 user_id 改为从 Request Cookie 解析可信身份；缺失/无效/过期返回 401，绝不 fallback 到 user 1 或请求头。
- 不保留生产 X-User-Id 切换开关。内部 Python 函数和 Repository 可继续接收 uid，保持现有业务测试和 CLI Runner 的整数 owner 模型。
- 对带 Origin 的写请求校验同源，拒绝 Sec-Fetch-Site=cross-site 的写请求；身份签发也拒绝明确跨站请求，防止跨站创建/替换身份。CLI 不带 Origin 时仍需合法 Cookie。
- Cookie 只在 identity 入口签发，业务 API 不隐式分配身份，避免并发首次请求建立多套身份。

### ID 分配与旧数据

- 新增 `anonymous_identity` 表，仅包含整数 user_id 主键和 created_at，用于保留已签发 ID，防止两个浏览器分配到相同 owner。
- 使用 secrets 生成 2..2^31-1 的正整数，兼容当前 Integer 字段和前端数值范围；1 永不签发。
- 分配前排除旧数据中已使用的 ID：SessionRecord.user_id、MealRecord.owner_user_id、FeedbackRecord.user_id、TraceRecord.user_id、UserProfileRecord.user_id、EvaluationCase/Dataset/Run.owner_user_id、DecisionRecord.state_json.ownerUserId；同时检查匿名身份表。唯一键竞争冲突时回滚并有限重试，耗尽返回明确服务错误。
- 旧数据留在数据库中，不自动迁给新访客；旧 owner 缺失数据继续只对内部 user 1 兼容，网页无法冒领。恢复旧数据如有需要另行设计受控迁移。
- 身份新增使用独立短事务，不能提交业务请求未完成的事务。无业务表列迁移。

### 配置和启动

- 新增 CHOICE_AGENT_SESSION_SECRET（至少 32 字节）、CHOICE_AGENT_COOKIE_SECURE（默认 true）。密钥在 lifespan 校验；未配置/太短时启动明确失败，不生成每次重启变化的临时密钥。
- .env.example、README、deploy.md 和 start.bat 同步说明：先设置密钥；本地 HTTP 明确关闭 Secure；公网 HTTPS 保持 Secure。应用不会自动读取 .env，不能让文档暗示已加载。
- Render Blueprint 使用 generateValue 生成稳定部署密钥；Docker/VPS 从环境注入。多实例需共用数据库及同一密钥。
- 不在日志、Trace、响应或 localStorage 输出签名密钥/Cookie 原文。

### 前端和验证脚本

- api.js 新增去重的 ensureIdentity promise；请求封装发送同源 Cookie，移除 X-User-Id，getUserId 返回已初始化的服务端 ID。
- app.js 首次渲染和用户交互前等待身份初始化；初始化失败给出可重试错误，身份成功前不加载私有资源。并发请求复用同一初始化结果。
- index.html 用户 ID 改为只读；移除 setUserId 和旧用户切换事件，保留只读 Debug 展示。
- conversation.js 继续沿用按用户划分的缓存键和过期请求保护；不认领旧 diet.userId 对应会话。
- Cookie 丢失/过期后的业务 401 要求重新初始化并刷新页面，清除内存中的旧身份和当前会话引用；不自动重放旧写请求到新身份。
- scripts/verify_main_flow.py 使用 CookieJar，先访问 identity，再验证业务链路，移除固定 X-User-Id。

## 2. Docker 构建上下文

- .dockerignore 排除 *.db、*.sqlite、*.sqlite3 及对应 -wal/-shm/-journal，并排除 .pytest-runtime 和 .test-tmp。
- 保留 domains/diet/data/*.sql 种子文件；不删除本地数据库，不改变当前业务数据。
- docs/deploy.md 明确运行数据库使用挂载卷/持久路径，镜像不携带本地数据。

## 3. 校验异常响应

- main.py 规范化 errors 列表，剔除或字符串化 ctx 中的异常对象，再交给 jsonable_encoder。
- 保留现有 message、errors 和 HTTP 422 合约；不回显无法序列化的原始输入对象。
- 用真实 ASGI 请求覆盖 required manual assertion，以及普通类型错误、缺失字段和非法 JSON，不能只调用处理器函数。

## 4. 历史查询

- DecisionRepository.list_for_user 使用 SQLAlchemy JSON 整数提取表达式，对 state_json.ownerUserId 在数据库 WHERE 过滤，然后按 updated_at、created_at 和 id 稳定排序并 LIMIT。
- 内部 user 1 加上 owner 缺失/null 的兼容分支；普通匿名 ID 只能匹配自己的明确 owner。
- 保留 visible_to_user 二次检查和旧记录解析能力；不增加 owner 索引列或进行 schema 迁移。

## 5. Case 乐观锁

- update_case 采用单条 WHERE id + owner_user_id + revision 的条件 UPDATE，写入 changes、revision+1、updated_at 和追加审计事件。
- 执行 SQL 前不修改 ORM row，避免 autoflush 发出无条件更新；使用 synchronize_session=False，成功后刷新 row，失败回滚并抛 EvaluationConflictError。
- 用户编辑继续经现有路由返回 409。成功提交前不发布新的 revision 或审计结果。
- 检查自动回归同步调用方：仍要求 result.caseRevision 匹配；竞争冲突时显式记录被跳过的 Case 与原因，保留已完成 Run 结果，不重试覆盖用户新编辑。该冲突记录附在 Run summary 的同步告警中并由 run_response 返回，不能静默忽略。

## 6. 文档和 Changelog

- README 的失效详细文档链接改为已有 docs 资料和 adr 入口；不为链接新增内容空泛的文档。
- VPS 安装命令改为 python -m pip install .，补充 Cookie/密钥、HTTPS 和匿名数据保留说明。
- CHANGELOG.md 新增单个 2026-10-26 日期项，精简记录身份边界和四项修复；不整理历史警告或无关代码。

## 文件清单

| 文件 | 计划修改 |
| --- | --- |
| 新增 `src/choice_agent/auth.py` | 签名、验签、身份分配和同源校验；保持单一小模块，不搭建通用登录框架。 |
| `src/choice_agent/config.py` | 两项会话配置及环境读取。 |
| `src/choice_agent/db_models.py` | 新增匿名身份保留表。 |
| `src/choice_agent/main.py` | 启动配置校验、身份入口/接线、校验错误 JSON 修复。 |
| `src/choice_agent/api/routes.py` | user_id 切换到签名 Cookie。 |
| `src/choice_agent/static/index.html` | 用户身份只读展示。 |
| `src/choice_agent/static/assets/js/api.js` | Cookie 请求、身份初始化和 401 处理。 |
| `src/choice_agent/static/assets/js/app.js` | 异步启动、错误重试、移除 ID 切换。 |
| `src/choice_agent/static/assets/js/conversation.js` | 仅在身份初始化/失效衔接确有需要时修改缓存接入。 |
| `src/choice_agent/repositories/decision_repository.py` | WHERE owner 后 LIMIT，保持 legacy 分支。 |
| `src/choice_agent/repositories/evaluation_repository.py` | 原子 revision 更新与刷新。 |
| `src/choice_agent/evaluation/service.py` | 自动回归同步的显式竞争告警。 |
| `.dockerignore` / `render.yaml` | 排除运行数据、生成稳定签名密钥。 |
| `.env.example` / `start.bat` / `README.md` / `docs/deploy.md` | 启动要求、Cookie 使用、部署及失效引用。 |
| `scripts/verify_main_flow.py` | CookieJar 身份初始化。 |
| 新增 `tests/test_auth.py`、`tests/test_http_errors.py`；现有 history/evaluation/static/config 相关测试 | 覆盖安全边界、HTTP 真实错误、历史漏查和并发覆盖。 |
| `CHANGELOG.md`、本 Plan | 简明记录结果并核对 Todo。 |

## 兼容性和风险

- 有意破坏 HTTP 客户端的 X-User-Id 演示协议；客户端须先拿 Cookie。内部业务 API 的路径、主体和决策响应保持不变。
- 新增身份入口和表；应用启动需要稳定密钥，本地 HTTP 需要显式配置。这些变化必须与文档同步。
- Cookie 丢失、到期或密钥轮换后会成为新访客，旧数据保留但无法通过匿名会话找回。
- 新匿名身份不会认领既有 ID 的历史、个人资料或餐食。
- 公开匿名使用仍可能产生模型/搜索费用；本轮不扩展到账户、计费或限流设计。
- 首次多标签页竞争及过期 Cookie 需回归；前端身份初始化必须早于缓存和请求指纹计算。
- SQL JSON owner 筛选避免漏查，但暂不提供 owner 索引；后续有性能证据再单独迁移。
- 不新增依赖；不顺带处理 datetime.utcnow 弃用告警。

## 验证方案

1. 身份专项：双 CookieJar 隔离；同身份恢复；伪造头、伪造/过期签名、旧 user 1 不可冒领；Secure/HttpOnly/SameSite、跨站写入拒绝；新 ID 碰撞重试；重启同密钥可用、缺密钥启动失败。
2. 普通与流式 API：同一 Cookie 身份贯穿创建、读取、追问、命令、个人资料和历史；无 Cookie 返回 401。用本地隔离数据库完成网页真实行为验证，若浏览器工具不可用需明确列出未验证项。
3. 校验：真实 HTTP/ASGI 层 422 回归，包含异常对象 ctx 的失败分支。
4. 历史：其他用户至少 150 条较新记录、limit 边界、并列时间排序、ownerless 兼容、跨用户详情拒绝。
5. Case：两个独立数据库 Session 均先读同 revision；只允许一方提交，另一方 409；审计不丢、版本只增一次；回归自动同步竞争不覆盖编辑且留下告警。
6. 部署：核对 Docker ignore 规则及 SQL 种子保留；有 Docker 时检查构建镜像内无数据库，无工具时明确未实构建。核对文档本地链接。
7. 各独立单元完成后跑专项测试；全部完成后跑完整 pytest、前端 node --check、git diff --check 和最终 diff。没有配置的 lint/typecheck 不虚报通过。

## 实施与验证结果（2026-10-26）

- 已完成五项修复、前端 Cookie 接入、启动/部署配置、验证脚本、文档链接和 CHANGELOG。
- 未增加依赖；新增 anonymous_identity 表，不迁移既有业务列，不认领旧用户数据。
- `python -m pytest`：314 passed，1481 条既有类型的 datetime.utcnow 弃用警告，无失败。全量收集后补充的匿名 ID 唯一键竞争测试单独运行通过，当前 315 个 Python 测试均有通过结果。
- `node --test tests/frontend_identity.test.cjs`：2 passed，覆盖普通/流式并发初始化、旧 ID 无效、初始化失败重试和 401 不重放写入。
- Python 源码语法、全部产品 JavaScript 语法、Docker ignore/SQL 种子保留及 README/部署文档本地链接检查通过。
- `scripts/verify_main_flow.py` 在独立 `.pytest-runtime/audit-web/browser.db` 服务上通过：Cookie 初始化、饮食会话、推荐、Trace、餐食 CRUD、反馈和评估。
- Edge 真实网页验证：首次身份初始化、资料保存、刷新后身份及内容恢复、只读 ID；撤销隔离测试身份后，保存返回 401，旧内容隐藏且无自动重发；手动刷新后获得新 ID，旧资料不会被新身份继承。
- `git diff` 已逐项审查；最终 `git diff --check` 通过。修改均属于已批准范围，未整理弃用告警或重构无关业务。
- Docker 可执行文件不可用，未实际构建镜像；已核对 COPY 对应的排除规则、Render 配置和部署步骤。未执行真实模型/联网搜索或云端部署，已有 Provider 替身回归随全量测试通过。
- 本轮测试未使用项目根目录的运行数据库；本地测试服务结束后停止。启动正式应用前仍需配置持久密钥；公网 HTTPS 保持 Secure=true。

## Todo

- [x] 实现服务端匿名签名身份、稳定密钥和身份分配碰撞保护，并完成安全边界测试。
- [x] 接入前端普通/流式请求、只读身份、初始化与失效处理，更新验证脚本并验证主流程。
- [x] 修复 Docker 数据库排除并核对部署身份配置。
- [x] 修复校验错误 JSON，验证非法输入返回 422。
- [x] 修复历史查询先过滤后限流，验证默认 limit 下的漏查用例与旧数据兼容。
- [x] 修复 Case 原子乐观锁及自动回归同步竞争处理，验证编辑冲突和审计保留。
- [x] 修复 README/VPS 指令，更新 CHANGELOG 和运行说明。
- [x] 完成全量测试、前端语法、主流程、最终 diff 检查，并记录不能执行的验证项。
