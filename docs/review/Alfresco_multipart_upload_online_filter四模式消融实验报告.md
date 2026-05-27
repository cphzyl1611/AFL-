# Alfresco multipart_upload online filter四模式消融实验报告

## 1. 背景

当前工程已经完成 `multipart_upload` / multipart/form-data 本地 mock target 的默认 `rule_ae` online filter smoke。本轮在同一 multipart_upload 本地 mock target、同一 seed、同一 AFL++ 代表链路下补充四模式消融实验，对比 `rule_only`、`rule_ae`、`rule_fanogan`、`rule_ae_fanogan` 的过滤行为、执行开销和运行错误情况。

本轮不访问真实 Alfresco 服务，不启动 O2OA、Flowable 或 Alfresco，不改变 AE v1 与 fAnoGAN candidate 的既有结论。

## 2. 实验目标

- 确认 multipart_upload online filter 四种模式均可由 AFL++ 调用；
- 对比 rule、AE v1、fAnoGAN candidate 在 multipart_upload 语义下的过滤分布；
- 观察 fAnoGAN candidate 在线路径是否可运行，以及是否出现 scoring error；
- 观察 fAnoGAN candidate 在线推理成本是否高于 AE v1；
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
| 运行脚本 | `scripts/run_alfresco_afl_multipart_online_filter_ablation.sh` |
| 汇总脚本 | `scripts/summarize_alfresco_afl_multipart_online_filter_ablation.py` |
| 输出目录 | `out/alfresco_afl_multipart_online_filter_ablation/` |
| 默认运行时长 | `DUR=20` |
| fAnoGAN 模式 AFL timeout | `AFL_EXEC_TIMEOUT_MS=5000` |
| target | 本地 multipart_upload mock target，不访问真实 Alfresco 服务 |

## 5. 每个模式的 AFL++ 运行结果

本节数值以 `out/alfresco_afl_multipart_online_filter_ablation/ablation_details.csv` 为准。四种模式均真实运行 AFL++。

| 模式 | execs_done | saved_crashes | saved_hangs | nv_err_exec | body_score_rpc_fail |
|---|---:|---:|---:|---:|---:|
| rule_only | 598 | 0 | 0 | 0 | 0 |
| rule_ae | 604 | 0 | 0 | 0 | 0 |
| rule_fanogan | 25 | 0 | 0 | 0 | 0 |
| rule_ae_fanogan | 27 | 0 | 0 | 0 | 0 |

`rule_fanogan` 与 `rule_ae_fanogan` 在 `FANOGAN_ENABLED=1`、`AFL_EXEC_TIMEOUT_MS=5000` 下完成在线路径调用。由于 fAnoGAN candidate 推理开销较高，两个 fAnoGAN 模式的 `execs_done` 明显低于 `rule_ae`，其中 AFL++ 的 `run_time` 字段记录为 0，表示该短时窗口主要消耗在慢速初始化、dry run 与少量执行上。

## 6. 过滤统计对比

过滤统计以 `ablation_details.csv` 与 `ablation_summary.csv` 为准：

| 模式 | sent_to_target | filtered_by_rule | filtered_by_ae | filtered_by_fanogan | filename_detected_count | content_type_detected_count |
|---|---:|---:|---:|---:|---:|---:|
| rule_only | 80 | 518 | 0 | 0 | 98 | 81 |
| rule_ae | 64 | 534 | 6 | 0 | 84 | 73 |
| rule_fanogan | 18 | 7 | 0 | 0 | 18 | 18 |
| rule_ae_fanogan | 20 | 7 | 0 | 0 | 20 | 20 |

## 7. fAnoGAN 在线路径观察

`rule_fanogan` 与 `rule_ae_fanogan` 均设置 `FANOGAN_ENABLED=1`，并使用 `AFL_EXEC_TIMEOUT_MS=5000` 适配 torch candidate scorer 初始化与推理开销。两种模式 `body_score_rpc_fail=0`，说明 fAnoGAN candidate 在线路径在本轮 multipart_upload 四模式消融中可运行且没有 scoring error。

fAnoGAN 两类模式的 `execs_done` 明显低于 `rule_ae`，说明在线推理成本仍高于 AE v1。本轮没有证据支持 fAnoGAN candidate 替代 AE v1。

## 8. 与 AE v1 主机制的关系

本轮只用于观察 multipart_upload online filter 四模式行为。除非 fAnoGAN candidate 在稳定性、过滤效果和执行开销上出现明确优于 AE v1 的证据，否则继续保持：

`ae_primary_recommendation=keep_ae_v1_as_primary`

## 9. 阶段性结论

本轮生成以下 evidence：

- `out/alfresco_afl_multipart_online_filter_ablation/rule_only/summary.csv`
- `out/alfresco_afl_multipart_online_filter_ablation/rule_only/eval_report.json`
- `out/alfresco_afl_multipart_online_filter_ablation/rule_only/fuzzer_stats`
- `out/alfresco_afl_multipart_online_filter_ablation/rule_ae/summary.csv`
- `out/alfresco_afl_multipart_online_filter_ablation/rule_ae/eval_report.json`
- `out/alfresco_afl_multipart_online_filter_ablation/rule_ae/fuzzer_stats`
- `out/alfresco_afl_multipart_online_filter_ablation/rule_fanogan/summary.csv`
- `out/alfresco_afl_multipart_online_filter_ablation/rule_fanogan/eval_report.json`
- `out/alfresco_afl_multipart_online_filter_ablation/rule_fanogan/fuzzer_stats`
- `out/alfresco_afl_multipart_online_filter_ablation/rule_ae_fanogan/summary.csv`
- `out/alfresco_afl_multipart_online_filter_ablation/rule_ae_fanogan/eval_report.json`
- `out/alfresco_afl_multipart_online_filter_ablation/rule_ae_fanogan/fuzzer_stats`
- `out/alfresco_afl_multipart_online_filter_ablation/ablation_summary.csv`
- `out/alfresco_afl_multipart_online_filter_ablation/ablation_details.csv`
- `out/alfresco_afl_multipart_online_filter_ablation/ablation_report.json`

`ablation_summary.csv` 的核心结论为：

- `scenario=multipart_upload`
- `modes=4`
- `total_execs_done=1254`
- `total_valid_exec=1200`
- `total_err_exec=0`
- `max_nv_err_rate=0.000000`
- `saved_crashes_total=0`
- `saved_hangs_total=0`
- `total_tmout=0`
- `scoring_error_total=0`
- `ae_primary_recommendation=keep_ae_v1_as_primary`
- `fanogan_online_observation=fanogan_online_path_runs_without_scoring_error_but_inference_cost_is_higher_keep_ae_v1_primary`

## 10. 边界

- 这是 multipart_upload online filter 四模式消融；
- 不等同于完整 SE-fAnoGAN-ES；
- 不等同于完整 GAN/fAnoGAN；
- 不代表真实 Alfresco 服务；
- mock target 不等同于真实 Alfresco 服务；
- 不代表所有场景完整 AFL++ mutation-chain；
- 不是四模式短时稳定性实验；
- AE v1 仍是主机制；
- 本轮不能宣称 fAnoGAN 替代 AE v1。
