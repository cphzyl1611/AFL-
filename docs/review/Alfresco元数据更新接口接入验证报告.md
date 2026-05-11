# Alfresco元数据更新接口接入验证报告

## 接入目的

本轮优先接入 Alfresco 文档元数据更新接口，原因如下：

- 该接口使用 JSON body，最适配当前 body-only JSON fuzz 框架；
- 可直接承载电子公文标题、描述等结构化元数据字段；
- multipart 文件上传和 `text/plain` 内容更新需要不同 body 类型，作为后续扩展处理。

## 接口语义

目标接口：

```text
PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/{NODE_ID}
```

业务映射：

- 电子公文创建与保存：作为前置 fixture，通过 Alfresco 创建一个测试文档节点；
- 电子公文元数据更新：对同一文档节点执行 JSON metadata update；
- 本轮只将 metadata update 作为 fuzz/smoke 目标；
- 该验证是 Alfresco 标准文档平台接口验证，不是 O2OA 原生电子公文接口覆盖。

## 本地执行结果

执行输出目录：

```text
out/alfresco_metadata_update_manual_latest
```

`summary.csv` 关键字段：

```text
mode=rule_score
nv_total_valid_exec=4
nv_err_exec=0
nv_err_rate=0.000000
saved_hangs=0
saved_crashes=0
last_http_code=200
last_latency_ms=71
last_ncov_total=0
body_rule_pass=3
body_rule_reject=1
body_score_pass=0
body_score_reject=0
body_score_rpc_ok=0
body_score_rpc_fail=0
summary_source=python_static_loop
execution_scope=alfresco_metadata_update_min_calibration
metric_semantics=Python static-loop Alfresco metadata update request replay; not a full AFL++ mutation-chain execution.
```

`details.csv` 逐 seed 结果：

| seed_file | rule_decision | http_code | latency_ms | score_decision | score_rpc_status | is_expected_negative | error_message |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `seed_bad_0.json` | `reject:name_must_be_string_len_1_255` | 0 | 0 | `not_scored` | `not_configured` | `true` | `preset_invalid_seed_rule_reject` |
| `seed_border_0.json` | `pass` | 200 | 72 | `not_configured` | `not_configured` | `false` |  |
| `seed_ok_0.json` | `pass` | 200 | 76 | `not_configured` | `not_configured` | `false` |  |
| `seed_ok_1.json` | `pass` | 200 | 71 | `not_configured` | `not_configured` | `false` |  |

结论：Alfresco metadata update smoke 通过。3 个合法/边界样本均成功执行 metadata update；`seed_bad_0.json` 是预设非法样本，本次在本地规则层被拒绝，未发送到 Alfresco，因此不计为主链失败。如果后续选择透传该非法样本，预期可用于观察 Alfresco 400 类错误响应。

本次未配置 `NV_BODY_SCORE_ENDPOINT`，因此 score 统计保持为 0，不影响本轮 JSON metadata update smoke 结论。

## 边界说明

Alfresco 在本轮中作为标准文档管理平台，用于验证“电子公文元数据更新 / 公文标题与描述更新”这类业务语义接口。

该验证不是 O2OA 原生电子公文接口覆盖。

该验证是 `python_static_loop` / `min_calibration` 级别的本地回放，不是完整 AFL++ mutation-chain。

该验证不代表完整拟态系统级动态异构冗余完成。
