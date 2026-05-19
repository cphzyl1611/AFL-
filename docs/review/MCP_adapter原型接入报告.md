# MCP_adapter原型接入报告

## 1. 背景

当前仓库已完成轻量 API、Alfresco AE v1 scoring adapter、本地 score service 联调和相关 evidence 归档。为了便于后续 AI Agent 或总项目工具层调用，本轮新增 MCP adapter prototype，将现有能力包装为白名单工具接口。

本轮不引入外部 MCP SDK，不启动服务，不访问 Alfresco，不执行 fuzz，只提供可本地调用的 MCP-like adapter skeleton。

## 2. adapter 原型设计

新增文件：

```text
integration/mcp_adapter.py
```

设计方式：

- 使用 Python 标准库；
- 支持本地函数入口；
- 支持 JSON stdin/stdout 形式调用；
- 不启动外部服务；
- 不执行 shell；
- 不读取任意路径；
- 只允许白名单工具；
- 复用 `model_stage.alfresco_ae_v1_scorer.AlfrescoAEV1Scorer`。

请求形态示例：

```json
{
  "tool": "score_alfresco_ae_v1_sample",
  "arguments": {
    "scenario": "metadata_update",
    "payload": {
      "name": "official_doc.txt",
      "properties": {
        "cm:title": "标题",
        "cm:description": "说明"
      }
    }
  }
}
```

## 3. 白名单工具

当前白名单工具如下：

| 工具 | 作用 |
|---|---|
| `get_capabilities` | 返回 adapter 支持的工具、场景和安全边界 |
| `score_alfresco_ae_v1_sample` | 对 Alfresco metadata/content/multipart 样本执行 AE v1 scoring |
| `list_reports` | 返回固定白名单报告路径 |
| `query_evidence` | 查询固定白名单 summary evidence 的 header、首行和行数 |

`score_alfresco_ae_v1_sample` 支持：

- `metadata_update`；
- `content_update`；
- `multipart_upload`。

`query_evidence` 只允许以下 evidence：

- `out/alfresco_ae_v1_score_compare/summary.csv`；
- `out/alfresco_ae_v1_threshold_sweep/summary.csv`；
- `out/alfresco_ae_v1_service_compare/summary.csv`；
- `out/alfresco_content_update_manual_latest/summary.csv`；
- `out/alfresco_multipart_upload_manual_latest/summary.csv`。

## 4. 与轻量 API 的关系

轻量 API 暴露 HTTP endpoint：

```text
POST /score/alfresco_ae_v1
```

MCP adapter prototype 不重复训练模型，也不访问轻量 API 的 HTTP server。它与轻量 API 共享同一个底层 scorer：

```text
model_stage.alfresco_ae_v1_scorer.AlfrescoAEV1Scorer
```

因此两者的 score、decision、threshold 和 model_type 口径保持一致。后续如果需要完整 MCP Server，可将本 prototype 中的白名单函数映射为 MCP tools。

## 5. smoke 结果

新增 smoke 脚本：

```text
scripts/smoke_mcp_adapter.py
```

覆盖：

- `get_capabilities`；
- `score_alfresco_ae_v1_sample metadata_update`；
- `score_alfresco_ae_v1_sample content_update`；
- `score_alfresco_ae_v1_sample multipart_upload`；
- `list_reports`；
- `query_evidence` 固定 summary；
- 非白名单 tool 拒绝；
- 任意路径 evidence 查询拒绝。

期望输出：

```text
MCP_ADAPTER_SMOKE_PASS
```

## 6. 可用于总项目联调的能力

当前 prototype 可用于：

- 查询可用工具；
- 对 Alfresco 文档类输入执行本地 AE v1 scoring；
- 列出关键报告；
- 查询固定 summary evidence 的结构和首行数据；
- 为后续 MCP Server 实现提供最小白名单工具设计参考。

## 7. 安全边界

- 不允许任意 shell；
- 不允许读取任意路径；
- 不暴露真实 token；
- 不访问 Alfresco 服务；
- 不访问 O2OA 或 Flowable；
- 不启动外部服务；
- 不运行 fuzz；
- `query_evidence` 只能读取固定白名单 evidence；
- 非白名单 tool 会返回 `status=reject`。

## 8. 后续计划

建议后续如确需接入 AI Agent：

1. 保留当前白名单工具设计；
2. 使用正式 MCP SDK 实现 MCP Server；
3. 将 `score_alfresco_ae_v1_sample`、`list_reports`、`query_evidence` 映射为 tools/resources；
4. 对执行类能力增加人工确认、审计日志和更严格的访问控制。

## 9. 边界

- 这是 MCP adapter prototype；
- 不等同于完整 MCP Server；
- 不等同于完整平台级 HTTP/RPC 网关；
- 不开放任意 shell；
- 不开放任意路径读取；
- 不访问 Alfresco 服务；
- 不代表 GAN / fAnoGAN；
- 不代表完整 SE-fAnoGAN；
- 不代表系统级 DHR。
