# 多轮反馈、候选来源与 Generic 状态模型 Plan

## 目标和成功标准

- Generic 新状态只默认 `target/priority`，历史旧字段兼容。
- 四领域统一五类反馈；整批拒绝/换一批 refresh，单候选不喜欢 rerank，推荐偏离先 audit。
- 每个推荐轮次保存独立 sourceSnapshot，前端按该轮展示来源。
- Diet/Travel/Shopping 正确性边界由回归测试证明。

## 设计与文件

1. 新增 `decision.feedback`：分类、候选排除、constraint audit 和执行建议。
2. 新增 `decision.source_snapshot`：从本轮计划和实际来源生成 JSON；Generic/Diet append 轮次时复制保存。
3. 清理 `decision.conversation`、`agents.conversation`、`decision.assistance` 的 Generic 场景硬编码，旧字段不主动删除。
4. 在现有 Profile/Provider 层实现 Diet 冲突过滤、Travel fixture 基准边界、Shopping usage 召回和模拟标识。
5. 前端消息携带 sourceSnapshot，增加“本轮候选来源”，并改名“餐食库范围”。
6. 补后端/前端回归，更新 CHANGELOG。

## 兼容性和风险

不改 API 路径、不迁移数据库、不增依赖。fixture 非基准出发地不再用模拟路程/预算评分，这是避免虚假精确性的有意行为。

## 验证

运行专项与完整 pytest、compileall、JS syntax check、git diff/check，并核对所有 Todo。

## Todo

- [ ] 实现统一反馈分类、constraint audit 与 rerank/refresh 映射。
- [ ] 实现每轮 sourceSnapshot 并接入 Generic/Diet 历史。
- [ ] 清理 Generic 固定字段和场景硬编码，保留历史读取。
- [ ] 修复 Diet/Travel/Shopping 领域正确性。
- [ ] 增加前端来源折叠项并调整 Diet 文案。
- [ ] 补回归测试和 CHANGELOG。
- [ ] 完成专项/全量验证、Todo 与最终 diff 检查。