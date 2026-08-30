# 前端 API 设置 Plan

## 目标和成功标准

目标：在前端增加设置入口，允许用户配置 OpenAI-compatible 模型 API；当浏览器侧未配置模型 API Key 时，首页明确显示演示模式，并让通用决策继续进入现有 demo 工作台。

成功标准：

- 顶部导航出现“设置”入口。
- `#/settings` 页面可配置 API Key、Base URL、主模型、轻量模型和是否启用模型。
- 设置保存到本浏览器，刷新后仍可读取。
- 未配置 API Key 或关闭启用开关时，首页显示演示模式状态。
- 已配置并启用时，饮食聊天和评估请求可把模型配置通过请求头传给后端。
- 模型密钥不进入 `ChatRequest.context`、Trace、AgentRun、数据库或 URL。
- 现有 `.env` 配置方式继续可用。
- 通用 demo、饮食聊天、个人餐食、Trace、评估页面不回归。

## 设计

### 前端设置模型

在 `api.js` 中新增浏览器模型设置：

```js
{
  enabled: true,
  apiKey: "",
  baseUrl: "https://api.openai.com/v1",
  mainModel: "gpt-5",
  lightModel: "gpt-5-mini"
}
```

保存 key：`choiceAgentModelSettings`。

提供函数：

- `DietApi.getModelSettings()`
- `DietApi.saveModelSettings(settings)`
- `DietApi.clearModelSettings()`
- `DietApi.hasConfiguredModel()`

`apiKey` 存在且 `enabled === true` 时视为浏览器侧模型已配置。

### 请求头传递

`DietApi.request()` 在浏览器侧模型已配置时添加：

- `X-Choice-Agent-Model-Enabled: true`
- `X-Choice-Agent-Model-Api-Key: <apiKey>`
- `X-Choice-Agent-Model-Base-Url: <baseUrl>`
- `X-Choice-Agent-Main-Model: <mainModel>`
- `X-Choice-Agent-Light-Model: <lightModel>`

不把这些值写入请求 body、query string 或 `context`。

### 后端运行时配置

在 `routes.py` 增加依赖函数，根据请求头生成运行时 settings / provider：

- 如果请求头中存在有效 API Key 且 enabled 为 true：基于应用全局 settings 派生一个临时 `Settings`，覆盖 `model_api_key`、`model_base_url`、`main_model`、`light_model`，设置 `enable_llm=True`，并构造临时 `OpenAICompatibleProvider(runtime_settings)`。
- 否则继续使用全局 `settings` 和全局 `provider`，保持 `.env` 部署兼容。

该临时配置只在当前请求内使用，不落库、不进入 Trace。

### 设置页路由

在 `index.html` 顶部导航增加 `设置`，指向 `#/settings`。

在 `app.js` 路由表增加 `/settings -> renderSettings()`。

设置页包含：

- 当前模式状态：已配置为“模型模式”，未配置为“演示模式”。
- 启用模型开关。
- API Key 密码输入框。
- Base URL 输入框。
- 主模型输入框。
- 轻量模型输入框。
- 保存按钮。
- 清除按钮。

页面文案明确：API Key 仅保存在当前浏览器；未配置时通用决策使用本地演示数据；饮食助手仍可使用本地规则链路。

### 首页模式提示

`renderGeneralHome()` 增加状态提示：

- 未配置浏览器模型：显示“演示模式”，说明通用问题将进入本地演示工作台。
- 已配置且启用：显示“模型配置已启用”，说明饮食链路会尝试使用该模型配置增强理解和解释。

不改变当前非饮食问题进入 demo 的事实，因为后端尚无通用 Agent API。

### 错误处理

前端：localStorage 读写失败时返回默认未配置状态，并 toast 提示保存失败；保存时裁剪空白字符；Base URL 为空时用默认值；API Key 清除后立即回到演示模式状态。

后端：请求头 enabled 非 true 时不使用浏览器设置；API Key 为空时不构造浏览器 Provider；Base URL 为空时沿用全局默认值；模型名为空时沿用全局默认值。

## 受影响文件

- `src/choice_agent/static/index.html`：增加“设置”导航入口。
- `src/choice_agent/static/assets/js/api.js`：增加模型设置 localStorage 读写，并在请求头附加浏览器模型配置。
- `src/choice_agent/static/assets/js/app.js`：增加 `/settings` 路由、设置页渲染、保存、清除事件和首页模式提示。
- `src/choice_agent/static/assets/css/app.css`：增加设置页表单、状态提示和响应式样式。
- `src/choice_agent/api/routes.py`：增加请求头解析和每请求临时 Provider；`chat()`、`evaluate()` 使用运行时 settings / provider。
- `tests/test_orchestrator.py` 或新增 `tests/test_runtime_model_settings.py`：覆盖请求头配置解析或密钥不进入 Trace 的关键行为。
- `README.md`：补充前端设置说明。
- `CHANGELOG.md`：记录新增前端 API 设置和演示模式提示。

## 兼容性和破坏性变更评估

API 路径不变；现有请求 body 不变；`.env` 配置方式保留；未配置浏览器模型时前端通用入口仍使用 demo；饮食聊天仍能在无模型时通过本地规则运行；新增请求头为可选，不影响旧客户端。无计划内破坏性变更。

## 风险和边界情况

- 浏览器 localStorage 保存 API Key 存在本机浏览器暴露风险，需明确提示。
- 请求头经过浏览器开发者工具可见，这是浏览器侧配置不可避免的边界。
- 后端 Trace 当前不记录 headers，本方案依赖该事实；不能后续把 headers 加入 Trace。
- 服务端 `.env` 已启用模型时，即使浏览器未配置，饮食链路仍可能使用服务端模型 Provider。页面应避免承诺“全站无模型调用”，只表达“浏览器未配置时通用决策进入演示模式”。
- 非饮食通用决策即使配置了模型，也仍进入 demo，因为当前没有通用后端 API。

## 验证方案

自动验证：

- `python -m compileall -q src scripts`
- `python -m pytest`
- `node --check src/choice_agent/static/assets/js/api.js`
- `node --check src/choice_agent/static/assets/js/app.js`
- `node --check src/choice_agent/static/assets/js/demo.js`

行为验证：

- 静态检查 `index.html` 包含设置导航。
- 静态检查 `app.js` 包含 `/settings` 路由。
- 使用 Node VM 或简单静态断言验证设置保存/清除函数。
- 通过后端测试验证浏览器模型请求头不会进入 Trace。
- 若本地 dev server 可启动，访问首页和设置页做 HTTP 资源检查。

Diff 检查：检查最终 `git diff`，确认没有计划外文件修改、调试输出、临时日志或密钥样例。

## 技术折衷

- 不新增后端持久化设置接口，避免把 API Key 存入数据库。
- 不把模型配置放入请求 body，避免 Trace 泄露。
- 不把通用 demo 改造成真实在线通用 Agent，避免扩大到通用 Orchestrator / Search Provider。
- 保留 `.env` 作为生产/服务端配置方式，前端设置只作为浏览器侧便捷覆盖。

## Todo

- [x] 在 `api.js` 增加浏览器模型设置读写和请求头注入。
- [x] 在 `index.html` 和 `app.js` 增加设置导航、路由和设置页。
- [x] 在首页增加当前模式提示。
- [x] 在 `app.css` 增加设置页样式并检查响应式布局。
- [x] 在 `routes.py` 增加运行时模型设置解析和临时 Provider。
- [x] 补充测试，覆盖请求头配置启用及密钥不进入 Trace。
- [x] 更新 `README.md` 和 `CHANGELOG.md`。
- [x] 执行 diff 检查、自动验证和可行行为验证。

## 验证结果

- `node --check src/choice_agent/static/assets/js/api.js`：通过。
- `node --check src/choice_agent/static/assets/js/app.js`：通过。
- `node --check src/choice_agent/static/assets/js/demo.js`：通过。
- `python -m compileall -q src scripts`：通过。
- `python -m pytest`：31 passed。
- `git diff --check`：通过。