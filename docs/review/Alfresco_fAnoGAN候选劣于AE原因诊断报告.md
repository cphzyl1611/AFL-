# Alfresco fAnoGAN候选劣于AE原因诊断报告

## 1. 背景

当前 Alfresco 已作为后续主验证平台，metadata update、text/plain content update、multipart upload 三类文档接口均已完成真实 smoke。基于这些接口样本，项目已经完成 AE v1 engineering scorer、阈值校准、score service、轻量 API adapter、MCP adapter prototype，以及 fAnoGAN v1 candidate 离线评分闭环。

在扩展样本二次评估中，fAnoGAN candidate 未优于 AE v1：

| 策略 | false_accept | false_reject | accuracy |
|---|---:|---:|---:|
| rule_ae | 0 | 4 | 0.937500 |
| rule_fanogan | 0 | 5 | 0.921875 |

因此本轮只做诊断审计和阈值敏感性分析，判断该差异更可能来自代码实现问题，还是模型形态、阈值或样本分布问题。

## 2. 现象

扩展样本集共 64 条，其中 expected_valid=45、expected_invalid=19。metadata/content/multipart 三类样本数量分别为 22、21、21。

当前 fAnoGAN candidate 的 model_type 为 `gan_style_statistical_candidate`。该模型是在 torch 不可用条件下的 GAN-style 统计候选，不是完整深度 fAnoGAN，也不是 SE-fAnoGAN-ES。

扩展评估结果显示：

- rule_ae 无误放，误拒 4 条；
- rule_fanogan 无误放，误拒 5 条；
- fAnoGAN candidate 比 AE v1 多误拒 1 条边界样本；
- 当前 recommendation 为 `keep_ae_v1_as_primary`。

## 3. 是否发现代码实现问题

诊断脚本输出路径：

- `out/alfresco_fanogan_candidate_diagnosis/diagnosis_summary.csv`
- `out/alfresco_fanogan_candidate_diagnosis/false_reject_samples.csv`
- `out/alfresco_fanogan_candidate_diagnosis/threshold_sensitivity.csv`
- `out/alfresco_fanogan_candidate_diagnosis/recommendation.txt`

诊断结论如下：

| 检查项 | 结果 | 说明 |
|---|---|---|
| feature_dim_match | PASS | extractor、AE v1、fAnoGAN candidate 均为 32 维 |
| feature_names_match | PASS | AE v1、fAnoGAN candidate 与 feature extractor 字段名一致 |
| scenario_mapping_ok | PASS | details 中仅包含 metadata_update、content_update、multipart_upload |
| rule_fanogan_definition_ok | PASS | rule_fanogan_pass 等于 rule_pass and fanogan_pass |
| rule_ae_definition_ok | PASS | rule_ae_pass 等于 rule_pass and ae_pass |
| expected_valid_bool_ok | PASS | details 中 expected_valid 均为 true/false |
| metrics_recomputed_ok | PASS | 从 details 重新计算的 false_accept/false_reject 与 summary 一致 |

本轮未发现 feature_dim、feature_names、scenario mapping、布尔字段读取或指标统计方面的实现错误。

## 4. false reject 样本分析

当前误拒样本共 5 条，其中 rule_ae 误拒 4 条，rule_fanogan 误拒 5 条。唯一的 fAnoGAN-only 误拒样本是：

| scenario | file | sample_type | ae_score | fanogan_score | difference_type |
|---|---|---|---:|---:|---|
| content_update | content_update/content_border_mixed_language.txt | border | 0.979206 | 2.264330 | fanogan_only_reject |

AE v1 和 fAnoGAN candidate 共同误拒的边界样本包括：

| scenario | file | sample_type | ae_score | fanogan_score |
|---|---|---|---:|---:|
| content_update | content_update/content_border_many_lines.txt | border | 8.017791 | 7.321540 |
| metadata_update | metadata_update/metadata_border_long_title.json | border | 5.793167 | 5.050635 |
| multipart_upload | multipart_upload/upload_border_long_filename.txt | border | 2.381578 | 2.041179 |
| multipart_upload | multipart_upload/upload_border_multiline.txt | border | 5.716241 | 5.749302 |

这些样本均为边界合法样本，说明主要问题不是非法样本误放，而是候选模型对部分边界合法输入偏严格。

## 5. 阈值敏感性分析

以当前 fAnoGAN candidate 的 `threshold_high=1.261566` 为基准，诊断脚本对多个阈值倍率进行 sensitivity sweep。

| threshold | false_accept | false_reject | accuracy | notes |
|---:|---:|---:|---:|---|
| 1.261566 | 0 | 5 | 0.921875 | still_more_false_reject_than_rule_ae |
| 1.387723 | 0 | 5 | 0.921875 | still_more_false_reject_than_rule_ae |
| 1.576958 | 0 | 5 | 0.921875 | still_more_false_reject_than_rule_ae |
| 1.892349 | 0 | 5 | 0.921875 | still_more_false_reject_than_rule_ae |
| 2.523132 | 0 | 3 | 0.953125 | matches_or_beats_rule_ae_without_false_accept |
| 3.784698 | 0 | 3 | 0.953125 | matches_or_beats_rule_ae_without_false_accept |

结果表明，在当前扩展样本集上，将阈值提高到 2.523132 后，fAnoGAN candidate 的误拒可以从 5 降到 3，且没有引入 false_accept。该现象支持“候选模型阈值偏严”这一判断。

## 6. 原因判断

当前 fAnoGAN candidate 劣于 AE v1 不意味着代码一定有 bug。本轮诊断未发现特征维度、特征名、场景映射、布尔读取或指标统计错误。

更可能的原因是：

- 当前模型是 `gan_style_statistical_candidate`，不是完整深度 fAnoGAN；
- 训练样本较少，边界样本覆盖仍有限；
- 当前 threshold_high 对部分边界合法输入偏严格；
- score 分布在边界样本上与 AE v1 存在差异。

因此，本轮更倾向于将问题归因为阈值、样本分布和候选模型形态，而不是实现缺陷。

## 7. 是否建议修复代码

当前不建议直接修改 fAnoGAN candidate 代码逻辑。

建议保持现有实现，并将本轮输出作为候选模型诊断 evidence。如果后续继续推进 fAnoGAN candidate，可优先做：

- 基于扩展样本重新校准 threshold_high；
- 增加边界合法样本；
- 在 torch 可用环境下评估真正的轻量 fAnoGAN-style candidate；
- 做更完整的验证集拆分和阈值选择。

这些属于后续模型评估工作，不应在当前阶段把 candidate 直接提升为主判定机制。

## 8. 是否建议继续推进 fAnoGAN

可以继续作为候选方向推进，但不建议替代 AE v1。

当前 recommendation 为：

```text
recommendation: fanogan_candidate_underperforms_due_to_threshold_strictness
action: keep_ae_v1_as_primary
reason: No code inconsistency found. Raising candidate threshold can match or beat rule_ae without false_accept; first such multiplier=2.00, threshold=2.523132.
boundary: diagnostic threshold sensitivity only; not full SE-fAnoGAN-ES; no model promotion
```

阶段性结论是：AE v1 继续作为当前 Alfresco 主二阶段有效性判定机制；fAnoGAN candidate 保留为离线候选和后续研究方向。

## 9. 边界

- 这是 Alfresco fAnoGAN candidate 的诊断审计和阈值敏感性分析；
- 不等同于完整 SE-fAnoGAN-ES；
- 不等同于完整 GAN/fAnoGAN；
- 不替代 AE v1；
- 不访问 Alfresco 服务；
- 不运行长时间 fuzz；
- 不是完整 AFL++ mutation-chain；
- 不代表系统级 DHR；
- 不代表 O2OA 原生接口覆盖。
