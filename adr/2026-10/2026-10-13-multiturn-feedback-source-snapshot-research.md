# 多轮反馈、候选来源与 Generic 状态模型 Research

## 需求与范围

研究覆盖四领域的多轮反馈语义、rerank/refresh、每轮来源保存与展示、Generic 固定字段、Diet 冲突过滤和 Travel/Shopping fixture 边界。保持现有 Orchestrator、StageRunner、DecisionState 主架构。

## ADR 检索

- `2026-09-04-generic-decision-evidence-workbench-*`：定义 Provider、来源边界和通用状态。
- `2026-10-12-decision-execution-workflow-optimization-*`：定义 refresh/rerank 执行规划和候选池复用。
- `2026-10-09-decision-workflow-ux-optimization-*`：已有来源提示，但历史轮次仍会读取当前来源。

记录均已完成且边界不同，本次新建 Research / Plan。

## 现状

- `StageRunner` 和 `plan_execution()` 已区分 refresh/rerank；自然语言反馈尚未统一成五类。
- Generic/Diet 轮次历史未保存来源，只保留可变 `domainState.source`。
- Generic 默认字段和 assistance 仍硬编码学习、通勤。
- Diet 没有清淡与麻辣/重辣/重油的排序前过滤。
- Travel fixture 静态路程/预算没有出发地适用边界；Shopping usage 只触发刷新，不影响 fixture 候选。
- 前端能恢复每轮卡片，但没有轮次来源对象。

## 约束与复用

复用现有 ExecutionMode、StageRunner、candidatePool、SearchRun、SourceDocument、Provider 和轮次历史，不新建流水线或数据表。历史 Generic 旧字段必须继续读取。仓库已有重叠的未提交改动，实施时只做增量修改。

## 待 Plan 决策

- sourceSnapshot 放入既有轮次历史。
- 推荐偏离先审计硬约束：旧池有合格替代项则 rerank，否则 refresh。
- Generic 动态信息沿用 assistance facts 与标准 constraints/criteria。