# O2OA 默认 AE@1.0 恢复执行报告

## 1. 执行依据

人工确认采用以下文件作为 O2OA 默认 AE@1.0 的最终恢复 source-of-truth：

- `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_model.pt`
- `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_meta.json`

本次执行只做定向恢复，不修改 AFL++ 主链代码，不修改 Flowable 最终口径，不重跑大型实验。

## 2. 已修改文件

本次修改了以下路径：

- `model_stage/models/sefanogan_ae_model.pt`
- `model_stage/models/sefanogan_ae_meta.json`
- `docs/final_delivery/fuzz_component_release/sefanogan_ae_model.pt`
- `docs/final_delivery/fuzz_component_release/sefanogan_ae_meta.json`
- `docs/review/O2OA默认AE恢复执行报告.md`

## 3. 拷贝关系

| 源文件 | 目标文件 | 目的 |
|---|---|---|
| `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_model.pt` | `model_stage/models/sefanogan_ae_model.pt` | 恢复 O2OA 默认 AE@1.0 运行路径下的模型权重 |
| `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_meta.json` | `model_stage/models/sefanogan_ae_meta.json` | 恢复 O2OA 默认 AE@1.0 运行路径下的 meta |
| `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_model.pt` | `docs/final_delivery/fuzz_component_release/sefanogan_ae_model.pt` | 补齐交付目录中的 O2OA 默认 AE 模型权重 |
| `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_meta.json` | `docs/final_delivery/fuzz_component_release/sefanogan_ae_meta.json` | 补齐交付目录中的 O2OA 默认 AE meta |

## 4. 恢复后哈希

### 4.1 模型权重

| 文件 | SHA256 |
|---|---|
| `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_model.pt` | `5de67e66e28af65fdf6adb5c506c91148fcc356accd49113c267896bbd69d3dc` |
| `model_stage/models/sefanogan_ae_model.pt` | `5de67e66e28af65fdf6adb5c506c91148fcc356accd49113c267896bbd69d3dc` |
| `docs/final_delivery/fuzz_component_release/sefanogan_ae_model.pt` | `5de67e66e28af65fdf6adb5c506c91148fcc356accd49113c267896bbd69d3dc` |

结论：运行路径与交付目录中的 O2OA 默认 AE 模型权重均已与 run3 source-of-truth 完全一致。

### 4.2 Meta

| 文件 | SHA256 |
|---|---|
| `docs/final_results/batch_compare_runs/baseline_156_run3/sefanogan_ae_meta.json` | `208daf66d82873dec8c19923d9c0a5a6b82ca36c512de52b0ff16b24ecb7acf2` |
| `model_stage/models/sefanogan_ae_meta.json` | `208daf66d82873dec8c19923d9c0a5a6b82ca36c512de52b0ff16b24ecb7acf2` |
| `docs/final_delivery/fuzz_component_release/sefanogan_ae_meta.json` | `208daf66d82873dec8c19923d9c0a5a6b82ca36c512de52b0ff16b24ecb7acf2` |

结论：运行路径与交付目录中的 O2OA 默认 AE meta 均已与 run3 source-of-truth 完全一致。

## 5. 交付目录补齐情况

`docs/final_delivery/fuzz_component_release/` 中已补齐并对齐以下 O2OA 默认 AE 文件：

- `docs/final_delivery/fuzz_component_release/sefanogan_ae_model.pt`
- `docs/final_delivery/fuzz_component_release/sefanogan_ae_meta.json`

两者均来自人工确认的 `baseline_156_run3` source-of-truth，哈希与源文件一致。

## 6. Flowable 口径影响检查

本次未修改以下 Flowable AE v3 文件：

- `model_stage/models/flowable_ae_v3_model.pt`
- `model_stage/models/flowable_ae_v3_meta.json`

复核当前 Flowable AE v3 哈希：

- `model_stage/models/flowable_ae_v3_model.pt`
  - SHA256: `8b73a7794720595cd5f7f6c298befe006197d43bff1ddf1da2a7f0225e8cd62e`
- `model_stage/models/flowable_ae_v3_meta.json`
  - SHA256: `3f1c50dd13a880cb5fc01d37b9f132c22471d60a1efacdd3a796d8159e2a779f`

结论：本次恢复只影响 O2OA 默认 AE 文件，不改动 Flowable 最终口径。

## 7. 阻塞项状态

### RISK-01

结论：已解除。

解除依据：

- O2OA 默认 AE@1.0 的 source-of-truth 已由人工确认。
- `model_stage/models/sefanogan_ae_model.pt` 与 `model_stage/models/sefanogan_ae_meta.json` 已恢复为 `baseline_156_run3` 对应文件。
- 恢复后哈希与源文件完全一致。

### RISK-02

结论：已解除。

解除依据：

- `docs/final_delivery/fuzz_component_release/` 已补齐 O2OA 默认 AE 模型权重与 meta。
- 交付目录中的 `sefanogan_ae_model.pt` 与 `sefanogan_ae_meta.json` 已与 `baseline_156_run3` source-of-truth 完全一致。

## 8. 当前是否仍存在阻塞项

本次修复范围内，不再存在 O2OA 默认 AE@1.0 模型权重与 meta source-of-truth 阻塞项。

未执行事项：

- 未重跑大型实验。
- 未重新训练模型。
- 未修改 AFL++ 主链代码。
- 未修改 Flowable 最终口径。

## 9. 最终结论

O2OA 默认 AE@1.0 已按人工确认的 `baseline_156_run3` source-of-truth 完成恢复；运行路径与交付目录均已补齐并通过 SHA256 哈希一致性验证。RISK-01 与 RISK-02 已解除。
