# O2OA 动态异构冗余效果对比报告

## 1. 实验目的

本报告对 O2OA `cms_doc_list` 场景下三种运行模式进行小样本效果对比：AE-only、AE + Rule fallback、AE + GAN online。目标是观察动态 second stage 对灰区样本分流、pass/reject 分布、RPC 稳定性和 HTTP smoke 结果的影响。

## 2. 三种模式说明

- AE-only：使用临时 profile `/tmp/o2oa_profile_ae_only.json`，`t_low=t_high=1.0`，`enable_second_stage=false`，只按 AE score 阈值判定。
- AE + Rule fallback：使用临时 profile `/tmp/o2oa_profile_rule_fallback.json`，保持正式灰区 `t_low=0.8`、`t_high=1.5`，`second_stage_type=gan`，但实验时不启动 `/tmp/nv_valid_gan.sock`，灰区样本按设计进入 `rule_fallback`。
- AE + GAN online：使用正式 `integration/platform_profiles/o2oa_default.json`，保持 `t_low=0.8`、`t_high=1.5`、`enable_second_stage=true`、`second_stage_endpoint=unix:///tmp/nv_valid_gan.sock`，启动 GAN socket 服务后进行验证。

## 3. 实验环境

- O2OA target：`targets/o2oa_query.json`，base=`http://127.0.0.1:20020`。
- AE score service：`/tmp/nv_valid_real.sock`。
- GAN score service：`/tmp/nv_valid_gan.sock`，仅 GAN online 模式启动。
- Seed：`in/o2oa_body_model_compare`，包含 `grey_probe_0.json`、`grey_probe_1.json`、`grey_probe_2.json`。
- 鉴权：运行时使用已有环境变量，报告和证据不保存鉴权凭据或密码明文。

## 4. 实验参数

- 每种模式运行次数：3 次。
- 单次时长：20 秒。
- 运行命名：`o2oa_compare_<mode>_run<id>`。
- 调试输出：`AFL_DEBUG_CHILD=1`、`NV_DEBUG_BODY_VALID=1`，用于捕获 `BODY_DECISION_DBG` 阶段统计。
- 正式 profile 未修改；AE-only 与 Rule fallback 均使用 `/tmp` 临时 profile。

## 5. 结果表

| mode | run | task_id | HTTP 200 | pass | reject | rpc_fail_total | ae_low | ae_high | second_pass | second_reject | gan_rpc | rule_fallback | gan_rpc_unavailable | crashes | hangs |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ae_only | 1 | `2a3865e1f9b5` | yes | 76 | 66 | 0 | 76 | 66 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ae_only | 2 | `04b1a65a6113` | yes | 83 | 60 | 0 | 83 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ae_only | 3 | `ee8ea5fb6f78` | yes | 83 | 62 | 0 | 83 | 62 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| rule_fallback | 1 | `c425bbeea3fd` | yes | 94 | 42 | 0 | 70 | 42 | 24 | 0 | 0 | 24 | 24 | 0 | 0 |
| rule_fallback | 2 | `71b43a8cb64d` | yes | 98 | 47 | 0 | 76 | 47 | 22 | 0 | 0 | 22 | 22 | 0 | 0 |
| rule_fallback | 3 | `53b86776a687` | yes | 103 | 44 | 0 | 80 | 44 | 23 | 0 | 0 | 23 | 23 | 0 | 0 |
| gan_online | 1 | `8bc51adeb48b` | yes | 88 | 54 | 0 | 74 | 45 | 14 | 9 | 23 | 0 | 0 | 0 | 0 |
| gan_online | 2 | `6a509b1c78dc` | yes | 87 | 50 | 0 | 73 | 40 | 14 | 10 | 24 | 0 | 0 | 0 | 0 |
| gan_online | 3 | `8c79a70f580e` | yes | 94 | 52 | 0 | 79 | 44 | 15 | 8 | 23 | 0 | 0 | 0 | 0 |

汇总均值与总量：

| mode | runs | HTTP 200 runs | avg pass | avg reject | rpc_fail total | second_pass total | second_reject total | gan_rpc total | rule_fallback total | crashes | hangs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ae_only | 3 | 3 | 80.67 | 62.67 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| rule_fallback | 3 | 3 | 98.33 | 44.33 | 0 | 69 | 0 | 0 | 69 | 0 | 0 |
| gan_online | 3 | 3 | 89.67 | 52.0 | 0 | 43 | 27 | 70 | 0 | 0 | 0 |

汇总 CSV：`docs/review/evidence/o2oa_dynamic_redundancy/effect_compare/o2oa_dynamic_redundancy_effect_compare.csv`。

## 6. 对比分析

- 三种模式的 9 次运行均返回 HTTP `200`，`rpc_fail_total=0`，未记录 crash/hang。
- AE-only 没有 second stage：`second_pass=0`、`second_reject=0`，pass/reject 均由 AE 阈值直接决定。
- AE + Rule fallback 在 3 次运行中累计 `rule_fallback=69`，其中 `second_pass=69`、`second_reject=0`，说明灰区样本确实进入了动态 second stage 并在 GAN 不可用时降级。
- AE + GAN online 在 3 次运行中累计 `gan_rpc=70`，其中 `second_pass=43`、`second_reject=27`，说明灰区样本进入 GAN RPC 并产生在线二阶段决策。
- 与 Rule fallback 相比，本次小样本中 GAN online 的平均 reject 更高、平均 pass 更低，表现为更严格的灰区判定；但本实验没有人工真值标签，也没有独立覆盖收益证明，因此不能把“更严格”直接等同于“效果更优”。

## 7. 结论边界

- 可以声称：本次小样本实验中，O2OA AE + Rule fallback 与 O2OA AE + GAN online 都完成了动态 second stage 运行路径验证，且 GAN online 确实出现 `second_stage_source=gan_rpc`。
- 可以声称：本次小样本中 GAN online 相比 Rule fallback 呈现更高 reject 倾向。
- 不能声称：GAN online 效果必然优于 Rule fallback；当前缺少真值标签、显著性检验、阈值定标和重复大样本统计。
- 不能声称：Flowable 动态冗余已完成。
- 不能声称：多平台动态异构冗余全部完成。
