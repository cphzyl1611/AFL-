# Flowable dynamic redundancy second stage probe report

## 1. 实验目的

本轮目标是做 Flowable second stage 的最小探针验证，验证 Flowable 灰区样本是否能够在临时 profile 下进入 `DecisionEngine` 的 second stage，并通过本地 rule fallback 产生 `second_pass` / `second_reject` 阶段结果。

本轮不修改 AFL++ 主链，不修改正式 `integration/platform_profiles/flowable_v2.json`，不复用 O2OA GAN，不声称 Flowable 动态冗余已经完整完成。

## 2. Flowable 当前状态

正式 profile：

`integration/platform_profiles/flowable_v2.json`

当前 decision 配置保持：

```json
{
  "t_low": 5.8,
  "t_high": 6.3,
  "enable_second_stage": false,
  "second_stage_type": "rule",
  "second_stage_threshold": 1.0
}
```

确认结果：

- Flowable-AE v2 模型存在：`model_stage/models/flowable_ae_v2_model.pt`；
- Flowable-AE v2 meta 存在：`model_stage/models/flowable_ae_v2_meta.json`；
- v2 样本目录存在：`in/flowable_process_start_dataset_v2`，80 个 JSON 样本；
- v3 样本目录存在：`in/flowable_process_start_dataset_v3`，130 个 JSON 样本；
- `scripts/run_flowable_process_start_compare.py` 已接入 `DecisionEngine`，并支持 `NV_DECISION_PROFILE_PATH`；
- 正式 Flowable profile 仍未启用 second stage。

## 3. 为什么不直接复用 O2OA GAN

O2OA GAN 已验证范围是 O2OA `cms_doc_list` 灰区 body。Flowable 场景是 `process_start`，请求结构、字段语义、训练域、阈值分布和服务行为不同。

因此本轮不配置 O2OA GAN，也不将 O2OA GAN 的有效性外推到 Flowable。Flowable 如需 GAN second stage，必须后续独立完成 Flowable 域模型、阈值扫描、在线 smoke 和标签评估。

## 4. Flowable AE score service

本轮使用 Flowable-AE v2 模型启动独立 AE score service：

```text
/tmp/nv_valid_flowable.sock
```

使用模型：

- `model_stage/models/flowable_ae_v2_model.pt`
- `model_stage/models/flowable_ae_v2_meta.json`

没有使用 O2OA AE 模型，也没有使用 O2OA GAN。

## 5. 灰区样本扫描结果

正式 Flowable 灰区：

```text
5.8 < ae_score < 6.3
```

扫描输出：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_grey_scan.csv`

扫描结果：

| dataset | total | grey |
| --- | ---: | ---: |
| v2 | 80 | 1 |
| v3 | 130 | 8 |
| total | 210 | 9 |

灰区样本数量为 9，满足最小 probe 验证需求，因此本轮没有生成轻量变异样本。

## 6. 临时 profile 说明

本轮生成临时 profile：

`/tmp/flowable_v2_second_stage_probe.json`

该 profile 从正式 `flowable_v2.json` 复制，只用于本轮探针验证。关键 decision 配置：

```json
{
  "t_low": 5.8,
  "t_high": 6.3,
  "enable_second_stage": true,
  "second_stage_type": "rule",
  "second_stage_threshold": 1.0
}
```

该 profile 不是正式 profile，不提交到仓库，不替代 `integration/platform_profiles/flowable_v2.json`。

## 7. second stage probe 结果

固定样本 probe 输出：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_second_stage_probe_results.csv`

结果汇总：

| metric | count |
| --- | ---: |
| grey samples probed | 9 |
| second_pass | 9 |
| second_reject | 0 |
| second_stage_source=local_rule | 9 |
| GAN used | 0 |

本轮最小 probe 证明：

- Flowable 灰区样本可以在临时 profile 下触发 second stage；
- rule fallback 路径可用；
- `DecisionEngine` 可被 Flowable 场景复用；
- 本轮未使用 O2OA GAN。

## Flowable 真实服务 smoke 尝试

本轮在固定样本 probe 之后追加 Flowable 真实服务环境诊断，目标是判断是否可以执行最短 20 秒真实 Flowable smoke。

诊断结果：

| check | result |
| --- | --- |
| Docker 容器 | 未发现 Flowable 容器；仅发现 O2OA 相关容器运行中 |
| 8080/8081/8082 端口 | 未发现监听 |
| Flowable compose | 未发现 `docker-compose.yml`、`compose.yml` 或可复用 Flowable compose |
| Flowable 服务启动脚本 | 未发现可直接启动 Flowable REST 服务的脚本 |
| 管理接口 | `http://127.0.0.1:8080/flowable-rest/service/management/engine` 返回 HTTP code `000`，连接失败 |
| 根路径 | `http://127.0.0.1:8080/` 返回 HTTP code `000`，连接失败 |
| REST 根路径 | `http://127.0.0.1:8080/flowable-rest/` 返回 HTTP code `000`，连接失败 |
| deployments 接口 | `http://127.0.0.1:8080/flowable-rest/service/repository/deployments` 返回 HTTP code `000`，连接失败 |

轻量诊断证据：

`docs/review/evidence/flowable_dynamic_redundancy/flowable_service_readiness_diagnostic.json`

因此 Flowable REST 服务未确认可用，本轮没有强跑真实 Flowable smoke。

未生成 Flowable smoke task_id，也未生成 runner/runs 或 runner/tasks 证据。

明确阻塞原因：

- 当前 Docker 中没有 Flowable 容器；
- `127.0.0.1:8080` 未监听；
- 仓库内没有可复用的 Flowable REST 服务启动脚本或 compose；
- Flowable REST endpoint 均连接失败；
- 因服务不可用，无法进入真实 HTTP smoke 阶段。

## Flowable second stage 真实服务 smoke

在后续环境补齐后，本轮重新检查 Flowable REST 服务并执行 20 秒真实服务 smoke。

环境确认：

- Flowable REST 管理接口已返回 HTTP `200`；
- `holidayRequest` 流程定义已存在；
- `POST /flowable-rest/service/runtime/process-instances` 可启动流程实例；
- 认证使用本地默认 Basic Auth 凭据验证，报告和 evidence 不记录明文凭据；
- Flowable-AE v2 score service 使用 `/tmp/nv_valid_flowable.sock`；
- 使用临时 profile `/tmp/flowable_v2_second_stage_probe.json`；
- 正式 `integration/platform_profiles/flowable_v2.json` 未修改，仍保持 `enable_second_stage=false`；
- 本轮未使用 O2OA GAN。

真实 smoke 结果：

| metric | value |
| --- | ---: |
| task_id | `b3de7a9854a0` |
| status | `exited` |
| duration | 20s |
| last_http_code | 201 |
| HTTP 200/201 count | 331 |
| rpc_fail_total | 0 |
| body_score_rpc_ok | 331 |
| body_score_rpc_fail | 0 |
| BODY_DECISION_DBG | 331 |
| ae_low | 0 |
| ae_high | 0 |
| second_pass | 331 |
| second_reject | 0 |
| second_stage_source=local_rule | 331 |
| rule_fallback | 0 |
| fallback_reason | `-` |
| pass | 331 |
| reject | 0 |
| crash / hang | 0 / 0 |

轻量 evidence：

- `docs/review/evidence/flowable_dynamic_redundancy/report_b3de7a9854a0_real_smoke.json`
- `docs/review/evidence/flowable_dynamic_redundancy/stdout_summary_b3de7a9854a0_real_smoke.log`
- `docs/review/evidence/flowable_dynamic_redundancy/decision_debug_excerpt_b3de7a9854a0_real_smoke.log`

结论：Flowable second stage 真实服务 smoke 已通过。当前结论可以从“固定样本 probe 通过”提升为“Flowable rule fallback second stage 真实服务 smoke 通过”。

边界仍需保留：

- 不能声称 Flowable GAN online 已完成；
- 不能声称 O2OA GAN 可直接迁移到 Flowable；
- 不能声称完整多平台动态异构冗余全部完成；
- 正式 `flowable_v2.json` 仍不启用 second stage。

## 9. 当前能否声称 Flowable 完整动态异构冗余完成

不能。

当前只能声称：

- Flowable second stage 最小固定样本探针通过；
- 临时 profile 下，灰区样本能够进入 local rule second stage；
- Flowable rule fallback second stage 真实服务 smoke 已通过；
- Flowable 具备继续做动态冗余迁移验证的基础。

不能声称：

- Flowable 动态冗余完整完成；
- Flowable GAN online 已完成；
- 完整多平台动态异构冗余已完成；
- O2OA GAN 可以直接迁移到 Flowable。

## 10. 后续路线

建议后续按以下顺序推进：

1. 继续保持正式 `flowable_v2.json` 不变；
2. 固化更多 Flowable 灰区样本；
3. 建立 Flowable valid / invalid 标签集；
4. 对 rule fallback 阈值做 Flowable 域定标；
5. 在更长时间和更多样本上重复 Flowable 真实服务 smoke；
6. 如需 GAN，先训练或确认 Flowable 域 GAN，再做独立阈值扫描和在线验证。

## 11. 结论

本轮完成 Flowable second stage 最小探针验证，并在 Flowable REST 服务可用后完成 20 秒真实服务 smoke。验证范围限定为临时 rule fallback profile，不包含 Flowable GAN，不改变正式 profile。
