# Alfresco metadata_update online filter四模式消融实验报告

## 1. 背景

当前工程已经完成 Alfresco `content_update` / text/plain 代表性 AFL++ mutation-chain、SE-fAnoGAN-ES-style online filter prototype、content_update 四模式消融和四模式短时稳定性实验，并已完成 `metadata_update` / application/json 本地 mock target 的默认 `rule_ae` online filter smoke。

本轮在同一 `metadata_update` / application/json 本地 mock target 上补充四模式消融实验，对比 `rule_only`、`rule_ae`、`rule_fanogan`、`rule_ae_fanogan` 的过滤行为和短时运行稳定性。

## 2. 实验目标

- 确认 metadata_update online filter 四种模式均可由 AFL++ 调用；
- 对比 rule、AE v1、fAnoGAN candidate 在 metadata_update 语义下的过滤分布；
- 观察 fAnoGAN candidate 在线路径是否可运行，以及是否出现 scoring error；
- 继续确认 AE v1 是否应作为当前主二阶段判定机制。

## 3. 四种模式说明

| 模式 | ONLINE_FILTER_MODE | FANOGAN_ENABLED | 说明 |
|---|---|---:|---|
| rule_only | `rule_only` | 0 | 只执行本地 metadata 规则过滤，通过后转发到 mock target。 |
| rule_ae | `rule_ae` | 0 | 规则通过后执行 AE v1 scoring，通过后转发到 mock target。 |
| rule_fanogan | `rule_fanogan` | 1 | 规则通过后执行 fAnoGAN candidate scoring。 |
| rule_ae_fanogan | `rule_ae_fanogan` | 1 | 规则通过后先执行 AE v1，再执行 fAnoGAN candidate。 |

## 4. 实验配置

| 项 | 值 |
|---|---|
| 场景 | `metadata_update` |
| body 类型 | `application/json` |
| seed 目录 | `in/alfresco_afl_metadata_update_smoke/` |
| 运行脚本 | `scripts/run_alfresco_afl_metadata_online_filter_ablation.sh` |
| 汇总脚本 | `scripts/summarize_alfresco_afl_metadata_online_filter_ablation.py` |
| 输出目录 | `out/alfresco_afl_metadata_online_filter_ablation/` |
| 默认运行时长 | `DUR=20` |
| fAnoGAN 模式 AFL timeout | `AFL_EXEC_TIMEOUT_MS=5000` |
| target | 本地 metadata mock target，不访问真实 Alfresco 服务 |

## 5. 每个模式的 AFL++ 运行结果

| mode | run_time | execs_done | saved_crashes | saved_hangs | nv_total_valid_exec | nv_err_exec | body_score_rpc_fail |
|---|---:|---:|---:|---:|---:|---:|---:|
| rule_only | 19 | 616 | 0 | 0 | 589 | 0 | 0 |
| rule_ae | 19 | 608 | 0 | 0 | 581 | 0 | 0 |
| rule_fanogan | 0 | 27 | 0 | 0 | 27 | 0 | 0 |
| rule_ae_fanogan | 0 | 27 | 0 | 0 | 27 | 0 | 0 |

## 6. 过滤统计对比

| mode | sent_to_target | filtered_by_rule | filtered_by_ae | filtered_by_fanogan |
|---|---:|---:|---:|---:|
| rule_only | 60 | 556 | 0 | 0 |
| rule_ae | 42 | 566 | 0 | 0 |
| rule_fanogan | 0 | 7 | 0 | 20 |
| rule_ae_fanogan | 0 | 7 | 0 | 21 |

总体汇总：

- `modes=4`
- `total_execs_done=1278`
- `total_valid_exec=1224`
- `total_err_exec=0`
- `max_nv_err_rate=0.000000`
- `saved_crashes_total=0`
- `saved_hangs_total=0`
- `scoring_error_total=0`
- `ae_primary_recommendation=keep_ae_v1_as_primary`

## 7. fAnoGAN 在线路径观察

`rule_fanogan` 和 `rule_ae_fanogan` 均设置 `FANOGAN_ENABLED=1`，并成功调用 fAnoGAN candidate scoring 路径；两种模式均未出现 `body_score_rpc_fail`。

同时，fAnoGAN 模式的 `execs_done` 明显低于 `rule_ae`，主要原因是 torch candidate scorer 初始化和推理成本较高。当前观测结论为：

`fanogan_online_path_runs_without_scoring_error_but_inference_cost_is_higher_keep_ae_v1_primary`

## 8. 与 AE v1 主机制的关系

本轮没有发现 fAnoGAN candidate 在 metadata_update online filter 中明显优于 AE v1 的证据。AE v1 的 `rule_ae` 模式在短时 AFL++ 运行中稳定，且没有 crash、hang、`nv_err_exec` 或 scoring error。

因此当前仍建议：

`ae_primary_recommendation=keep_ae_v1_as_primary`

## 9. 阶段性结论

本轮已完成 metadata_update online filter 四模式消融实验：

- 四种模式均由 AFL++ 调用并产生 evidence；
- `rule_only`、`rule_ae`、`rule_fanogan`、`rule_ae_fanogan` 均未出现 crash 或 hang；
- 四种模式 `nv_err_exec=0`；
- 四种模式 `body_score_rpc_fail=0`；
- fAnoGAN candidate 在线路径可运行，但短时样本量受推理成本限制；
- 当前仍保持 AE v1 为主二阶段判定机制。

生成 evidence：

- `out/alfresco_afl_metadata_online_filter_ablation/rule_only/summary.csv`
- `out/alfresco_afl_metadata_online_filter_ablation/rule_only/eval_report.json`
- `out/alfresco_afl_metadata_online_filter_ablation/rule_only/fuzzer_stats`
- `out/alfresco_afl_metadata_online_filter_ablation/rule_ae/summary.csv`
- `out/alfresco_afl_metadata_online_filter_ablation/rule_ae/eval_report.json`
- `out/alfresco_afl_metadata_online_filter_ablation/rule_ae/fuzzer_stats`
- `out/alfresco_afl_metadata_online_filter_ablation/rule_fanogan/summary.csv`
- `out/alfresco_afl_metadata_online_filter_ablation/rule_fanogan/eval_report.json`
- `out/alfresco_afl_metadata_online_filter_ablation/rule_fanogan/fuzzer_stats`
- `out/alfresco_afl_metadata_online_filter_ablation/rule_ae_fanogan/summary.csv`
- `out/alfresco_afl_metadata_online_filter_ablation/rule_ae_fanogan/eval_report.json`
- `out/alfresco_afl_metadata_online_filter_ablation/rule_ae_fanogan/fuzzer_stats`
- `out/alfresco_afl_metadata_online_filter_ablation/ablation_summary.csv`
- `out/alfresco_afl_metadata_online_filter_ablation/ablation_details.csv`
- `out/alfresco_afl_metadata_online_filter_ablation/ablation_report.json`

## 10. 边界

- 这是 metadata_update online filter 四模式消融；
- 不等同于完整 SE-fAnoGAN-ES；
- 不等同于完整 GAN/fAnoGAN；
- 不代表真实 Alfresco 服务；
- 不代表所有场景完整 AFL++ mutation-chain；
- AE v1 仍是主机制；
- 本轮不能宣称 fAnoGAN 替代 AE v1。
