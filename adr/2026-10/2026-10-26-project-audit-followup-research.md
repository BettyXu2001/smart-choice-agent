# 项目复查四项问题 Research

## 需求与范围

用户要求逐个修复整体检查新增确认的四个问题：运行时 Provider 地址造成 SSRF 风险、Case 模块筛选漏查、Case 可空字段不能清空、时间范围混用时区造成 500。本轮涉及安全边界和接口语义，按大改动处理。Research/Plan 完成并经用户明确批准后实施；当前不修改产品代码。

## ADR 检索与归档

已按运行时配置、Base URL、模块筛选、评估编辑、时区和相关路径检索 ADR：

- `adr/2026-08/2026-08-30-frontend-api-settings-research.md` / `plan.md`：浏览器密钥及 Base URL 经请求头传递，兼容服务端设置。
- `adr/2026-09/2026-09-09-browser-real-api-settings-research.md` / `plan.md`：扩展到模型、搜索、普通及流式接口；没有目标地址访问限制。
- `adr/2026-09/2026-09-05-evaluation-dashboard-research.md` / `plan.md`：模块筛选、Case 编辑、owner 和 revision 约束。
- `adr/2026-10/2026-10-26-project-audit-fixes-research.md` / `plan.md`：上一轮匿名身份、历史筛选、错误序列化与并发修复；已标记实施完成。

没有发现已解决本轮四项问题的记录。上述历史主题已完成，追加会混淆原实施结论，因此新建 followup 文件，不改写旧 Plan。

## 核心文件、调用链与真实行为

### 1. Provider 目标地址

- `static/assets/js/api.js` 从本浏览器设置发送模型/搜索 enabled、API Key、Base URL 请求头。
- `api/routes.py` 的 `get_runtime_model` → `runtime_model_from_headers` 接受地址，派生临时 Settings；饮食、通用决策、普通及流式入口共用该依赖。
- `orchestration/generic.py` / `diet.py` 用 Settings 创建搜索 Provider，模型 Provider 则由运行时依赖创建。
- `providers/model.py` 拼接 `/chat/completions` 后调用 urllib；`providers/search.py` 拼接 `/responses` 后调用 urllib。未限制浏览器传入地址，默认传输会跟随重定向。
- `config.py` 已有管理员配置的模型/搜索地址，无浏览器目标白名单。运行时密钥只在内存中，不能改变这一边界。
- `tests/test_runtime_model_settings.py` 已覆盖独立运行时配置和关闭开关；`test_model_provider_observability.py` 通过替身传输验证响应和用量，需随传输入口调整。

复查通过真实 ASGI 路由建立匿名身份并提交决策，拦截出站函数后确认目标为客户端传入的 `http://127.0.0.1:54321/internal/chat/completions`。没有实际访问内网。

### 2. Case 模块筛选

- `api/evaluations.py:list_cases` 将 module、owner、其他筛选和 limit 传给 `EvaluationRepository.list_cases`。
- `repositories/evaluation_repository.py` 对 owner/status/errorType/q 执行 SQL 筛选，但先排序并 LIMIT，再在 Python 进行模块数组成员判断。
- `static/assets/js/evaluation.js:filterCases` 使用该接口，默认 limit=100，因此匹配项不在最新 100 条内时会丢失。
- modules 是 JSON 列；现有 Python 数组成员判断是精确匹配，可继续复用，避免引入数据库方言专用 JSON 查询。

复查创建较旧 target 模块和较新 other 模块记录，查询 module=target&limit=1 返回空数组，单条 target 仍存在。

### 3. Case 清空字段

- `static/assets/js/evaluation.js:updateCase` 对空 diagnosis/fixPlan/fixVersion 发送 null。
- `EvaluationCaseUpdate` 所有可选更新字段默认 None；Pydantic 可以区分未提供与显式 null。
- `evaluation/service.py:update_case` 使用 exclude_none=True，因此 null 在进入仓库前被删除。
- `db_models.py` 中 actual_behavior、diagnosis、fix_plan、fix_version 可空；title/expected_behavior/error_type/modules/status/case_data 不可空。
- `EvaluationRepository.update_case` 已有原子 revision 条件更新与审计，应直接复用，不能退回无条件 ORM 写入。

复查清空三个已有字段，HTTP 200、revision 从 1 变 2，但三个字段仍为旧值。直接取消 exclude_none 会把不可空列写成 null，必须同时明确更新校验。

### 4. 时间范围

- `api/routes.py:list_traces` 接受两个 datetime 查询参数；`evaluate` 接受 `schemas.py:EvaluationRequest` 的两个 datetime 字段。
- 两入口先直接比较 start/end，再传入 DietRepository 的 Trace 和 Feedback 查询。
- Pydantic 接受带偏移和不带时区的 datetime；混用时 Python 比较抛 TypeError，未转为业务错误。
- 当前数据库时间由 `db_models.py:utcnow` 调用 datetime.now() 生成，实际是服务器本地无时区时间；前端 datetime-local 原样发送无时区文本。
- 同为 aware 的时间即使比较成功，直接传入 SQLite 无时区列也不能依赖其自动处理偏移。

复查 startAt=2026-10-01T00:00:00Z、endAt=2026-10-26T00:00:00，真实 ASGI 路由抛出 offset-naive / offset-aware 比较 TypeError。

## 可复用能力、约束与待决策

- 复用标准库 urllib、现有 Settings、统一依赖、SQLAlchemy 结果迭代、Pydantic exclude_unset、现有 Web fixture、owner/revision 错误映射。不增依赖、不迁移数据库。
- 浏览器任意网关能力与公开服务端安全边界有冲突，Plan 必须明确谁能授权访问哪些地址，不能只做 URL 字符串格式检查。
- 仅校验 DNS 一次无法覆盖连接时重新解析；允许所有公网域名再做预解析不是本轮最小可靠方案。
- 禁止重定向会影响要求重定向的网关，需明确错误及文档；浏览器密钥不能随重定向发送到其他地址。
- 模块流式过滤需要扫描至足够匹配项或数据耗尽；本轮不增加索引、JSON 方言或分页接口。
- 时间方案应兼容现有 naive 输入和本地时间存储；本轮不统一全库 UTC、不改旧数据、不顺带清理 datetime.utcnow 告警。
- 当前工作区已有上一轮未提交修复，实施需精准叠加，不能回滚或覆盖。

## 已执行验证基线

上一轮整体复查：Python 315 passed（1481 条 datetime.utcnow 弃用警告）；Node 身份测试 2 passed；全部产品 JS 语法、diff 空白检查、隔离数据库的真实 HTTP 主流程通过。四个问题另用隔离数据复现。该结果是修改前基线，不能作为本轮实施后的验证结果。
