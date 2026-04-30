# O2OA 默认 AE@1.0 Source-of-Truth 定位报告

## 1. 审查边界

本报告只定位 O2OA 默认 AE@1.0 的最终模型权重与 meta source-of-truth，不执行文件替换、不修改模型、不覆盖交付物。

审查对象包括：

- `model_stage/models/sefanogan_ae_model.pt`
- `model_stage/models/sefanogan_ae_meta.json`
- `model_stage/models/flowable_ae_v3_model.pt`
- `model_stage/models/flowable_ae_v3_meta.json`
- `docs/final_results/batch_compare_runs/` 下 `baseline_156_run*` 目录内的 AE 模型与 meta
- O2OA 默认 AE 口径相关文档、模板、总结文件

## 2. 关键事实

### 2.1 当前 `model_stage/models/sefanogan_ae_*` 不适合作为可信 source-of-truth

`model_stage/models/sefanogan_ae_model.pt` 与 `model_stage/models/flowable_ae_v3_model.pt` 的 SHA256 完全一致：

- `model_stage/models/sefanogan_ae_model.pt`
  - SHA256: `8b73a7794720595cd5f7f6c298befe006197d43bff1ddf1da2a7f0225e8cd62e`
- `model_stage/models/flowable_ae_v3_model.pt`
  - SHA256: `8b73a7794720595cd5f7f6c298befe006197d43bff1ddf1da2a7f0225e8cd62e`

`model_stage/models/sefanogan_ae_meta.json` 与 `model_stage/models/flowable_ae_v3_meta.json` 的核心指标也一致，均表现为 Flowable AE v3 口径：

- `train_count`: 56
- `val_count`: 74
- `input_dim`: 38
- `latent_dim`: 8
- `train_normal.mean`: `0.004890987806512774`
- `val_normal.mean`: `0.018669855725117184`
- `val_border.mean`: `4.730679528182373`
- `val_abnormal.mean`: `3919.48664132397`

结论：当前 `model_stage/models/sefanogan_ae_*` 极可能被 Flowable AE v3 文件覆盖或混入，不能直接认定为 O2OA 默认 AE@1.0 的可信源。

### 2.2 O2OA 默认 AE 口径在文档与模板中指向 baseline_156

以下文件一致指向 O2OA 默认 AE@1.0 的配置口径：

- `runner/templates/task_ae_default.json`
  - `model_name`: `ae`
  - `threshold`: `1.0`
  - `manifest`: `model_stage/manifests/dataset_manifest_156.txt`
  - `seed_dir`: `in/o2oa_body_model_compare`
- `docs/project_docs/current_default_baseline.md`
  - 默认基线为 156 行数据、AE 模型、阈值 `1.0`
  - 运行路径写为 `model_stage/models/sefanogan_ae_model.pt` 与 `model_stage/models/sefanogan_ae_meta.json`
- `docs/final_results/final_conclusion_current_stage.md`
  - 明确当前阶段默认项目基线为 `156 rows + AE + threshold=1.0 + rule_score-only`
  - 明确 baseline_156 是默认基线，enhanced_182 是增强实验配置
- `docs/final_results/batch_compare_runs/batch_compare_summary.md`
  - 对 baseline_156 和 enhanced_182 做三轮对比
  - 收口结论保留 baseline_156 作为默认项目基线
- `docs/final_delivery/current_stage_release/final_conclusion_current_stage.md`
  - 与 final_results 收口结论一致
- `docs/final_delivery/fuzz_component_release/fuzz_component_quickstart.md`
  - 运行入口仍以 `model_stage/models/sefanogan_ae_model.pt` 与 `model_stage/models/sefanogan_ae_meta.json` 为默认 AE 文件位置
  - 但已提示需确认其与 O2OA 默认 AE@1.0 对齐

结论：O2OA 默认 AE@1.0 的配置 source-of-truth 是 baseline_156，而不是 Flowable AE v3，也不是 enhanced_182。

## 3. 候选清单与排序

| 排名 | 候选 `.pt + meta` | 可信度 | 证据 | 判断 |
|---:|---|---|---|---|
| 1 | `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_model.pt` + `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_meta.json` | 中高 | 位于 baseline_156 三轮批量对比目录；manifest 为 `dataset_manifest_156.txt`；阈值口径为 AE@1.0；是 baseline_156 三个归档 run 中时间最新的一组；指标未脱离三轮均值 | 推荐作为恢复候选 |
| 2 | `docs/final_results/batch_compare_runs/baseline_156_run1/sefanogan_ae_model.pt` + `docs/final_results/batch_compare_runs/baseline_156_run1/sefanogan_ae_meta.json` | 中 | 位于 baseline_156 批量对比目录；manifest、阈值、场景均匹配；60s 结果较好 | 可作为备选，但不是最新归档 run |
| 3 | `docs/final_results/batch_compare_runs/baseline_156_run2/sefanogan_ae_model.pt` + `docs/final_results/batch_compare_runs/baseline_156_run2/sefanogan_ae_meta.json` | 中 | 位于 baseline_156 批量对比目录；manifest、阈值、场景均匹配 | 可作为备选，但缺少优先于 run3 的证据 |
| 4 | `docs/final_results/sefanogan_ae_meta_156_seed_20260319.json`、`docs/final_results/sefanogan_ae_meta_156_seed_20260320.json`、`docs/final_results/sefanogan_ae_meta_156_seed_20260321.json` | 低到中 | 文件名与 156 seed 相关，指标口径支持 baseline_156 路线 | 只有 meta，未在同一位置发现配套 `.pt`，不能单独作为恢复 source-of-truth |
| 5 | `docs/final_delivery/fuzz_component_release/sefanogan_ae_meta.json` | 低 | 位于交付目录，但指标更接近 enhanced_182，且缺少配套 `.pt` | 不适合作为 O2OA 默认 AE@1.0 恢复源 |
| 6 | `model_stage/models/sefanogan_ae_model.pt` + `model_stage/models/sefanogan_ae_meta.json` | 低 | 路径是默认运行路径，但内容与 Flowable AE v3 完全重合 | 当前文件不可信，不能作为 source-of-truth |
| 7 | `model_stage/models/flowable_ae_v3_model.pt` + `model_stage/models/flowable_ae_v3_meta.json` | 不成立 | 明确属于 Flowable AE v3，且与当前 `sefanogan_ae_*` 重合 | 排除 |

## 4. 候选证据细节

### 4.1 `baseline_156_run1`

文件：

- `docs/final_results/batch_compare_runs/baseline_156_run1/sefanogan_ae_model.pt`
- `docs/final_results/batch_compare_runs/baseline_156_run1/sefanogan_ae_meta.json`

权重 SHA256：

- `e69550b4be4c84bc57af3e04eb83109fd91ef3796b5f5a0baf06ab49d14b3525`

meta 核心指标：

- `train_count`: 79
- `val_count`: 77
- `train_normal.mean`: `0.038486479209806725`
- `val_normal.mean`: `0.06818048020496088`
- `val_border.mean`: `5.0522979781031605`
- `val_abnormal.mean`: `428.5447178301604`

实验结果：

- 20s: pass/reject `82/36`
- 60s: pass/reject `98/52`

判断：口径匹配 O2OA baseline_156，但不是三轮中时间最新的归档。

### 4.2 `baseline_156_run2`

文件：

- `docs/final_results/batch_compare_runs/baseline_156_run2/sefanogan_ae_model.pt`
- `docs/final_results/batch_compare_runs/baseline_156_run2/sefanogan_ae_meta.json`

权重 SHA256：

- `8430ed7d23d6015265de85783a81694b8e7667e4eac75c2d1ffb4e861382f1a2`

meta 核心指标：

- `train_count`: 79
- `val_count`: 77
- `train_normal.mean`: `0.034894824626301474`
- `val_normal.mean`: `0.061555715962587035`
- `val_border.mean`: `5.713790791667998`
- `val_abnormal.mean`: `420.98362946510315`

实验结果：

- 20s: pass/reject `78/42`
- 60s: pass/reject `87/67`

判断：口径匹配 O2OA baseline_156，但没有证据显示其优先级高于 run3。

### 4.3 `baseline_156_run3`

文件：

- `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_model.pt`
- `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_meta.json`

权重 SHA256：

- `5de67e66e28af65fdf6adb5c506c91148fcc356accd49113c267896bbd69d3dc`

meta 核心指标：

- `train_count`: 79
- `val_count`: 77
- `train_normal.mean`: `0.02944083351795149`
- `val_normal.mean`: `0.05658056608894292`
- `val_border.mean`: `5.025843648053706`
- `val_abnormal.mean`: `518.7413820287455`

实验结果：

- 20s: pass/reject `77/49`
- 60s: pass/reject `94/65`

判断：口径匹配 O2OA baseline_156，是三轮 baseline_156 归档中时间最新的一组。虽然最终结论采用三轮平均而非显式指定 run3，但在需要恢复一个具体 runtime `.pt + meta` 时，run3 是当前仓库内最合理的单组恢复候选。

## 5. 与四类口径的匹配判断

| 判断维度 | 最匹配候选 | 依据 |
|---|---|---|
| O2OA 默认模板 | `baseline_156_run3` | `runner/templates/task_ae_default.json` 指向 `dataset_manifest_156.txt`、AE、threshold `1.0`、O2OA 输入目录；run3 属于 baseline_156 |
| batch_compare 默认结果 | `baseline_156_run3`，同时 run1/run2 为同级证据 | `batch_compare_summary.md` 对 baseline_156 三轮求平均；run3 是三轮之一且不是异常离群 |
| final_results 收口结论 | baseline_156 系列整体；单组恢复推荐 run3 | `final_conclusion_current_stage.md` 明确默认基线为 baseline_156；未指定单一 run 哈希 |
| quickstart / final_delivery 口径 | runtime 路径为 `model_stage/models/sefanogan_ae_*`；内容应恢复为 baseline_156 | quickstart 与交付目录要求默认 AE 文件位于 `model_stage/models/`，但当前该路径内容与 Flowable v3 重合，因此应以 baseline_156 候选恢复 |

## 6. 推荐恢复方案

推荐将以下一组作为 O2OA 默认 AE@1.0 的恢复 source-of-truth：

- 源权重：
  - `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_model.pt`
- 源 meta：
  - `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_meta.json`
- 目标权重：
  - `model_stage/models/sefanogan_ae_model.pt`
- 目标 meta：
  - `model_stage/models/sefanogan_ae_meta.json`

推荐理由：

1. 该组文件属于 `baseline_156`，与 O2OA 默认 AE@1.0 的正式收口口径一致。
2. 该组文件与 `runner/templates/task_ae_default.json` 的 manifest、场景和 threshold 口径一致。
3. 该组文件位于 `docs/final_results/batch_compare_runs/`，有配套模型、meta、实验信息和批量对比结果。
4. 该组文件是三轮 baseline_156 候选中时间最新的归档 run。
5. 该组指标满足正常样本误差低、边界样本明显升高、异常样本显著升高的 AE 判别链路要求，且未偏离三轮平均结论。

## 7. 不确定性说明

本报告对 `baseline_156_run3` 的推荐把握程度为：中。

不能给出“高”把握的原因是：

1. `docs/final_results/final_conclusion_current_stage.md` 和 `batch_compare_summary.md` 明确确认的是 baseline_156 作为默认配置，而不是显式确认 `baseline_156_run3` 的 SHA256 为最终发布权重。
2. 三轮 baseline_156 都有完整 `.pt + meta`，且均与默认口径匹配；仓库内没有发现“run3 为最终模型”的签收文件、发布清单或哈希锁定记录。
3. `model_stage/models/sefanogan_ae_*` 是运行默认路径，但当前内容已经与 Flowable AE v3 重合，因此不能反向证明历史上最终默认 AE 的确切文件。
4. `docs/final_results/sefanogan_ae_meta_156_seed_*.json` 可作为 156 路线辅助证据，但缺少同目录配套 `.pt`，不能直接参与恢复。

如果需要审计级 source-of-truth，还需要补充以下证据之一：

- 明确写有最终 O2OA 默认 AE 权重 SHA256 的发布清单；
- 明确声明 `baseline_156_run3` 为最终发布模型的评审记录或交付记录；
- 与 `model_stage/models/sefanogan_ae_model.pt` 历史正确版本一致的备份文件及哈希；
- 人工确认三轮 baseline_156 中应选哪一轮作为交付 runtime 模型。

## 8. 最终结论

当前仓库中，O2OA 默认 AE@1.0 的最可信 source-of-truth 候选是：

- `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_model.pt`
- `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_meta.json`

建议最终将该组恢复为：

- `model_stage/models/sefanogan_ae_model.pt`
- `model_stage/models/sefanogan_ae_meta.json`

但该建议的把握程度为“中”，原因是仓库内缺少显式锁定 `baseline_156_run3` 为最终发布模型的 source-of-truth 文件。严谨验收口径下，应在执行恢复前由负责人确认 `baseline_156_run3` 是否就是最终选定的 O2OA 默认 AE@1.0 权重。
