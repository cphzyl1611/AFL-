# Alfresco_AE_v1轻量API接入报告

## 1. 背景

Alfresco 已作为后续主验证平台，metadata update、text/plain content update、multipart upload 三类文档接口已完成真实 smoke。Alfresco AE v1 engineering scorer 已完成本地 score compare、阈值校准、误判分析和本地 HTTP score service 联调。

本轮将 Alfresco AE v1 scoring 接入 `integration/api_server.py`，作为轻量 API 的本地可调用评分能力，便于总项目集成联调阶段通过统一 API 调用模型评分。

## 2. API adapter 设计

新增轻量 API endpoint：

```text
POST /score/alfresco_ae_v1
```

实现方式：

- 直接复用 `model_stage.alfresco_ae_v1_scorer.AlfrescoAEV1Scorer`；
- 不要求 `127.0.0.1:18181` score service 常驻；
- 不访问 Alfresco 服务；
- 不访问外部网络；
- 不执行任意 shell；
- 不读取任意路径。

该 endpoint 是轻量 API 内部 scoring adapter，不是完整平台级 HTTP/RPC 网关。

## 3. endpoint 说明

### metadata_update

请求示例：

```json
{
  "scenario": "metadata_update",
  "payload": {
    "name": "official_doc.txt",
    "properties": {
      "cm:title": "标题",
      "cm:description": "说明"
    }
  }
}
```

### content_update

请求示例：

```json
{
  "scenario": "content_update",
  "content": "正文内容"
}
```

### multipart_upload

请求示例：

```json
{
  "scenario": "multipart_upload",
  "filename": "official_doc.txt",
  "fields": {
    "nodeType": "cm:content",
    "autoRename": "true"
  },
  "content": "上传文件内容"
}
```

响应字段：

```json
{
  "status": "ok",
  "tool": "alfresco_ae_v1_score",
  "scenario": "metadata_update",
  "score": 0.937674,
  "pass": true,
  "decision": "pass",
  "reason": "score_within_threshold",
  "threshold_high": 1.623614,
  "model_name": "alfresco_ae_v1",
  "model_type": "ae_like_statistical_baseline"
}
```

## 4. smoke 结果

`scripts/smoke_api_server.py` 已扩展覆盖：

- `GET /health`；
- `GET /capabilities`；
- `GET /reports`；
- `POST /fuzz/submit` dry run；
- `POST /score/alfresco_ae_v1 metadata_update`；
- `POST /score/alfresco_ae_v1 content_update`；
- `POST /score/alfresco_ae_v1 multipart_upload`。

本轮 smoke 期望输出：

```text
API_SMOKE_PASS
```

## 5. 与 score service 的关系

`model_stage/alfresco_ae_v1_score_service.py` 是独立的 localhost-only score service，默认监听 `127.0.0.1:18181`。

轻量 API 的 `/score/alfresco_ae_v1` 不依赖该 service 常驻，而是在 API 进程内直接复用 `AlfrescoAEV1Scorer`。两者使用同一份模型元数据：

```text
model_stage/models/alfresco_ae_v1_meta.json
```

这样做可以降低集成演示时的进程依赖，同时保留独立 score service 供 service/profile 联调使用。

## 6. 与 MCP 的关系

该 endpoint 可作为未来 MCP tool 的后端能力来源，例如映射为：

```text
score_alfresco_ae_v1_sample
```

但本轮没有实现完整 MCP Server，也没有暴露任意工具执行能力。MCP 接入仍应遵循只读优先、白名单工具、禁止任意 shell、禁止 token 暴露的边界。

## 7. 阶段性结论

Alfresco AE v1 已接入轻量 API，形成可通过 `POST /score/alfresco_ae_v1` 调用的本地评分 adapter。该能力可支撑总项目集成联调阶段对 Alfresco 文档类输入进行本地 AE-like score 判定。

## 8. 边界

- 这是轻量 API adapter；
- 不等同于完整平台级 HTTP/RPC 网关；
- 不等同于完整 MCP Server；
- 不等同于 GAN / fAnoGAN；
- 不等同于完整 SE-fAnoGAN；
- 不是完整 AFL++ mutation-chain；
- 不是系统级 DHR；
- 当前模型仍是 `ae_like_statistical_baseline`，不是 torch autoencoder 或完整深度 AE。
