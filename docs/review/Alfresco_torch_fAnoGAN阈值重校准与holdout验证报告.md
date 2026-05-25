# Alfresco torch fAnoGAN阈值重校准与holdout验证报告

## 1. 背景

Alfresco 已作为后续主验证平台，metadata update、text/plain content update、multipart upload 三类文档接口均已完成真实 smoke。当前 AE v1 已完成二阶段有效性判定、阈值校准、score service、轻量 API adapter 和 MCP adapter prototype；fAnoGAN candidate 已完成 fallback、torch fAnoGAN-style 复评和劣势诊断。

上一轮 torch fAnoGAN-style candidate 在扩展样本整体评估中没有优于 AE v1：

| 策略 | false_accept | false_reject | accuracy |
|---|---:|---:|---:|
| rule_ae | 0 | 4 | 0.937500 |
| rule_fanogan | 0 | 5 | 0.921875 |

诊断显示没有发现 feature_dim、feature_names、scenario mapping、metrics 或 expected_valid bool 读取问题，主要疑点是 `threshold_high` 偏严格。本轮因此做 threshold calibration / holdout 验证，避免用同一批样本既调阈值又宣称效果。

## 2. 为什么需要 calibration / holdout

直接在全量扩展样本上提高阈值可以减少 false_reject，但这会把验证集同时当作调参集，不能作为稳定优于 AE v1 的证据。

本轮采用固定随机种子进行 deterministic split：

- calibration split：只用于选择 fAnoGAN threshold；
- holdout split：只用于最终比较 rule_ae、默认 rule_fanogan 和校准后 rule_fanogan。

本轮不重训模型，不访问 Alfresco 服务，不运行 fuzz。

## 3. 数据划分

输入数据来自：

- `in/alfresco_extended_eval_dataset/manifest.json`

划分策略：

- 固定随机种子：`20260519`；
- 按 `scenario` 与 `expected_valid` 分层；
- 保证 calibration 和 holdout 都覆盖 `metadata_update`、`content_update`、`multipart_upload`；
- calibration 样本数：30；
- holdout 样本数：34。

## 4. 阈值候选与选择规则

当前 torch candidate 默认阈值：

```text
threshold_high=1.926977
```

候选阈值包括：

- `threshold_high`；
- `threshold_high * 1.1`；
- `threshold_high * 1.25`；
- `threshold_high * 1.5`；
- `threshold_high * 2.0`；
- `threshold_high * 2.5`；
- `threshold_high * 3.0`；
- calibration fanogan_score 分位数：p80、p85、p90、p95、p97.5。

选择规则：

1. 优先选择 `false_accept=0` 的候选；
2. 在 `false_accept=0` 的候选中选择 `false_reject` 最小者；
3. 若多个候选相同，选择较小阈值；
4. 若所有候选都有 false_accept，则选择 accuracy 最高且 false_accept 最低者。

## 5. calibration 结果

`out/alfresco_fanogan_threshold_holdout_eval/calibration_summary.csv` 关键结果：

| threshold | false_accept | false_reject | accuracy | selected |
|---:|---:|---:|---:|---|
| 1.926977 | 0 | 4 | 0.866667 | false |
| 2.408721 | 0 | 3 | 0.900000 | false |
| 5.233747 | 0 | 2 | 0.933333 | false |
| 7.113244 | 0 | 1 | 0.966667 | false |
| 12.511790 | 0 | 0 | 1.000000 | true |

最终选择：

```text
chosen_threshold=12.511790
```

选择原因：

```text
selected lowest false_reject among false_accept=0 candidates; tie-breaker lower threshold
```

## 6. holdout 结果

`out/alfresco_fanogan_threshold_holdout_eval/holdout_summary.csv` 关键结果：

| 策略 | false_accept | false_reject | accuracy |
|---|---:|---:|---:|
| rule_ae | 0 | 0 | 1.000000 |
| rule_fanogan_default | 0 | 1 | 0.970588 |
| rule_fanogan_calibrated | 0 | 0 | 1.000000 |

holdout 样本：

- total_samples=34；
- expected_valid=24；
- expected_invalid=10。

校准后 fAnoGAN 在 holdout 上修复了默认阈值的 1 个 false_reject，且没有引入 false_accept。

## 7. 与 AE v1 对比

在 holdout split 上：

- AE v1 已达到 `false_accept=0,false_reject=0,accuracy=1.000000`；
- 校准后 fAnoGAN 也达到 `false_accept=0,false_reject=0,accuracy=1.000000`；
- 因此校准后 fAnoGAN 相对默认 fAnoGAN 有改进，但没有优于 AE v1。

这说明当前 torch fAnoGAN-style candidate 可进入后续扩展评估，但不能替代 AE v1。

## 8. recommendation

`out/alfresco_fanogan_threshold_holdout_eval/recommendation.txt` 给出：

```text
recommendation: keep_ae_v1_as_primary
chosen_threshold: 12.511790
reason: calibrated fAnoGAN candidate does not clearly outperform AE v1 on the holdout split
boundary: holdout validation only; not full SE-fAnoGAN-ES; no automatic replacement of AE v1
```

## 9. 阶段性结论

本轮完成了 torch fAnoGAN-style candidate 的阈值重校准与 holdout 验证：

- calibration 上选择的阈值为 `12.511790`；
- holdout 上校准后 fAnoGAN 从默认的 1 个 false_reject 降为 0；
- holdout 上校准后 fAnoGAN 与 AE v1 持平；
- 当前仍没有证据证明 fAnoGAN candidate 稳定优于 AE v1；
- 当前继续保持 AE v1 为主二阶段有效性判定机制。

## 10. 边界

- 这是 torch fAnoGAN-style candidate 阈值验证；
- 不等同于完整 SE-fAnoGAN-ES；
- 不等同于生产级 GAN/fAnoGAN；
- 不访问 Alfresco 服务；
- 不启动 O2OA 或 Flowable；
- 不运行长时间 fuzz；
- 不是完整 AFL++ mutation-chain；
- 不代表系统级 DHR；
- 是否替代 AE v1 取决于后续更大 holdout 或真实服务联调结果。
