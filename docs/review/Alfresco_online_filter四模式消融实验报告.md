# Alfresco online filter四模式消融实验报告

## 1. 背景

当前工程已完成 SE-fAnoGAN-ES-style online filter prototype，并在代表性 Alfresco `content_update` / text/plain 本地 mock target 上完成默认 `rule_ae` 模式 AFL++ smoke。本轮在同一 seed、同一 mock target、同一 AFL++ 代表链路下补充四模式消融实验，对比 `rule_only`、`rule_ae`、`rule_fanogan`、`rule_ae_fanogan` 的在线过滤行为。

本轮不访问真实 Alfresco 服务，不启动 O2OA、Flowable 或 Alfresco，不改变 AE v1 与 fAnoGAN candidate 的既有结论。

## 2. 实验目标

本轮目标是验证 online filter wrapper 的四种路径均可被 AFL++ 调用，并记录各模式的过滤统计、crash/hang 情况和 scorer 错误情况。

重点观察：

- 四种模式是否都能真实运行 `afl-fuzz`；
- `rule_fanogan` 与 `rule_ae_fanogan` 是否真实启用 fAnoGAN candidate；
- 每种模式是否出现 crash、hang 或 scoring error；
- 四模式结果是否支持 fAnoGAN candidate 替代 AE v1。

## 3. 四种模式说明

| mode | FANOGAN_ENABLED | 判定链路 | 说明 |
|---|---:|---|---|
| `rule_only` | 0 | rule -> mock target | 只验证规则过滤路径 |
| `rule_ae` | 0 | rule -> AE v1 -> mock target | 默认主路径，AE v1 为主二阶段判定 |
| `rule_fanogan` | 1 | rule -> fAnoGAN candidate -> mock target | 验证 fAnoGAN candidate 在线路径 |
| `rule_ae_fanogan` | 1 | rule -> AE v1 -> fAnoGAN candidate -> mock target | 验证 AE + fAnoGAN 串联路径 |

## 4. 实验配置

| 配置项 | 值 |
|---|---|
| target wrapper | `targets/alfresco_content_update_online_filter_wrapper.py` |
| mock target semantics | `targets/alfresco_content_update_mock.py` |
| seed 目录 | `in/alfresco_afl_content_update_smoke/` |
| 运行脚本 | `scripts/run_alfresco_afl_online_filter_ablation.sh` |
| 单模式 smoke 脚本 | `scripts/run_alfresco_afl_online_filter_smoke.sh` |
| 汇总脚本 | `scripts/summarize_alfresco_afl_online_filter_ablation.py` |
| 默认单模式 DUR | 20 秒 |
| 输出目录 | `out/alfresco_afl_online_filter_ablation/` |

fAnoGAN candidate 依赖 torch scorer，单次执行明显慢于 rule/AE 路径。本轮在 fAnoGAN 模式下设置 AFL 单次执行超时为 5000 ms，避免 AFL++ dry-run 将 torch scorer 初始化误判为 target timeout；总运行仍保持短时 smoke 口径。

## 5. 每个模式的 AFL++ 运行结果

| mode | run_time | execs_done | execs_per_sec | saved_crashes | saved_hangs | nv_err_exec |
|---|---:|---:|---:|---:|---:|---:|
| `rule_only` | 17 | 550 | 32.20 | 0 | 0 | 0 |
| `rule_ae` | 17 | 544 | 31.87 | 0 | 0 | 0 |
| `rule_fanogan` | 0 | 25 | 25000.00 | 0 | 0 | 0 |
| `rule_ae_fanogan` | 0 | 25 | 25000.00 | 0 | 0 | 0 |

四种模式均真实运行 AFL++，均未出现 crash、hang 或 NV 错误。fAnoGAN 两个模式的 `execs_done` 明显少于 `rule_only` / `rule_ae`，主要原因是 torch fAnoGAN-style candidate scorer 在 Python AFL faux forkserver 路径下初始化和推理成本较高，20 秒短时预算内有效样本量较小。

## 6. 过滤统计对比

| mode | sent_to_target | filtered_by_rule | filtered_by_ae | filtered_by_fanogan | body_score_rpc_ok | body_score_rpc_fail |
|---|---:|---:|---:|---:|---:|---:|
| `rule_only` | 113 | 437 | 0 | 0 | 0 | 0 |
| `rule_ae` | 111 | 432 | 2 | 0 | 113 | 0 |
| `rule_fanogan` | 18 | 7 | 0 | 0 | 18 | 0 |
| `rule_ae_fanogan` | 18 | 7 | 0 | 0 | 18 | 0 |

`rule_fanogan` 和 `rule_ae_fanogan` 的 `body_score_rpc_ok=18`，说明 fAnoGAN candidate 在线 scorer 已实际运行且未出现 scoring error。由于这两个模式的总样本数较少，不能把绝对过滤数量直接解释为 fAnoGAN 优于或劣于 AE v1。

## 7. 对 AE v1 与 fAnoGAN candidate 的解释

本轮结果说明：

- AE v1 在线路径运行稳定，仍适合作为默认主二阶段判定机制；
- fAnoGAN candidate 在线路径已经接入并可运行；
- fAnoGAN candidate 在线路径在短时 AFL++ smoke 中无 scoring error；
- fAnoGAN candidate 在线路径因 torch scorer 成本导致短时样本量明显低于 rule/AE 路径；
- 本轮没有证据表明 fAnoGAN candidate 优于 AE v1。

因此当前 recommendation 仍为 `keep_ae_v1_as_primary`。fAnoGAN candidate 可保留为后续研究增强方向，但不能替代 AE v1。

## 8. 阶段性结论

本轮已完成 SE-fAnoGAN-ES-style online filter 四模式消融实验，并生成以下 evidence：

- `out/alfresco_afl_online_filter_ablation/rule_only/summary.csv`
- `out/alfresco_afl_online_filter_ablation/rule_only/eval_report.json`
- `out/alfresco_afl_online_filter_ablation/rule_only/fuzzer_stats`
- `out/alfresco_afl_online_filter_ablation/rule_ae/summary.csv`
- `out/alfresco_afl_online_filter_ablation/rule_ae/eval_report.json`
- `out/alfresco_afl_online_filter_ablation/rule_ae/fuzzer_stats`
- `out/alfresco_afl_online_filter_ablation/rule_fanogan/summary.csv`
- `out/alfresco_afl_online_filter_ablation/rule_fanogan/eval_report.json`
- `out/alfresco_afl_online_filter_ablation/rule_fanogan/fuzzer_stats`
- `out/alfresco_afl_online_filter_ablation/rule_ae_fanogan/summary.csv`
- `out/alfresco_afl_online_filter_ablation/rule_ae_fanogan/eval_report.json`
- `out/alfresco_afl_online_filter_ablation/rule_ae_fanogan/fuzzer_stats`
- `out/alfresco_afl_online_filter_ablation/ablation_summary.csv`
- `out/alfresco_afl_online_filter_ablation/ablation_details.csv`
- `out/alfresco_afl_online_filter_ablation/ablation_report.json`

聚合结论：

- `modes=4`
- `total_execs_done=1144`
- `total_valid_exec=1090`
- `total_err_exec=0`
- `saved_crashes_total=0`
- `saved_hangs_total=0`
- `ae_primary_recommendation=keep_ae_v1_as_primary`
- `fanogan_online_observation=fanogan_online_path_runs_without_scoring_error_but_short_sample_count_keep_ae_v1_primary`

## 9. 边界

- 这是 SE-fAnoGAN-ES-style online filter 四模式消融。
- 不等同于完整 SE-fAnoGAN-ES。
- 不等同于完整 GAN/fAnoGAN。
- 不代表真实 Alfresco 服务。
- 不代表所有场景完整 AFL++ mutation-chain。
- mock target 不等同于真实 Alfresco 服务。
- AE v1 仍是主机制，除非后续独立实验明确证明 fAnoGAN 更优。
- 本轮不能宣称 fAnoGAN 替代 AE v1。
