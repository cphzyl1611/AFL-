# Alfresco metadata_update online filter smoke报告

## 1. 背景

当前工程已经完成 Alfresco `content_update` / text/plain 代表性 AFL++ mutation-chain smoke、短时稳定性实验、SE-fAnoGAN-ES-style online filter prototype、四模式消融和四模式短时稳定性实验。

本轮在不访问真实 Alfresco 服务的前提下，将 online filter 链路扩展到 Alfresco `metadata_update` / application/json 语义，形成第二类文档语义的代表性 AFL++ online filter smoke。

## 2. 为什么扩展 metadata_update

`content_update` 证明了 text/plain 文档内容更新语义可以接入 AFL++ online filter 链路。`metadata_update` 是 Alfresco 标准文档接口中的 JSON body 场景，能够验证同一套 rule + AE v1 + 可选 fAnoGAN candidate 判定能力是否可用于结构化 metadata 输入。

该扩展不改变 AE v1 与 fAnoGAN candidate 的既有关系，只补充一条 application/json 语义下的最小闭环。

## 3. metadata mock规则

本轮新增本地 mock target：

- `targets/alfresco_metadata_update_mock.py`

mock 规则：

| 输入条件 | 判定 |
|---|---|
| 空文件、非 UTF-8、破损 JSON | invalid |
| JSON array、number、string 等非 object | invalid |
| JSON object | 继续检查字段 |
| 允许字段 | `name`、`title`、`description`、`properties` |
| `name` / `title` / `description` | 如存在必须为 string，并限制长度 |
| `properties` | 如存在必须为 object，属性值限制为简单 JSON 标量 |
| `{}` | 作为边界样本，判定为 valid |

mock target 不访问网络，不调用 shell，不访问真实 Alfresco 服务。

## 4. online filter链路

本轮新增 wrapper：

- `targets/alfresco_metadata_update_online_filter_wrapper.py`

链路如下：

| 阶段 | 说明 |
|---|---|
| AFL++ mutation input | `afl-fuzz` 从 `in/alfresco_afl_metadata_update_smoke/` 读取 seed 并变异 |
| metadata rule | 调用 `classify_metadata(data)` 进行 JSON 与字段类型检查 |
| AE v1 scoring | 默认 `rule_ae` 模式调用 `AlfrescoAEV1Scorer.score_metadata_payload` |
| fAnoGAN candidate scoring | 支持 `rule_fanogan` / `rule_ae_fanogan`，默认不启用 |
| mock target execution | 通过 online filter 的输入才进入本地 metadata mock 分类 |
| evidence | `fuzzer_stats`、`filter_stats.jsonl`、`summary.csv`、`eval_report.json` |

## 5. 运行命令

```bash
bash scripts/run_alfresco_afl_metadata_online_filter_smoke.sh
python3 scripts/summarize_alfresco_afl_metadata_online_filter_smoke.py
cat out/alfresco_afl_metadata_online_filter_smoke_latest/summary.csv
cat out/alfresco_afl_metadata_online_filter_smoke_latest/eval_report.json
cat out/alfresco_afl_metadata_online_filter_smoke_latest/fuzzer_stats
```

默认配置：

- `ONLINE_FILTER_MODE=rule_ae`
- `FANOGAN_ENABLED=0`
- `DUR=20`
- seed 目录：`in/alfresco_afl_metadata_update_smoke/`
- 输出目录：`out/alfresco_afl_metadata_online_filter_smoke_latest/`

## 6. AFL++ smoke结果

本轮已真实运行 AFL++，evidence 路径如下：

- `out/alfresco_afl_metadata_online_filter_smoke_latest/summary.csv`
- `out/alfresco_afl_metadata_online_filter_smoke_latest/eval_report.json`
- `out/alfresco_afl_metadata_online_filter_smoke_latest/fuzzer_stats`

`fuzzer_stats` 摘要：

| 字段 | 值 |
|---|---:|
| run_time | 19 |
| execs_done | 597 |
| execs_per_sec | 31.32 |
| corpus_count | 4 |
| saved_crashes | 0 |
| saved_hangs | 0 |
| nv_total_valid_exec | 570 |
| nv_err_exec | 0 |
| nv_err_rate | 0.000000 |

online filter 摘要：

| 字段 | 值 |
|---|---:|
| summary_source | `afl_fuzz_metadata_online_filter` |
| execution_scope | `alfresco_metadata_update_mock_afl_online_filter_smoke` |
| scenario | `metadata_update` |
| online_filter_mode | `rule_ae` |
| body_rule_pass | 46 |
| body_rule_reject | 551 |
| body_score_pass | 46 |
| body_score_reject | 551 |
| body_score_rpc_ok | 46 |
| body_score_rpc_fail | 0 |
| sent_to_target | 46 |
| filtered_by_rule | 551 |
| filtered_by_ae | 0 |
| filtered_by_fanogan | 0 |

## 7. summary.csv / eval_report.json说明

`summary.csv` 沿用项目既有 summary 字段，并追加 metadata online filter 字段：

- `scenario`
- `online_filter_mode`
- `sent_to_target`
- `filtered_by_rule`
- `filtered_by_ae`
- `filtered_by_fanogan`

`eval_report.json` 记录 AFL++ 统计、online filter 统计、输出路径和边界说明。

## 8. 与content_update链路的关系

`content_update` 链路验证 text/plain 文档内容更新语义；本轮 `metadata_update` 链路验证 application/json 元数据更新语义。两者都使用本地 mock target，不访问真实 Alfresco 服务。

当前 online filter 已覆盖两类文档语义的代表性本地 mock 链路，但这不等同于所有 Alfresco 场景完整 AFL++ mutation-chain 覆盖。

## 9. 阶段性结论

本轮完成了 Alfresco `metadata_update` / application/json 的 online filter smoke 实现：

- 新增 metadata_update 本地 mock target；
- 新增 metadata_update online filter wrapper；
- 默认 `rule_ae` 模式使用 AE v1 scorer；
- fAnoGAN candidate 保持可选，不默认启用；
- 生成独立 summary / eval_report / fuzzer_stats evidence；
- 不修改 AE v1 作为主机制的结论。

## 10. 边界

- 这是 metadata_update online filter smoke。
- 不等同于完整 SE-fAnoGAN-ES。
- 不等同于完整 GAN/fAnoGAN。
- 不代表真实 Alfresco 服务。
- mock target 不等同于真实 Alfresco 服务。
- 不代表所有场景完整 AFL++ mutation-chain。
- AE v1 仍是主机制。
- fAnoGAN candidate 未替代 AE v1。
