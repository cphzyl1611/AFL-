# AFL++ documentation

This is the overview of the AFL++ docs content.

For general information on AFL++, see the
[README.md of the repository](../README.md).

Also take a look at our [FAQ.md](FAQ.md) and
[best_practices.md](best_practices.md).

## Fuzzing targets with the source code available

You can find a quickstart for fuzzing targets with the source code available in
the [README.md of the repository](../README.md#quick-start-fuzzing-with-afl).

For in-depth information on the steps of the fuzzing process, see
[fuzzing_in_depth.md](fuzzing_in_depth.md) or click on the following
image and select a step.

![Fuzzing process overview](https://raw.githubusercontent.com/AFLplusplus/AFLplusplus/dev/docs/resources/0_fuzzing_process_overview.drawio.svg "Fuzzing process overview")

For further information on instrumentation, see the
[READMEs in the instrumentation/ folder](../instrumentation/).

### Instrumenting the target

For more information, click on the following image and select a step.

![Instrumenting the target](https://raw.githubusercontent.com/AFLplusplus/AFLplusplus/dev/docs/resources/1_instrument_target.drawio.svg "Instrumenting the target")

### Preparing the fuzzing campaign

For more information, click on the following image and select a step.

![Preparing the fuzzing campaign](https://raw.githubusercontent.com/AFLplusplus/AFLplusplus/dev/docs/resources/2_prepare_campaign.drawio.svg "Preparing the fuzzing campaign")

### Fuzzing the target

For more information, click on the following image and select a step.

![Fuzzing the target](https://raw.githubusercontent.com/AFLplusplus/AFLplusplus/dev/docs/resources/3_fuzz_target.drawio.svg "Fuzzing the target")

### Managing the fuzzing campaign

For more information, click on the following image and select a step.

![Managing the fuzzing campaign](https://raw.githubusercontent.com/AFLplusplus/AFLplusplus/dev/docs/resources/4_manage_campaign.drawio.svg "Managing the fuzzing campaign")

## Fuzzing other targets

To learn about fuzzing other targets, see:

* Binary-only: [fuzzing_binary-only_targets.md](fuzzing_binary-only_targets.md)
* GUI programs:
  [best_practices.md#fuzzing-a-gui-program](best_practices.md#fuzzing-a-gui-program)
* Libraries: [frida_mode/README.md](../frida_mode/README.md)
* Network services:
  [best_practices.md#fuzzing-a-network-service](best_practices.md#fuzzing-a-network-service)
* Non-linux: [unicorn_mode/README.md](../unicorn_mode/README.md)

## Additional information

* Tools that help fuzzing with AFL++:
  [third_party_tools.md](third_party_tools.md)
* Tutorials: [tutorials.md](tutorials.md)

# 动态异构冗余有效性评估机制

## 为什么需要该机制

现有链路以单模型静态阈值作为有效性判定主依据，虽然实现简单，但存在两个现实问题：

- 单模型存在误判风险。AE 重构误差适合做快速筛选，但对边界样本、分布漂移样本和局部结构异常样本可能出现误接收或误拒绝。
- 模糊测试输入分布复杂。AFL++ 会持续产生高扰动、非平稳、灰区密集的 JSON body，单一阈值很难同时覆盖低风险样本与高风险样本。

因此，本项目将有效性判定从“单模型静态拒绝”升级为“动态异构冗余调度”，在不破坏现有主链的前提下增加第二条判定路径。

## 机制设计思想

- AE 作为第一层快速筛选器：用较低成本先完成大部分样本分流。
- 灰区输入触发第二模型：只有 AE 分数位于不确定区间时，才进入第二阶段，避免把全部输入都送入冗余路径。
- 分区决策：将输入划分为 `low / high / uncertain` 三个区间。
- `low`：`ae_score <= t_low`，直接通过。
- `high`：`ae_score >= t_high`，直接拒绝。
- `uncertain`：`t_low < ae_score < t_high`，触发第二阶段。

当前 O2OA 正式 profile 中，第二阶段优先走 GAN RPC 路径；若 GAN RPC 不可用，则进入规则型 fallback 路径。Flowable 正式 `flowable_v2.json` 已启用 `flowable_rule_v1` second stage，并完成正式启用后长时 smoke、回滚演练和恢复验证；Flowable-GAN 未完成。

## 架构链路

文字链路如下：

`fuzz_adapter -> decision_engine -> AE / GAN / Rule -> final decision`

工程内的实际落点为：

- `integration/fuzz_adapter.py`：加载平台 profile，并把 `decision` 配置透传到 runner 运行环境。
- `nv_body_valid.py`：在 AE score 返回后执行 runtime 决策。
- `integration/decision_engine.py`：完成分区判断、第二阶段调度、GAN 调用、local rule 与 rule fallback。

## 决策流程

伪代码如下：

```python
ae_score = run_ae(sample)
decision_engine = DecisionEngine(profile["decision"])
decision, meta = decision_engine.decide(ae_score, sample)

if ae_score <= t_low:
    return "pass", {"stage": "ae_low"}

if ae_score >= t_high:
    return "reject", {"stage": "ae_high"}

if enable_second_stage:
    second_score = run_gan(sample) or run_rule_fallback(sample)
    if second_score < second_stage_threshold:
        return "pass", {"stage": "second_pass"}
    return "reject", {"stage": "second_reject"}

return "reject", {"stage": "fallback"}
```

## 与 fault tolerance 的关系

该机制属于 fault tolerance 中的动态恢复机制，原因如下：

- 冗余：系统不再依赖单一 AE 路径，而是具备 `AE + GAN / Rule` 的多路径判定能力。
- 异构：AE 采用重构误差原理，GAN 采用不同的生成式异常评分原理，Rule fallback 采用显式结构风险规则，三者不是同构重复。
- 动态：第二阶段不是静态总是执行，而是由运行时 AE score 触发调度。

因此，本实现不是静态冗余堆叠，而是按风险区间执行的动态异构冗余。

## 当前实现范围

当前版本的实现边界如下：

- O2OA 正式 profile 已启用 GAN second stage，默认 `second_stage_threshold=1.0`；`threshold=1.2` 仅作为下一轮扩样本验证候选，不是正式默认。
- Flowable 正式 profile 已启用 `flowable_rule_v1` second stage，`flowable_v2.json` 当前保持 `enable_second_stage=true`、`second_stage_type=flowable_rule`、`second_stage_threshold=1.0`。
- 当前属于工程实现与阶段性交付验证完成状态。第一阶段仍由 AE 主导，第二阶段只在灰区触发，不改变 AFL++、runner 和平台接入主链；Flowable-GAN、跨平台 GAN 迁移和完整强多平台动态异构冗余仍需后续独立验证。

## 动态异构冗余机制阶段性结论

当前可交付口径如下：

- 最终口径：动态异构冗余机制在工程实现与阶段性交付验证意义上已完成。
- O2OA：AE + GAN online second stage 动态异构冗余闭环已完成，正式 profile 启用 GAN second stage，默认 `second_stage_threshold=1.0`。
- Flowable：正式 `integration/platform_profiles/flowable_v2.json` 已启用 AE + `flowable_rule_v1` second stage，并完成正式启用后 180s / 300s 长时 smoke、回滚演练和恢复验证。
- 总体：O2OA 与 Flowable 双平台动态二阶段机制已完成阶段性交付验证。

当前不能声称：

- Flowable GAN online 已完成；
- O2OA GAN 可以直接迁移到 Flowable；
- GAN 效果优于 rule fallback；
- 180s / 300s smoke 等同于生产级长期验证；
- 完整强多平台动态异构冗余全部完成。

关键报告路径：

- `docs/review/动态异构冗余机制最终完成说明.md`
- `docs/review/动态异构冗余机制总体阶段性收口报告.md`
- `docs/review/动态异构冗余机制真实联调验证报告.md`
- `docs/review/Flowable_dynamic_redundancy_second_stage_probe_report.md`
- `docs/review/O2OA_GAN_second_stage_threshold_policy_decision.md`

## 后续扩展方向

- 多模型投票：将第二阶段扩展为 `GAN + Rule + 其他分类器` 的加权投票，而不是单一备用路径。
- confidence 机制：在 `DecisionEngine` 中加入模型置信度或 RPC 可靠度，避免仅凭固定阈值做最终判定。
- risk 分级输出：将当前 `pass / reject` 扩展为 `low / medium / high risk`，为 runner 报表和平台侧回溯提供更细粒度结果。
