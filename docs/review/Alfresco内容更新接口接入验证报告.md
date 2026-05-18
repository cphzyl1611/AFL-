# Alfresco内容更新接口接入验证报告

## 1. 背景

Alfresco Community Edition 是标准文档管理平台，已完成本地部署与手工 REST 验证，包括 root node、文档创建/保存、文档内容更新和文档元数据更新。

本轮在既有 Alfresco metadata update JSON 接入基础上，补充 text/plain 文档内容更新接口的最小校准脚本和 seed/rule/profile，用于增强“文档内容更新”业务语义验证能力。

## 2. 接口说明

目标接口：

```text
PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/{nodeId}/content?majorVersion=false&comment=content-update-min-calibration
```

请求体：

```text
Content-Type: text/plain; charset=utf-8
```

业务映射：

- 电子公文创建与保存：前置 fixture，通过 Alfresco 创建一个临时 text/plain 文档节点；
- 电子公文内容更新：对该文档节点执行 text/plain 内容覆盖更新；
- 当前只把 text/plain content update 作为 min_calibration 目标。

## 3. seed 与规则

新增 seed 目录：

```text
in/alfresco_content_update_dataset/
```

seed 类型：

- `seed_ok_0.txt`：正常中文通知文本；
- `seed_ok_1.txt`：正常中文会议纪要文本；
- `seed_border_0.txt`：边界短文本 `A`；
- `seed_bad_0.txt`：预设非法样本，包含 `__EXPECTED_INVALID_EMPTY_CONTENT__` 标记。

新增规则：

```text
validity/alfresco_content_update_rules.json
```

规则要点：

- content must be `text/plain`；
- UTF-8 文本；
- 内容长度 1 到 4096 bytes；
- 不允许二进制 NUL 字节；
- `seed_bad_0.txt` 是 expected negative，在规则层拒绝，不发送到 Alfresco。

## 4. 运行方式

```bash
python3 -m py_compile scripts/run_alfresco_content_update_compare.py

ALFRESCO_BASE=http://127.0.0.1:8080 \
ALFRESCO_USER=admin \
ALFRESCO_PASS=admin \
IN_DIR=in/alfresco_content_update_dataset \
OUT_DIR=out/alfresco_content_update_manual_latest \
python3 scripts/run_alfresco_content_update_compare.py
```

结果文件：

```text
out/alfresco_content_update_manual_latest/summary.csv
out/alfresco_content_update_manual_latest/details.csv
```

本次真实验证使用 `ALFRESCO_BASE=http://localhost:8080` 访问本机 Alfresco，root API 已返回 HTTP 200。

## 5. summary 结果

本次真实服务 min_calibration smoke 已通过，summary 关键字段如下：

```text
mode=rule_score
nv_total_valid_exec=4
nv_err_exec=0
nv_err_rate=0.000000
saved_hangs=0
saved_crashes=0
last_http_code=200
body_rule_pass=3
body_rule_reject=1
body_score_pass=0
body_score_reject=0
body_score_rpc_ok=0
body_score_rpc_fail=0
summary_source=python_static_loop
execution_scope=alfresco_content_update_min_calibration
```

该结果来自：

```text
out/alfresco_content_update_manual_latest/summary.csv
```

## 6. details 结果

本次 details 逐 seed 结果如下：

```text
seed_bad_0.txt:
  is_expected_negative=true
  rule_pass=false
  sent_to_target=false
  http_code=0
  error=preset_invalid_seed_rule_reject

seed_border_0.txt:
  is_expected_negative=false
  rule_pass=true
  sent_to_target=true
  http_code=200

seed_ok_0.txt:
  is_expected_negative=false
  rule_pass=true
  sent_to_target=true
  http_code=200

seed_ok_1.txt:
  is_expected_negative=false
  rule_pass=true
  sent_to_target=true
  http_code=200
```

`seed_bad_0.txt` 是预设非法样本，在规则层拒绝，不发送到 Alfresco，不计为主链失败。

该结果来自：

```text
out/alfresco_content_update_manual_latest/details.csv
```

## 7. 阶段性结论

当前已完成 Alfresco text/plain 内容更新接口的 seed、规则、profile、运行脚本和真实服务 min_calibration smoke。3 个合法/边界样本返回 HTTP 200，1 个 expected negative 样本在规则层拒绝，`nv_err_exec=0`。

该接入补强了标准文档平台“文档内容更新”业务语义验证能力。

## 8. 边界

- 这是 Alfresco 标准文档平台内容更新接口；
- 不等同于 O2OA 原生电子公文接口；
- 不是完整 AFL++ mutation-chain；
- 本轮不包含 multipart 上传；
- 不代表完整平台级 HTTP/RPC 网关；
- 不代表完整拟态系统级动态异构冗余完成。
