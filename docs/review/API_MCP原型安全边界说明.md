# API_MCP原型安全边界说明

## 1. 文档目的

本文用于说明模糊测试模块中 lightweight API prototype 与 MCP-like adapter prototype 的能力范围和安全边界，避免把本地原型扩大解释为生产级平台网关或完整 MCP Server。

## 2. lightweight API prototype 说明

lightweight API prototype 位于：

- `integration/api_server.py`

当前定位：

- 本地能力查询；
- 报告索引查询；
- 任务语义封装；
- AE v1 scoring adapter；
- localhost-only 或本地原型定位。

典型能力包括：

- `GET /health`
- `GET /capabilities`
- `GET /reports`
- `POST /score/alfresco_ae_v1`
- 轻量 fuzz task dry run / submit 语义封装

该 API 不等同于完整平台级 HTTP/RPC 网关，不宣称生产级认证鉴权、多租户、审计、权限管理或公网暴露能力。

## 3. MCP-like adapter prototype 说明

MCP-like adapter prototype 位于：

- `integration/mcp_adapter.py`

它不依赖外部 MCP SDK，仅提供白名单 JSON stdin/stdout 风格工具调用原型，用于验收阶段展示 AI Agent 接入边界。

## 4. 白名单能力

MCP-like adapter 白名单工具包括：

| 工具 | 作用 |
|---|---|
| `get_capabilities` | 返回 adapter prototype 能力和边界 |
| `score_alfresco_ae_v1_sample` | 对单个 Alfresco metadata/content/multipart 样本执行 AE v1 本地评分 |
| `list_reports` | 返回固定报告白名单 |
| `query_evidence` | 读取固定 evidence 白名单中的 header 和首行 |

## 5. 安全边界

lightweight API 与 MCP-like adapter 均保持以下边界：

- 不执行任意 shell；
- 不读取任意路径；
- 不访问真实 Alfresco；
- 不写真实 token；
- 不启动 O2OA、Flowable 或 Alfresco；
- 不训练模型；
- 不运行 AFL++；
- `POST /score/alfresco_ae_v1` 仅为本地 scoring adapter；
- report/evidence 查询限定在白名单路径；
- 不等同于生产级权限系统。

## 6. 不能宣称内容

- 不能宣称已实现完整 MCP Server；
- 不能宣称已实现完整平台级 HTTP/RPC 网关；
- 不能宣称具备生产级认证鉴权、多租户、审计和权限管理；
- 不能宣称 API/MCP prototype 访问或覆盖真实 Alfresco 服务；
- 不能宣称 fAnoGAN candidate 替代 AE v1；
- 不能宣称完整 SE-fAnoGAN-ES 或完整 GAN/fAnoGAN。

## 7. 后续扩展建议

后续如需扩展为正式集成能力，建议：

- 引入正式 MCP SDK 或平台网关框架；
- 增加认证、授权、审计和速率限制；
- 继续保持工具白名单；
- 将真实服务访问放入授权隔离环境；
- 区分 dry run、mock run 和 real service run；
- 保留敏感信息扫描和路径白名单策略。
