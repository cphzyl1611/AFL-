# 轻量API调用说明

## 1. API定位

轻量 API 用于总项目集成联调阶段调用模糊测试模块的既有能力和 evidence。

该 API 的定位是：

- 本地集成联调入口；
- 封装已有 runner、scripts 和 evidence 查询；
- 默认只读或轻量检查既有 NV_MAB summary；
- 不重新实现 fuzz 逻辑；
- 不默认执行 O2OA、Flowable、Alfresco 真实服务实验；
- 提供 Alfresco AE v1 本地评分 adapter；
- 不是生产平台级 HTTP/RPC 网关。

默认监听：

```text
127.0.0.1:18081
```

## 2. 启动命令

```bash
python3 integration/api_server.py --host 127.0.0.1 --port 18081
```

不要在未加访问控制的情况下监听公网地址。

## 3. Health

请求：

```bash
curl --noproxy '*' http://127.0.0.1:18081/health
```

示例响应：

```json
{
  "status": "ok",
  "service": "fuzzing-module-api",
  "version": "stage-delivery"
}
```

## 4. Capabilities

请求：

```bash
curl --noproxy '*' http://127.0.0.1:18081/capabilities
```

示例响应字段：

```json
{
  "scenarios": [
    "nv_mab_smoke",
    "nv_mab_stability",
    "nv_mab_ablation",
    "alfresco_metadata_update",
    "flowable_doc_create",
    "flowable_doc_update",
    "alfresco_ae_v1_score_service",
    "o2oa_smoke_optional"
  ],
  "tools": {
    "alfresco_ae_v1_score": {
      "description": "Alfresco AE v1 local scoring adapter",
      "endpoint": "POST /score/alfresco_ae_v1",
      "model_type": "ae_like_statistical_baseline"
    }
  },
  "notes": {
    "o2oa_smoke_optional": "requires NV_TOKEN and authorized local O2OA environment"
  }
}
```

## 5. Alfresco AE v1 Scoring

轻量 API 提供本地 Alfresco AE v1 scoring adapter：

```text
POST /score/alfresco_ae_v1
```

该 endpoint 直接复用 `model_stage.alfresco_ae_v1_scorer.AlfrescoAEV1Scorer`，不要求 `127.0.0.1:18181` score service 常驻，不访问 Alfresco 服务，也不访问外部网络。

metadata update 示例：

```bash
curl --noproxy '*' -X POST http://127.0.0.1:18081/score/alfresco_ae_v1 \
  -H 'Content-Type: application/json' \
  --data '{"scenario":"metadata_update","payload":{"name":"official_doc.txt","properties":{"cm:title":"标题","cm:description":"说明"}}}'
```

content update 示例：

```bash
curl --noproxy '*' -X POST http://127.0.0.1:18081/score/alfresco_ae_v1 \
  -H 'Content-Type: application/json' \
  --data '{"scenario":"content_update","content":"正文内容"}'
```

multipart upload 示例：

```bash
curl --noproxy '*' -X POST http://127.0.0.1:18081/score/alfresco_ae_v1 \
  -H 'Content-Type: application/json' \
  --data '{"scenario":"multipart_upload","filename":"official_doc.txt","fields":{"nodeType":"cm:content","autoRename":"true"},"content":"上传文件内容"}'
```

响应会包含 `score`、`decision`、`reason`、`threshold_high`、`model_name` 和 `model_type`。当前 `model_type=ae_like_statistical_baseline`。

## 6. Submit Dry Run

请求：

```bash
curl --noproxy '*' -X POST http://127.0.0.1:18081/fuzz/submit \
  -H 'Content-Type: application/json' \
  --data '{"scenario":"nv_mab_smoke","out_dir":"out/api_demo_nv_mab","dry_run":true}'
```

说明：

- `scenario` 必须来自白名单；
- `dry_run=true` 只返回固定命令模板，不实际执行；
- API 不接受任意 shell 命令；
- `out_dir` 必须位于仓库目录内。

## 7. Submit Lightweight Check

当前默认只支持以下本地安全场景：

- `nv_mab_smoke`
- `nv_mab_stability`
- `nv_mab_ablation`

这些场景不会重跑大型 fuzz，只检查既有 summary evidence 是否存在。

示例：

```bash
curl --noproxy '*' -X POST http://127.0.0.1:18081/fuzz/submit \
  -H 'Content-Type: application/json' \
  --data '{"scenario":"nv_mab_stability","out_dir":"out/api_demo_stability","dry_run":false}'
```

Flowable、Alfresco、O2OA 场景在轻量 API 中默认不执行真实服务实验，会返回 `unsupported_runtime` 或提示手工复现。

## 8. Query Task

```bash
curl --noproxy '*' http://127.0.0.1:18081/fuzz/tasks/<task_id>
```

示例响应字段：

```json
{
  "task_id": "demo",
  "status": "completed",
  "returncode": 0,
  "started_at": "2026-05-12T00:00:00+00:00",
  "finished_at": "2026-05-12T00:00:01+00:00",
  "out_dir": "out/api_demo_nv_mab",
  "log_path": "out/api_demo_nv_mab/api_task.log"
}
```

## 9. Stop Task

```bash
curl --noproxy '*' -X POST http://127.0.0.1:18081/fuzz/tasks/<task_id>/stop \
  -H 'Content-Type: application/json' \
  --data '{}'
```

当前默认任务通常是短命令检查，可能在 stop 前已经完成。

## 10. Task Report

```bash
curl --noproxy '*' http://127.0.0.1:18081/fuzz/tasks/<task_id>/report
```

响应会列出白名单内的 summary 和报告路径，例如：

```json
{
  "task_id": "demo",
  "status": "completed",
  "out_dir": "out/api_demo_nv_mab",
  "summary_files": [
    "out/nv_mab_smoke_summary.csv"
  ],
  "report_files": [
    "docs/review/NV_MAB反馈变异策略阶段性收口报告.md"
  ],
  "notes": "Lightweight API report; evidence files are returned by whitelist only."
}
```

## 11. Reports

```bash
curl --noproxy '*' http://127.0.0.1:18081/reports
```

该接口返回 `docs/review/` 下关键报告的白名单列表，不读取任意路径。

当前 `/reports` 包含 Alfresco AE v1 相关报告和 summary evidence，例如：

- `docs/review/Alfresco_AE_v1二阶段有效性判定验证报告.md`
- `docs/review/Alfresco_AE_v1阈值校准与误判分析报告.md`
- `docs/review/Alfresco_AE_v1_score_service联调报告.md`
- `docs/review/Alfresco_AE_v1轻量API接入报告.md`
- `out/alfresco_ae_v1_score_compare/summary.csv`
- `out/alfresco_ae_v1_threshold_sweep/summary.csv`
- `out/alfresco_ae_v1_service_compare/summary.csv`

## 12. MCP Adapter Prototype

当前已新增 MCP adapter prototype：

```text
integration/mcp_adapter.py
```

白名单工具包括：

- `get_capabilities`
- `score_alfresco_ae_v1_sample`
- `list_reports`
- `query_evidence`

该 adapter 复用 `AlfrescoAEV1Scorer`，不访问 Alfresco 服务，不开放任意 shell 或任意路径读取，不等同于完整 MCP Server。

## 13. 安全边界

- API 默认绑定 `127.0.0.1`；
- 不允许任意 shell 命令执行；
- `subprocess` 使用 list 参数，且 `shell=False`；
- 执行命令来自固定白名单 command builder；
- 不允许读取任意系统路径；
- `out_dir` 必须位于仓库目录内；
- `/score/alfresco_ae_v1` 只做本地评分，不访问 Alfresco 服务；
- 不写真实 token；
- O2OA 场景默认不执行，除非后续显式接入授权环境和 token 注入策略；
- 该 API 不是完整平台级 HTTP/RPC 网关。

## 14. 边界表述

可以表述为：

> 已新增本地轻量 API，支持能力查询、任务提交占位、任务状态查询和 evidence 报告索引，便于总项目集成联调。

不能表述为：

> 已交付生产平台网关或完整 MCP Server。
