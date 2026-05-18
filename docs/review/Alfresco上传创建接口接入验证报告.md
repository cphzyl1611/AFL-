# Alfresco上传创建接口接入验证报告

## 1. 背景

Alfresco Community Edition 是标准文档管理平台，已完成本地部署和 REST 验证。本项目此前已完成 Alfresco metadata update 与 text/plain content update 的最小校准接入。

本轮补充 multipart/form-data 上传接口，用于验证标准文档平台“文档创建与保存”业务语义接口能力。

## 2. 接口说明

目标接口：

```text
POST /alfresco/api/-default-/public/alfresco/versions/1/nodes/-my-/children
```

请求体：

```text
Content-Type: multipart/form-data
filedata: text/plain 文件内容
name: 生成的唯一 .txt 文件名
nodeType: cm:content
autoRename: true
```

业务映射：

- 文档创建与保存：通过 Alfresco multipart upload 创建 `cm:content` 文档节点；
- 当前只把 multipart upload 作为 `min_calibration` 目标；
- 本轮不覆盖 O2OA 原生电子公文接口。

## 3. seed 与规则

新增 seed 目录：

```text
in/alfresco_multipart_upload_dataset/
```

seed 类型：

- `seed_ok_0.txt`：正常中文通知文本；
- `seed_ok_1.txt`：正常中文会议纪要文本；
- `seed_border_0.txt`：边界短文本 `A`；
- `seed_bad_0.txt`：预设非法样本，包含 `__EXPECTED_INVALID_EMPTY_UPLOAD__` 标记。

新增规则：

```text
validity/alfresco_multipart_upload_rules.json
```

规则要点：

- method 为 `POST`；
- content type 为 `multipart/form-data`；
- file field 为 `filedata`；
- nodeType 为 `cm:content`；
- `autoRename=true`；
- 文件名必须以 `.txt` 结尾；
- 文件内容必须是 UTF-8 text；
- 内容长度 1 到 4096 bytes；
- 不允许二进制 NUL 字节；
- `seed_bad_0.txt` 是 expected negative，在规则层拒绝，不发送到 Alfresco。

## 4. 运行方式

先确认 Alfresco root API 可访问：

```bash
curl -i -u admin:admin \
  "http://localhost:8080/alfresco/api/-default-/public/alfresco/versions/1/nodes/-root-" \
  -m 20
```

运行 multipart upload min_calibration：

```bash
ALFRESCO_BASE=http://localhost:8080 \
ALFRESCO_USER=admin \
ALFRESCO_PASS=admin \
IN_DIR=in/alfresco_multipart_upload_dataset \
OUT_DIR=out/alfresco_multipart_upload_manual_latest \
python3 scripts/run_alfresco_multipart_upload_compare.py
```

结果文件：

```text
out/alfresco_multipart_upload_manual_latest/summary.csv
out/alfresco_multipart_upload_manual_latest/details.csv
```

本次真实验证使用 `ALFRESCO_BASE=http://localhost:8080`，root API 返回 HTTP 200。

## 5. summary 结果

本次真实服务 multipart upload min_calibration smoke 已通过，summary 关键字段如下：

```text
mode=rule_score
nv_total_valid_exec=4
nv_err_exec=0
nv_err_rate=0.000000
saved_hangs=0
saved_crashes=0
last_http_code=201
body_rule_pass=3
body_rule_reject=1
body_score_pass=0
body_score_reject=0
body_score_rpc_ok=0
body_score_rpc_fail=0
summary_source=python_static_loop
execution_scope=alfresco_multipart_upload_min_calibration
```

该结果来自：

```text
out/alfresco_multipart_upload_manual_latest/summary.csv
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
  http_code=201

seed_ok_0.txt:
  is_expected_negative=false
  rule_pass=true
  sent_to_target=true
  http_code=201

seed_ok_1.txt:
  is_expected_negative=false
  rule_pass=true
  sent_to_target=true
  http_code=201
```

`seed_bad_0.txt` 是预设非法样本，在规则层拒绝，不发送到 Alfresco，不计为主链失败。3 个合法/边界样本均上传成功并返回 Alfresco node id。

该结果来自：

```text
out/alfresco_multipart_upload_manual_latest/details.csv
```

## 7. 阶段性结论

当前已完成 Alfresco multipart/form-data 上传创建接口的 seed、规则、profile、运行脚本和真实服务 min_calibration smoke。3 个合法/边界样本返回 HTTP 201，1 个 expected negative 样本在规则层拒绝，`nv_err_exec=0`。

该接入补强了标准文档平台“文档创建与保存”业务语义验证能力。

## 8. 边界

- 这是 Alfresco 标准文档平台 multipart 上传/创建接口；
- 对应文档创建与保存业务语义；
- 不等同于 O2OA 原生电子公文接口；
- 不是完整 AFL++ mutation-chain；
- 不代表完整平台级 HTTP/RPC 网关；
- 不代表完整拟态系统级动态异构冗余完成。
