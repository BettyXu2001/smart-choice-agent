# Decision Canvas 与 What-if 产品化 Plan

日期：2026-09-05

## 目标和成功标准

目标是把通用决策产品的核心从聊天旁边的辅助信息升级为持续更新的 Decision Canvas，并把假设分析作为独立、可见、可探索的能力呈现。

成功标准：

- 通用 / 购物 / 旅行决策页面右侧呈现固定 Decision Canvas 模块。
- Canvas 包含当前建议、为什么、选择它的代价、当前结论为什么发生变化、还缺什么关键信息。
- 理由只显示真正影响结论的 2 到 4 条；信息不足时允许少于 2 条。
- What-if 模块展示 2 到 3 条可能改变当前结论的条件；数据不足时允许少于 2 条或展示缺口。
- 点击建议条件或输入自定义假设后，返回假设比较，并明确显示“这是一次假设比较，没有修改当前保存的正式条件”。
- 假设比较不修改正式 fields、candidate facts、candidate states、recommendation。
- 饮食决策现有页面和行为不因通用 Canvas 改版发生布局回归。
- 现有测试继续通过，并补充正式 Canvas、假设分析隔离、结论变化说明和 What-if 建议测试。

## 架构和逻辑设计

### 1. 分离正式分析和假设分析

在 `domain_state["assistance"]` 下新增面板数据，保留旧字段兼容：

```python
{
    "analysis": {...},
    "currentAnalysis": {...},
    "whatIfAnalysis": {...},
    "whatIfScenarios": [...],
    "lastOfficialChange": {...}
}
```

非假设轮：写入 `currentAnalysis`，同步 `analysis = currentAnalysis`，标记旧 `whatIfAnalysis.stale = true`，更新 `whatIfScenarios`。

假设轮：写入 `whatIfAnalysis`，不更新正式 `Recommendation`，不更新正式 fields、facts、candidate states。前端 Canvas 默认仍以 `currentAnalysis` 作为正式区域，假设结果显示在独立区域。

旧 snapshot：没有 `currentAnalysis` 时，前端从旧 `assistance.analysis`、`recommendation` 和 `displayBlocks` 降级渲染。

### 2. Decision Canvas 固定模块

前端新增通用决策专用 Canvas 渲染：

- 当前建议：展示“当前更推荐 X”。
- 为什么：展示 `keyReasons` 或 `reasons`，最多 4 条。
- 选择它的代价：展示 `tradeoffs`，最多 4 条。
- 当前结论为什么发生变化：展示 `lastOfficialChange`；无变化时显示倾向未变或本轮形成当前倾向。
- 还缺什么关键信息：展示 `missingInfo`；旧字段降级读取 `question`。
- 什么会改变我的决定：展示 `whatIfScenarios`，支持点击和自定义输入。
- 假设结果：展示最近一次 `whatIfAnalysis`，并显示未修改正式条件提示。

桌面通用决策采用约 40% 聊天、60% Canvas。饮食页面继续使用现有布局。移动端通用决策使用“决策 / 对话”切换，默认展示决策 Canvas；饮食流程继续使用现有抽屉。

### 3. 结论变化说明

在 `GenericDecisionService.message` 和 `command` 中，在正式状态 mutation 前捕获 baseline：previous recommendation、official analysis summary、相关 fields、候选 eligibility/risk 轻量快照。

运行完成后，只对非假设轮生成 `lastOfficialChange`：

```python
{
    "from": {"candidateId": "b", "label": "B 公司"},
    "to": {"candidateId": "a", "label": "A 公司"},
    "reason": "你刚刚补充了每天最多接受 1 小时通勤，因此 B 的通勤风险升高，当前倾向转向 A。",
    "changed": true,
    "evidence": []
}
```

没有 old recommendation 时，不伪造“从 X 转向 Y”。old/new 相同但理由或风险变化时，说明“倾向未变，但判断依据发生变化”。

### 4. 理由、代价和缺失信息

增强 `assistance` 解释结构：

- `keyReasons`：2 到 4 条，优先来自排序中实际拉开差距的 criteria、硬约束、明确偏好和候选事实。
- `tradeoffs`：保留代价逻辑，但避免把所有竞争候选 summary 直接塞入。
- `missingInfo`：从 unresolved criteria、候选事实缺失、用户明确顾虑中生成 1 到 3 条。

原则是展示影响结论的差异，不复述所有输入；不足时少展示，不硬凑。

### 5. 通勤支持做窄范围增强

为支持“每天最多接受 1 小时通勤”等示例：

- 通用领域增加 `maxCommuteMinutes` 与 `commuteBasis`（`one_way` / `daily`）。
- 解析候选事实中的通勤时长，保存为候选级 measured fact，包含 minutes 与 basis。
- 支持“单程 40 分钟”“每天通勤 2 小时”“每天最多接受 1 小时通勤”。
- 只有口径明确或可合理默认时才执行硬约束；含糊的“两小时通勤”优先作为待确认信息。
- 不修改 `ranking.py` 全局缺失策略。

### 6. What-if 建议生成

新增 `src/choice_agent/decision/what_if.py` 或等价 helper，封装 scenario 生成和 dry-run。

建议来源优先级：

- 已知优先级互换，例如成长机会高于稳定性。
- 已知硬约束边界，例如通勤上限、预算上限、行程耗时。
- 已知候选数值差异，例如薪资、预算、时间、距离。
- 模型补充的候选边界条件，但必须经过候选 id、字段名、事实来源和数值可计算性校验。

展示最多 3 条。只有 dry-run 后推荐确实改变时标记为“可能改变当前建议”；只改变风险时标记为“会改变判断依据”。没有可计算事实时不生成伪精确阈值。

### 7. 假设入口和隔离

前端点击 scenario 后发送自然语言假设消息，并带 request-only context：

```json
{
  "analysisMode": "what_if",
  "scenarioId": "..."
}
```

自定义假设输入独立于聊天草稿。后端过滤 `analysisMode`、`scenarioId`、`scenarioText` 等 request-only key，禁止写入长期 context。假设链路在正式 understand / rank / scene mutation 前判断，继续允许聊天历史记录该假设问题和回答。

本次不提供“一键应用假设到正式条件”，避免把探索和正式状态编辑混在一起。

## 受影响文件

- `src/choice_agent/decision/assistance.py`：分离 official / what-if analysis，生成 key reasons、tradeoffs、missing info、change explanation、what-if scenarios。
- `src/choice_agent/decision/what_if.py`：新增 helper，封装 scenario 生成和 dry-run。
- `src/choice_agent/agents/conversation.py`：增强通勤字段和候选通勤 fact 解析。
- `src/choice_agent/decision/conversation.py`：增加通用领域 commute 字段校验和 criteria 同步。
- `src/choice_agent/domains/comparison.py`：接入正式/假设分析分离和通用通勤 ranking 处理。
- `src/choice_agent/orchestration/generic.py`：捕获 official baseline，过滤 request-only context，持久化新 assistance 字段。
- `src/choice_agent/schemas.py`：必要时扩展 assistance 相关 schema，优先保持 `domain_state` 兼容。
- `src/choice_agent/static/assets/js/conversation.js`：新增 Decision Canvas、What-if 入口、自定义假设输入、移动端 tabs。
- `src/choice_agent/static/assets/js/app.js`：配合通用详情和 demo 状态展示。
- `src/choice_agent/static/assets/css/main.css`：新增通用决策专用布局和 Canvas 样式，保护饮食布局。
- `tests/test_decision_assistance.py`：更新既有 analysis 断言。
- `tests/test_decision_canvas.py`：新增 Canvas、变化说明、缺失信息测试。
- `tests/test_what_if.py`：新增假设隔离、scenario 生成、自定义假设测试。
- `CHANGELOG.md`：实施完成后记录用户可感知变化。

## 兼容性和破坏性变更

API 路径不变，message request 不新增必填字段。`domain_state["assistance"]["analysis"]` 保留，新字段都放在 assistance dict 下。旧 snapshot 缺失新字段时降级渲染。receipt fingerprint 不通过新增默认 schema 字段改变旧请求结构。

## 风险和边界情况

- 结论变化说明缺少 previous baseline 时只能说明形成当前倾向，不能编造转向。
- What-if scenario 数量不足 3 条时需要空态说明。
- 模型补充 scenario 必须校验，避免不存在候选、伪造数值或污染正式状态。
- 通勤单程和每日口径不能混用。
- command 链路必须先捕获 baseline 再 mutation。
- 移动端 tabs 需要保留聊天草稿、滚动位置和 retry 状态。
- demo 数据和旧历史数据可能没有新字段，前端必须兼容。

## 验证方案

自动验证：

- `python -m pytest tests/test_decision_assistance.py`
- `python -m pytest tests/test_decision_canvas.py tests/test_what_if.py`
- `python -m pytest`
- `python -m compileall -q src scripts`
- `node --check src/choice_agent/static/assets/js/api.js`
- `node --check src/choice_agent/static/assets/js/app.js`
- `node --check src/choice_agent/static/assets/js/conversation.js`
- `git diff --check`

行为验证：

- 普通通用决策录入 A/B 公司，补充稳定、成长、通勤，Canvas 显示当前建议、理由、代价、变化和缺失信息。
- 先让 B 占优，再补充通勤上限，确认变化模块说明从 B 转向 A 的原因。
- 点击“如果成长优先于稳定”，展示假设结果且正式建议不变。
- 输入“假设我可以接受两小时通勤”，展示假设提示并不修改正式条件。
- 候选缺少工作强度时，缺失信息模块明确说明。
- 移动端通用决策默认显示 Canvas，可切换聊天且草稿保留。
- 饮食流程布局和既有交互不被通用 Canvas 样式改变。

无法完全验证的部分：若模型 provider 未配置，无法验证真实模型补充 scenario 的质量；使用 mock / rule fallback 测试校验边界。

## 技术折衷

- 不新增 endpoint，减少 API 变更面。
- 不做“一键应用假设为正式条件”。
- 不重写 `ranking.py` 全局 missing policy。
- 不强制每次显示 3 条 What-if 条件。
- 不将模型生成内容直接进入 Canvas，必须经过候选、字段、数值和来源校验。

## Todo

- [x] 扩展后端 assistance canvas 数据结构，分离正式分析和假设分析，并保持旧 `analysis` 兼容。
- [x] 在 service 层捕获正式状态变更前后的 baseline，生成结构化结论变化说明。
- [x] 增强通用领域通勤字段和候选通勤 fact 解析，保持 ranking 全局行为不变。
- [x] 新增 What-if helper，生成可靠 scenario 并复用 dry-run 假设分析。
- [x] 改造通用决策前端 Decision Canvas、What-if 入口和移动端 tabs，保护饮食布局。
- [x] 补充后端测试并执行前端语法验证，覆盖正式 Canvas、变化说明和假设隔离。
- [x] 执行完整验证，检查 diff，并按规则更新 `CHANGELOG.md`。