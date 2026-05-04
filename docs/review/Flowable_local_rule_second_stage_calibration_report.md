# Flowable local rule second stage calibration report

## 1. 实验目的

本轮目标是对 Flowable local rule second stage 做小规模定标与效果验证，回答 local rule 是否只证明链路可用，还是已经具备初步过滤能力。本轮不修改 AFL++ 主链，不修改正式 `integration/platform_profiles/flowable_v2.json`，不复用 O2OA GAN，不训练 GAN。

## 2. 当前 Flowable second stage 状态

Flowable 已通过临时 probe profile 完成 AE + local rule second stage 真实服务 smoke。关键 smoke 证据为 `task_id=b3de7a9854a0`，`last_http_code=201`，`rpc_fail_total=0`，`BODY_DECISION_DBG=331`，stage 分布为 `ae_low=0`、`ae_high=0`、`second_pass=331`、`second_reject=0`，`second_stage_source=local_rule`。

正式 `integration/platform_profiles/flowable_v2.json` 仍保持 `enable_second_stage=false`，本轮没有修改正式 profile。

## 3. 为什么需要定标

上一轮真实服务 smoke 中所有 second stage 样本均为 `second_pass`。只读审查显示，当前 `DecisionEngine` 的 local rule 是通用 JSON 结构风险分数，主要由以下因素构成：

- body 大小；
- JSON 嵌套深度；
- JSON key 数量；
- 最长字符串长度。

该规则不检查 Flowable 业务 schema，例如 `processDefinitionKey` 是否存在、流程定义是否存在、`variables` 是否为数组、变量项是否含 `name` / `value`。因此短小但业务非法的 Flowable JSON 可能得到较低 rule score 并通过。

## 4. 样本来源

本轮标签集输出：

`docs/review/evidence/flowable_dynamic_redundancy/rule_calibration/flowable_labeled_set.csv`

样本来源包括：

- `in/flowable_process_start_dataset_v2` 中的既有 valid / invalid / border 样本；
- `in/flowable_process_start_dataset_v3` 中的既有 valid / invalid / border 样本；
- evidence 目录中本轮生成的离线 invalid 样本，未写入 `in/` 正式数据目录。

本轮生成的 invalid 类型覆盖：空 JSON、缺少 `processDefinitionKey`、不存在的 `processDefinitionKey`、`variables` 非数组、变量缺少 `name`、变量 `value` 类型异常、JSON 结构损坏、超长字段、非法嵌套字段和变量数组异常放大。

## 5. 标签策略

标签采用保守规则：

- `valid`：结构完整，包含 `processDefinitionKey=holidayRequest`，且 `variables` 中包含核心变量；
- `invalid`：明显缺少关键字段、结构不符合 Flowable process start API，或为本轮构造的非法样本；
- `uncertain`：边界样本或缺少人工真值的样本，不用于强效果结论。

标签规模：total=36，valid=10，invalid=20，uncertain=6。

## 6. 固定回放结果

回放结果 CSV：

`docs/review/evidence/flowable_dynamic_redundancy/rule_calibration/flowable_rule_replay_results.csv`

汇总 CSV：

`docs/review/evidence/flowable_dynamic_redundancy/rule_calibration/flowable_rule_calibration_summary.csv`

结果摘要：

| 指标 | 数值 |
| --- | ---: |
| total | 36 |
| valid / invalid / uncertain | 10 / 20 / 6 |
| local rule pass / reject | 35 / 1 |
| valid_pass / valid_reject | 10 / 0 |
| invalid_pass / invalid_reject | 19 / 1 |
| uncertain_pass / uncertain_reject | 6 / 0 |
| HTTP 2xx / 4xx / 5xx / unavailable | 23 / 13 / 0 / 0 |
| second_pass / second_reject | 35 / 1 |

## 7. local rule 是否过宽

当前 local rule 判定偏宽。

本轮虽然观察到 `second_reject=1`，说明存在 reject 条件，但 `invalid_pass=19`，表明大量短小、schema 非法或业务非法样本仍会被 local rule 放行。原因是现有规则主要衡量结构复杂度和体积风险，不衡量 Flowable process start 业务字段合法性。

因此，当前 local rule 可以证明 second stage 链路可用，并对极端结构风险样本具备一定拦截能力，但不具备充分过滤能力。

## 8. 是否观察到 second_reject

本轮观察到 `second_reject=1`。

本轮唯一 reject 来自无法解析的损坏 JSON，其 rule score 走默认拒绝分数。超长字段、变量数组异常放大和非法嵌套样本仍低于当前 `second_stage_threshold=1.0` 并被 `second_pass`，说明当前结构风险公式和阈值对 Flowable 场景仍偏宽。普通短小 schema-invalid 样本也仍可能 `second_pass`。

## 9. 是否建议启用正式 profile

不建议现在启用正式 `flowable_v2.json` 的 second stage。

原因：

- 当前规则仍有 `invalid_pass=19`；
- local rule 缺少 Flowable process start schema 校验；
- 当前标签集规模有限，不能支撑强效果结论；
- 真实 smoke 证明链路可用，但不能证明过滤能力充分；
- Flowable-GAN、Flowable 阈值定标和更大规模标签集仍未完成。

## 10. 后续建议

1. 增加 Flowable process start schema 校验：`processDefinitionKey`、`variables` 数组、变量 `name` / `value`；
2. 对已知流程定义做白名单或服务端反馈结合；
3. 将 HTTP 4xx/5xx 反馈纳入规则定标，而不是只依赖 JSON 结构复杂度；
4. 扩大 valid / invalid 标签集，尤其是短小但业务非法的样本；
5. 在规则增强后重新做固定回放和真实服务 smoke；
6. Flowable-GAN 仅作为后续独立增强方向，不能复用 O2OA GAN 后直接声称有效。

## 11. 结论边界

可以写：Flowable local rule second stage 具备链路可用性，并能拒绝无法解析的损坏 JSON。

必须保留：当前规则对短小 schema-invalid 样本和部分高结构风险样本仍偏宽，不具备充分过滤能力，不能据此建议正式启用 `flowable_v2.json` 的 second stage；不能声称 Flowable-GAN 已完成；不能声称完整强多平台动态异构冗余全部完成。
