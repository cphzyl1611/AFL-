# Flowable rule v1 multirun smoke report

## 1. 实验目的

本轮目标是在真实 Flowable REST 服务环境中，对 `flowable_rule_v1` 做多轮 smoke 稳定性验证，确认该 Flowable 专用 second stage 规则是否能稳定进入 runtime，并持续产生可观测的 `second_pass` / `second_reject`。

本轮不修改 AFL++ 主链，不修改正式 `integration/platform_profiles/flowable_v2.json`，不训练 GAN，不复用 O2OA GAN。

## 2. 实验环境

- Flowable REST：`http://127.0.0.1:8080/flowable-rest/service/`
- Flowable process definition：`holidayRequest`
- Flowable-AE v2 score service：`/tmp/nv_valid_flowable.sock`
- 临时 profile：`/tmp/flowable_rule_v1_probe.json`
- 候选 profile 来源：`integration/platform_profiles/flowable_rule_v1_probe.example.json`
- 正式 profile：`integration/platform_profiles/flowable_v2.json` 保持 `enable_second_stage=false`

报告和 evidence 中不记录明文认证凭据。

## 3. 为什么做多轮 smoke

上一轮 `flowable_rule_v1` 已完成固定标签集回放和一次 20 秒真实 smoke。固定回放显示该规则将 `invalid_pass` 从 19 降低到 0，且 `valid_reject` 未增加；单轮 smoke 显示 `second_stage_source=flowable_rule_v1` 已进入真实服务 runtime。

单轮 smoke 只能证明链路可运行，不能证明运行稳定性。因此本轮执行 3 轮 20 秒 smoke，并在环境稳定后追加 1 轮 60 秒 smoke，观察 RPC、HTTP、second stage 分布、crash / hang 是否稳定。

## 4. 每轮结果表

| run_id | task_id | duration | last_http_code | HTTP 200/201 count | rpc_fail_total | BODY_DECISION_DBG | ae_low / ae_high | second_pass / second_reject | flowable_rule_v1 count | crash / hang |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |
| flowable_rule_v1_smoke_run1 | `26a0a386e8b3` | 20s | 201 | 304 | 0 | 342 | 0 / 0 | 304 / 38 | 342 | 0 / 0 |
| flowable_rule_v1_smoke_run2 | `38c6c245a87b` | 20s | 201 | 309 | 0 | 348 | 0 / 0 | 309 / 39 | 348 | 0 / 0 |
| flowable_rule_v1_smoke_run3 | `428493bb37c2` | 20s | 201 | 310 | 0 | 349 | 0 / 0 | 310 / 39 | 349 | 0 / 0 |
| flowable_rule_v1_smoke_run_long60 | `9132783c9ea1` | 60s | 201 | 932 | 0 | 1049 | 0 / 0 | 932 / 117 | 1049 | 0 / 0 |

汇总 CSV：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_multirun/flowable_rule_v1_multirun_summary.csv`

## 5. 平均 second_pass / second_reject

3 轮 20 秒 smoke 的平均值：

- 平均 `second_pass=307.67`
- 平均 `second_reject=38.67`

追加 60 秒 smoke 结果为：

- `second_pass=932`
- `second_reject=117`

由于 60 秒 smoke 时长不同，不与 20 秒结果直接做简单均值比较。按比例观察，4 轮的 reject 占比均约为 11%，未出现明显漂移。

## 6. rpc_fail 和 HTTP 状态

4 轮运行均满足：

- `rpc_fail_total=0`
- `body_score_rpc_fail=0`
- `last_http_code=201`
- HTTP 200/201 count 均大于 0

说明 Flowable-AE v2 score service 与真实 Flowable REST 调用在本轮 smoke 中未观察到 RPC 中断或 HTTP 末态异常。

## 7. 稳定性分析

`flowable_rule_v1_count` 与 `BODY_DECISION_DBG` 在每轮中一致：

- run1：342 / 342
- run2：348 / 348
- run3：349 / 349
- long60：1049 / 1049

这说明 `flowable_rule_v1` 在本轮真实服务运行中稳定进入 second stage runtime。3 轮 20 秒 smoke 的 `second_reject` 分别为 38、39、39，追加 60 秒 smoke 的 `second_reject=117`，按运行时长观察分布基本一致。

本轮未观察到 crash 或 hang。

## 8. 是否建议正式启用 flowable_v2 second stage

暂不建议直接启用正式 `flowable_v2.json` 的 second stage。

理由：

- 本轮验证了真实服务 smoke 稳定性，但样本、流程定义和运行时长仍有限；
- `flowable_rule_v1` 仍是候选规则，需要继续覆盖更多 Flowable process definition 和变量 schema；
- 尚未完成 Flowable second stage 的大规模标签评估、覆盖收益分析和长期运行稳定性评估；
- Flowable-GAN 未完成，不能将本轮 local rule 结果外推为 Flowable GAN online 完成。

## 9. 后续建议

1. 扩充 Flowable valid / invalid 标签集，覆盖更多 process definition key；
2. 针对不同流程定义建立更细的变量 schema；
3. 继续做更长时长和更多轮次真实 smoke；
4. 收集覆盖率、执行效率、误放和误拒指标；
5. 在证据更充分后，再评估是否将 Flowable second stage 从临时 profile 迁移到正式 profile；
6. Flowable-GAN 需要独立模型、阈值定标和在线验证，不能复用 O2OA GAN 结论。

## 10. 结论边界

可以写：`flowable_rule_v1` 在本轮多轮真实 smoke 中稳定进入 second stage，并产生可观测 `second_pass` / `second_reject`。

不能写：Flowable-GAN 已完成；完整强多平台动态异构冗余全部完成；正式 `flowable_v2.json` 已启用 second stage。
