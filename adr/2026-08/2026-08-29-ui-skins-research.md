# UI 多套皮肤 Research

## 当前需求和研究范围

用户希望 `choice-agent-v2` 支持多套 UI 皮肤：第一套保留当前浅绿色风格，第二套参考 `D:\Code\AI Coding\eat-what` 的年轻、鲜亮风格。

本次研究范围限定为前端静态 UI 主题能力，不修改推荐算法、接口、数据模型或后端流程。

## ADR 检索结果

已检索 `adr/` 中与 `theme`、`skin`、`皮肤`、`主题`、`UI`、`style`、`颜色`、`green`、`浅绿`、`eat-what` 相关的记录。

相关候选：

- `adr/2026-08/2026-08-29-home-general-decision-mode-research.md`：记录当前视觉主题偏绿色、轻食感较强，并把视觉主题调整作为后续问题。
- `adr/2026-08/2026-08-29-home-general-decision-mode-plan.md`：明确当次不做整体视觉主题重构。
- `adr/2026-08/2026-08-29-eat-what-selector-integration-research.md`：研究 `eat-what` 的选择策略、历史冷却和选择洞察，明确不直接迁移 React 前端和 PWA 能力。
- `adr/2026-08/2026-08-29-eat-what-selector-integration-plan.md`：明确不把 `eat-what` 的 UI 直接搬入当前项目，避免引入 React 技术栈。

判断：本次是新的 UI 皮肤主题能力，追加到上述文档会造成历史语义混乱，因此新建 Research / Plan。

## 核心文件及职责

### choice-agent-v2

- `src/choice_agent/static/index.html`：静态页面入口，引入 CSS、API JS 和应用 JS，包含固定顶栏、导航、用户 ID 输入和主渲染容器。
- `src/choice_agent/static/assets/css/app.css`：当前 UI 的主要视觉来源；`:root` 定义全局颜色、阴影、圆角等 CSS 变量，各组件通过变量复用主题。
- `src/choice_agent/static/assets/js/app.js`：静态前端的路由、状态和 HTML 模板渲染，当前没有主题状态、主题切换控件或 localStorage 持久化。
- `CHANGELOG.md`：记录用户可感知功能变化。新增皮肤切换属于用户可见功能，实施后应追加记录。

### eat-what

- `Eat-What/src/App.tsx`：React + Tailwind 主界面，视觉核心是鲜亮底色、黑白强对比、粗体标题、粗描边、强投影、圆形结果盘、胶囊控件和图标按钮。
- `Eat-What/src/components/ResultCard.tsx`：黑底结果卡片，白字，使用主题色点缀概率和图标。
- `Eat-What/src/components/InsightsPanel.tsx`：半透明白色面板、黑色细边框、圆角、粗体小标题、胶囊预设按钮。
- `Eat-What/src/constants.ts`：分类色较丰富，包含红、黄、绿、蓝、紫等鲜亮颜色。

## 关键调用链和数据流

`index.html` 加载静态资源后，`app.js` 获取 `#app`、`#toast`、`#userIdInput`，初始化内存 `state`，绑定 `hashchange`、点击、提交事件，并根据 `location.hash` 渲染对应页面。

各页面模板复用统一 class，例如 `.btn`、`.card`、`.section`、`.badge`、`.chip`。多数视觉样式通过 CSS 变量集中控制：`--bg`、`--surface`、`--surface-soft`、`--primary`、`--primary-dark`、`--primary-soft`、`--accent`、`--text`、`--muted`、`--border`、`--shadow` 和圆角变量。

因此新增皮肤可以优先通过 `data-theme` 或 class 覆盖 CSS 变量实现。

## 当前实现逻辑

当前 UI 是浅绿色、柔和、健康感较强的设计：

- `:root` 使用 `#f4faf7`、`#2f9e73`、`#7cc9b0` 等绿色系；
- 页面背景是浅色渐变和左上角柔和径向光；
- 顶栏、卡片、区块都是半透明白底和轻阴影；
- 大部分按钮是圆角胶囊；
- 字体权重适中，整体偏清爽、克制；
- 所有页面共享同一套全局变量。

当前没有主题枚举、主题切换 UI、主题偏好持久化、按主题切换品牌文案或主题说明，也没有对主题变量之外的硬编码颜色做系统化封装。

## eat-what 可复用的视觉能力

不适合直接迁移 React 组件结构、Tailwind class、`motion/react` 动效、PWA / 本地词库 UI、食物 / 饮品双模式业务逻辑。

适合翻译为当前 CSS 主题的视觉特征：

- 鲜亮主色：食物橙 `#FF6321` 可作为第二套皮肤主色；
- 黑白强对比：按钮、选中态、结果重点信息使用黑底白字；
- 粗描边：核心按钮、卡片、输入框可在第二套皮肤下使用更明显边框；
- 硬投影：用偏移式黑色或深色投影替代当前柔和绿色阴影；
- 更强字体权重：品牌、标题、按钮、标签在第二套皮肤下更年轻、更有冲击力；
- 半透明面板：保留白色内容面板，但降低柔和健康感；
- 多彩标签：可通过已有分类色、badge/chip 风格增强活力。

## 已有可复用能力

当前 CSS 已大量使用变量，适合做主题覆盖。当前 HTML 顶栏已有右侧区域，理论上可放主题切换控件，但该区域已有用户 ID，需要谨慎处理移动端布局。`app.js` 已有全局 `state` 和事件代理机制，可增加主题状态、主题动作和持久化逻辑。当前没有构建工具，所有改动可以保持在静态 HTML/CSS/JS 中，不需要新增依赖。

## 潜在问题和隐患

- `app.css` 中仍有硬编码颜色，例如 body 渐变、统计卡背景、模式提示、表格头、JSON 背景、toast 背景等。只覆盖变量不能让第二套皮肤完整统一。
- `eat-what` 风格使用较多超大圆角和装饰光斑；当前项目规则要求卡片圆角保持克制，不应照搬。
- 过度引入橙黑高对比可能影响后台 Trace / 评估页的可读性，需要让第二套皮肤活泼但仍适合工具页面。
- 顶栏空间有限，新增主题控件可能挤压导航和用户 ID，必须验证移动端。
- 如果仅做临时按钮切换但不持久化，体验会割裂；应使用 localStorage 保存用户选择。
- 如果主题切换依赖 JS 太晚执行，页面首次加载可能出现浅绿色闪动；可接受范围需要在 Plan 中处理。

## 与需求相关的约束

- 不引入 React、Tailwind、motion 或图标库依赖。
- 不改变后端 API。
- 不改变现有路由和主要页面结构。
- 第一套皮肤应保持当前浅绿色视觉基本不变。
- 第二套皮肤应参考 `eat-what` 的年轻鲜亮气质，但适配当前 Choice Agent 的通用决策定位。
- 需要保留可访问性基本要求：按钮可理解、焦点态可见、对比度不能明显下降。

## 尚未确定、需要在 Plan 阶段决策的问题

- 主题切换控件放在顶栏右侧，还是放在导航附近；
- 第二套皮肤命名；
- 是否只提供两套主题，还是为未来主题预留数据结构；
- 是否需要在首次加载前通过内联脚本提前设置 `data-theme`，减少主题闪动；
- 是否调整 JS 模板中的按钮文案以适应主题切换。