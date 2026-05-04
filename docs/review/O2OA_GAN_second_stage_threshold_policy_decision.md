# O2OA GAN second stage 阈值策略决策报告

## 背景与目的

O2OA AE + GAN online second stage 动态异构冗余已经完成机制闭环，并形成了 smoke、离线阈值扫描、在线阈值对比和固定灰区样本回放证据。

本报告用于对当前 threshold=1.0 与 threshold=1.2 的工程策略进行收口，明确默认策略、候选策略和降级策略。本文不提出修改正式 `o2oa_default` profile，不扩展 Flowable，也不声称 GAN 效果优于 rule fallback。

## 已完成验证

### 离线阈值扫描

已完成 O2OA 灰区样本的 GAN threshold 离线扫描，候选阈值包括：

```text
0.6, 0.8, 1.0, 1.2, 1.5, 2.0
```

离线扫描给出了 threshold=1.2 作为后续候选的初步依据，但样本量与标签规模不足以证明 1.2 是最优阈值。

### 在线 smoke 对比

已完成 threshold=1.0 与 threshold=1.2 的在线 smoke 对比，每组 3 次，每次 20 秒。

| threshold | 平均 pass | 平均 reject | 平均 second_pass | 平均 second_reject | rpc_fail_total | HTTP |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1.0 | 91.67 | 51.33 | 14.67 | 9.00 | 0 | 200 |
| 1.2 | 91.00 | 52.00 | 14.67 | 7.33 | 0 | 200 |

在线 smoke 表明两组均可稳定走通 GAN online second stage，且 threshold=1.2 在该小样本在线复验中降低了平均 `second_reject`。但在线 smoke 来自 fuzz 过程，不是严格同输入回放，因此不能单独用于阈值优劣结论。

### 固定灰区样本回放

已完成固定灰区样本回放，使用 24 个已标注灰区样本。

标签分布：

| label | count |
| --- | ---: |
| valid | 11 |
| invalid | 7 |
| uncertain | 6 |

回放结果：

| mode | pass | reject | valid_reject | invalid_pass |
| --- | ---: | ---: | ---: | ---: |
| rule fallback | 24 | 0 | 0 | 7 |
| GAN threshold=1.0 | 5 | 19 | 9 | 1 |
| GAN threshold=1.2 | 17 | 7 | 4 | 4 |

固定回放显示：threshold=1.2 相比 1.0 降低 valid 误拒，从 9 降到 4；同时增加 invalid 误放，从 1 增到 4。

## threshold=1.0 与 threshold=1.2 的差异

threshold=1.0 的特点：

- 更保守；
- reject 倾向更强；
- 固定回放中 invalid_pass 更低；
- 固定回放中 valid_reject 更高；
- 适合作为当前正式默认策略继续保留。

threshold=1.2 的特点：

- 更宽松；
- 固定回放中 valid_reject 降低；
- 固定回放中 invalid_pass 增加；
- 可作为下一轮平衡候选策略，但不能作为当前正式默认策略直接替换。

## 为什么不能直接改成 1.2

当前不建议直接将正式 `o2oa_default` profile 的 `second_stage_threshold` 从 1.0 修改为 1.2，原因如下：

1. 1.2 降低 valid 误拒的同时增加 invalid 误放，存在明确取舍；
2. 当前固定回放样本只有 24 个，valid / invalid 标签数量仍不足；
3. `uncertain` 样本不能作为强结论依据；
4. 在线 smoke 不是严格同输入回放，不能单独证明阈值优势；
5. 尚缺少覆盖率收益、异常发现率、延迟开销和多轮统计显著性数据；
6. 当前证据不足以证明 1.2 是最优阈值，也不足以证明 GAN 效果优于 rule fallback。

## 推荐策略

### 1.0：保守默认策略

正式 `integration/platform_profiles/o2oa_default.json` 继续保持：

```text
second_stage_threshold=1.0
```

该策略更保守，适合当前默认发布和可复核工程交付。

### 1.2：平衡候选策略

新增候选 profile 示例：

`integration/platform_profiles/o2oa_gan_balanced_t1_2.example.json`

该 profile 仅用于下一轮扩样本验证，不应直接替代 `o2oa_default`。当前证据只能说明 1.2 在固定回放中降低 valid 误拒，同时增加 invalid 误放。

### rule fallback：GAN 不可用时的降级路径

rule fallback 保持为 GAN RPC 不可用时的降级路径。它保障动态冗余机制在 GAN 服务不可用时仍能给出 second stage 判定，但当前不能据此声称 rule fallback 或 GAN 其中之一具有整体效果优势。

## 当前最终工程口径

建议使用以下工程交付口径：

> O2OA AE + GAN online second stage 动态异构冗余机制已经完成阶段性工程闭环。当前正式阈值策略保持 threshold=1.0 作为保守默认；threshold=1.2 可作为下一轮平衡候选阈值继续扩样本验证。现有固定回放显示 1.2 降低 valid 误拒，但同时增加 invalid 误放，因此暂不建议修改正式 profile。当前不能证明 1.2 是最优阈值，也不能证明 GAN 效果优于 rule fallback。

不能使用以下口径：

- threshold=1.2 是最优阈值；
- GAN 效果优于 rule fallback；
- Flowable GAN online 已完成；
- 完整多平台动态异构冗余已完成。

## 后续需要补充的数据

后续如需推动阈值策略从候选走向正式默认，至少需要补充：

1. 更大规模 O2OA 灰区样本；
2. 更多 valid / invalid 真值标签；
3. 多轮同输入回放与在线 smoke 统计；
4. 覆盖率收益、异常发现率和稳定性指标；
5. 阈值变化对延迟、吞吐和降级路径的影响；
6. Flowable second stage 的独立实现与验证；
7. 多平台条件下的一致性评估。

## 结论边界

可以确认：

- threshold=1.0 是当前保守默认策略；
- threshold=1.2 是下一轮平衡候选策略；
- rule fallback 是 GAN 不可用时的降级路径；
- threshold=1.2 在当前固定回放中降低 valid 误拒；
- threshold=1.2 同时增加 invalid 误放。

不能确认：

- threshold=1.2 是最优阈值；
- 现在可以直接修改正式 profile；
- GAN 效果优于 rule fallback；
- Flowable 动态冗余完成；
- 多平台动态异构冗余完成。
