# Alfresco SE-fAnoGAN-ES online filter原型报告

## 1. 背景

当前工程已经完成 Alfresco 主验证平台、三类文档接口真实 smoke、AE v1 主二阶段有效性判定、fAnoGAN candidate fallback/torch/holdout 验证，以及代表性 AFL++ mutation-chain smoke 和 3 轮短时稳定性实验。

在此基础上，本轮新增一个 SE-fAnoGAN-ES-style online filter prototype，用于把规则过滤、AE v1 scorer 和可选 fAnoGAN candidate scorer 放到代表性 AFL++ mutation-chain 的前置过滤流程中，形成“mutation input -> rule/AE/fAnoGAN online 判定 -> mock target execution”的最小闭环。

## 2. 为什么在 v0.3.6 后做 online filter

v0.3.6 已证明代表性 AFL++ 链路可以真实执行并在短时多轮运行中保持稳定。本轮进一步验证二阶段判定能力可以进入 AFL++ 执行链路的在线路径，而不是只停留在离线 compare 或 service/API 调用。

本轮仍不访问真实 Alfresco 服务，不启动 O2OA、Flowable 或 Alfresco，不改变 AE v1 作为主机制的结论。

## 3. online filter 链路

本轮新增文件：

- `targets/alfresco_content_update_online_filter_wrapper.py`
- `scripts/run_alfresco_afl_online_filter_smoke.sh`
- `scripts/summarize_alfresco_afl_online_filter_smoke.py`
- `integration/platform_profiles/alfresco_afl_online_filter_smoke.json`

链路如下：

| 阶段 | 说明 |
|---|---|
| AFL++ mutation input | `afl-fuzz` 从 `in/alfresco_afl_content_update_smoke/` 读取 seed 并变异 |
| rule check | 复用 `targets/alfresco_content_update_mock.py` 的 text/plain 内容规则 |
| AE v1 scoring | 默认 `rule_ae` 模式下调用 `AlfrescoAEV1Scorer.score_text_content` |
| fAnoGAN candidate scoring | 原型支持 `rule_fanogan` / `rule_ae_fanogan`，但默认不启用 |
| target execution | 通过 online filter 的输入才进入本地 mock target 分类逻辑 |
| evidence | `fuzzer_stats`、`filter_stats.jsonl`、`summary.csv`、`eval_report.json` |

## 4. 支持的 filter mode

| mode | 说明 |
|---|---|
| `rule_only` | 只执行 rule-level content 检查 |
| `rule_ae` | 默认模式，先 rule 后 AE v1，AE v1 为主判定 |
| `rule_fanogan` | 先 rule 后 fAnoGAN candidate，用于候选扩展观察 |
| `rule_ae_fanogan` | 先 rule、AE v1，再 fAnoGAN candidate |

本轮 smoke 使用：

- `ONLINE_FILTER_MODE=rule_ae`
- `FANOGAN_ENABLED=0`

## 5. AFL++ smoke 运行结果

运行命令：

```bash
bash scripts/run_alfresco_afl_online_filter_smoke.sh
python3 scripts/summarize_alfresco_afl_online_filter_smoke.py
```

输出目录：

- `out/alfresco_afl_online_filter_smoke_latest/`

`fuzzer_stats` 摘要：

| 字段 | 值 |
|---|---:|
| run_time | 19 |
| execs_done | 606 |
| execs_per_sec | 31.75 |
| corpus_count | 4 |
| saved_crashes | 0 |
| saved_hangs | 0 |
| nv_total_valid_exec | 579 |
| nv_err_exec | 0 |
| nv_err_rate | 0.000000 |

online filter 摘要：

| 字段 | 值 |
|---|---:|
| online_filter_mode | `rule_ae` |
| body_rule_pass | 155 |
| body_rule_reject | 451 |
| body_score_pass | 154 |
| body_score_reject | 452 |
| body_score_rpc_ok | 155 |
| body_score_rpc_fail | 0 |
| sent_to_target | 154 |
| filtered_by_rule | 451 |
| filtered_by_ae | 1 |
| filtered_by_fanogan | 0 |

## 6. summary.csv / eval_report.json 说明

本轮 evidence：

- `out/alfresco_afl_online_filter_smoke_latest/summary.csv`
- `out/alfresco_afl_online_filter_smoke_latest/eval_report.json`
- `out/alfresco_afl_online_filter_smoke_latest/fuzzer_stats`

`summary.csv` 沿用项目既有 summary 字段，并追加 online filter 字段：

- `online_filter_mode`
- `sent_to_target`
- `filtered_by_rule`
- `filtered_by_ae`
- `filtered_by_fanogan`

`eval_report.json` 记录 AFL++ 统计、online filter 统计和边界说明。

## 7. 与 AE v1 / fAnoGAN candidate 的关系

本轮默认模式为 `rule_ae`，即 AE v1 仍是主二阶段判定机制。fAnoGAN candidate scorer 已可由 wrapper 以 `rule_fanogan` 或 `rule_ae_fanogan` 模式调用，但本轮 smoke 未默认启用，也不作为替代 AE v1 的依据。

当前结论仍为：

- AE v1 仍是主机制；
- fAnoGAN candidate 未替代 AE v1；
- online filter 是原型链路，不是完整 SE-fAnoGAN-ES。

## 8. 阶段性结论

本轮已真实运行 AFL++ online filter smoke，完成 mutation input、rule/AE online 判定、mock target execution 和 evidence 汇总的最小闭环。

运行结果显示：`saved_crashes=0`、`saved_hangs=0`、`nv_err_exec=0`，默认 `rule_ae` 模式下过滤逻辑正常工作，未访问真实 Alfresco 服务。

## 9. 边界

- 这是 SE-fAnoGAN-ES-style online filter prototype。
- 不等同于完整 SE-fAnoGAN-ES。
- 不等同于完整 GAN/fAnoGAN。
- 不等同于所有场景完整 AFL++ mutation-chain。
- mock target 不等同于真实 Alfresco 服务。
- AE v1 仍是主机制。
- fAnoGAN candidate 未替代 AE v1。
- 不代表 O2OA 原生接口覆盖。
