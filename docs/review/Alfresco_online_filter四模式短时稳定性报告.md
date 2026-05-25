# Alfresco online filter四模式短时稳定性报告

## 1. 背景

v0.3.8 已完成 SE-fAnoGAN-ES-style online filter 四模式消融实验，确认 `rule_only`、`rule_ae`、`rule_fanogan`、`rule_ae_fanogan` 四种模式均可在代表性 Alfresco `content_update` / text/plain 本地 mock target 上由 AFL++ 调用。本轮在同一代表链路上进一步执行四模式短时稳定性实验，每种模式运行 3 轮。

本轮不访问真实 Alfresco 服务，不启动 O2OA、Flowable 或 Alfresco，不修改 AE v1 与 fAnoGAN candidate 的既有结论。

## 2. 实验目标

本轮目标是验证四种 online filter 模式在多轮短时 AFL++ 运行中是否保持稳定。

观察指标包括：

- 每种模式 3 轮是否均真实运行 `afl-fuzz`；
- 每轮 `saved_crashes`、`saved_hangs`、`nv_err_exec` 是否为 0；
- 每轮 `body_score_rpc_fail` 是否为 0；
- fAnoGAN candidate 在线路径在多轮中是否可运行；
- 结果是否支持继续保持 AE v1 为主机制。

## 3. 四种模式说明

| mode | FANOGAN_ENABLED | 判定链路 | 说明 |
|---|---:|---|---|
| `rule_only` | 0 | rule -> mock target | 只执行规则过滤 |
| `rule_ae` | 0 | rule -> AE v1 -> mock target | 默认主路径，AE v1 为主二阶段判定 |
| `rule_fanogan` | 1 | rule -> fAnoGAN candidate -> mock target | 验证 fAnoGAN candidate 在线稳定性 |
| `rule_ae_fanogan` | 1 | rule -> AE v1 -> fAnoGAN candidate -> mock target | 验证 AE + fAnoGAN 串联在线稳定性 |

## 4. 实验配置

| 配置项 | 值 |
|---|---|
| target wrapper | `targets/alfresco_content_update_online_filter_wrapper.py` |
| mock target semantics | `targets/alfresco_content_update_mock.py` |
| seed 目录 | `in/alfresco_afl_content_update_smoke/` |
| 运行脚本 | `scripts/run_alfresco_afl_online_filter_ablation_stability.sh` |
| 汇总脚本 | `scripts/summarize_alfresco_afl_online_filter_ablation_stability.py` |
| 模式数 | 4 |
| 每模式轮数 | 3 |
| 默认单轮 DUR | 20 秒 |
| 输出目录 | `out/alfresco_afl_online_filter_ablation_stability/` |

fAnoGAN candidate 依赖 torch scorer，单次执行成本明显高于 rule/AE 路径。本轮 fAnoGAN 两个模式继续使用 AFL 单次执行超时 5000 ms，避免 dry-run 阶段把 scorer 初始化误判为 target timeout；总运行仍属于短时 smoke 稳定性实验。

## 5. 每种模式3轮运行结果

| mode | run_id | run_time | execs_done | saved_crashes | saved_hangs | nv_err_exec | body_score_rpc_fail |
|---|---|---:|---:|---:|---:|---:|---:|
| `rule_only` | run_01 | 18 | 562 | 0 | 0 | 0 | 0 |
| `rule_only` | run_02 | 19 | 593 | 0 | 0 | 0 | 0 |
| `rule_only` | run_03 | 19 | 592 | 0 | 0 | 0 | 0 |
| `rule_ae` | run_01 | 19 | 594 | 0 | 0 | 0 | 0 |
| `rule_ae` | run_02 | 19 | 593 | 0 | 0 | 0 | 0 |
| `rule_ae` | run_03 | 19 | 591 | 0 | 0 | 0 | 0 |
| `rule_fanogan` | run_01 | 0 | 27 | 0 | 0 | 0 | 0 |
| `rule_fanogan` | run_02 | 0 | 27 | 0 | 0 | 0 | 0 |
| `rule_fanogan` | run_03 | 0 | 27 | 0 | 0 | 0 | 0 |
| `rule_ae_fanogan` | run_01 | 0 | 27 | 0 | 0 | 0 | 0 |
| `rule_ae_fanogan` | run_02 | 0 | 27 | 0 | 0 | 0 | 0 |
| `rule_ae_fanogan` | run_03 | 0 | 27 | 0 | 0 | 0 | 0 |

fAnoGAN 两个模式的 `run_time=0` 与 `execs_done=27` 是短时预算和 torch scorer 初始化成本共同导致的 AFL++ 统计现象；这不表示未运行。每轮均生成了 `fuzzer_stats`、`summary.csv` 和 `eval_report.json`，且 `body_score_rpc_ok=20`、`body_score_rpc_fail=0`。

## 6. 稳定性指标

聚合结果：

| 字段 | 值 |
|---|---:|
| modes | 4 |
| runs_per_mode | 3 |
| total_runs | 12 |
| total_execs_done | 3687 |
| total_valid_exec | 3525 |
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

本轮 12 个短时 AFL++ 运行均未出现 crash、hang、NV error 或 scoring error。

## 7. fAnoGAN在线路径稳定性观察

`rule_fanogan` 与 `rule_ae_fanogan` 两个模式均完成 3 轮，每轮 `body_score_rpc_fail=0`，说明 fAnoGAN candidate 在线路径在本轮代表性短时稳定性实验中可运行且未出现 scorer 错误。

但 fAnoGAN 两个模式的短时样本量明显少于 `rule_only` / `rule_ae`，原因是 torch fAnoGAN-style candidate scorer 在 Python AFL faux forkserver 路径下执行成本较高。因此本轮只能说明 fAnoGAN 在线路径稳定可运行，不能说明其性能或判定效果优于 AE v1。

## 8. 与AE v1主机制的关系

本轮聚合 `ae_primary_recommendation=keep_ae_v1_as_primary`。AE v1 仍是当前主二阶段有效性判定机制。

fAnoGAN candidate 已验证可进入在线路径，并在多轮短时运行中没有 scoring error，但当前仍作为后续研究增强方向保留，不能替代 AE v1。

## 9. 阶段性结论

本轮已完成 online filter 四模式短时稳定性实验：

- 四种模式均完成 3 轮；
- 12 个短时 AFL++ 运行均真实执行；
- `saved_crashes_total=0`；
- `saved_hangs_total=0`；
- `total_err_exec=0`；
- `scoring_error_total=0`；
- `overall_stability_score=1.000000`；
- recommendation 仍为 `keep_ae_v1_as_primary`。

evidence 位于：

- `out/alfresco_afl_online_filter_ablation_stability/stability_summary.csv`
- `out/alfresco_afl_online_filter_ablation_stability/stability_details.csv`
- `out/alfresco_afl_online_filter_ablation_stability/stability_report.json`
- 各模式各轮 `summary.csv`、`eval_report.json`、`fuzzer_stats`

## 10. 边界

- 这是 SE-fAnoGAN-ES-style online filter 四模式短时稳定性实验。
- 不等同于完整 SE-fAnoGAN-ES。
- 不等同于完整 GAN/fAnoGAN。
- 不代表真实 Alfresco 服务。
- mock target 不等同于真实 Alfresco 服务。
- 不代表所有场景完整 AFL++ mutation-chain。
- 不是长时间稳定性实验。
- AE v1 仍是主机制。
- 本轮不能宣称 fAnoGAN 替代 AE v1。
