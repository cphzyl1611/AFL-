# Alfresco multipart_upload online filter smoke报告

## 1. 背景

当前工程已经完成 `content_update` / text/plain 与 `metadata_update` / application/json 两类本地 mock 文档语义的 online filter smoke，并完成两类语义的四模式消融和四模式短时稳定性实验。本轮补充 `multipart_upload` / multipart/form-data 本地 mock 语义的 online filter smoke，用于形成第三类文档接口语义的代表性 AFL++ online filter 链路。

本轮不访问真实 Alfresco 服务，不启动 O2OA、Flowable 或 Alfresco，不改变 AE v1 与 fAnoGAN candidate 的既有结论。

## 2. 为什么扩展 multipart_upload

Alfresco 文档接口已经覆盖 metadata update、text/plain content update 与 multipart upload 三类典型输入形态。前两类已经具备 online filter 代表链路，本轮扩展 multipart_upload 的目标是验证同一 rule + AE v1 + 可选 fAnoGAN candidate 结构可以处理 multipart/form-data 文件上传语义。

## 3. multipart mock规则

新增本地 mock target：

- `targets/alfresco_multipart_upload_mock.py`

核心规则：

- 输入必须是小型 multipart/form-data body；
- body 中必须包含可解析 boundary；
- 至少包含一个 `filedata` 或 `file` 文件字段；
- `Content-Disposition` 必须包含非空 `filename`；
- 文件 `Content-Type` 可为 `text/plain`、`application/octet-stream` 或 `application/json`；
- 文件内容必须非空且不超过本地 smoke 限制；
- 明显二进制噪声、破损 boundary、缺 file 字段、缺 filename 或空文件均判定为 invalid；
- invalid 输入受控处理，不作为 AFL++ crash。

## 4. online filter链路

新增 wrapper：

- `targets/alfresco_multipart_upload_online_filter_wrapper.py`

默认配置：

- `ONLINE_FILTER_MODE=rule_ae`
- `FANOGAN_ENABLED=0`
- AE v1 仍为主二阶段判定机制

链路顺序：

1. 从 AFL++ `@@` 文件读取 multipart body；
2. 执行 multipart rule classifier；
3. 在 `rule_ae` 模式下执行 `AlfrescoAEV1Scorer.score_multipart_upload`；
4. 通过过滤后再调用本地 multipart mock classifier；
5. 写入 `filter_stats.jsonl`，供汇总脚本生成 summary/report。

## 5. 运行命令

```bash
bash scripts/run_alfresco_afl_multipart_online_filter_smoke.sh
python3 scripts/summarize_alfresco_afl_multipart_online_filter_smoke.py
cat out/alfresco_afl_multipart_online_filter_smoke_latest/summary.csv
cat out/alfresco_afl_multipart_online_filter_smoke_latest/eval_report.json
cat out/alfresco_afl_multipart_online_filter_smoke_latest/fuzzer_stats
```

## 6. AFL++ smoke结果

本轮为短时 smoke，默认 `DUR=20`，默认只运行 `rule_ae`，不做四模式消融，不做稳定性实验。

本轮实际结果：

- `run_time=19`
- `execs_done=599`
- `execs_per_sec=31.41`
- `nv_total_valid_exec=572`
- `nv_err_exec=0`
- `saved_crashes=0`
- `saved_hangs=0`
- `body_score_rpc_fail=0`

结果以以下 evidence 为准：

- `out/alfresco_afl_multipart_online_filter_smoke_latest/summary.csv`
- `out/alfresco_afl_multipart_online_filter_smoke_latest/eval_report.json`
- `out/alfresco_afl_multipart_online_filter_smoke_latest/fuzzer_stats`

## 7. summary.csv / eval_report.json说明

`summary.csv` 沿用 online filter smoke 统计字段，并新增 multipart 语义统计：

- `scenario=multipart_upload`
- `summary_source=afl_fuzz_multipart_online_filter`
- `execution_scope=alfresco_multipart_upload_mock_afl_online_filter_smoke`
- `sent_to_target`
- `filtered_by_rule`
- `filtered_by_ae`
- `filtered_by_fanogan`
- `filename_detected_count`
- `content_type_detected_count`

本轮 `summary.csv` 核心值：

- `scenario=multipart_upload`
- `online_filter_mode=rule_ae`
- `sent_to_target=101`
- `filtered_by_rule=492`
- `filtered_by_ae=7`
- `filtered_by_fanogan=0`
- `filename_detected_count=130`
- `content_type_detected_count=114`

`eval_report.json` 记录 fuzzer_stats 摘要、online filter 计数、输出路径和边界声明。

## 8. 与 content_update / metadata_update 链路的关系

本轮复用现有 AE v1 scorer 和 online filter 统计格式，只新增 multipart_upload 本地 mock target、wrapper、seed、运行脚本和汇总脚本。它补齐第三类本地 mock 文档语义，但不改变前两类 evidence，也不扩大 fAnoGAN candidate 的结论。

## 9. 阶段性结论

本轮完成 multipart_upload online filter smoke：

- 新增 multipart_upload 本地 mock target；
- 新增 multipart_upload online filter wrapper；
- 默认 `rule_ae` 模式接入 AE v1；
- `FANOGAN_ENABLED=0`，fAnoGAN candidate 未启用；
- 形成 `summary.csv`、`eval_report.json` 和 `fuzzer_stats` 小型 evidence。

## 10. 边界

- 这是 multipart_upload online filter smoke；
- 不等同于完整 SE-fAnoGAN-ES；
- 不等同于完整 GAN/fAnoGAN；
- 不代表真实 Alfresco 服务；
- mock target 不等同于真实 Alfresco 服务；
- 不代表所有场景完整 AFL++ mutation-chain；
- 不是四模式消融；
- 不是短时稳定性实验；
- AE v1 仍是主机制；
- fAnoGAN candidate 未替代 AE v1。
