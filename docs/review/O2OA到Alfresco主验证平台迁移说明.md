# O2OA到Alfresco主验证平台迁移说明

## 1. 背景

项目原始测试场景包含 O2OA 电子公文数据接口。当前仓库中 O2OA 相关文档和 evidence 已保留，包括 O2OA CMS document filter/list 真实服务 smoke 结果和相关审计、收口报告。

现阶段 O2OA 作为历史 smoke 证据、原项目指定场景对照和需求追溯材料继续保留。后续主验证平台拟调整为 Alfresco，用于持续复现和扩展文档类业务语义接口验证。

## 2. 迁移原因

O2OA 原生电子公文写入接口受当前会话 token、权限、表单上下文、栏目配置和平台状态影响较大，本地复现与持续自动化存在不稳定因素。

Alfresco 是标准文档管理平台，REST API 对文档节点、内容、元数据和上传创建的语义更清晰，接口边界更稳定，更适合作为标准化、可复现的文档类业务接口验证平台。

## 3. 业务语义映射

| 原 O2OA 业务语义 | Alfresco 对应接口 | 当前 evidence |
|---|---|---|
| 电子公文创建与保存 | multipart upload 创建 `cm:content` 文档节点 | `out/alfresco_multipart_upload_manual_latest/summary.csv`、`out/alfresco_multipart_upload_manual_latest/details.csv`、`docs/review/Alfresco上传创建接口接入验证报告.md` |
| 电子公文内容更新 | `PUT /nodes/{nodeId}/content`，`text/plain` | `out/alfresco_content_update_manual_latest/summary.csv`、`out/alfresco_content_update_manual_latest/details.csv`、`docs/review/Alfresco内容更新接口接入验证报告.md` |
| 电子公文元数据更新 | `PUT /nodes/{nodeId}`，JSON metadata | `out/alfresco_metadata_update_manual_latest/summary.csv`、`out/alfresco_metadata_update_manual_latest/details.csv`、`docs/review/Alfresco元数据更新接口接入验证报告.md` |

## 4. 已完成 evidence

当前 Alfresco 标准文档平台已完成三类核心文档接口验证：

- Alfresco metadata update：真实 smoke 通过；
- Alfresco text/plain content update：真实服务 `min_calibration` smoke 通过；
- Alfresco multipart upload：真实服务 `min_calibration` smoke 通过。

以上结果均为 `python_static_loop` / `min_calibration` 范围，不是完整 AFL++ mutation-chain。

## 5. O2OA 文档保留策略

- 不删除 O2OA 相关报告；
- 不删除 O2OA smoke evidence；
- O2OA 保留为原始项目场景、历史验证和需求对照；
- 后续如果项目组提供稳定 O2OA 原生写入接口环境，可继续补充 O2OA 原生创建/更新接口验证。

## 6. 对项目完成度的影响

迁移口径调整后，文档类业务语义接口能力显著增强。Alfresco 已覆盖标准文档平台的创建/保存、内容更新和元数据更新三类核心接口，可支撑后续 Alfresco AE v1、score profile 和二阶段有效性判定。

该调整不改变 O2OA 历史 smoke 证据的价值，也不能宣称 O2OA 原生电子公文接口全覆盖。

## 7. 后续计划

1. Alfresco AE v1 二阶段有效性判定；
2. Alfresco score profile；
3. 如有必要，再评估 GAN / fAnoGAN 候选；
4. 如需系统级 DHR，等待拟态执行体环境。

## 8. 边界

- Alfresco 是后续主验证平台，不等同于 O2OA 原生接口；
- 不宣称 O2OA 原生电子公文接口全覆盖；
- 不宣称完整 AFL++ mutation-chain；
- 不宣称完整平台级 HTTP/RPC 网关；
- 不宣称完整拟态系统级动态异构冗余；
- 不宣称完整 NC_MAB 理论闭环；
- O2OA 相关文档与 evidence 保留。
