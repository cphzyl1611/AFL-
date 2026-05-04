# Flowable rule v1 second stage validation report

## 1. 实验目的

本轮目标是实现 Flowable 专用 local rule v1，并用上一轮同一批 36 条标签样本做固定回放验证。验证重点是比较旧 `local_rule` 与新 `flowable_rule_v1` 的 pass/reject、invalid_pass、valid_reject 变化。本轮不修改 AFL++ 主链，不修改正式 `integration/platform_profiles/flowable_v2.json`，不训练 GAN，不复用 O2OA GAN。

## 2. 上一轮 local rule 过宽问题

上一轮定标结果显示：标签集 total=36，valid / invalid / uncertain = 10 / 20 / 6，旧 `local_rule` pass/reject = 35 / 1，`invalid_pass=19`。原因是旧规则主要基于 JSON 结构复杂度、body 大小、key 数量和最长字符串，不检查 Flowable process start 的业务 schema。

因此，短小但业务非法的样本，例如缺少 `processDefinitionKey`、`variables` 不是数组、变量缺少 `name` 或 `value`，仍可能被旧 `local_rule` 放行。

## 3. flowable_rule_v1 规则设计

`flowable_rule_v1` 是显式 opt-in 的 Flowable 专用 second stage 规则。只有 profile 选择 `second_stage_type=flowable_rule` 或 `flowable_rule_v1` 时才启用；旧 `second_stage_type=rule` 和 O2OA `second_stage_type=gan` 路径保持原行为。

规则设计包括：

- JSON 必须可解析；
- 顶层必须是 object；
- `processDefinitionKey` 必须存在且为非空字符串；
- 如果 profile 配置 `allowed_process_definition_keys`，key 必须在白名单中；
- 如果存在 `variables`，必须是数组；
- 每个 variable 必须是 object；
- 每个 variable 必须有非空字符串 `name`；
- 每个 variable 必须包含 `value`；
- `value` 只允许 scalar、null、简单 object 或简单 array；
- 拒绝明显过深嵌套、超长字符串、字段数量异常膨胀和变量数量异常膨胀；
- 对 `holidayRequest` 示例配置要求 `employee` 和 `nrOfHolidays`，并校验 `employee` 为 string、`nrOfHolidays` 为 number。

候选 profile：

`integration/platform_profiles/flowable_rule_v1_probe.example.json`

该 profile 是实验 probe profile，不替代正式 `flowable_v2.json`。

## 4. 固定标签集回放结果

样本级 CSV：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_validation/flowable_rule_v1_replay_results.csv`

汇总 CSV：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_validation/flowable_rule_v1_summary.csv`

结果表：

| mode | total | pass | reject | valid_pass | valid_reject | invalid_pass | invalid_reject | uncertain_pass | uncertain_reject |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| old_local_rule | 36 | 35 | 1 | 10 | 0 | 19 | 1 | 6 | 0 |
| flowable_rule_v1 | 36 | 16 | 20 | 10 | 0 | 0 | 20 | 6 | 0 |

## 5. 与旧 local_rule 对比

`flowable_rule_v1` 将 invalid_pass 从 19 降低到 0，invalid_reject 从 1 提升到 20。

valid_reject 从 0 变为 0。

## 6. 是否降低 invalid_pass

是。固定标签集上，`flowable_rule_v1` 明显降低 invalid_pass，说明相比旧 `local_rule` 具备更明确的 Flowable schema 过滤能力。

## 7. 是否引入 valid_reject

本轮 valid_reject=0。如果后续扩样本后出现 valid_reject，需要重点审查 `holidayRequest` 变量约束、白名单和字段类型提示是否过紧。

## 8. 是否执行真实 smoke

已执行 20 秒真实 Flowable smoke。

执行前条件：

- 固定回放中 invalid_pass 从 19 降到 0；
- 固定回放中 valid_reject=0；
- Flowable REST 管理接口返回 HTTP 200；
- Flowable-AE v2 score service 使用 `/tmp/nv_valid_flowable.sock`；
- 使用临时 profile `/tmp/flowable_rule_v1_probe.json`；
- 正式 `integration/platform_profiles/flowable_v2.json` 未修改。

真实 smoke 结果：

| 指标 | 数值 |
| --- | ---: |
| task_id | `aef8406c3b18` |
| status | `exited` |
| duration | 20s |
| last_http_code | 201 |
| HTTP 200/201 count | 301 |
| rpc_fail_total | 0 |
| body_score_rpc_ok | 339 |
| body_score_rpc_fail | 0 |
| BODY_DECISION_DBG | 339 |
| ae_low / ae_high | 0 / 0 |
| second_pass / second_reject | 301 / 38 |
| second_stage_source=flowable_rule_v1 | 339 |
| pass / reject | 301 / 38 |
| crash / hang | 0 / 0 |

轻量证据：

- `docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_validation/smoke_summary_aef8406c3b18_flowable_rule_v1.json`
- `docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_validation/stdout_summary_aef8406c3b18_flowable_rule_v1.log`
- `docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_validation/decision_debug_excerpt_aef8406c3b18_flowable_rule_v1.log`

## 9. 是否建议正式启用 flowable_v2 second stage

暂不建议。

理由：

- 本轮只完成 36 条小规模固定回放；
- 规则约束只覆盖当前标签集中最明确的 Flowable process start schema；
- 尚未进行扩样本、重复 smoke、覆盖收益和延迟影响评估；
- 正式 `flowable_v2.json` 仍应保持 `enable_second_stage=false`。

## 10. 后续建议

1. 扩充 valid / invalid / uncertain 标签集，覆盖更多流程定义 key；
2. 根据 HTTP 4xx/5xx 反馈补充规则定标；
3. 在更大样本上检查 valid_reject 风险；
4. 重复多轮 20 秒和更长时长真实 smoke；
5. 仅在扩样本和多轮真实 smoke 都稳定后，再讨论是否修改正式 Flowable profile；
6. Flowable-GAN 仍需独立训练或验证，不能由本规则推出完成。

## 11. 结论边界

可以写：`flowable_rule_v1` 在固定标签集回放中显著降低 invalid_pass，并具备初步 Flowable schema 过滤能力。

不能写：Flowable-GAN 已完成；完整强多平台动态异构冗余全部完成；正式 `flowable_v2.json` 已启用 second stage。
