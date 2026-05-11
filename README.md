# 广义功能安全模糊测试组件

## 1. 项目定位

本仓库实现基于 AFL++ 改造的广义功能安全模糊测试组件，面向 HTTP/REST JSON API 和文档类业务接口。

当前组件支持：

- 多平台 seed 管理；
- 结构保持型 JSON 变异；
- 规则过滤；
- score / decision 判定；
- NV_MAB 反馈变异；
- `summary.csv`、`details.csv`、`fuzzer_stats`、`plot_data` 等 evidence 输出。

## 2. 当前阶段性结论

当前模糊测试模块已具备阶段性验收条件：

- 文档类业务语义接口能力已阶段性收口；
- 测评链路版动态异构冗余判定机制已阶段性收口；
- NV_MAB 工程闭环基本完成，并完成轻量稳定性与最小多轮消融验证；
- 可进入总项目集成联调。

## 3. 当前已验证能力矩阵

| 能力项 | 当前状态 | 说明 |
|---|---|---|
| O2OA HTTP/REST JSON 主链 | 已验证 | O2OA CMS document filter/list 真实服务 smoke 已通过，是 O2OA 基础 HTTP/REST JSON 主链证据。 |
| Flowable `documentProcess` 创建/保存替代场景 | 已验证 | 映射为流程实例启动，是电子公文创建/保存的建模替代场景。 |
| Flowable `documentProcess` 内容更新替代场景 | 已验证 | 映射为流程变量更新，`seed_bad_0.json` 是预设非法样本。 |
| Alfresco 文档创建/保存 | 已手工验证 | 标准文档平台原生接口，作为文档类业务语义证据。 |
| Alfresco 文档内容更新 | 已手工验证 | 标准文档平台原生内容更新接口。 |
| Alfresco 元数据更新 | 已接入 smoke | JSON body 接口，适配当前 body-only JSON fuzz 框架。 |
| NV_MAB 反馈变异策略 | 基本完成 | 已完成工程闭环、最小 smoke、轻量稳定性和最小多轮消融验证。 |
| 测评链路版 DHR | 基本完成 | O2OA AE + GAN online、Flowable AE v2 + `flowable_rule_v1` 支撑二阶段异构判定增强。 |
| 完整系统级 DHR | 未完成/不宣称 | 不含多执行体调度、输出裁决、动态重构、自愈恢复。 |

## 4. 快速复现入口

完整复现步骤见：

- `docs/reproduce/实验复现指南.md`

## 5. 主要报告索引

- `docs/review/模糊测试模块项目要求完成证明与复现说明.md`
- `docs/review/文档类业务接口能力阶段性收口报告.md`
- `docs/review/动态异构冗余判定机制阶段性收口报告.md`
- `docs/review/NV_MAB反馈变异策略阶段性收口报告.md`
- `docs/review/NV_MAB轻量稳定性与最小消融验证报告.md`
- `docs/review/Flowable电子公文替代场景验证报告.md`
- `docs/review/Alfresco文档接口手工验证报告.md`
- `docs/review/Alfresco元数据更新接口接入验证报告.md`
- `docs/review/真实服务环境smoke验证报告.md`
- `docs/review/接口能力审计报告.md`

## 6. 当前不能宣称的内容

当前不能宣称：

- O2OA 原生电子公文创建/保存、内容更新接口已全覆盖；
- Flowable 替代了 O2OA；
- Alfresco 等同于 O2OA；
- 完整 NC_MAB 理论闭环完成；
- 完整自动化语义种子生成完成；
- 长时间稳定性或完整论文级消融完成；
- Flowable 完整 AFL++ mutation-chain 完成；
- 完整拟态系统级动态异构冗余完成；
- 完整平台 HTTP/RPC 网关服务已完成。

## 7. 后续工作

- 如有稳定 O2OA 写入接口环境，可补原生 O2OA 创建/更新接口；
- 如有需求，可扩展 Alfresco `text/plain` 内容 fuzz 和 multipart 上传 fuzz；
- 如总项目提供拟态执行体环境，再做系统级 DHR；
- 当前阶段建议停止扩功能，转入集成联调和交付。
