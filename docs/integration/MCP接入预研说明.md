# MCP接入预研说明

## 1. MCP原理简述

MCP 面向 AI Agent / LLM Host 场景，用于把外部能力以标准化方式暴露给模型宿主。

典型 MCP Server 可以暴露：

- `tools`：可调用动作，例如提交 fuzz 任务、查询任务、获取报告；
- `resources`：可读取资源，例如报告索引、summary evidence；
- `prompts`：可复用提示模板，例如生成阶段性汇报。

MCP 不是普通后端 API 的替代。普通 HTTP API 更适合系统间集成，MCP 更适合 AI Agent 以工具方式调用已有能力。对本项目而言，MCP Server 更适合作为轻量 API 的 adapter，而不是直接绕过安全边界执行底层命令。

## 2. 本项目适合暴露的MCP tools

建议工具：

| MCP tool | 对应能力 |
|---|---|
| `list_capabilities` | 查询当前支持的 fuzz 场景白名单 |
| `list_reports` | 查询关键 review 报告 |
| `submit_fuzz_task` | 提交白名单 fuzz 任务或 dry run |
| `query_fuzz_task` | 查询任务状态 |
| `stop_fuzz_task` | 停止仍在运行的任务 |
| `get_fuzz_report` | 获取任务关联 summary/report 列表 |
| `score_alfresco_ae_v1_sample` | 对 Alfresco metadata/content/multipart 样本执行 AE v1 scoring |
| `query_evidence` | 查询固定白名单 summary evidence |

建议 resources：

| MCP resource | 内容 |
|---|---|
| `fuzz://reports` | 关键报告索引 |
| `fuzz://capabilities` | 场景能力白名单 |
| `fuzz://evidence/nv_mab` | NV_MAB smoke / stability / ablation summary 路径 |

## 3. 安全边界

MCP 接入必须遵守以下边界：

- 不允许任意 shell；
- 不允许读取任意路径；
- 不暴露真实 token；
- O2OA 场景默认禁用；
- 执行类工具需要人工确认；
- 默认只读 reports 更安全；
- MCP Server 不应直接暴露公网；
- MCP tool 应调用轻量 API 或固定白名单函数，不应直接拼接用户输入为命令。

## 4. 推荐实现路线

### 第一阶段：轻量 API

当前阶段先提供 `integration/api_server.py`：

- 支持 `/health`；
- 支持 `/capabilities`；
- 支持 `/fuzz/submit`；
- 支持 `/fuzz/tasks/{task_id}`；
- 支持 `/fuzz/tasks/{task_id}/stop`；
- 支持 `/fuzz/tasks/{task_id}/report`；
- 支持 `/reports`。

该阶段服务于总项目本地集成联调。

### 第二阶段：MCP Server 作为 API adapter

在轻量 API 稳定后，可新增 MCP Server：

- MCP tool 不直接执行底层脚本；
- MCP tool 调用轻量 API；
- MCP resource 映射报告索引和 evidence 索引；
- 执行类 tool 增加确认机制和审计日志。

### 第三阶段：接入总项目或 AI Agent

总项目或 AI Agent 可通过 MCP 调用：

- 能力查询；
- 任务 dry run；
- 任务状态查询；
- 报告索引读取；
- evidence 路径汇总。

## 5. 当前状态

当前已新增 MCP adapter prototype：

当前可交付内容是：

- 本地轻量 API；
- API 调用说明；
- MCP 接入路线和安全边界说明。
- `integration/mcp_adapter.py`；
- `scripts/smoke_mcp_adapter.py`；
- `docs/review/MCP_adapter原型接入报告.md`。

prototype 白名单工具包括：

- `get_capabilities`；
- `score_alfresco_ae_v1_sample`；
- `list_reports`；
- `query_evidence`。

该 prototype 复用 `AlfrescoAEV1Scorer`，不访问 Alfresco 服务，不开放任意 shell，不开放任意路径读取。

当前仍不能宣称完整 MCP Server 已经交付，也不能把轻量 API 或 MCP adapter prototype 表述为生产平台网关。
