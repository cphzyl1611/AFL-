# Alfresco代表性AFL++变异链路短时稳定性报告

## 1. 背景

上一轮已完成 Alfresco `content_update` / text/plain 语义的代表性 AFL++ mutation-chain smoke，使用本地 mock target 证明项目至少具备一条真实 AFL++ 变异执行链路。本轮在该链路基础上执行 3 轮短时稳定性实验，验证该代表链路在多轮短时运行中是否保持无 crash、无 hang、无 NV 错误的稳定状态。

本轮不启动 O2OA、Flowable 或 Alfresco，不访问外部网络，不修改 AE v1 与 fAnoGAN candidate 的既有结论。

## 2. 实验目标

本轮目标是复用既有 smoke target、seed 和汇总口径，在独立输出目录下运行 3 轮短时 AFL++ smoke，并聚合每轮 `fuzzer_stats`、`summary.csv` 和 `eval_report.json`。

实验关注：

- 每轮是否真实执行 `afl-fuzz`；
- 每轮 `saved_crashes`、`saved_hangs`、`nv_err_exec` 是否为 0；
- 多轮 `execs_done` 是否处于相近量级；
- 聚合 `stability_score` 是否达到 1.000000。

## 3. 实验配置

| 配置项 | 值 |
|---|---|
| target | `targets/alfresco_content_update_mock.py` |
| seed 目录 | `in/alfresco_afl_content_update_smoke/` |
| 运行脚本 | `scripts/run_alfresco_afl_content_update_stability.sh` |
| 单轮 smoke 脚本 | `scripts/run_alfresco_afl_content_update_smoke.sh` |
| 汇总脚本 | `scripts/summarize_alfresco_afl_content_update_stability.py` |
| 轮数 | 3 |
| 本轮 DUR | 20 秒 |
| 输出目录 | `out/alfresco_afl_content_update_stability/` |

每轮输出目录：

- `out/alfresco_afl_content_update_stability/run_01/`
- `out/alfresco_afl_content_update_stability/run_02/`
- `out/alfresco_afl_content_update_stability/run_03/`

## 4. 三轮运行结果

| run_id | run_time | execs_done | execs_per_sec | nv_total_valid_exec | nv_err_exec | saved_crashes | saved_hangs |
|---|---:|---:|---:|---:|---:|---:|---:|
| run_01 | 19 | 1188 | 60.92 | 1161 | 0 | 0 | 0 |
| run_02 | 19 | 1183 | 60.58 | 1156 | 0 | 0 | 0 |
| run_03 | 19 | 1186 | 60.73 | 1159 | 0 | 0 | 0 |

每轮都生成：

- `summary.csv`
- `eval_report.json`
- `fuzzer_stats`

未将 AFL++ `queue/`、`crashes/`、`hangs/`、`fastresume.bin`、`mock_stats.jsonl` 等运行内部目录或中间文件纳入正式 evidence。

## 5. 稳定性指标

聚合结果：

| 字段 | 值 |
|---|---:|
| runs | 3 |
| total_execs_done | 3557 |
| total_valid_exec | 3476 |
| total_err_exec | 0 |
| mean_nv_err_rate | 0.000000 |
| max_nv_err_rate | 0.000000 |
| min_execs_done | 1183 |
| max_execs_done | 1188 |
| median_execs_done | 1186 |
| iqr_execs_done | 2 |
| saved_crashes_total | 0 |
| saved_hangs_total | 0 |
| stability_score | 1.000000 |

本轮三轮均无 crash、无 hang、无 NV 错误，代表性链路在短时多轮运行中保持稳定。

## 6. stability_summary.csv / stability_report.json 说明

稳定性 evidence 位于：

- `out/alfresco_afl_content_update_stability/stability_summary.csv`
- `out/alfresco_afl_content_update_stability/stability_details.csv`
- `out/alfresco_afl_content_update_stability/stability_report.json`

`stability_summary.csv` 使用聚合字段记录总执行数、错误数、错误率、execs 分布和稳定性分数。

`stability_report.json` 记录每轮 summary 路径、`fuzzer_stats` 路径、聚合 summary 和实验边界，便于复核。

## 7. 阶段性结论

本轮已真实运行 3 轮 AFL++ 短时稳定性实验。三轮均为 `saved_crashes=0`、`saved_hangs=0`、`nv_err_exec=0`，聚合 `stability_score=1.000000`。

该结果说明代表性 Alfresco `content_update` mock mutation-chain 在短时多轮执行中保持稳定，可作为当前工程交付中“至少一条真实 AFL++ 变异执行链路具备短时稳定性”的补充 evidence。

AE v1 仍作为 Alfresco 主二阶段有效性判定机制；fAnoGAN candidate 未替代 AE v1。

## 8. 边界

- 这是代表性 AFL++ mutation-chain 短时稳定性实验。
- 不等同于长时间稳定性实验。
- 不等同于所有场景完整 AFL++ mutation-chain。
- mock target 不等同于真实 Alfresco 服务。
- 不访问 O2OA、Flowable 或 Alfresco 服务。
- 不等同于完整 SE-fAnoGAN-ES。
- 不等同于完整 GAN/fAnoGAN。
- 不改变 AE v1 为主机制。
