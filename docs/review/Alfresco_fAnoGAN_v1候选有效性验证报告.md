# Alfresco fAnoGAN v1候选有效性验证报告

## 1. 背景

Alfresco 已作为后续主验证平台，metadata update、text/plain content update、multipart upload 三类标准文档接口已完成真实 smoke。此前已完成 Alfresco AE v1 engineering scorer、阈值校准、score service、轻量 API adapter 和 MCP adapter prototype。

本轮在不访问 Alfresco 服务、不运行 fuzz、不训练深度模型的前提下，新增 Alfresco fAnoGAN v1 candidate，用于和当前 AE v1 二阶段判定结果做离线对比。

## 2. 为什么在 AE v1 后评估 fAnoGAN candidate

AE v1 在当前样本集上已经能通过 rule+AE 拦截规则层放过的高熵异常样本。fAnoGAN candidate 的目的不是替代 AE v1，而是验证 GAN-style 异常评分是否在相同特征、相同样本和相同规则条件下具备进一步增益。

## 3. 模型类型说明

当前环境未提供 PyTorch，因此本轮生成的是：

```text
model_type=gan_style_statistical_candidate
```

该 candidate 复用 Alfresco 固定长度特征向量，并基于合法/边界 seed 的统计分布计算 GAN-style score：

```text
0.55*rms_z_distance + 0.35*nearest_normal_distance + 0.10*entropy_penalty
```

这不是完整 fAnoGAN，也不是完整 SE-fAnoGAN-ES。

## 4. 样本设计

训练样本只使用 expected_valid=true 的合法/边界 seed：

- metadata_update：3 个；
- content_update：3 个；
- multipart_upload：3 个。

由于样本量较小，构建阶段对正常样本做了确定性轻量 jitter augmentation，仅用于阈值估计：

```text
train_sample_count=9
augmentation_count=18
```

对比样本复用 AE v1 threshold sweep 的样本设计，包括 12 个既有 seed 和 21 个 synthetic invalid 样本，总计 33 个样本。

## 5. Scoring 方法

fAnoGAN candidate 使用 `model_stage/alfresco_feature_extractor.py` 的 32 维特征，不新增独立特征体系。新增文件包括：

- `model_stage/alfresco_fanogan_v1_candidate.py`
- `model_stage/alfresco_fanogan_v1_candidate_scorer.py`
- `scripts/build_alfresco_fanogan_v1_candidate.py`
- `scripts/run_alfresco_fanogan_v1_candidate_compare.py`
- `integration/platform_profiles/alfresco_fanogan_v1_candidate.json`

模型 meta 路径：

```text
model_stage/models/alfresco_fanogan_v1_candidate_meta.json
```

当前阈值：

```text
threshold_low=0.671197
threshold_high=1.261566
```

## 6. 与 AE v1 对比

对比输出：

- `out/alfresco_fanogan_v1_candidate_compare/summary.csv`
- `out/alfresco_fanogan_v1_candidate_compare/details.csv`
- `out/alfresco_fanogan_v1_candidate_compare/compare_with_ae.csv`
- `out/alfresco_fanogan_v1_candidate_compare/recommendation.txt`

关键对比结果：

| strategy | false_accept | false_reject | accuracy |
|---|---:|---:|---:|
| rule_only | 1 | 0 | 0.969697 |
| ae_only | 20 | 0 | 0.393939 |
| rule_ae | 0 | 0 | 1.000000 |
| fanogan_only | 12 | 0 | 0.636364 |
| rule_fanogan | 0 | 0 | 1.000000 |

## 7. Summary 结果

`summary.csv` 关键字段：

```text
mode=rule_score
total_samples=33
expected_valid=9
expected_invalid=24
rule_only_pass=10
rule_only_reject=23
ae_v1_pass=29
ae_v1_reject=4
fanogan_pass=21
fanogan_reject=12
rule_fanogan_pass=9
rule_fanogan_reject=24
false_accept=0
false_reject=0
accuracy=1.000000
model_type=gan_style_statistical_candidate
execution_scope=alfresco_fanogan_v1_candidate_min_calibration
```

## 8. Details 概况

33 个样本均完成离线 scoring。9 个 expected_valid seed 在 rule_fanogan 策略下通过，24 个 expected_invalid 样本在 rule_fanogan 策略下拒绝。

单独使用 fAnoGAN candidate 仍会放过部分非法样本，因此不能替代规则过滤。rule_fanogan 与 rule_ae 在当前样本集上均达到 `false_accept=0`、`false_reject=0`。

## 9. Recommendation

`recommendation.txt` 结论：

```text
recommendation: keep_ae_v1_as_primary
reason: fAnoGAN candidate does not outperform AE v1 on current samples
```

因此建议继续以 AE v1 作为当前主二阶段判定机制，fAnoGAN candidate 仅保留为后续扩展评估对象。

## 10. 阶段性结论

Alfresco fAnoGAN v1 candidate 已完成离线异常评分闭环，并可与 AE v1 在同一批 seed + synthetic invalid 样本上进行横向比较。当前 candidate 未优于 AE v1，不建议提升为主判定链路。

## 11. 边界

- 这是 Alfresco fAnoGAN v1 candidate；
- 不等同于完整 SE-fAnoGAN-ES；
- 不等同于完整 GAN / fAnoGAN；
- 不替代 AE v1；
- 不是完整 AFL++ mutation-chain；
- 不是系统级 DHR；
- 不代表 O2OA 原生接口覆盖。
