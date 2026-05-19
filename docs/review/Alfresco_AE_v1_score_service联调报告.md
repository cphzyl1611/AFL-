# Alfresco_AE_v1_score_service联调报告

## 1. 背景

Alfresco 已作为后续主验证平台。当前 metadata update、text/plain content update、multipart upload 创建/保存三类标准文档接口均已完成真实 smoke，Alfresco AE v1 engineering scorer 也已完成本地 score compare、阈值 sweep 和误判分析。

本轮目标是将 Alfresco AE v1 从本地 scorer 推进到可通过 HTTP 调用的本地 score service / decision profile 联调形态，便于后续总项目集成联调。

## 2. service 设计

新增本地 score service：

```text
model_stage/alfresco_ae_v1_score_service.py
```

设计约束：

- 默认只监听 `127.0.0.1`；
- 默认端口 `18181`；
- 不访问外部网络；
- 不访问 Alfresco 服务；
- 只做本地 AE v1 scoring；
- 复用 `model_stage/alfresco_ae_v1_scorer.py`；
- 读取 `model_stage/models/alfresco_ae_v1_meta.json`。

当前模型类型仍为：

```text
model_type=ae_like_statistical_baseline
```

推荐阈值沿用阈值校准结果：

```text
threshold_low=0.933776
threshold_high=1.623614
```

## 3. 接口说明

### GET /health

返回 service 健康状态：

```json
{
  "status": "ok",
  "service": "alfresco_ae_v1_score_service"
}
```

### GET /model

返回模型元信息：

```json
{
  "model_name": "alfresco_ae_v1",
  "model_type": "ae_like_statistical_baseline",
  "threshold_low": 0.933776,
  "threshold_high": 1.623614,
  "train_sample_count": 9
}
```

### POST /score

支持三类输入：

- `metadata_update`；
- `content_update`；
- `multipart_upload`。

返回字段包括：

- `score`；
- `pass`；
- `decision`；
- `reason`；
- `threshold_high`；
- `model_name`；
- `model_type`；
- `feature_vector`。

## 4. smoke 测试

新增 smoke 脚本：

```text
scripts/smoke_alfresco_ae_v1_score_service.py
```

该脚本会临时启动本地 score service，依次测试：

- `GET /health`；
- `GET /model`；
- `POST /score metadata_update`；
- `POST /score content_update`；
- `POST /score multipart_upload`。

本轮 smoke 输出：

```text
ALFRESCO_AE_V1_SCORE_SERVICE_SMOKE_PASS
```

说明：该 smoke 只访问本机 `127.0.0.1:18181`，不访问 Alfresco，不运行 fuzz。

## 5. service compare summary

新增 service compare 脚本：

```text
scripts/run_alfresco_ae_v1_service_compare.py
```

输出：

```text
out/alfresco_ae_v1_service_compare/summary.csv
out/alfresco_ae_v1_service_compare/details.csv
```

summary 关键字段：

```text
mode=rule_score
nv_total_valid_exec=12
nv_err_exec=0
nv_err_rate=0.000000
saved_hangs=0
saved_crashes=0
last_http_code=200
body_rule_pass=9
body_rule_reject=3
body_score_pass=9
body_score_reject=3
body_score_rpc_ok=12
body_score_rpc_fail=0
summary_source=python_static_loop
execution_scope=alfresco_ae_v1_score_service_min_calibration
```

## 6. details 概况

逐 seed 判定概况：

- metadata update：3 个合法/边界 seed 通过，`seed_bad_0.json` 规则拒绝，service HTTP 200；
- content update：3 个合法/边界 seed 通过，`seed_bad_0.txt` 规则拒绝，service HTTP 200；
- multipart upload：3 个合法/边界 seed 通过，`seed_bad_0.txt` 规则拒绝，service HTTP 200。

12 个 seed 均完成 service scoring，`body_score_rpc_ok=12`，`body_score_rpc_fail=0`。

## 7. 与本地 scorer 的关系

score service 没有重新实现模型逻辑，而是复用：

```text
model_stage/alfresco_ae_v1_scorer.py
```

本地 scorer 负责：

- 特征抽取；
- root mean square z-distance score；
- `threshold_high=1.623614` 判定；
- 输出 `pass/reject` 和 feature vector。

score service 只提供本地 HTTP 封装，方便联调与 profile 对接。

## 8. 阶段性结论

Alfresco AE v1 已从本地 scorer 推进到本地 HTTP score service / decision profile 联调形态。该 service 能对三类 Alfresco 文档接口输入进行统一评分，并保持 summary/details 统计口径与既有 `rule_score` 风格一致。

该结果可支撑后续轻量 API 或 MCP adapter 层将 Alfresco AE v1 scoring 作为可调用能力暴露给总项目联调。

## 9. 边界

- 这是 Alfresco AE v1 本地 score service 联调；
- 不等同于完整平台级 HTTP/RPC 网关；
- 不等同于完整 MCP Server；
- 不等同于完整 SE-fAnoGAN；
- 不等同于 GAN / fAnoGAN；
- 不是完整 AFL++ mutation-chain；
- 不是系统级 DHR；
- 当前 AE v1 仍是 `ae_like_statistical_baseline`，不是 torch autoencoder 或深度 AE。
