# O2OA GAN second stage 固定灰区样本回放验证

## 实验目的

本次验证用于补足在线 smoke 对比的不足：在线 smoke 来自 fuzz 过程，不是严格同输入回放，因此不能直接判断 threshold=1.0 与 threshold=1.2 在同一批输入上的判定差异。

本轮固定使用已完成离线阈值定标阶段的 O2OA 灰区样本，比较三种 second stage 判定：

- rule fallback
- GAN threshold=1.0
- GAN threshold=1.2

本次验证不修改 `integration/platform_profiles/o2oa_default.json`，不修改 AFL++ 主链，不扩展 Flowable。

## 样本来源

样本与标签来自：

- `docs/review/evidence/o2oa_dynamic_redundancy/gan_threshold_calibration/o2oa_grey_labeled_set.csv`
- `docs/review/evidence/o2oa_dynamic_redundancy/gan_threshold_calibration/o2oa_grey_sample_scores.csv`

本次共读取 24 个样本，缺失样本数为 0。重新通过 AE score service 回放后，24 个样本均仍满足正式灰区：

```text
0.8 < ae_score < 1.5
```

标签分布：

| label | count |
| --- | ---: |
| valid | 11 |
| invalid | 7 |
| uncertain | 6 |

标签是保守小规模标注，不等同于生产环境真值集；`uncertain` 样本不作为强结论依据。

## 回放方法

每个样本执行以下固定流程：

1. 通过 `/tmp/nv_valid_real.sock` 计算 AE score；
2. 判断是否仍落入正式灰区；
3. 使用本地 rule fallback 逻辑计算 rule decision；
4. 通过 `/tmp/nv_valid_gan.sock` 计算 GAN score；
5. 分别按 threshold=1.0 和 threshold=1.2 计算 GAN decision；
6. 按 label 汇总 pass/reject、valid_reject 和 invalid_pass。

正式 profile 保持：

- `t_low=0.8`
- `t_high=1.5`
- `enable_second_stage=true`
- `second_stage_type=gan`
- `second_stage_endpoint=unix:///tmp/nv_valid_gan.sock`
- `second_stage_threshold=1.0`

## 结果表

汇总结果保存于：

`docs/review/evidence/o2oa_dynamic_redundancy/fixed_replay_validation/o2oa_fixed_replay_summary.csv`

| mode | total | pass | reject | valid_pass | valid_reject | invalid_pass | invalid_reject | uncertain_pass | uncertain_reject |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rule_fallback | 24 | 24 | 0 | 11 | 0 | 7 | 0 | 6 | 0 |
| gan_threshold_1_0 | 24 | 5 | 19 | 2 | 9 | 1 | 6 | 2 | 4 |
| gan_threshold_1_2 | 24 | 17 | 7 | 7 | 4 | 4 | 3 | 6 | 0 |

样本级明细保存于：

`docs/review/evidence/o2oa_dynamic_redundancy/fixed_replay_validation/o2oa_fixed_replay_sample_results.csv`

## 差异分析

threshold=1.2 相比 threshold=1.0 的变化：

- valid_reject 从 9 降低到 4，说明在本批固定灰区样本中，1.2 表现出降低 valid 误拒的倾向；
- invalid_pass 从 1 增加到 4，说明阈值放宽同时带来 invalid 误放增加；
- uncertain_reject 从 4 降低到 0，但 uncertain 样本不能作为强结论依据。

rule fallback 与 GAN 的差异：

- rule fallback 本批 24 个样本全部 pass，因此 valid_reject 为 0，但 invalid_pass 为 7；
- GAN threshold=1.0 更严格，reject 19 个样本，同时 valid_reject 较高；
- GAN threshold=1.2 相比 1.0 放宽，减少 valid_reject，但仍 reject 7 个样本；
- 这说明 rule fallback、GAN 1.0、GAN 1.2 的行为差异清晰存在，但不能仅凭本批小样本证明 GAN 效果整体优于 rule fallback。

## 是否建议将 1.2 作为后续候选

建议将 threshold=1.2 作为下一轮候选阈值继续验证。

理由是：固定回放中 1.2 相比 1.0 降低了 valid 误拒，但 invalid 误放也同步增加，需要更大规模、更可靠标签和覆盖收益数据确认该取舍是否合理。

## 是否建议直接修改正式 profile

不建议直接修改正式 profile。

当前正式 `o2oa_default` profile 的 `second_stage_threshold=1.0` 应继续保持不变。threshold=1.2 只能作为下一轮候选阈值进入更大样本、同输入回放、在线 smoke 和覆盖收益联合评估。

## 结论边界

可以声称：

- O2OA GAN second stage 已完成固定灰区样本回放验证；
- 在本批 24 个固定灰区样本上，threshold=1.2 相比 1.0 表现出降低 valid 误拒的倾向；
- threshold=1.2 同时增加 invalid 误放，因此只是后续候选阈值，不是最优阈值结论。

不能声称：

- threshold=1.2 是最优阈值；
- GAN online 效果优于 rule fallback；
- 可以直接修改正式 profile；
- Flowable 动态冗余已完成；
- 多平台动态异构冗余已完成。
