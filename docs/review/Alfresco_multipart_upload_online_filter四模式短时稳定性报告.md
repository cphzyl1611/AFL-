# Alfresco multipart_upload online filter四模式短时稳定性报告

## 1. 背景

当前工程已经完成 `multipart_upload` / multipart-form-data 本地 mock target 的 online filter smoke 和四模式消融实验。本轮在同一 multipart_upload 本地 mock target、同一 seed、同一 AFL++ 代表链路下，对 `rule_only`、`rule_ae`、`rule_fanogan`、`rule_ae_fanogan` 分别执行 3 轮短时稳定性实验。

本轮不访问真实 Alfresco 服务，不启动 O2OA、Flowable 或 Alfresco，不改变 AE v1 与 fAnoGAN candidate 的既有结论。

## 2. 实验目标

- 确认 multipart_upload online filter 四种模式均可完成 3 轮 AFL++ 短时运行；
- 统计每种模式的 crash、hang、`nv_err_exec` 与 `body_score_rpc_fail`；
- 观察 fAnoGAN candidate 在线路径是否多轮无 scoring error；
- 观察 fAnoGAN candidate 在线推理成本是否仍高于 AE v1；
- 继续确认 AE v1 是否应作为当前主二阶段判定机制。

## 3. 四种模式说明

| 模式 | ONLINE_FILTER_MODE | FANOGAN_ENABLED | 说明 |
|---|---|---:|---|
| rule_only | `rule_only` | 0 | 只执行本地 multipart rule filter，通过后转发到 mock target。 |
| rule_ae | `rule_ae` | 0 | 规则通过后执行 AE v1 scoring，通过后转发到 mock target。 |
| rule_fanogan | `rule_fanogan` | 1 | 规则通过后执行 fAnoGAN candidate scoring。 |
| rule_ae_fanogan | `rule_ae_fanogan` | 1 | 规则通过后先执行 AE v1，再执行 fAnoGAN candidate。 |

## 4. 实验配置

| 项 | 值 |
|---|---|
| 场景 | `multipart_upload` |
| body 类型 | `multipart/form-data` |
| seed 目录 | `in/alfresco_afl_multipart_upload_smoke/` |
| 运行脚本 | `scripts/run_alfresco_afl_multipart_online_filter_ablation_stability.sh` |
| 汇总脚本 | `scripts/summarize_alfresco_afl_multipart_online_filter_ablation_stability.py` |
| 输出目录 | `out/alfresco_afl_multipart_online_filter_ablation_stability/` |
| 每模式轮次 | 3 |
| 默认运行时长 | `DUR=20` |
| fAnoGAN 模式 AFL timeout | `AFL_EXEC_TIMEOUT_MS=5000` |
| target | 本地 multipart_upload mock target，不访问真实 Alfresco 服务 |

## 5. 每种模式 3 轮运行结果

本节数值以 `out/alfresco_afl_multipart_online_filter_ablation_stability/stability_details.csv` 为准。四种模式均完成 3 轮 AFL++ 短时运行。

| 模式 | 轮次 | execs_done | saved_crashes | saved_hangs | nv_err_exec | body_score_rpc_fail |
|---|---|---:|---:|---:|---:|---:|
| rule_only | run_01 | 599 | 0 | 0 | 0 | 0 |
| rule_only | run_02 | 594 | 0 | 0 | 0 | 0 |
| rule_only | run_03 | 592 | 0 | 0 | 0 | 0 |
| rule_ae | run_01 | 599 | 0 | 0 | 0 | 0 |
| rule_ae | run_02 | 595 | 0 | 0 | 0 | 0 |
| rule_ae | run_03 | 593 | 0 | 0 | 0 | 0 |
| rule_fanogan | run_01 | 27 | 0 | 0 | 0 | 0 |
| rule_fanogan | run_02 | 27 | 0 | 0 | 0 | 0 |
| rule_fanogan | run_03 | 27 | 0 | 0 | 0 | 0 |
| rule_ae_fanogan | run_01 | 27 | 0 | 0 | 0 | 0 |
| rule_ae_fanogan | run_02 | 27 | 0 | 0 | 0 | 0 |
| rule_ae_fanogan | run_03 | 27 | 0 | 0 | 0 | 0 |

## 6. 稳定性指标

稳定性指标以 `stability_summary.csv` 为准。如果某模式所有轮次均满足 `saved_crashes=0`、`saved_hangs=0`、`nv_err_exec=0`、`body_score_rpc_fail=0`，则该模式 `stability_score=1.000000`。

| 指标 | 值 |
|---|---:|
| scenario | multipart_upload |
| modes | 4 |
| runs_per_mode | 3 |
| total_runs | 12 |
| total_execs_done | 3734 |
| total_valid_exec | 3572 |
| total_err_exec | 0 |
| max_nv_err_rate | 0.000000 |
| saved_crashes_total | 0 |
| saved_hangs_total | 0 |
| total_tmout | 0 |
| scoring_error_total | 0 |
| rule_only_stability_score | 1.000000 |
| rule_ae_stability_score | 1.000000 |
| rule_fanogan_stability_score | 1.000000 |
| rule_ae_fanogan_stability_score | 1.000000 |
| overall_stability_score | 1.000000 |

## 7. fAnoGAN 在线路径稳定性观察

`rule_fanogan` 与 `rule_ae_fanogan` 均设置 `FANOGAN_ENABLED=1`，并使用 `AFL_EXEC_TIMEOUT_MS=5000` 适配 torch candidate scorer 初始化与推理开销。

两类 fAnoGAN 模式 6 个轮次均为 `body_score_rpc_fail=0`，说明 fAnoGAN candidate 在线路径在本轮 multipart_upload 四模式短时稳定性实验中多轮可运行且无 scoring error。

fAnoGAN 模式总执行量明显低于 `rule_ae`：`rule_fanogan_total_execs_done=81`，`rule_ae_fanogan_total_execs_done=81`，而 `rule_ae_total_execs_done=1787`。这说明 fAnoGAN candidate 在线推理成本仍明显高于 AE v1。本轮没有证据支持 fAnoGAN candidate 替代 AE v1。

## 8. 与 AE v1 主机制的关系

本轮只用于观察 multipart_upload online filter 四模式短时稳定性。除非 fAnoGAN candidate 在稳定性、过滤效果和执行开销上出现明确优于 AE v1 的证据，否则继续保持：

`ae_primary_recommendation=keep_ae_v1_as_primary`

## 9. 阶段性结论

本轮生成以下 evidence：

- `out/alfresco_afl_multipart_online_filter_ablation_stability/stability_summary.csv`
- `out/alfresco_afl_multipart_online_filter_ablation_stability/stability_details.csv`
- `out/alfresco_afl_multipart_online_filter_ablation_stability/stability_report.json`
- 每个模式每轮的 `summary.csv`
- 每个模式每轮的 `eval_report.json`
- 每个模式每轮的 `fuzzer_stats`

正式纳入 Git 的 evidence 只包括上述小型 summary/report/fuzzer_stats 文件，不包括 `queue/`、`crashes/`、`hangs/`、`fastresume*`、`filter_stats*`、`plot_data`、`cmdline`、`fuzzer_setup`、`target_hash` 等 AFL++ 运行内部文件。

`stability_summary.csv` 的核心结论为：

- `scenario=multipart_upload`
- `modes=4`
- `runs_per_mode=3`
- `total_runs=12`
- `total_execs_done=3734`
- `total_valid_exec=3572`
- `total_err_exec=0`
- `max_nv_err_rate=0.000000`
- `saved_crashes_total=0`
- `saved_hangs_total=0`
- `total_tmout=0`
- `scoring_error_total=0`
- `overall_stability_score=1.000000`
- `ae_primary_recommendation=keep_ae_v1_as_primary`
- `fanogan_online_stability_observation=fanogan_online_path_stable_without_scoring_error_but_inference_cost_is_higher_keep_ae_v1_primary`

## 10. 边界

- 这是 multipart_upload online filter 四模式短时稳定性实验；
- 不等同于完整 SE-fAnoGAN-ES；
- 不等同于完整 GAN/fAnoGAN；
- 不代表真实 Alfresco 服务；
- mock target 不等同于真实 Alfresco 服务；
- 不代表所有场景完整 AFL++ mutation-chain；
- 不是长时间稳定性实验；
- AE v1 仍是主机制；
- 本轮不能宣称 fAnoGAN 替代 AE v1。
