# Alfresco扩展样本与fAnoGAN候选二次评估报告

## 1. 背景

上一轮已完成 Alfresco fAnoGAN v1 candidate 离线评分闭环。由于当时样本规模较小，`rule_ae` 与 `rule_fanogan` 在 33 个样本上均为 `false_accept=0`、`false_reject=0`，无法证明 fAnoGAN candidate 相比 AE v1 存在增益。

本轮扩充 Alfresco 三类接口样本集，并在不访问 Alfresco 服务、不运行 fuzz、不训练完整深度模型的前提下重新评估 AE v1 与 fAnoGAN candidate。

## 2. 为什么需要扩充样本

fAnoGAN candidate 只有在更丰富的正常、边界和异常样本下，才可能暴露相对 AE v1 的误拒、误放差异。本轮扩展样本重点覆盖：

- metadata update 的长标题、Unicode 文件名、字段类型错误和空 payload；
- content update 的多行文本、混合语言、高熵文本、空内容、NUL byte 和非 UTF-8；
- multipart upload 的长文件名、多行内容、错误扩展名、缺失 nodeType、`autoRename=false` 和二进制内容。

## 3. 扩展样本设计

新增样本目录：

```text
in/alfresco_extended_eval_dataset/
```

新增 manifest：

```text
in/alfresco_extended_eval_dataset/manifest.json
```

样本数量：

| scenario | expected_valid | expected_invalid | total |
|---|---:|---:|---:|
| metadata_update | 15 | 7 | 22 |
| content_update | 15 | 6 | 21 |
| multipart_upload | 15 | 6 | 21 |
| 合计 | 45 | 19 | 64 |

## 4. 评估方法

新增脚本：

```text
scripts/run_alfresco_extended_candidate_eval.py
```

该脚本读取 manifest，对每个样本执行：

- 规则判定；
- AE v1 score；
- fAnoGAN candidate score；
- `rule_ae` 决策；
- `rule_fanogan` 决策。

输出目录：

```text
out/alfresco_extended_candidate_eval/
```

输出文件：

- `summary.csv`
- `details.csv`
- `compare_with_previous.csv`
- `recommendation.txt`

## 5. AE v1 与 fAnoGAN candidate 对比

当前 fAnoGAN candidate 仍为：

```text
model_type=gan_style_statistical_candidate
```

不是 PyTorch fAnoGAN，也不是完整 SE-fAnoGAN-ES。

扩展样本对比结果：

| strategy | false_accept | false_reject | accuracy |
|---|---:|---:|---:|
| rule_ae | 0 | 4 | 0.937500 |
| rule_fanogan | 0 | 5 | 0.921875 |

fAnoGAN candidate 没有降低 `false_accept`，并且比 AE v1 多 1 个 `false_reject`。

## 6. Summary 结果

`summary.csv` 关键字段：

```text
total_samples=64
expected_valid=45
expected_invalid=19
rule_only_false_accept=1
rule_only_false_reject=0
ae_only_false_accept=16
ae_only_false_reject=4
rule_ae_false_accept=0
rule_ae_false_reject=4
fanogan_only_false_accept=7
fanogan_only_false_reject=5
rule_fanogan_false_accept=0
rule_fanogan_false_reject=5
rule_ae_accuracy=0.937500
rule_fanogan_accuracy=0.921875
recommendation=keep_ae_v1_as_primary
execution_scope=alfresco_extended_candidate_eval
```

## 7. Details 概况

`rule_ae` 的误拒样本主要是边界样本：

- `content_update/content_border_many_lines.txt`
- `metadata_update/metadata_border_long_title.json`
- `multipart_upload/upload_border_long_filename.txt`
- `multipart_upload/upload_border_multiline.txt`

`rule_fanogan` 除上述样本外，还额外误拒：

- `content_update/content_border_mixed_language.txt`

这说明 fAnoGAN candidate 在扩展样本下没有改善边界样本误拒，反而更保守。

## 8. 与上一轮 candidate 结果对比

上一轮 33 个样本：

```text
rule_ae=false_accept=0,false_reject=0,accuracy=1.000000
rule_fanogan=false_accept=0,false_reject=0,accuracy=1.000000
```

本轮 64 个扩展样本：

```text
rule_ae=false_accept=0,false_reject=4,accuracy=0.937500
rule_fanogan=false_accept=0,false_reject=5,accuracy=0.921875
```

扩展样本暴露了边界样本误拒问题，但没有证明 fAnoGAN candidate 优于 AE v1。

## 9. Recommendation

`recommendation.txt` 结论：

```text
recommendation: keep_ae_v1_as_primary
reason: fAnoGAN candidate does not outperform AE v1 on the extended sample set
```

因此仍建议保留 AE v1 为主二阶段判定机制。

## 10. 阶段性结论

Alfresco 扩展样本集与 fAnoGAN candidate 二次评估已完成。结果表明，在更大样本集下，fAnoGAN candidate 仍未优于 AE v1，且出现更多边界样本误拒。当前不建议将 fAnoGAN candidate 提升为主判定机制。

## 11. 边界

- 这是扩展样本下的离线二次评估；
- 不等同于完整 SE-fAnoGAN-ES；
- 不等同于完整 GAN/fAnoGAN；
- 不等同于完整 AFL++ mutation-chain；
- 不访问 Alfresco 服务；
- 不代表 O2OA 原生接口覆盖；
- 是否保留 AE v1 为主机制以 `recommendation.txt` 为准。
