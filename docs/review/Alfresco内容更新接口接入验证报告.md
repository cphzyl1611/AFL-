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

如果本机 `127.0.0.1:8080` Alfresco 不可访问，脚本会写入 `mode=skipped` 的 summary，并返回 0，避免把环境不可用误判为接口实现失败。

## 5. summary 结果

本轮当前执行环境无法访问本机 Alfresco API，fixture 创建阶段返回：

```text
<urlopen error [Errno 1] Operation not permitted>
```

因此本轮 summary 为 skipped，不作为目标系统真实回放通过证据：

```text
mode=skipped
nv_total_valid_exec=0
nv_err_exec=0
nv_err_rate=0.000000
last_http_code=0
body_rule_pass=0
body_rule_reject=0
summary_source=python_static_loop
execution_scope=alfresco_content_update_min_calibration
```

待本地 Alfresco 可访问时，期望结果为：

- `seed_ok_0.txt`、`seed_ok_1.txt`、`seed_border_0.txt` 返回 2xx；
- `seed_bad_0.txt` 在规则层拒绝，不发送到目标；
- `nv_err_exec=0`；
- `saved_hangs=0`；
- `saved_crashes=0`。

## 6. details 结果

当前 skipped 环境下，`details.csv` 记录 fixture 创建不可访问：

```text
seed_file=__fixture__
sent_to_target=false
http_code=0
error=<urlopen error [Errno 1] Operation not permitted>
```

本地 Alfresco 可访问后，逐 seed details 应记录：

- `seed_ok_0.txt`：`rule_pass=true`，`sent_to_target=true`；
- `seed_ok_1.txt`：`rule_pass=true`，`sent_to_target=true`；
- `seed_border_0.txt`：`rule_pass=true`，`sent_to_target=true`；
- `seed_bad_0.txt`：`is_expected_negative=true`，`rule_pass=false`，`sent_to_target=false`。

## 7. 阶段性结论

当前已完成 Alfresco text/plain 内容更新接口的 seed、规则、profile、运行脚本和报告接入。该接入补强了标准文档平台“文档内容更新”业务语义验证能力。

本轮执行环境未实际访问 Alfresco，因此不能把当前 skipped 结果写成目标系统 smoke 已通过。待本地 Alfresco 服务可访问时，按本报告运行命令重跑并归档 summary/details。

## 8. 边界

- 这是 Alfresco 标准文档平台内容更新接口；
- 不等同于 O2OA 原生电子公文接口；
- 不是完整 AFL++ mutation-chain；
- 本轮不包含 multipart 上传；
- 不代表完整平台级 HTTP/RPC 网关；
- 不代表完整拟态系统级动态异构冗余完成。
