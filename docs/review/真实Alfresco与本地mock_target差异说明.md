# 真实Alfresco与本地mock_target差异说明

## 1. 文档目的

本文用于说明三语义 online filter 交付中本地 mock target 与真实 Alfresco 服务的差异，避免把本地可复现实验扩大解释为真实服务完整覆盖。

## 2. 为什么使用本地 mock target

本地 mock target 用于在授权、可控、可复现环境中验证 AFL++ mutation-chain、online filter、AE v1 scorer 和 fAnoGAN candidate 在线路径。它不依赖真实服务账号、网络状态、权限配置、节点清理或服务稳定性，适合 smoke、四模式消融和四模式短时稳定性实验。

## 3. 本地 mock target 与真实 Alfresco 差异表

| 对比项 | 本地 mock target | 真实 Alfresco 服务 | 当前项目口径 |
|---|---|---|---|
| 网络依赖 | 无网络访问，进程内本地分类 | 依赖 HTTP、端口、网络、反向代理或容器状态 | online filter 三语义实验不代表真实网络链路 |
| 认证与权限 | 无真实账号、token、租户和权限校验 | 需要用户、权限、会话、CSRF 或 repository 权限 | 不宣称真实认证权限覆盖 |
| 数据持久化 | 不写真实仓库，只返回受控分类结果 | 可能创建、修改、删除真实节点和元数据 | mock 结果不能等同真实 repository 行为 |
| 节点创建/删除 | 不创建真实 node，不需要清理 | 文件上传和 metadata update 可能产生持久副作用 | 真实服务扩展必须设计清理策略 |
| 服务状态依赖 | 只依赖本地 Python 与 AFL++ | 依赖 Alfresco 版本、插件、数据库、存储和后台服务 | 本地稳定性不代表真实服务稳定性 |
| 可复现性 | 高，可用固定 seed 和短时运行复现 | 受账号、数据状态、服务负载影响 | 本地 evidence 适合作为交付复现基线 |
| 安全风险 | 不触达外部系统，输入副作用受控 | fuzz 输入可能污染内容库或触发审计告警 | 真实 fuzz 必须在隔离授权环境中执行 |
| fuzz 输入副作用 | 被 reject 的输入受控退出；通过 filter 的输入只进 mock target | 通过的输入可能触发真实业务逻辑 | 不把 mock target 当作真实服务防护结论 |
| evidence 稳定性 | summary/report/fuzzer_stats 可稳定归档 | 真实服务 evidence 可能受环境差异影响 | 当前正式 evidence 以本地 mock 为主 |
| 当前交付结论 | 三语义 online filter 阶段性交付闭环完成 | 保留部分 min_calibration/manual evidence | 不宣称真实 Alfresco 服务完整覆盖 |

## 4. 当前三语义 online filter 的适用范围

当前三语义 online filter 适用于：

- content_update / text/plain 本地 mock 语义；
- metadata_update / application/json 本地 mock 语义；
- multipart_upload / multipart-form-data 本地 mock 语义；
- rule_only、rule_ae、rule_fanogan、rule_ae_fanogan 四模式的短时 AFL++ 运行对比；
- AE v1 主机制和 fAnoGAN candidate 在线路径的工程可运行性验证。

## 5. 真实服务 evidence 的定位

仓库保留的 Alfresco min_calibration / manual evidence 只能证明真实服务接口具备阶段性可达性或最小验证价值。它不能扩大解释为：

- 真实 Alfresco 服务完整 fuzz 覆盖；
- 真实权限、审计、清理和持久化链路完整覆盖；
- 所有 Alfresco 场景完整 AFL++ mutation-chain；
- 生产级安全防护结论。

## 6. 验收口径

建议验收口径：

三语义 online filter 在本地 mock target 上完成 smoke、四模式消融和四模式短时稳定性实验，形成可复现工程 evidence。真实 Alfresco 服务相关结论仅限于已有 min_calibration / manual evidence 的最小可达性和阶段性验证，不代表完整真实服务 fuzz 覆盖。

## 7. 后续可选真实服务扩展路线

真实服务扩展必须满足：

- 授权环境；
- 隔离部署；
- 可清理数据集；
- 明确账号和权限范围；
- 限制 fuzz 时长与速率；
- 保留审计和回滚方案；
- 区分真实服务 evidence 与本地 mock evidence。

## 8. 仍不能宣称的内容

- mock target 不等同于真实 Alfresco；
- 不代表真实 Alfresco 服务完整覆盖；
- 不代表所有场景完整 AFL++ mutation-chain；
- 不等同于长时间稳定性实验；
- 不代表系统级 DHR 完整完成。
