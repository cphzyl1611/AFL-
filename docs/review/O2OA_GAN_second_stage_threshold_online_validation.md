# O2OA GAN second stage 阈值在线复验报告

## 1. 实验目的

本报告对 GAN second stage 候选阈值 `1.2` 做在线 smoke 复验，并与正式阈值 `1.0` 对比。目标是观察候选阈值是否在真实 O2OA runtime 中减少 `second_reject`，而不是证明 `1.2` 是最优阈值。

本轮未修改 AFL++ 主链，未修改 `integration/platform_profiles/o2oa_default.json`，未扩展 Flowable。

## 2. 为什么验证 threshold=1.2

离线阈值扫描中，`1.2` 相比正式阈值 `1.0` 降低了 valid 样本误拒，但仍保留部分 invalid 拒绝能力。因此本轮只把 `1.2` 作为下一轮候选阈值进行在线复验。

正式 profile 仍保持 `second_stage_threshold=1.0`。本轮 `1.2` 通过临时 profile `/tmp/o2oa_default_gan_threshold_1_2.json` 注入，不修改正式 profile。

## 3. 实验设置

- 正式阈值组：`integration/platform_profiles/o2oa_default.json`，`second_stage_threshold=1.0`。
- 候选阈值组：`/tmp/o2oa_default_gan_threshold_1_2.json`，仅把 `decision.second_stage_threshold` 改为 `1.2`。
- 每组运行次数：3 次。
- 单次时长：20 秒。
- AE score service：`/tmp/nv_valid_real.sock`。
- GAN score service：`/tmp/nv_valid_gan.sock`。
- Seed：`in/o2oa_body_model_compare/`，包含 `grey_probe_0.json`、`grey_probe_1.json`、`grey_probe_2.json`。
- 调试输出：`AFL_DEBUG_CHILD=1`、`NV_DEBUG_BODY_VALID=1`，用于提取 `BODY_DECISION_DBG`。

## 4. 每组 3 次结果

| threshold | run | task_id | HTTP 200 | pass | reject | rpc_fail_total | second_pass | second_reject | gan_rpc_count | crash | hang |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.0 | 1 | `e31451449ab6` | yes | 94 | 49 | 0 | 16 | 8 | 24 | 0 | 0 |
| 1.0 | 2 | `9d911fb306cf` | yes | 94 | 47 | 0 | 14 | 8 | 22 | 0 | 0 |
| 1.0 | 3 | `8b9b3ba1e102` | yes | 87 | 58 | 0 | 14 | 11 | 25 | 0 | 0 |
| 1.2 | 1 | `b59b0a70ee98` | yes | 90 | 58 | 0 | 14 | 7 | 21 | 0 | 0 |
| 1.2 | 2 | `dfe4dbbcc3ba` | yes | 92 | 48 | 0 | 16 | 8 | 24 | 0 | 0 |
| 1.2 | 3 | `b767dd6b5c9c` | yes | 91 | 50 | 0 | 14 | 7 | 21 | 0 | 0 |

## 5. 汇总对比

| threshold | runs | HTTP 200 runs | rpc_fail_total | avg pass | avg reject | avg second_pass | avg second_reject | avg gan_rpc_count | crash total | hang total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.0 | 3 | 3 | 0 | 91.67 | 51.33 | 14.67 | 9.00 | 23.67 | 0 | 0 |
| 1.2 | 3 | 3 | 0 | 91.00 | 52.00 | 14.67 | 7.33 | 22.00 | 0 | 0 |

明细 CSV：`docs/review/evidence/o2oa_dynamic_redundancy/gan_threshold_online_validation/o2oa_gan_threshold_online_runs.csv`。

汇总 CSV：`docs/review/evidence/o2oa_dynamic_redundancy/gan_threshold_online_validation/o2oa_gan_threshold_online_summary.csv`。

## 6. 对比分析

- 两组 6 次任务均返回 HTTP `200`，`rpc_fail_total=0`，未记录 crash/hang。
- 正式阈值 `1.0` 平均 pass/reject 为 `91.67/51.33`，平均 `second_pass/second_reject` 为 `14.67/9.00`。
- 候选阈值 `1.2` 平均 pass/reject 为 `91.00/52.00`，平均 `second_pass/second_reject` 为 `14.67/7.33`。
- 本次小样本在线复验中，`1.2` 相比 `1.0` 的平均 `second_reject` 更低，表现为更宽松的灰区二阶段判定。
- 由于 6 次 smoke 并非同一输入序列的严格配对回放，整体 pass/reject 还受 AE 低风险与高风险分布影响；本轮只把 `second_reject` 降低作为小样本现象记录。

## 7. 是否建议进入下一轮验证

建议把 `1.2` 作为下一轮候选阈值继续验证。建议的下一轮验证应扩大运行次数和时长，并结合离线标签集、真实接口响应、异常发现率、误拒成本与覆盖收益一起评估。

## 8. 是否建议修改正式 profile

不建议本轮直接修改正式 `integration/platform_profiles/o2oa_default.json`。

原因：本轮只有每组 3 次、每次 20 秒的小样本在线 smoke，足以说明 `1.2` 在本次复验中减少了 `second_reject`，但不足以证明 `1.2` 是最优阈值，也不足以证明 GAN online 优于 rule fallback。

## 9. 结论边界

- 可以说：候选阈值 `1.2` 在本次小样本在线复验中减少了 `second_reject`。
- 不能说：`1.2` 是最优阈值。
- 不能直接修改正式 profile。
- 不能声称 GAN 优于 rule fallback。
- 不能声称 Flowable 动态冗余已完成。
- 不能声称多平台动态异构冗余全部完成。
