# Flowable rule v1 formal enable report

## 1. 启用目的

本轮目标是在已完成候选评审、受控灰度验证和变更评审包的基础上，正式启用 Flowable `flowable_rule_v1` second stage。

本轮允许修改正式 `integration/platform_profiles/flowable_v2.json`，但不修改 O2OA 配置、不修改 AFL++ 主链、不修改模型、不修改 runner 主逻辑，也不训练或接入 Flowable-GAN。

## 2. 修改的正式 profile

正式修改文件：

`integration/platform_profiles/flowable_v2.json`

该文件现在是 Flowable-AE v2 + Flowable local rule v1 second stage 的正式 profile。

## 3. 修改前配置

修改前 decision 配置为：

```json
{
  "t_low": 5.8,
  "t_high": 6.3,
  "enable_second_stage": false,
  "second_stage_type": "rule",
  "second_stage_threshold": 1.0
}
```

修改前 Flowable 正式 profile 只启用 AE 第一阶段，second stage 未启用。

## 4. 修改后配置

修改后 decision 配置为：

```json
{
  "t_low": 5.8,
  "t_high": 6.3,
  "enable_second_stage": true,
  "second_stage_type": "flowable_rule",
  "second_stage_threshold": 1.0
}
```

同时合入候选 profile 已验证的 Flowable rule v1 配置：

- `allowed_process_definition_keys`
- `flowable_rule_allowed_root_fields`
- `flowable_rule_required_variables_by_key`
- `flowable_rule_variable_type_hints`
- `flowable_rule_max_json_depth`
- `flowable_rule_max_string_len`
- `flowable_rule_max_total_keys`
- `flowable_rule_max_variables`
- `flowable_rule_max_variable_name_len`

## 5. 与候选 profile 的关系

正式 profile 变更来源于候选配置：

`integration/platform_profiles/flowable_rule_v1_formal_candidate.example.json`

候选 profile 已完成固定标签集回放、多轮真实 smoke、扩样本与多流程 key 覆盖验证、受控灰度验证、正式启用候选评审和正式启用变更评审包。

本轮将候选 profile 中经过验证的 Flowable rule v1 配置迁移到正式 `flowable_v2.json`。

## 6. 启用后 smoke 结果

使用修改后的正式 `flowable_v2.json` 执行 20s 和 60s smoke。

汇总 evidence：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_formal_enable/flowable_rule_v1_formal_enable_summary.csv`

| duration | task_id | last_http_code | HTTP 200/201 | rpc_fail_total | BODY_DECISION_DBG | ae_low / ae_high | second_pass / second_reject | source count | pass / reject | crash / hang |
| ---: | --- | ---: | ---: | ---: | ---: | --- | --- | ---: | --- | --- |
| 20s | `7ac054e8bdfb` | 201 | 309 | 0 | 348 | 0 / 0 | 309 / 39 | 348 | 309 / 39 | 0 / 0 |
| 60s | `779145c12c25` | 201 | 934 | 0 | 1051 | 0 / 0 | 934 / 117 | 1051 | 934 / 117 | 0 / 0 |

结论：

- 正式 `flowable_v2.json` 已进入 `flowable_rule_v1`；
- 两轮均 `rpc_fail_total=0`；
- 两轮 HTTP 末态均为 201；
- 两轮均未观察到 crash / hang；
- `flowable_rule_v1_count` 与 `BODY_DECISION_DBG` 一致，说明正式 profile 稳定进入 Flowable rule v1 runtime。

## 7. O2OA 回归确认

O2OA 正式 profile 未修改。

确认结果：

- `integration/platform_profiles/o2oa_default.json` 仍为 `second_stage_type=gan`；
- `second_stage_threshold=1.0`；
- O2OA DecisionEngine 静态回归不进入 `flowable_rule_v1`；
- 本轮未运行 O2OA fuzz，也未修改 O2OA 配置。

## 8. 风险与回滚策略

风险：

- Flowable rule v1 更严格，仍可能在更大真实业务流量中出现误拒；
- 当前启用后 smoke 是最小回归，不等价于长期生产流量验证；
- Flowable-GAN 未完成，不能把本轮结果外推为 Flowable GAN online；
- 不同部署环境和流程变量 schema 仍需持续复核。

回滚策略：

1. 恢复 `integration/platform_profiles/flowable_v2.json` 中：
   - `enable_second_stage=false`
   - `second_stage_type=rule`
2. 保留 `t_low=5.8`、`t_high=6.3`、`second_stage_threshold=1.0`；
3. 回滚后 Flowable 回到 AE v2 第一阶段正式 baseline；
4. 使用本轮 evidence 和后续异常样本进行误拒归因，再决定是否重新启用。

## 8.1 启用后长时稳定性与回滚演练补充

后续已完成 Flowable `flowable_rule_v1` 正式启用后的长时稳定性验证与回滚演练：

- 报告：`docs/review/Flowable_rule_v1_post_enable_stability_and_rollback_report.md`
- evidence：`docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_post_enable_stability/`

补充结果：

| phase | task_id | duration | second_pass / second_reject | rpc_fail_total | last_http_code | crash / hang |
| --- | --- | ---: | --- | ---: | ---: | --- |
| post-enable stability | `a494bb5476ca` | 180s | 2794 / 350 | 0 | 201 | 0 / 0 |
| post-enable stability | `54a4832c00ee` | 300s | 4657 / 582 | 0 | 201 | 0 / 0 |
| rollback drill | `9bc0d4fe3eee` | 20s | 0 / 0 | 0 | 0 | 0 / 0 |
| restore validation | `b2bd9603650a` | 20s | 311 / 39 | 0 | 201 | 0 / 0 |

回滚态未进入 `flowable_rule_v1`；恢复正式启用后重新进入 `flowable_rule_v1`。

## 9. 当前可声称内容

可以声称：

- Flowable 正式 `flowable_v2.json` 已启用 `flowable_rule_v1` second stage；
- 启用后 20s 与 60s 最小 smoke 通过；
- 正式 profile 中 `flowable_rule_v1` 稳定进入 runtime；
- `rpc_fail_total=0`，HTTP 末态为 201，未观察到 crash / hang；
- O2OA 未受影响，仍为 GAN second stage。

## 10. 当前不能声称内容

不能声称：

- Flowable-GAN 已完成；
- O2OA GAN 可以直接迁移到 Flowable；
- GAN 效果优于 rule fallback；
- 完整强多平台动态异构冗余全部完成；
- 本轮最小 smoke 已经覆盖长期生产稳定性或完整业务误拒风险。
