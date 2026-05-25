# Alfresco torch fAnoGAN候选复评报告

## 1. 背景

Alfresco 已作为后续主验证平台。当前已完成 metadata update、text/plain content update、multipart upload 三类文档接口真实 smoke，并已完成 AE v1 engineering scorer、阈值校准、score service、轻量 API adapter、MCP adapter prototype，以及 fAnoGAN v1 candidate 离线对比。

上一轮 fAnoGAN candidate 采用 `gan_style_statistical_candidate`，原因是 base Python 环境中没有 torch。本轮确认项目 `.venv` 环境可用 torch，因此使用 `.venv` 重新构建 torch fAnoGAN-style candidate，并与 AE v1 和上一轮 fallback candidate 做离线对比。

## 2. 为什么之前 fallback

之前 Codex 使用 base Python 执行构建脚本，base 环境无法导入 torch，因此构建脚本生成了 dependency-free fallback：

- `model_type=gan_style_statistical_candidate`
- 未生成 `.pt` 权重文件；
- recommendation 为 `keep_ae_v1_as_primary`。

本轮强制使用：

```text
/home/dministrator/AFLplusplus/.venv/bin/python
```

## 3. 本轮 torch 环境

本轮环境确认结果：

| 项 | 值 |
|---|---|
| Python | `/home/dministrator/AFLplusplus/.venv/bin/python` |
| torch | `2.11.0+cu130` |
| cuda | `False` |

虽然 torch 构建版本带 CUDA 后缀，但当前运行环境下 `torch.cuda.is_available()` 返回 `False`，因此本轮训练和评分使用 CPU 路径完成。

## 4. torch candidate 模型说明

本轮新增/修正 torch candidate 分支，继续复用现有 32 维 Alfresco feature extractor。训练样本只使用 expected_valid=true 的合法/边界 seed。

输出文件：

- `model_stage/models/alfresco_fanogan_v1_candidate_meta.json`
- `model_stage/models/alfresco_fanogan_v1_candidate.pt`

meta 关键字段：

| 字段 | 值 |
|---|---|
| model_type | `torch_fanogan_style_candidate` |
| feature_dim | 32 |
| latent_dim | 8 |
| hidden_dim | 64 |
| train_sample_count | 9 |
| augmentation_count | 18 |
| threshold_low | 0.991476 |
| threshold_high | 1.926977 |
| torch_version | `2.11.0+cu130` |
| device_used | `cpu` |

评分公式为：

```text
0.75*sqrt(residual_mse) + 0.25*sqrt(critic_feature_mse)
```

该模型是轻量 torch fAnoGAN-style candidate，不是完整 SE-fAnoGAN-ES，也不是生产级 GAN/fAnoGAN。

## 5. 与 AE v1 对比

在原 fAnoGAN candidate compare 样本集上：

| 策略 | false_accept | false_reject | accuracy |
|---|---:|---:|---:|
| rule_only | 1 | 0 | 0.969697 |
| ae_only | 20 | 0 | 0.393939 |
| rule_ae | 0 | 0 | 1.000000 |
| fanogan_only | 12 | 0 | 0.636364 |
| rule_fanogan | 0 | 0 | 1.000000 |

在该小样本集合上，torch fAnoGAN-style candidate 与 AE v1 的 rule+score 策略表现持平，但没有优于 AE v1。

## 6. 与 fallback candidate 对比

上一轮 fallback candidate 在扩展样本集上的结果为：

| 策略 | false_accept | false_reject | accuracy |
|---|---:|---:|---:|
| rule_ae | 0 | 4 | 0.937500 |
| rule_fanogan | 0 | 5 | 0.921875 |

本轮 torch candidate 在扩展样本集上的聚合结果仍为：

| 策略 | false_accept | false_reject | accuracy |
|---|---:|---:|---:|
| rule_ae | 0 | 4 | 0.937500 |
| rule_fanogan | 0 | 5 | 0.921875 |

因此，在当前扩展样本集上，torch candidate 没有带来相对 fallback candidate 的聚合指标增益。

## 7. 扩展样本结果

扩展样本集：

- total_samples=64；
- expected_valid=45；
- expected_invalid=19；
- metadata/content/multipart 分别为 22/21/21。

`out/alfresco_extended_candidate_eval/summary.csv` 关键结果：

| 字段 | 值 |
|---|---:|
| rule_ae_false_accept | 0 |
| rule_ae_false_reject | 4 |
| rule_fanogan_false_accept | 0 |
| rule_fanogan_false_reject | 5 |
| rule_ae_accuracy | 0.937500 |
| rule_fanogan_accuracy | 0.921875 |

结论：torch fAnoGAN-style candidate 在扩展样本集上仍未优于 AE v1。

## 8. 诊断结果

`out/alfresco_fanogan_candidate_diagnosis/diagnosis_summary.csv` 显示：

- feature_dim_match=PASS；
- feature_names_match=PASS；
- scenario_mapping_ok=PASS；
- rule_fanogan_definition_ok=PASS；
- rule_ae_definition_ok=PASS；
- expected_valid_bool_ok=PASS；
- metrics_recomputed_ok=PASS。

误拒样本仍为 5 条，其中 fAnoGAN-only 误拒 1 条：

```text
content_update/content_border_mixed_language.txt
```

阈值敏感性结果显示，当前 `threshold_high=1.926977` 偏严格；提高到 `2.408721` 后可达到 `false_accept=0`、`false_reject=3`、`accuracy=0.953125`。

## 9. recommendation

当前 recommendation：

```text
recommendation: fanogan_candidate_underperforms_due_to_threshold_strictness
action: keep_ae_v1_as_primary
reason: No code inconsistency found. Raising candidate threshold can match or beat rule_ae without false_accept; first such multiplier=1.25, threshold=2.408721.
boundary: diagnostic threshold sensitivity only; not full SE-fAnoGAN-ES; no model promotion
```

综合判断：

- torch candidate 已完成可运行复评；
- 当前没有发现代码一致性问题；
- 当前结果更像阈值偏严和样本规模限制；
- AE v1 继续作为当前主二阶段有效性判定机制；
- fAnoGAN candidate 可保留为后续扩展评估方向，但不应直接替代 AE v1。

## 10. 边界

- 这是 torch fAnoGAN-style candidate 复评；
- 不等同于完整 SE-fAnoGAN-ES；
- 不等同于生产级 GAN/fAnoGAN；
- 不替代 AE v1；
- 不访问 Alfresco 服务；
- 不启动 O2OA 或 Flowable；
- 不是完整 AFL++ mutation-chain；
- 不代表完整系统级 DHR；
- 不代表 O2OA 原生接口覆盖。
