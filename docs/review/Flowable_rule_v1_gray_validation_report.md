# Flowable rule v1 gray validation report

## 1. 实验目的

本轮目标是做 Flowable `flowable_rule_v1` 受控灰度验证，对比正式 baseline profile 与 `flowable_rule_v1` candidate profile 在同一灰区样本 smoke 路径下的运行差异，为后续是否进入正式启用评审下一阶段提供工程证据。

本轮不修改 AFL++ 主链，不修改正式 `integration/platform_profiles/flowable_v2.json`，不修改 O2OA 配置，不训练 GAN，不复用 O2OA GAN。

## 2. baseline 与 candidate 配置说明

baseline：

- profile：`integration/platform_profiles/flowable_v2.json`
- `t_low=5.8`
- `t_high=6.3`
- `enable_second_stage=false`
- 用途：当前正式 Flowable 基线

candidate：

- 临时 profile：`/tmp/flowable_rule_v1_gray_candidate.json`
- 来源：`integration/platform_profiles/flowable_rule_v1_formal_candidate.example.json`
- `t_low=5.8`
- `t_high=6.3`
- `enable_second_stage=true`
- `second_stage_type=flowable_rule`
- 用途：受控灰度候选，不替代正式 `flowable_v2.json`

## 3. 环境说明

环境检查结果：

- Flowable REST management endpoint 返回 200；
- 7 个目标流程定义均存在；
- Flowable-AE v2 score service `/tmp/nv_valid_flowable.sock` 可用；
- 正式 `flowable_v2.json` 保持 `enable_second_stage=false`；
- O2OA `o2oa_default.json` 保持 `second_stage_type=gan`、`second_stage_threshold=1.0`。

本报告和 evidence 不记录明文认证凭据。

## 4. 每轮结果表

汇总 CSV：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_gray_validation/flowable_rule_v1_gray_validation_summary.csv`

| mode | run_id | task_id | duration | last_http_code | rpc_fail_total | BODY_DECISION_DBG | second_pass / second_reject | pass / reject | source_count | crash / hang |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |
| baseline | flowable_baseline_run1_20s | `9b2519c51f3d` | 20s | 0 | 0 | 379 | 0 / 0 | 0 / 379 | 0 | 0 / 0 |
| baseline | flowable_baseline_run2_20s | `971ca3367121` | 20s | 0 | 0 | 378 | 0 / 0 | 0 / 378 | 0 | 0 / 0 |
| baseline | flowable_baseline_run3_20s | `be394bb7b263` | 20s | 0 | 0 | 379 | 0 / 0 | 0 / 379 | 0 | 0 / 0 |
| baseline | flowable_baseline_run4_60s | `03c3035a32a9` | 60s | 0 | 0 | 1131 | 0 / 0 | 0 / 1131 | 0 | 0 / 0 |
| candidate | flowable_rule_v1_gray_run1_20s | `843cefc1623a` | 20s | 201 | 0 | 348 | 309 / 39 | 309 / 39 | 348 | 0 / 0 |
| candidate | flowable_rule_v1_gray_run2_20s | `17b1c997f48a` | 20s | 201 | 0 | 347 | 308 / 39 | 308 / 39 | 347 | 0 / 0 |
| candidate | flowable_rule_v1_gray_run3_20s | `3487ac322ab9` | 20s | 201 | 0 | 349 | 310 / 39 | 310 / 39 | 349 | 0 / 0 |
| candidate | flowable_rule_v1_gray_run4_60s | `16547e55b10f` | 60s | 201 | 0 | 1051 | 934 / 117 | 934 / 117 | 1051 | 0 / 0 |

baseline 使用灰区样本且正式 profile 未启用 second stage，因此所有灰区样本按 baseline 策略拒绝，没有发出 HTTP 请求，`last_http_code=0` 是预期行为。

## 5. baseline 与 candidate 对比

baseline：

- `rpc_fail_total=0`；
- 不进入 second stage；
- 灰区样本全部 reject；
- 无 HTTP 发送，因此无 HTTP 2xx 计数；
- 无 crash / hang。

candidate：

- `rpc_fail_total=0`；
- 每轮 `second_stage_source_count` 等于 `BODY_DECISION_DBG`；
- 每轮稳定进入 `flowable_rule_v1`；
- HTTP 末态均为 201；
- 20s 三轮 `second_reject=39/39/39`，分布稳定；
- 60s 长轮次 `second_reject=117`，与 20s 比例基本一致；
- 无 crash / hang。

## 6. flowable_rule_v1 是否稳定进入 runtime

是。candidate 4 轮中：

- run1：348 / 348
- run2：347 / 347
- run3：349 / 349
- run4：1051 / 1051

上述数值为 `second_stage_source_count / BODY_DECISION_DBG`，说明候选 profile 在灰区样本路径中稳定进入 `flowable_rule_v1` runtime。

## 7. HTTP / RPC / crash / hang 结果

candidate 4 轮均满足：

- `rpc_fail_total=0`
- `last_http_code=201`
- 未观察到 crash / hang

baseline 4 轮也满足 `rpc_fail_total=0` 且无 crash / hang，但由于 baseline 正式策略对灰区样本直接 reject，不发送 HTTP 请求，因此不与 candidate 的 HTTP 2xx 计数直接比较。

## 8. reject 比例分析

candidate 20s 三轮：

- run1：39 / 348，约 11.21%
- run2：39 / 347，约 11.24%
- run3：39 / 349，约 11.17%

candidate 60s 长轮次：

- 117 / 1051，约 11.13%

reject 比例稳定，未观察到异常过高或异常过低的漂移。

baseline 对本轮灰区样本全部 reject，这是正式 profile 未启用 second stage 时的预期行为，不能解释为 baseline 更优。

## 9. 风险分析

当前风险：

- candidate reject 增加不等于效果更好，仍需结合标签集、HTTP 行为、覆盖收益和误拒成本；
- 本轮灰度验证使用灰区样本，不能代表全部 Flowable 业务流量；
- 正式启用前仍需更多流程变量 schema、长时稳定性和覆盖收益数据；
- Flowable-GAN 未完成，不能由 `flowable_rule_v1` 推出 Flowable-GAN 结论；
- 正式 `flowable_v2.json` 仍不能直接修改。

## 10. 是否建议进入正式启用评审下一阶段

建议进入正式启用评审下一阶段。

理由：

- candidate 在受控灰度验证中保持 RPC 稳定；
- candidate 在灰区样本中稳定进入 `flowable_rule_v1`；
- candidate HTTP 末态均为 201；
- 未观察到 crash / hang；
- reject 比例稳定；
- 前序扩展标签集验证已显示 `invalid_pass=0`、`valid_reject=0`。

## 11. 是否建议直接修改 flowable_v2.json

不建议。

下一阶段应继续使用候选 profile 做受控验证和灰度评审。正式 `integration/platform_profiles/flowable_v2.json` 应继续保持 `enable_second_stage=false`，直到更大规模验证、业务误拒评审、覆盖收益和回滚演练完成。

## 12. 结论边界

可以写：`flowable_rule_v1` candidate 在受控灰度验证中保持 HTTP/RPC 稳定，并稳定进入 second stage。

可以写：建议进入下一阶段正式启用评审。

不能写：直接修改正式 `flowable_v2.json`；Flowable-GAN 已完成；完整强多平台动态异构冗余全部完成。
