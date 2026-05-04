# Flowable local rule improvement suggestions

## 1. 背景

本轮 Flowable local rule second stage 定标显示，当前 local rule 主要基于 JSON 结构复杂度评分。它能拒绝无法解析的损坏 JSON，但对短小的 Flowable schema-invalid 样本、超长字段、深嵌套和字段数量异常样本仍偏宽。

本文件只给出后续规则增强建议，不修改 `integration/decision_engine.py`，不修改正式 `integration/platform_profiles/flowable_v2.json`。

## 2. 建议增加的结构校验

- 根节点必须是 JSON object；
- 必须存在 `processDefinitionKey`；
- `variables` 必须存在且必须是数组；
- `variables` 中每个元素必须是 object；
- 每个变量元素必须包含 `name`；
- 每个变量元素应包含 `value` 或显式允许的空值语义；
- 限制最大嵌套深度、最大变量数量和最大 body bytes。

## 3. 建议增加的字段合法性校验

- `processDefinitionKey` 应先限制为当前部署流程的候选集合；
- `name` 为空字符串、超长字符串或异常字符比例过高时提高风险；
- `nrOfHolidays` 等数字字段应限制类型和合理范围；
- `employee` 等文本字段应限制长度和控制字符；
- 未知字段嵌套层级过深时提高风险。

## 4. 建议增加的 HTTP 反馈规则

- 将 Flowable REST 返回的 4xx 作为 invalid 反馈样本，用于后续规则定标；
- 区分 schema 错误、流程定义不存在、变量类型错误和服务端异常；
- 将稳定 2xx 的样本作为 valid 候选，但仍需人工抽样确认；
- 记录 HTTP code 分类，不记录认证信息、请求正文或响应正文中的敏感内容。

## 5. 下一轮实现建议

1. 先新增 Flowable 专用 rule 函数或 profile 参数，不影响 O2OA；
2. 用本轮 `flowable_labeled_set.csv` 和 `flowable_rule_replay_results.csv` 做回归基线；
3. 扩充至少 100 条 valid / invalid 标签样本；
4. 重新扫描 threshold 或 risk score 分界；
5. 再执行固定回放和 20 秒真实服务 smoke；
6. 仍不建议在没有扩样本证据前启用正式 `flowable_v2.json` second stage。
