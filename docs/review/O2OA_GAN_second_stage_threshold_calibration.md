# O2OA GAN second stage 阈值定标报告

## 1. 实验目的

本报告面向 O2OA 正式 AE 灰区 `0.8 < ae_score < 1.5`，对 GAN second stage 候选阈值进行离线扫描，并与 rule fallback 在同一批灰区样本上的判定结果进行对比。目标是给出初步阈值建议，而不是重新证明 GAN online 路径能否跑通。

本轮未修改 AFL++ 主链，未修改 `integration/platform_profiles/o2oa_default.json`，未扩展 Flowable，未运行新的 O2OA/fuzzer smoke。

## 2. 样本来源

样本目录：`docs/review/evidence/o2oa_dynamic_redundancy/gan_threshold_calibration/`。

样本组成：

- 现有灰区样本：`in/o2oa_body_model_compare/grey_probe_0.json`、`grey_probe_1.json`、`grey_probe_2.json`；
- 轻量变异样本：从 `cms_doc_list` JSON 结构出发生成，保存于 `docs/review/evidence/o2oa_dynamic_redundancy/gan_threshold_calibration/generated_samples/`；
- 所有纳入扫描的样本均满足正式 AE 灰区：`0.8 < ae_score < 1.5`。

样本总数：`24`。

标签分布：

| label | count |
| --- | ---: |
| valid | 11 |
| invalid | 7 |
| uncertain | 6 |

## 3. 标签策略

标签只作为小规模离线定标参考，不伪造人工真值。

- `valid`：包含 `cms_doc_list` 必要字段，字段类型符合规则，字段值为常见业务形态；
- `invalid`：JSON 本身合法，但缺少关键字段或字段类型明显不符合 `cms_doc_list` 规则；
- `uncertain`：结构基本完整，但额外字段或业务语义未独立验证，不能硬判为 valid 或 invalid。

详细标签见：`docs/review/evidence/o2oa_dynamic_redundancy/gan_threshold_calibration/o2oa_grey_labeled_set.csv`。

## 4. 阈值扫描结果

候选阈值：`0.6, 0.8, 1.0, 1.2, 1.5, 2.0`。判定规则为 `gan_score < threshold` 通过，否则拒绝。

| threshold | gan_pass | gan_reject | valid_pass | valid_reject | invalid_pass | invalid_reject | uncertain_pass | uncertain_reject | false_reject_rate | false_accept_rate | precision | recall | f1 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.6 | 0 | 24 | 0 | 11 | 0 | 7 | 0 | 6 | 1.0000 | 0.0000 | 0.3889 | 1.0000 | 0.5600 |
| 0.8 | 0 | 24 | 0 | 11 | 0 | 7 | 0 | 6 | 1.0000 | 0.0000 | 0.3889 | 1.0000 | 0.5600 |
| 1 | 5 | 19 | 2 | 9 | 1 | 6 | 2 | 4 | 0.8182 | 0.1429 | 0.4000 | 0.8571 | 0.5455 |
| 1.2 | 17 | 7 | 7 | 4 | 4 | 3 | 6 | 0 | 0.3636 | 0.5714 | 0.4286 | 0.4286 | 0.4286 |
| 1.5 | 22 | 2 | 9 | 2 | 7 | 0 | 6 | 0 | 0.1818 | 1.0000 | 0.0000 | 0.0000 |  |
| 2 | 24 | 0 | 11 | 0 | 7 | 0 | 6 | 0 | 0.0000 | 1.0000 |  | 0.0000 |  |


完整扫描结果见：`docs/review/evidence/o2oa_dynamic_redundancy/gan_threshold_calibration/o2oa_gan_threshold_sweep.csv`。

## 5. Rule fallback 与 GAN 对比

对同一批灰区样本比较：

- rule fallback decision；
- GAN decision under threshold=`1.0`；
- GAN decision under recommended threshold=`1.2`。

Formal threshold `1.0` 对比：

| comparison | count |
| --- | ---: |
| same_decision | 5 |
| rule_pass_gan_reject | 19 |
| rule_reject_gan_pass | 0 |

Recommended threshold `1.2` 对比：

| comparison | count |
| --- | ---: |
| same_decision | 17 |
| rule_pass_gan_reject | 7 |
| rule_reject_gan_pass | 0 |

完整对比见：`docs/review/evidence/o2oa_dynamic_redundancy/gan_threshold_calibration/rule_vs_gan_compare.csv`。

## 6. 推荐阈值

本轮初步推荐 GAN second stage 阈值候选：`1.2`。

推荐理由：

- `0.6` 与 `0.8` 会拒绝全部样本，包括所有 `valid` 样本，不适合作为均衡阈值建议；
- 正式阈值 `1.0` 保持较强拒绝倾向，`false_accept_rate=0.1429`，但 `false_reject_rate=0.8182` 偏高；
- `1.2` 在当前小样本中把 `false_reject_rate` 降至 `0.3636`，同时仍保留部分 invalid 拒绝能力，适合作为下一轮验证的初步候选；
- `1.5` 与 `2.0` 对 invalid 的拒绝能力明显不足，不适合作为当前候选。

该建议不修改正式 `o2oa_default` profile。正式 profile 当前仍保持 `second_stage_threshold=1.0`。

## 7. 结论边界

- 本轮完成的是离线阈值定标与灰区样本描述性评估；
- 当前标签集规模较小，且 `uncertain` 样本不能作为硬真值；
- 可以说：`1.2` 是当前小样本下的初步阈值候选；
- 不能说：GAN second stage 必然优于 rule fallback；
- GAN 更严格不等于更优，是否更优取决于 valid/invalid 真值、覆盖收益、异常发现率、误拒成本和重复统计；
- 不能声称 Flowable GAN online 已完成；
- 不能声称完整多平台动态异构冗余全部完成。
