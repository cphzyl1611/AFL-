# Flowable rule v1 post-enable stability and rollback report

## 1. 实验目的

本报告记录 Flowable `flowable_rule_v1` 正式启用后的长时稳定性验证与受控回滚演练。

本轮使用正式 `integration/platform_profiles/flowable_v2.json`，不使用临时 candidate profile；回滚演练阶段临时关闭 second stage，随后恢复正式启用状态。最终提交状态必须保持 `enable_second_stage=true`、`second_stage_type=flowable_rule`。

本轮不修改 O2OA 配置，不修改 AFL++ 主链，不训练 GAN，不复用 O2OA GAN。

## 2. 当前正式启用状态

Flowable 正式 profile：

`integration/platform_profiles/flowable_v2.json`

当前 decision 配置：

- `t_low=5.8`
- `t_high=6.3`
- `enable_second_stage=true`
- `second_stage_type=flowable_rule`
- `second_stage_threshold=1.0`

O2OA 正式 profile 保持：

- `second_stage_type=gan`
- `second_stage_threshold=1.0`

## 3. 长时 smoke 结果

使用正式 `flowable_v2.json` 执行 180s 和 300s smoke。

汇总 CSV：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_post_enable_stability/flowable_rule_v1_post_enable_stability_summary.csv`

| duration | task_id | last_http_code | HTTP 200/201 | rpc_fail_total | BODY_DECISION_DBG | second_pass / second_reject | flowable_rule_v1 count | throughput | last_latency_ms | crash / hang |
| ---: | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
| 180s | `a494bb5476ca` | 201 | 2794 | 0 | 3144 | 2794 / 350 | 3144 | 17.467 exec/s | 4 | 0 / 0 |
| 300s | `54a4832c00ee` | 201 | 4657 | 0 | 5239 | 4657 / 582 | 5239 | 17.463 exec/s | 4 | 0 / 0 |

长时 smoke 结论：

- 两轮均稳定进入 `flowable_rule_v1` runtime；
- 两轮均 `rpc_fail_total=0`；
- HTTP 末态均为 201；
- 未观察到 crash / hang；
- 180s 与 300s 的吞吐接近，未观察到明显漂移。

## 4. 回滚演练过程

回滚演练步骤：

1. 临时将 `flowable_v2.json` 改为：
   - `enable_second_stage=false`
   - `second_stage_type=rule`
2. 使用回滚状态执行 20s baseline smoke；
3. 验证回滚状态不进入 `flowable_rule_v1`；
4. 恢复正式启用状态：
   - `enable_second_stage=true`
   - `second_stage_type=flowable_rule`
5. 使用恢复后的正式启用状态执行 20s smoke。

## 5. 回滚后 baseline 行为

回滚态 task_id：`9bc0d4fe3eee`

| 项目 | 结果 |
| --- | ---: |
| duration | 20s |
| last_http_code | 0 |
| rpc_fail_total | 0 |
| BODY_DECISION_DBG | 377 |
| second_pass / second_reject | 0 / 0 |
| flowable_rule_v1 count | 0 |
| pass / reject | 0 / 377 |
| crash / hang | 0 / 0 |

结论：

- 回滚状态不进入 `flowable_rule_v1`；
- 灰区样本按 baseline 策略拒绝；
- `rpc_fail_total=0`；
- 未观察到 crash / hang。

## 6. 恢复正式启用后的验证

恢复后 task_id：`b2bd9603650a`

| 项目 | 结果 |
| --- | ---: |
| duration | 20s |
| last_http_code | 201 |
| HTTP 200/201 | 311 |
| rpc_fail_total | 0 |
| BODY_DECISION_DBG | 350 |
| second_pass / second_reject | 311 / 39 |
| flowable_rule_v1 count | 350 |
| pass / reject | 311 / 39 |
| crash / hang | 0 / 0 |

结论：

- 恢复正式启用后重新进入 `flowable_rule_v1`；
- HTTP 末态恢复为 201；
- `rpc_fail_total=0`；
- 未观察到 crash / hang。

## 7. O2OA 不受影响确认

O2OA profile 未修改：

- `integration/platform_profiles/o2oa_default.json`
- `second_stage_type=gan`
- `second_stage_threshold=1.0`

本轮未运行 O2OA fuzz。静态配置检查和 DecisionEngine 静态回归确认 O2OA 不进入 `flowable_rule_v1`。

## 8. 风险与限制

当前风险与限制：

- 180s / 300s smoke 仍不是生产级长期验证；
- 本轮样本仍来自既有灰区样本路径，不能覆盖所有 Flowable 业务输入；
- 回滚演练验证了配置层回滚路径，但没有覆盖部署系统的发布回滚流程；
- Flowable-GAN 未完成；
- 不能将 `flowable_rule_v1` 结论外推为 GAN 效果结论；
- 完整强多平台动态异构冗余仍需更多平台、标签、覆盖收益和长期统计支撑。

## 9. 当前可声称内容

可以声称：

- Flowable `flowable_rule_v1` 正式启用后完成 180s 和 300s 长时 smoke；
- 长时 smoke 中 `rpc_fail_total=0`，HTTP 末态为 201，未观察到 crash / hang；
- 回滚路径已完成受控演练；
- 回滚状态不进入 `flowable_rule_v1`；
- 恢复正式启用后再次进入 `flowable_rule_v1`，并通过 20s 验证；
- O2OA 未受影响。

## 10. 当前不能声称内容

不能声称：

- Flowable-GAN 已完成；
- O2OA GAN 可以直接迁移到 Flowable；
- GAN 效果优于 rule fallback；
- 完整强多平台动态异构冗余全部完成；
- 180s / 300s smoke 等同于生产级长期验证。
