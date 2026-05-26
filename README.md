# 广义功能安全模糊测试组件

## 1. 项目定位

本仓库实现基于 AFL++ 改造的广义功能安全模糊测试组件，面向 HTTP/REST JSON API 和文档类业务接口。

当前组件支持：

- 多平台 seed 管理；
- 结构保持型 JSON 变异；
- 规则过滤；
- score / decision 判定；
- NV_MAB 反馈变异；
- Alfresco fAnoGAN v1 candidate 离线对比；
- 代表性 AFL++ mutation-chain smoke、短时稳定性实验、online filter 原型、metadata_update online filter smoke、metadata_update 四模式消融与四模式短时稳定性实验、content_update 四模式消融与四模式短时稳定性实验；
- MCP adapter prototype；
- `summary.csv`、`details.csv`、`fuzzer_stats`、`plot_data` 等 evidence 输出。

## 2. 当前阶段性结论

当前模糊测试模块已具备阶段性验收条件：

- 文档类业务语义接口能力已阶段性收口；
- 测评链路版动态异构冗余判定机制已阶段性收口；
- NV_MAB 工程闭环基本完成，并完成轻量稳定性与最小多轮消融验证；
- 可进入总项目集成联调。

当前冻结交付版本见：

- `docs/review/v0.3.5最终工程交付状态冻结说明.md`

## 3. 平台定位

当前平台口径：

- 后续主验证平台：Alfresco，已覆盖 multipart upload 创建/保存、text/plain 内容更新、JSON metadata update 三类标准文档接口；
- Alfresco 二阶段有效性判定：已新增 AE v1 engineering scorer，覆盖三类标准文档接口输入，并完成阈值 sweep、误判分析、本地 score service 联调和轻量 API adapter 接入；
- Alfresco fAnoGAN v1 candidate：已完成 fallback 与 `.venv` torch fAnoGAN-style 候选评分、扩展样本二次评估、劣势诊断、阈值重校准和 holdout 验证；当前 recommendation 仍为继续以 AE v1 作为主二阶段判定；
- MCP adapter prototype：已新增白名单工具原型，支持 Alfresco AE v1 scoring、报告列表和固定 evidence 查询；
- 代表性 AFL++ mutation-chain smoke：已新增 Alfresco `content_update` 本地 mock target 短时 AFL++ smoke，并完成 3 轮短时稳定性实验；已新增 SE-fAnoGAN-ES-style online filter prototype、`content_update` 与 `metadata_update` 四模式消融和四模式 3 轮短时稳定性实验，以及 `metadata_update` / application/json online filter smoke，默认主机制仍为 AE v1，fAnoGAN candidate 在线路径已验证但未替代 AE v1；这些链路不访问真实 Alfresco 服务，不代表所有场景完整 AFL++ mutation-chain；
- 历史保留平台：O2OA，保留为原项目指定场景、历史 smoke 和需求对照；
- 流程替代平台：Flowable，保留为 `documentProcess` 电子公文替代场景。

迁移说明见：

- `docs/review/O2OA到Alfresco主验证平台迁移说明.md`

## 4. 当前已验证能力矩阵

| 能力项 | 当前状态 | 说明 |
|---|---|---|
| O2OA HTTP/REST JSON 主链 | 已验证 | O2OA CMS document filter/list 真实服务 smoke 已通过，是 O2OA 基础 HTTP/REST JSON 主链证据。 |
| Flowable `documentProcess` 创建/保存替代场景 | 已验证 | 映射为流程实例启动，是电子公文创建/保存的建模替代场景。 |
| Flowable `documentProcess` 内容更新替代场景 | 已验证 | 映射为流程变量更新，`seed_bad_0.json` 是预设非法样本。 |
| Alfresco 文档创建/保存 | 已手工验证，已完成 multipart upload 真实服务 min_calibration smoke | 标准文档平台原生创建/保存接口；evidence 位于 `out/alfresco_multipart_upload_manual_latest/summary.csv` 和 `details.csv`。 |
| Alfresco 文档内容更新 | 已手工验证，已完成 text/plain 真实服务 min_calibration smoke | 标准文档平台原生内容更新接口；evidence 位于 `out/alfresco_content_update_manual_latest/summary.csv` 和 `details.csv`。 |
| Alfresco 元数据更新 | 已接入 smoke | JSON body 接口，适配当前 body-only JSON fuzz 框架。 |
| Alfresco AE v1 二阶段有效性判定 | 已接入本地 score compare、阈值 sweep / 误判分析、本地 score service 和轻量 API adapter | AE-like statistical baseline，覆盖 metadata/content/upload 三类输入；轻量 API endpoint 为 `POST /score/alfresco_ae_v1`；score compare、阈值分析和 service compare evidence 已归档。 |
| Alfresco fAnoGAN v1 candidate | 已完成 fallback 与 torch 候选对比、扩展样本二次评估、诊断复评、阈值重校准和 holdout 验证 | 当前 `.venv` 复评为 `torch_fanogan_style_candidate`，用于和 AE v1 对比；holdout 上校准后 rule_fanogan 与 rule_ae 均为 `false_accept=0,false_reject=0`，candidate 未优于 AE v1，recommendation 仍为 `keep_ae_v1_as_primary`。 |
| Alfresco content_update 代表性 AFL++ mutation-chain smoke | 已完成短时真实 AFL++ smoke | 使用本地 mock target，不访问真实 Alfresco；evidence 位于 `out/alfresco_afl_content_update_smoke_latest/summary.csv`、`eval_report.json` 和 `fuzzer_stats`。 |
| Alfresco content_update 代表性 AFL++ mutation-chain 短时稳定性 | 已完成 3 轮短时稳定性实验 | 三轮均为 `saved_crashes=0,saved_hangs=0,nv_err_exec=0`，`stability_score=1.000000`；evidence 位于 `out/alfresco_afl_content_update_stability/`。 |
| SE-fAnoGAN-ES-style online filter prototype | 已完成代表性 AFL++ online filter smoke、四模式消融与四模式短时稳定性实验 | 默认 `rule_ae`，AE v1 在线判定后再执行本地 mock target；四模式消融和 3 轮短时稳定性实验验证了 fAnoGAN candidate 在线路径可运行且无 scoring error，但短时样本量受 torch scorer 成本限制，AE v1 仍为主机制。 |
| Alfresco metadata_update online filter smoke、四模式消融与短时稳定性 | 已完成短时真实 AFL++ smoke、四模式消融和四模式 3 轮短时稳定性实验 | 使用 application/json 本地 mock target，默认 `rule_ae`，并已验证 `rule_only`、`rule_ae`、`rule_fanogan`、`rule_ae_fanogan`；fAnoGAN candidate 在线路径多轮可运行且无 scoring error，但推理成本较高，AE v1 仍为主机制；evidence 位于 `out/alfresco_afl_metadata_online_filter_smoke_latest/`、`out/alfresco_afl_metadata_online_filter_ablation/` 和 `out/alfresco_afl_metadata_online_filter_ablation_stability/`。 |
| MCP adapter prototype | 已接入原型 | 白名单工具包括 `get_capabilities`、`score_alfresco_ae_v1_sample`、`list_reports`、`query_evidence`；不是完整 MCP Server。 |
| NV_MAB 反馈变异策略 | 基本完成 | 已完成工程闭环、最小 smoke、轻量稳定性和最小多轮消融验证。 |
| 测评链路版 DHR | 基本完成 | O2OA AE + GAN online、Flowable AE v2 + `flowable_rule_v1` 支撑二阶段异构判定增强。 |
| 完整系统级 DHR | 未完成/不宣称 | 不含多执行体调度、输出裁决、动态重构、自愈恢复。 |

## 5. 快速复现入口

| 文档 | 用途 |
|---|---|
| `docs/reproduce/实验复现指南.md` | 完整复现实验，包含环境、平台、token 和多场景复现 |
| `docs/reproduce/快速演示命令.md` | 快速确认交付状态、preflight、API smoke 和轻量 API 查询 |

完整复现按 `docs/reproduce/实验复现指南.md` 执行；现场快速确认优先使用 `docs/reproduce/快速演示命令.md`。

## 6. 轻量 API 与集成调用

本仓库提供本地轻量 API Server，用于总项目集成联调阶段查询能力、查看报告索引，并以白名单方式提交轻量任务或 dry run。

入口文件：

- `integration/api_server.py`

启动命令：

```bash
python3 integration/api_server.py --host 127.0.0.1 --port 18081
```

常用接口：

| 接口 | 作用 |
|---|---|
| `GET /health` | 服务健康检查 |
| `GET /capabilities` | 查看支持的测试场景 |
| `GET /reports` | 查看关键报告索引 |
| `POST /score/alfresco_ae_v1` | Alfresco AE v1 本地评分 adapter |
| `POST /fuzz/submit` | 提交白名单测试任务或 dry run |
| `GET /fuzz/tasks/{task_id}` | 查询任务状态 |
| `POST /fuzz/tasks/{task_id}/stop` | 停止任务 |
| `GET /fuzz/tasks/{task_id}/report` | 查询任务报告 |

详细文档：

- `docs/integration/轻量API调用说明.md`
- `docs/integration/MCP接入预研说明.md`
- `integration/mcp_adapter.py`

边界：

- 这是本地轻量集成 API；
- 不是完整平台级 HTTP/RPC 网关；
- 当前只有 MCP adapter prototype，未实现完整 MCP Server；
- 不允许任意 shell 命令；
- `POST /score/alfresco_ae_v1` 是本地 scoring adapter，不访问 Alfresco 服务；
- O2OA token 不应写入仓库。

## 7. 工程质量检查与 CI

当前仓库已补充基础工程质量检查入口：

- GitHub Actions `delivery-check`；
- `scripts/delivery_preflight_check.py` 一键交付预检查；
- `scripts/validate_project_configs.py` 配置、schema、seed 和 summary evidence 校验；
- `tests/` 基础 `unittest`；
- API smoke；
- 敏感信息扫描；
- 口径扫描。

常用命令：

```bash
python3 scripts/delivery_preflight_check.py
python3 scripts/validate_project_configs.py
python3 -m unittest discover -s tests
```

这些检查用于阶段性交付质量保障，不等同于完整平台级质量保障体系。

## 8. 主要报告索引

- `docs/review/模糊测试模块项目要求完成证明与复现说明.md`
- `docs/review/文档类业务接口能力阶段性收口报告.md`
- `docs/review/动态异构冗余判定机制阶段性收口报告.md`
- `docs/review/NV_MAB反馈变异策略阶段性收口报告.md`
- `docs/review/NV_MAB轻量稳定性与最小消融验证报告.md`
- `docs/review/Flowable电子公文替代场景验证报告.md`
- `docs/review/Alfresco文档接口手工验证报告.md`
- `docs/review/Alfresco元数据更新接口接入验证报告.md`
- `docs/review/Alfresco内容更新接口接入验证报告.md`
- `docs/review/Alfresco上传创建接口接入验证报告.md`
- `docs/review/Alfresco_AE_v1二阶段有效性判定验证报告.md`
- `docs/review/Alfresco_AE_v1阈值校准与误判分析报告.md`
- `docs/review/Alfresco_AE_v1_score_service联调报告.md`
- `docs/review/Alfresco_AE_v1轻量API接入报告.md`
- `docs/review/Alfresco_fAnoGAN_v1候选有效性验证报告.md`
- `docs/review/Alfresco扩展样本与fAnoGAN候选二次评估报告.md`
- `docs/review/Alfresco_fAnoGAN候选劣于AE原因诊断报告.md`
- `docs/review/Alfresco_torch_fAnoGAN候选复评报告.md`
- `docs/review/Alfresco_torch_fAnoGAN阈值重校准与holdout验证报告.md`
- `docs/review/Alfresco代表性AFL++变异链路smoke报告.md`
- `docs/review/Alfresco代表性AFL++变异链路短时稳定性报告.md`
- `docs/review/Alfresco_SE-fAnoGAN-ES_online_filter原型报告.md`
- `docs/review/Alfresco_online_filter四模式消融实验报告.md`
- `docs/review/Alfresco_online_filter四模式短时稳定性报告.md`
- `docs/review/Alfresco_metadata_update_online_filter_smoke报告.md`
- `docs/review/Alfresco_metadata_update_online_filter四模式消融实验报告.md`
- `docs/review/Alfresco_metadata_update_online_filter四模式短时稳定性报告.md`
- `docs/review/v0.3.5最终工程交付状态冻结说明.md`
- `docs/review/MCP_adapter原型接入报告.md`
- `docs/review/O2OA到Alfresco主验证平台迁移说明.md`
- `docs/review/真实服务环境smoke验证报告.md`
- `docs/review/接口能力审计报告.md`

## 9. 当前不能宣称的内容

当前不能宣称：

- O2OA 原生电子公文创建/保存、内容更新接口已全覆盖；
- Flowable 替代了 O2OA；
- Alfresco 等同于 O2OA；
- 完整 SE-fAnoGAN 或完整 GAN 已完成；
- Alfresco fAnoGAN v1 candidate 已替代 AE v1；
- 完整 NC_MAB 理论闭环完成；
- 完整自动化语义种子生成完成；
- 长时间稳定性或完整论文级消融完成；
- Flowable 完整 AFL++ mutation-chain 完成；
- 所有 Alfresco 场景完整 AFL++ mutation-chain 完成；
- 完整拟态系统级动态异构冗余完成；
- 已实现完整 MCP Server；
- 完整平台 HTTP/RPC 网关服务已完成。

## 10. 后续工作

- 后续可围绕 Alfresco AE v1 扩展更多真实业务样本；当前扩展样本二次评估显示 fAnoGAN candidate 未优于 AE v1，如需推进深度 GAN / fAnoGAN，应先补充更大规模样本和误判分析；如需正式 AI Agent 集成，可在 MCP adapter prototype 基础上实现完整 MCP Server；
- 如有稳定 O2OA 写入接口环境，可补原生 O2OA 创建/更新接口；
- 如有需求，可在 Alfresco `text/plain` 内容更新和 multipart upload min_calibration 基础上扩展更长时间 fuzz；
- 如总项目提供拟态执行体环境，再做系统级 DHR；
- 当前阶段建议停止扩功能，转入集成联调和交付。
