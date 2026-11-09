# 项目复查四项问题修复 Plan

## 状态与目标

2026-10-26：用户明确回复“实施”，已批准本 Plan。按下列顺序执行，每项完成专项验证后再继续。

成功标准：

1. 浏览器不能使模型/搜索访问任意目标；可信地址仍可使用浏览器自带密钥；重定向不能绕过地址授权。
2. Case 模块筛选先匹配再应用数量上限，不漏掉较旧记录，仍保证 owner 隔离和精确模块成员匹配。
3. Case 未提供的字段不变，显式 null 能清空可空字段，不可空字段的 null 返回 422；保留原子 revision 和审计。
4. 两个时间入口接受现有无时区输入，拒绝混用时区并返回可解析 400；两个带偏移时间按真实时刻查询，不产生 500 或偏移误查。

## 1. Provider 地址授权与重定向

### 设计

采取部署者控制的精确 Base URL 白名单，不开放任意公网 URL，也不新增 DNS 预解析或自定义 TLS 连接层。

- `Settings` 新增浏览器模型与搜索地址附加白名单，分别对应 `CHOICE_AGENT_MODEL_BASE_URL_ALLOWLIST`、`CHOICE_AGENT_SEARCH_BASE_URL_ALLOWLIST`，采用 JSON 字符串数组；空值表示没有附加项，错误配置明确报错。
- 模型默认允许 `https://api.deepseek.com`、`https://api.openai.com/v1`；搜索默认允许 `https://api.openai.com/v1`。各自管理员设置的 model_base_url/search_base_url 也为可信地址；附加列表用于管理员授权自定义网关。
- 白名单条目为完整 Base URL（包括路径），不支持域名通配符或前缀匹配。统一规范化 scheme/hostname 大小写、默认端口及尾斜杠；路径精确匹配，不解码或合并任意路径。拒绝 userinfo、query、fragment、控制字符和不支持的 scheme；拒绝含混的反斜杠、路径点段及编码绕过形式。
- 默认及附加白名单仅接受 HTTPS。管理员通过原有服务端 Base URL 明确配置的 HTTP/内网端点视为运维授权，保留本地模型兼容性；浏览器不能自行增加该授权。此信任边界必须写入部署文档，不宣称对管理员恶意配置提供隔离。
- 只有 enabled 且带 key 的对应运行时配置才检查目标；关闭或无 key 时沿用现有 fallback，不因无效的闲置输入报错。未提供或空白 Base URL 继续沿用对应服务端地址。
- 拒绝的运行时地址在依赖层返回 400，错误提示联系部署者配置可信地址，不返回密钥或完整敏感 URL；普通、流式、capabilities 入口行为一致。
- 新增小型 `providers/http.py`，提供模型和搜索共用的禁止重定向 opener。生产 HTTP 传输对所有 3xx 明确失败，不自动发送下一跳请求；禁止只验证首跳后继续跟随。urllib 其余 TLS、超时和错误机制保留。
- URL 授权/规范化放在同一小模块复用；不建立通用网络框架，不把 API Key 或完整请求头写入日志。
- 设置页给两处 Base URL 增加简短提示：自定义地址需部署者授权；不增加管理面板或暴露白名单查询接口。

### 边界与折衷

这是服务端配置的目标授权机制。可信域名的 DNS/网络和运维配置属于部署边界；不声称能防止可信供应商或部署配置被攻陷。需要跳转的网关必须填写最终地址。保留服务端本地模型能力意味着管理员可明确授权内网目标，但公开访客不能自行选择其他内网目标。

## 2. Case 模块筛选

- 复用现有 owner/status/errorType/q SQL 条件和精确 Python 数组成员判断。
- 无 module 时保留 SQL LIMIT；有 module 时使用有序结果分批迭代，逐行匹配，收满 limit 后停止，数据耗尽则返回已有匹配项。
- 排序沿用 updated_at 降序并补 id 稳定次序，避免并列时间顺序不定。
- 不先截取固定倍数，不使用 JSON 文本子串 LIKE；不为了此问题迁移字段或引入方言专用查询。
- 最坏情况下扫描当前 owner 的全部候选记录；通过批量迭代避免一次性加载全部对象。后续有性能证据再设计索引与分页。

## 3. Case 更新与清空

- Service 改为 exclude_unset=True，并排除 revision。保留显式 null，仅对数据库可空的 actual_behavior/diagnosis/fix_plan/fix_version 接受清空。
- `EvaluationCaseUpdate` 校验显式传入的 title/expected_behavior/error_type/modules/status/case_data 不能为 null，返回 422；省略它们仍合法。title/expected_behavior 的非空要求与创建语义一致。
- modules 用 [] 清空，case_data 用合法结构更新；本轮不新增删除 Case 能力。
- 继续调用已有原子 update_case，不改 owner/revision/verified 状态约束；清空仍写审计并只递增一次 revision。
- 前端现有发送 null 的行为保留，无需重写表单。

## 4. 时间参数

- 在 routes.py 内增加两个入口共用的小函数，验证和规范化范围，不新建时间处理框架。
- 两个参数均 naive：保留现有服务器本地时间语义。
- 一个 aware、一个 naive：返回 400，提示开始与结束时间需采用一致的时区格式。
- 两个参数均 aware：按偏移表示的真实时刻转换为服务器本地时间，再移除时区以匹配现有数据库存储；不直接去掉偏移。
- 规范化后检查 start < end；相等或倒序仍返回现有业务 400。
- list_traces、evaluate 的 Trace 与 Feedback 查询均使用规范化后的范围；评估响应 startAt/endAt 保留用户原始格式，不修改请求对象。
- 不改变存储、服务器时区、前端 datetime-local 或既有数据库数据；全库 UTC 迁移另立任务。

## 受影响文件

| 文件 | 计划改动 |
| --- | --- |
| `src/choice_agent/config.py` | 两类附加白名单及 JSON 配置读取、校验。 |
| 新增 `src/choice_agent/providers/http.py` | 精确地址规范化/授权、小型禁止重定向传输封装。 |
| `src/choice_agent/providers/model.py`、`search.py` | 共用禁止重定向传输，保留现有输出解析和可观测性。 |
| `src/choice_agent/api/routes.py` | 运行时地址检查、400 映射、共用时间范围规范化及两个入口接线。 |
| `src/choice_agent/repositories/evaluation_repository.py` | 模块匹配完成后限量、稳定排序及分批迭代。 |
| `src/choice_agent/evaluation/schemas.py` | 更新字段显式 null 与非空值校验。 |
| `src/choice_agent/evaluation/service.py` | 区分字段省略和清空，复用原子更新。 |
| `src/choice_agent/static/assets/js/app.js` | 两个 Base URL 字段的授权说明。 |
| `.env.example`、`README.md`、`docs/deploy.md` | 白名单配置、管理员信任边界、重定向与时间格式说明。 |
| `tests/test_runtime_model_settings.py`、`test_model_provider_observability.py`、`test_candidate_search_productization.py` | 适配授权配置/传输替身，保持正常配置与用量回归。 |
| 新增 `tests/test_provider_http.py` | URL 绕过、授权及真实本地重定向拒绝验证。 |
| `tests/test_evaluation_api.py`、`test_evaluation_service.py`、`test_http_errors.py` | 模块漏查、清空/省略、null 校验、时间范围和 owner/revision 回归。 |
| `CHANGELOG.md`、本 Plan | 追加当日条目，逐项记录完成与验证结果。 |

## 兼容性与风险

- 请求路径、响应结构、身份及数据库 schema 不变；不增依赖。
- 有意收紧浏览器任意目标能力，现有自定义网关需部署者加入白名单；禁止 Provider 3xx 自动跳转。
- Case 非空列的显式 null 从忽略变为 422，可空列 null 从忽略变为清空。
- 混用时区从 500 变为 400；两个 aware 输入按数据库本地时间正确查询。已有 naive 输入保留服务器本地语义，因此浏览器与服务器跨时区问题不在本轮全面解决。
- 检查并保护现有未提交修复；不更新之前已完成的审计 Plan，不顺便重构其他 API。

## 验证方案

1. 地址：默认/服务器/附加可信端点、尾斜杠与端口规范化、关闭或无 key fallback；未授权公网、loopback、IPv6、private/link-local 地址、userinfo、相似域名、路径前缀/点段/编码等绕过均拒绝，拒绝时出站调用为零。用现有 Web fixture 覆盖匿名 Cookie + 普通/流式/capabilities；在本地测试服务器覆盖 301/302/303/307/308，无第二跳请求。保留密钥不进入 Trace/响应的回归。
2. 模块：大量较新无关 Case，旧目标记录仍返回；limit、空结果、精确成员、其他组合筛选、并列时间和跨 owner；不只验证两条数据的演示用例。
3. 更新：真实 ASGI 请求清空三个表单字段及 actualBehavior；省略字段不变，modules=[] 可清空；不可空列 null 返回 422且 revision/数据不变；成功清空保留审计，过期 revision 409。
4. 时间：两个入口分别覆盖 naive、Z、不同显式偏移、混合格式、相等/倒序；插入固定 Trace/Feedback 验证偏移规范化后查询正确，不只检查状态码。使用固定偏移/时间替身避免依赖执行机器时区。
5. 每项专项测试完成后更新 Todo；末尾执行完整 pytest、Node 身份测试、全部产品 JS 语法、隔离数据库真实 HTTP 主流程、git diff --check 与最终 diff 检查。
6. 不调用付费外部 Provider；Docker 实构建、真实供应商可用性、不可执行的浏览器行为需如实记录。未配置 lint/typecheck 不虚报通过。

## 实施与验证结果（2026-10-26）

- 四项修复均按本 Plan 完成，配置/设置页说明及当日 CHANGELOG 已同步。未新增依赖、未迁移数据库，保留此前未提交的修复。
- Provider 专项 45 passed；Case API 15 passed；时间与饮食回归 36 passed。拒绝的运行时目标没有出站请求，真实本地重定向测试没有第二跳；模块测试覆盖 205 条记录、精确成员和 owner 隔离；清空和时间范围测试通过真实 ASGI 路由验证持久化/查询结果。
- 完整 `python -m pytest -p no:cacheprovider --basetemp .pytest-runtime/followup-full`：373 passed，1481 条既有 datetime.utcnow 弃用警告，523.37 秒。使用项目 `.venv/Scripts/python.exe`，未使用根目录运行数据库。
- `node --test tests/frontend_identity.test.cjs`：2 passed；全部产品 JavaScript 的 node --check、Python AST 语法检查、README/部署文档本地链接检查通过。
- 在本地独立临时数据库启动真实 Uvicorn HTTP 服务，执行 `scripts/verify_main_flow.py` 主流程通过；服务已停止，临时主流程数据库已清理。
- 最终 diff 与新增文件已检查，git diff --check 通过，无调试日志、未完成占位代码或本轮计划外改动。
- 未执行真实浏览器交互及真实外部模型/搜索调用，因此不宣称供应商端到端可用性；没有 Docker 可执行文件，未实构建镜像。项目未配置 lint/typecheck，不虚报通过。
- 安全边界：部署者负责可信端点及其 DNS/网络配置；自定义网关须明确授权且使用最终地址。时间仍采用既有服务器本地存储语义，本轮没有全库 UTC 迁移。

## Todo

- [x] 修复运行时 Provider 地址授权和重定向绕过，完成安全与兼容专项测试（45 passed）。
- [x] 修复 Case 模块筛选顺序，验证旧记录、limit、精确匹配和 owner 隔离（专项通过）。
- [x] 修复 Case 可空字段清空与省略语义，验证 422、409、审计和持久化结果（Case API 15 passed）。
- [x] 修复两个时间入口，验证混用 400 和带偏移范围的真实查询结果（时间与饮食回归 36 passed）。
- [x] 同步配置/设置提示/文档及当日 CHANGELOG。
- [x] 完成全量测试、JS、真实 HTTP 主流程和最终 diff 审查，记录未验证项。
