# 轻量API调用说明

## 1. API定位

轻量 API 用于总项目集成联调阶段调用模糊测试模块的既有能力和 evidence。

该 API 的定位是：

- 本地集成联调入口；
- 封装已有 runner、scripts 和 evidence 查询；
- 默认只读或轻量检查既有 NV_MAB summary；
- 不重新实现 fuzz 逻辑；
- 不默认执行 O2OA、Flowable、Alfresco 真实服务实验；
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
    "o2oa_smoke_optional"
  ],
  "notes": {
    "o2oa_smoke_optional": "requires NV_TOKEN and authorized local O2OA environment"
  }
}
```

## 5. Submit Dry Run

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

## 6. Submit Lightweight Check

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

## 7. Query Task

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

## 8. Stop Task

```bash
curl --noproxy '*' -X POST http://127.0.0.1:18081/fuzz/tasks/<task_id>/stop \
  -H 'Content-Type: application/json' \
  --data '{}'
```

当前默认任务通常是短命令检查，可能在 stop 前已经完成。

## 9. Task Report

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

## 10. Reports

```bash
curl --noproxy '*' http://127.0.0.1:18081/reports
```

该接口返回 `docs/review/` 下关键报告的白名单列表，不读取任意路径。

## 11. 安全边界

- API 默认绑定 `127.0.0.1`；
- 不允许任意 shell 命令执行；
- `subprocess` 使用 list 参数，且 `shell=False`；
- 执行命令来自固定白名单 command builder；
- 不允许读取任意系统路径；
- `out_dir` 必须位于仓库目录内；
- 不写真实 token；
- O2OA 场景默认不执行，除非后续显式接入授权环境和 token 注入策略；
- 该 API 不是完整平台级 HTTP/RPC 网关。

## 12. 边界表述

可以表述为：

> 已新增本地轻量 API，支持能力查询、任务提交占位、任务状态查询和 evidence 报告索引，便于总项目集成联调。

不能表述为：

> 已交付生产平台网关或完整 MCP Server。
