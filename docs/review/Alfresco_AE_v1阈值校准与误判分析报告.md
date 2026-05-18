# Alfresco_AE_v1阈值校准与误判分析报告

## 1. 背景

Alfresco 已作为后续主验证平台，当前已完成 metadata update、text/plain content update、multipart upload 创建/保存三类标准文档接口的真实 smoke。

上一阶段已新增 Alfresco AE v1 engineering scorer，用于对三类输入执行本地 rule + score 判定。本轮在不启动 Alfresco 服务、不运行 fuzz、不训练深度模型的前提下，对 AE v1 做阈值校准、误判分析和最小消融。

## 2. 当前 AE v1 模型说明

当前模型文件：

```text
model_stage/models/alfresco_ae_v1_meta.json
```

关键字段：

```text
model_name=alfresco_ae_v1
model_type=ae_like_statistical_baseline
threshold_low=0.933776
threshold_high=1.623614
train_sample_count=9
scenario_coverage.metadata_update=3
scenario_coverage.content_update=3
scenario_coverage.multipart_upload=3
```

当前 AE v1 不是 torch autoencoder，不是 GAN / fAnoGAN。它使用合法/边界 seed 的特征均值和标准差，计算 root mean square z-distance 作为工程化异常分数。

## 3. 样本设计

本轮样本总数为 33：

- expected_valid=9：复用三类 Alfresco 合法/边界 seed；
- expected_invalid=24：包含 3 个既有 `seed_bad_0` 和 21 个 synthetic invalid。

synthetic invalid 覆盖：

- metadata：missing name、name object、properties missing、title array、description object、超长 name、空 title；
- content：empty content、NUL byte、非 UTF-8、超长文本、高熵 ASCII 文本、纯空白；
- multipart：非 `.txt` 文件名、缺失 nodeType、错误 nodeType、缺失 autoRename、autoRename=false、缺失 filedata、NUL byte content、超长内容。

synthetic invalid 只在脚本内构造，不写入 `in/` seed 目录。

## 4. 阈值 sweep 方法

新增脚本：

```text
scripts/run_alfresco_ae_v1_threshold_sweep.py
```

输出：

```text
out/alfresco_ae_v1_threshold_sweep/summary.csv
out/alfresco_ae_v1_threshold_sweep/details.csv
out/alfresco_ae_v1_threshold_sweep/score_distribution.csv
```

候选阈值：

```text
0.500000
0.933776
1.000000
1.623614
2.000000
2.029517
2.435421
3.000000
```

每个阈值同时统计：

- rule_only；
- ae_only；
- rule+AE。

其中 summary 中的 `false_accept`、`false_reject`、`accuracy` 为 rule+AE 策略结果；额外列给出 rule_only 和 ae_only 的误放/误拒。

## 5. rule_only / ae_only / rule+AE 对比

推荐阈值为当前 `threshold_high=1.623614`，它是本轮 sweep 中第一个让 rule+AE 达到 0 误放、0 误拒的阈值。

在 `threshold=1.623614` 时：

```text
total_samples=33
expected_valid=9
expected_invalid=24
rule_only_pass=10
rule_only_reject=23
ae_only_pass=29
ae_only_reject=4
rule_ae_pass=9
rule_ae_reject=24
rule_only_false_accept=1
rule_only_false_reject=0
ae_only_false_accept=20
ae_only_false_reject=0
false_accept=0
false_reject=0
accuracy=1.000000
```

对比结论：

- rule_only：整体较强，但会放过一个高熵 ASCII 文本样本；
- ae_only：不能单独作为有效性判定，语义类非法样本与正常样本距离较近，误放较多；
- rule+AE：在当前样本集上消除了 rule_only 的 1 个误放，同时没有引入误拒。

## 6. score 分布

score 分布摘要：

```text
metadata_update valid seed: min=0.937674, median=1.060269, max=1.123614
metadata_update synthetic invalid: min=0.885073, median=0.974091, max=4.318939
content_update valid seed: min=0.752459, median=0.773157, max=0.811793
content_update synthetic invalid: min=0.653128, median=0.905434, max=182.470788
multipart_upload valid seed: min=0.919997, median=0.933776, max=1.033334
multipart_upload synthetic invalid: min=0.771050, median=0.800870, max=238.412539
```

分析：

- 超长文本、超长 multipart 内容、超长 metadata name、高熵 ASCII 文本等数值/分布异常样本分数明显升高；
- 纯字段类型错误、缺字段等语义规则类异常分数可能接近正常样本，仍需要规则层兜底；
- AE v1 更适合作为二阶段补充判定和异常解释，不适合作为规则替代。

## 7. 误判分析

在当前推荐阈值 `1.623614` 下：

- rule+AE：未发现误放；
- rule+AE：未发现误拒；
- ae_only：存在 20 个误放，说明 AE-like baseline 不能单独承担有效性判定；
- rule_only：存在 1 个误放，即规则可通过但高熵 ASCII 文本应视为 synthetic invalid；
- rule+AE 对该高熵样本给出 `ae_score=14.458226`，成功拒绝。

低阈值会引入误拒：

- `threshold=0.933776`：rule+AE false_reject=4；
- `threshold=1.000000`：rule+AE false_reject=3。

因此不建议把阈值调低到 `threshold_low` 附近。

## 8. 是否建议进入 GAN / fAnoGAN

当前不建议立即进入 GAN / fAnoGAN。

理由：

- rule+AE 在当前 synthetic set 上已达到 0 误放、0 误拒；
- AE v1 已能补一个规则盲点，即高熵但规则合法的文本；
- 误判分析显示主要不足来自语义类非法样本分数接近正常样本，这更需要扩展特征、样本和规则，而不是直接进入 GAN；
- 当前样本规模仍小，尚不足以支撑稳定 GAN / fAnoGAN 训练与结论。

建议下一步优先扩充 Alfresco 样本集、扩展 score service/profile 联调，再评估是否需要 GAN / fAnoGAN。

## 9. 边界

- 当前 AE v1 是 `ae_like_statistical_baseline`；
- 本轮是阈值校准和误判分析；
- 不等同于完整深度 AE；
- 不等同于 GAN / fAnoGAN；
- 不等同于完整 AFL++ mutation-chain；
- 不等同于系统级 DHR；
- 不等同于 O2OA 原生接口覆盖。
