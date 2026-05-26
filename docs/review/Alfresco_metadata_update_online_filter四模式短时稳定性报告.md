# Alfresco metadata_update online filter四模式短时稳定性报告

## 1. 背景

当前工程已经完成 `metadata_update` / application/json 本地 mock target 的 online filter smoke 和四模式消融实验。本轮在同一 metadata_update 本地 mock target 上继续执行四模式短时稳定性实验，对 `rule_only`、`rule_ae`、`rule_fanogan`、`rule_ae_fanogan` 每种模式各运行 3 轮 AFL++ 短时 smoke。

## 2. 实验目标

- 验证 metadata_update online filter 四种模式在多轮短时 AFL++ 运行中是否稳定；
- 统计每种模式每轮的 crash、hang、`nv_err_exec` 和 `body_score_rpc_fail`；
- 验证 fAnoGAN candidate 在线路径在多轮中是否无 scoring error；
- 观察 fAnoGAN candidate 在线推理成本是否仍高于 AE v1；
- 保持 AE v1 是否仍为当前主二阶段判定机制的结论。

## 3. 四种模式说明

| 模式 | ONLINE_FILTER_MODE | FANOGAN_ENABLED | 说明 |
|---|---|---:|---|
| rule_only | `rule_only` | 0 | 只执行 metadata rule filter，通过后转发到本地 mock target。 |
| rule_ae | `rule_ae` | 0 | 规则通过后执行 AE v1 scoring，通过后转发到本地 mock target。 |
| rule_fanogan | `rule_fanogan` | 1 | 规则通过后执行 fAnoGAN candidate scoring。 |
| rule_ae_fanogan | `rule_ae_fanogan` | 1 | 规则通过后先执行 AE v1，再执行 fAnoGAN candidate。 |

## 4. 实验配置

| 项 | 值 |
|---|---|
| 场景 | `metadata_update` |
| body 类型 | `application/json` |
| seed 目录 | `in/alfresco_afl_metadata_update_smoke/` |
| 运行脚本 | `scripts/run_alfresco_afl_metadata_online_filter_ablation_stability.sh` |
| 汇总脚本 | `scripts/summarize_alfresco_afl_metadata_online_filter_ablation_stability.py` |
| 输出目录 | `out/alfresco_afl_metadata_online_filter_ablation_stability/` |
| 每模式轮数 | `RUNS=3` |
| 每轮时长 | `DUR=20` |
| fAnoGAN 模式 AFL timeout | `AFL_EXEC_TIMEOUT_MS=5000` |
| target | 本地 metadata mock target，不访问真实 Alfresco 服务 |

## 5. 每种模式 3 轮运行结果

| mode | run_id | execs_done | saved_crashes | saved_hangs | nv_err_exec | body_score_rpc_fail |
|---|---|---:|---:|---:|---:|---:|
| rule_only | run_01 | 610 | 0 | 0 | 0 | 0 |
| rule_only | run_02 | 601 | 0 | 0 | 0 | 0 |
| rule_only | run_03 | 602 | 0 | 0 | 0 | 0 |
| rule_ae | run_01 | 605 | 0 | 0 | 0 | 0 |
| rule_ae | run_02 | 603 | 0 | 0 | 0 | 0 |
| rule_ae | run_03 | 603 | 0 | 0 | 0 | 0 |
| rule_fanogan | run_01 | 26 | 0 | 0 | 0 | 0 |
| rule_fanogan | run_02 | 27 | 0 | 0 | 0 | 0 |
| rule_fanogan | run_03 | 27 | 0 | 0 | 0 | 0 |
| rule_ae_fanogan | run_01 | 27 | 0 | 0 | 0 | 0 |
| rule_ae_fanogan | run_02 | 27 | 0 | 0 | 0 | 0 |
| rule_ae_fanogan | run_03 | 27 | 0 | 0 | 0 | 0 |

四种模式均完成 3 轮，合计 `total_runs=12`。

## 6. 稳定性指标

| 指标 | 值 |
|---|---:|
| total_execs_done | 3785 |
| total_valid_exec | 3623 |
| total_err_exec | 0 |
| max_nv_err_rate | 0.000000 |
| saved_crashes_total | 0 |
| saved_hangs_total | 0 |
| scoring_error_total | 0 |
| rule_only_stability_score | 1.000000 |
| rule_ae_stability_score | 1.000000 |
| rule_fanogan_stability_score | 1.000000 |
| rule_ae_fanogan_stability_score | 1.000000 |
| overall_stability_score | 1.000000 |

## 7. fAnoGAN 在线路径稳定性观察

`rule_fanogan` 与 `rule_ae_fanogan` 均在 3 轮中启用 `FANOGAN_ENABLED=1`，并使用 `AFL_EXEC_TIMEOUT_MS=5000` 适配 torch candidate scorer 初始化与推理开销。两种 fAnoGAN 模式 6 轮合计 `body_score_rpc_fail=0`，说明 fAnoGAN candidate 在线路径在本轮短时多轮运行中没有 scoring error。

同时，fAnoGAN 两类模式每轮 `execs_done` 约为 26 到 27，明显低于 `rule_ae` 的约 603 到 605，说明在线推理成本仍明显高于 AE v1。

本轮观察结论为：

`fanogan_online_path_stable_without_scoring_error_but_inference_cost_is_higher_keep_ae_v1_primary`

## 8. 与 AE v1 主机制的关系

本轮没有出现支持 fAnoGAN candidate 替代 AE v1 的证据。`rule_ae` 三轮均未出现 crash、hang、`nv_err_exec` 或 scoring error，且吞吐显著高于 fAnoGAN 模式。

因此当前仍建议：

`ae_primary_recommendation=keep_ae_v1_as_primary`

## 9. 阶段性结论

本轮已完成 metadata_update online filter 四模式短时稳定性实验：

- 四种模式均完成 3 轮；
- 12 轮均真实运行 AFL++；
- 12 轮均 `saved_crashes=0`；
- 12 轮均 `saved_hangs=0`；
- 12 轮均 `nv_err_exec=0`；
- 12 轮均 `body_score_rpc_fail=0`；
- fAnoGAN candidate 在线路径多轮无 scoring error；
- fAnoGAN candidate 在线推理成本仍明显高于 AE v1；
- AE v1 仍是当前主二阶段判定机制。

生成 evidence：

- `out/alfresco_afl_metadata_online_filter_ablation_stability/stability_summary.csv`
- `out/alfresco_afl_metadata_online_filter_ablation_stability/stability_details.csv`
- `out/alfresco_afl_metadata_online_filter_ablation_stability/stability_report.json`
- `out/alfresco_afl_metadata_online_filter_ablation_stability/<mode>/run_01/summary.csv`
- `out/alfresco_afl_metadata_online_filter_ablation_stability/<mode>/run_01/eval_report.json`
- `out/alfresco_afl_metadata_online_filter_ablation_stability/<mode>/run_01/fuzzer_stats`
- `out/alfresco_afl_metadata_online_filter_ablation_stability/<mode>/run_02/summary.csv`
- `out/alfresco_afl_metadata_online_filter_ablation_stability/<mode>/run_02/eval_report.json`
- `out/alfresco_afl_metadata_online_filter_ablation_stability/<mode>/run_02/fuzzer_stats`
- `out/alfresco_afl_metadata_online_filter_ablation_stability/<mode>/run_03/summary.csv`
- `out/alfresco_afl_metadata_online_filter_ablation_stability/<mode>/run_03/eval_report.json`
- `out/alfresco_afl_metadata_online_filter_ablation_stability/<mode>/run_03/fuzzer_stats`

## 10. 边界

- 这是 metadata_update online filter 四模式短时稳定性实验；
- 不等同于完整 SE-fAnoGAN-ES；
- 不等同于完整 GAN/fAnoGAN；
- 不代表真实 Alfresco 服务；
- 不代表所有场景完整 AFL++ mutation-chain；
- 不是长时间稳定性实验；
- AE v1 仍是主机制；
- 本轮不能宣称 fAnoGAN 替代 AE v1。
