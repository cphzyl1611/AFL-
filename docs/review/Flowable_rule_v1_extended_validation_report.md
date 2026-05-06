# Flowable rule v1 extended validation report

## 1. 实验目的

本轮目标是扩充 Flowable 标签集和流程定义 key 覆盖，验证 `flowable_rule_v1` 在更多流程定义和更多样本类型下是否仍然具备稳定的初步过滤能力。

本轮不修改 AFL++ 主链，不修改正式 `integration/platform_profiles/flowable_v2.json`，不训练 GAN，不复用 O2OA GAN。

## 2. 为什么需要扩样本和多流程 key

上一轮固定回放使用 36 条样本，证明 `flowable_rule_v1` 可将 `invalid_pass` 从 19 降到 0，并保持 `valid_reject=0`。随后多轮真实 smoke 证明它能稳定进入真实服务 runtime。

但上一轮样本规模和流程 key 覆盖仍有限，因此本轮扩展到 84 条样本，并覆盖当前 Flowable REST 中可查询到的 7 个 processDefinitionKey，用于观察规则是否只对单一 `holidayRequest` 有效，还是能覆盖更多 Flowable process start 请求形态。

## 3. 样本构成

扩展标签集：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_extended_validation/flowable_extended_labeled_set.csv`

样本正文：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_extended_validation/sample_bodies/`

样本规模：

| label | 数量 |
| --- | ---: |
| valid | 28 |
| invalid | 42 |
| uncertain | 14 |
| total | 84 |

invalid 样本覆盖缺少 `processDefinitionKey`、空 key、未知 key、`variables` 非数组、变量元素非 object、变量缺少 `name`、空 `name`、缺少 `value`、嵌套过深、超长字符串、字段数量异常、损坏 JSON、顶层非 object、额外 root 字段和 holidayRequest 类型不匹配等类型。

uncertain 样本为结构不明显非法但业务语义缺少人工真值的请求，不参与强结论。

## 4. 流程 key 覆盖情况

Flowable REST 查询到的目标流程定义：

- `holidayRequest`
- `oneTaskProcess`
- `vacationRequest`
- `createTimersProcess`
- `fixSystemFailure`
- `escalationExample`
- `reviewSaledLead`

上述 7 个流程定义均存在，未发现目标 key 缺失。

valid 样本覆盖 7 个真实存在的 processDefinitionKey，每个 key 4 条结构合法请求。invalid 样本还包含缺失 key 和未知 key，用于验证拒绝路径。

## 5. 固定回放结果

固定回放输出：

- `docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_extended_validation/flowable_rule_v1_extended_replay_results.csv`
- `docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_extended_validation/flowable_rule_v1_extended_summary.csv`

汇总结果：

| mode | total | pass | reject | valid_pass | valid_reject | invalid_pass | invalid_reject | uncertain_pass | uncertain_reject |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| old_local_rule | 84 | 82 | 2 | 28 | 0 | 40 | 2 | 14 | 0 |
| flowable_rule_v1 | 84 | 42 | 42 | 28 | 0 | 0 | 42 | 14 | 0 |

## 6. invalid_pass 和 valid_reject 分析

`flowable_rule_v1` 在扩展标签集上将 `invalid_pass` 从旧 `local_rule` 的 40 降为 0。

`valid_reject=0`，未观察到 valid 样本被 rule v1 拒绝。

这说明在当前 84 条扩展样本中，`flowable_rule_v1` 相比旧 `local_rule` 具备更充分的初步过滤证据。

## 7. HTTP 结果分析

固定回放同时发送真实 Flowable REST 请求，HTTP 分布为：

| HTTP class | 数量 |
| --- | ---: |
| 2xx | 52 |
| 4xx | 23 |
| 5xx | 9 |

按标签观察：

| label | 2xx | 4xx | 5xx |
| --- | ---: | ---: | ---: |
| valid | 24 | 0 | 4 |
| invalid | 16 | 23 | 3 |
| uncertain | 12 | 0 | 2 |

`createTimersProcess` 在本地 REST 环境中出现 5xx，因此不能把 HTTP 结果简单等同为规则真值。规则侧仍按结构和 schema 进行本地 second stage 判定，HTTP 结果用于辅助观察服务行为。

## 8. 是否执行多轮 smoke

已执行多轮真实 smoke。

执行原因：

- 扩展固定回放中 `invalid_pass=0`，明显低于旧 `local_rule`；
- 扩展固定回放中 `valid_reject=0`，不超过 2；
- Flowable REST 可用；
- Flowable-AE v2 score service 可用；
- 正式 `flowable_v2.json` 未修改；
- 使用临时 `flowable_rule_v1` probe profile。

多轮 smoke 使用灰区样本触发真实 second stage runtime；扩样本与多流程 key 覆盖由固定回放提供。

## 9. 多轮 smoke 结果

多轮 smoke evidence：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_extended_validation/multirun/`

汇总 CSV：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_extended_validation/multirun/flowable_rule_v1_extended_multirun_summary.csv`

| run_id | task_id | duration | last_http_code | rpc_fail_total | BODY_DECISION_DBG | second_pass / second_reject | flowable_rule_v1 count | crash / hang |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| flowable_rule_v1_extended_smoke_run1 | `9ff3b520f0fd` | 20s | 201 | 0 | 347 | 308 / 39 | 347 | 0 / 0 |
| flowable_rule_v1_extended_smoke_run2 | `e2a017131bd7` | 20s | 201 | 0 | 348 | 309 / 39 | 348 | 0 / 0 |
| flowable_rule_v1_extended_smoke_run3 | `c1322fcdb523` | 20s | 201 | 0 | 349 | 310 / 39 | 349 | 0 / 0 |
| flowable_rule_v1_extended_smoke_long60 | `182a4ee1e838` | 60s | 201 | 0 | 1044 | 928 / 116 | 1044 | 0 / 0 |

4 轮均满足 `rpc_fail_total=0`，HTTP 末态均为 201，未观察到 crash / hang。

## 10. 是否建议进入正式 profile 启用候选

建议进入正式 profile 启用候选评审，但不建议直接修改正式 `flowable_v2.json`。

理由：

- 扩展固定回放已覆盖 84 条样本和 7 个真实流程定义 key；
- `invalid_pass=0`、`valid_reject=0`；
- 多轮 smoke 中 `flowable_rule_v1` 稳定进入 runtime；
- 但仍缺少更大规模样本、更多业务变量 schema、覆盖收益、延迟和长期稳定性数据。

## 11. 是否建议直接修改 flowable_v2.json

不建议。

正式 `integration/platform_profiles/flowable_v2.json` 应继续保持 `enable_second_stage=false`。下一步应将 `flowable_rule_v1` 作为正式启用候选进行评审和扩样本验证，而不是直接替换正式 profile。

## 12. 结论边界

可以写：`flowable_rule_v1` 在扩展标签集和多流程 key 下具备更充分的初步过滤证据，并在多轮真实 smoke 中稳定进入 second stage runtime。

不能写：Flowable-GAN 已完成；完整强多平台动态异构冗余全部完成；正式 `flowable_v2.json` 已启用 second stage。
