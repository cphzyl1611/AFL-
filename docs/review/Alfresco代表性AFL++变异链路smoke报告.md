# Alfresco代表性AFL++变异链路smoke报告

## 1. 背景

当前交付版本已经完成 Alfresco 三类文档接口真实 smoke、AE v1 主二阶段判定、轻量 API adapter、MCP adapter prototype、fAnoGAN candidate 复评和 holdout 验证。本轮补充一个短时、可复现、低风险的 AFL++ mutation-chain smoke，用于证明项目至少具备一条真实 AFL++ 变异执行链路。

本轮不访问真实 Alfresco 服务，不启动 O2OA、Flowable 或 Alfresco，不重跑长时间 fuzz，不修改 AE v1 与 fAnoGAN candidate 的既有结论。

## 2. 为什么选择 content_update mock

Alfresco `content_update` 对应 text/plain 文档内容更新语义，已有真实服务 min_calibration evidence 和报告，可与当前项目的文档类业务接口口径保持一致。为避免本轮引入外部服务依赖，本轮使用本地 mock target 模拟 text/plain 内容更新的合法/非法输入判定。

mock target 位于：

- `targets/alfresco_content_update_mock.py`

seed 目录位于：

- `in/alfresco_afl_content_update_smoke/`

该 target 只读取 AFL++ 传入的 `@@` 输入文件或 stdin，不访问网络，不执行 shell，不遍历其他路径。

## 3. AFL++ mutation-chain 组成

本轮链路组成如下：

| 环节 | 文件或机制 | 说明 |
|---|---|---|
| AFL++ executor | `./afl-fuzz` | 真实执行 AFL++，使用 `AFL_NO_UI=1` 和短时 timeout |
| seed corpus | `in/alfresco_afl_content_update_smoke/` | 4 个 text/plain seed，覆盖正常、边界和预设非法输入 |
| 本地 target | `targets/alfresco_content_update_mock.py` | 模拟 Alfresco content_update 语义，不访问真实服务 |
| profile | `integration/platform_profiles/alfresco_afl_content_update_smoke.json` | 记录 `target_type=local_mock`、`scenario=alfresco_content_update` |
| 运行脚本 | `scripts/run_alfresco_afl_content_update_smoke.sh` | 运行短时 AFL++ smoke，不删除既有 evidence |
| 汇总脚本 | `scripts/summarize_alfresco_afl_content_update_smoke.py` | 读取 `fuzzer_stats` 和 mock JSONL，生成 summary/eval report |

## 4. 运行命令

本轮使用命令：

```bash
bash scripts/run_alfresco_afl_content_update_smoke.sh
python3 scripts/summarize_alfresco_afl_content_update_smoke.py
```

脚本内部执行的 AFL++ 命令等价于：

```bash
AFL_NO_UI=1 timeout 20s ./afl-fuzz -n -m none \
  -i in/alfresco_afl_content_update_smoke \
  -o out/alfresco_afl_content_update_smoke_latest \
  -- python3 targets/alfresco_content_update_mock.py @@
```

本轮输出目录：

- `out/alfresco_afl_content_update_smoke_latest/`

## 5. fuzzer_stats 摘要

本轮 `fuzzer_stats` 摘要：

| 字段 | 值 |
|---|---:|
| run_time | 19 |
| execs_done | 1192 |
| execs_per_sec | 61.07 |
| corpus_count | 4 |
| saved_crashes | 0 |
| saved_hangs | 0 |
| nv_total_valid_exec | 1165 |
| nv_err_exec | 0 |
| nv_err_rate | 0.000000 |

`fuzzer_stats` evidence 路径：

- `out/alfresco_afl_content_update_smoke_latest/fuzzer_stats`

## 6. summary.csv / eval_report.json 说明

汇总输出：

- `out/alfresco_afl_content_update_smoke_latest/summary.csv`
- `out/alfresco_afl_content_update_smoke_latest/eval_report.json`

`summary.csv` 继续使用项目已有 summary 字段口径，关键字段为：

| 字段 | 值 |
|---|---|
| mode | `afl_mock_smoke` |
| nv_total_valid_exec | `1165` |
| nv_err_exec | `0` |
| nv_err_rate | `0.000000` |
| saved_hangs | `0` |
| saved_crashes | `0` |
| body_rule_pass | `284` |
| body_rule_reject | `909` |
| summary_source | `afl_fuzz` |
| execution_scope | `alfresco_content_update_mock_afl_mutation_chain_smoke` |

`metric_semantics` 明确为代表性 AFL++ mutation-chain smoke，不代表所有场景，也不代表真实 Alfresco 服务。

## 7. 阶段性结论

本轮已真实运行 AFL++，完成从 seed corpus、AFL++ 变异执行、本地 content_update mock target、`fuzzer_stats`、`summary.csv` 到 `eval_report.json` 的代表性 mutation-chain smoke 闭环。

该结果补充了项目至少具备一条真实 AFL++ 变异执行链路的工程 evidence。当前 AE v1 仍作为 Alfresco 主二阶段有效性判定机制，fAnoGAN candidate 仍保留为后续研究增强方向。

## 8. 边界

- 这是代表性 AFL++ mutation-chain smoke。
- 不等同于所有场景完整 AFL++ mutation-chain。
- mock target 不等同于真实 Alfresco 服务。
- 不访问 O2OA、Flowable 或 Alfresco 服务。
- 不等同于完整 SE-fAnoGAN-ES。
- 不等同于完整 GAN/fAnoGAN。
- 不改变 AE v1 为主机制的结论。
