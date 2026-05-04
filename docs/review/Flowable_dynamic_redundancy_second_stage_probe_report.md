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

## 8. 真实 Flowable smoke

本轮检查本地 Flowable REST 管理接口，结果为连接失败，HTTP code 记录为 `000`。因此 Flowable 服务未确认可用，本轮没有强跑真实 Flowable smoke。

未生成 Flowable smoke task_id，也未生成 runner/runs 或 runner/tasks 证据。

## 9. 当前能否声称 Flowable 动态冗余完成

不能。

当前只能声称：

- Flowable second stage 最小固定样本探针通过；
- 临时 profile 下，灰区样本能够进入 local rule second stage；
- Flowable 具备继续做动态冗余迁移验证的基础。

不能声称：

- Flowable 动态冗余完整完成；
- Flowable 真实服务 second stage smoke 已完成；
- Flowable GAN online 已完成；
- 多平台动态异构冗余已完成；
- O2OA GAN 可以直接迁移到 Flowable。

## 10. 后续路线

建议后续按以下顺序推进：

1. 准备可用的 Flowable REST 服务环境；
2. 继续保持正式 `flowable_v2.json` 不变；
3. 固化更多 Flowable 灰区样本；
4. 建立 Flowable valid / invalid 标签集；
5. 对 rule fallback 阈值做 Flowable 域定标；
6. 使用临时 profile 做 20 秒 Flowable smoke；
7. 如需 GAN，先训练或确认 Flowable 域 GAN，再做独立阈值扫描和在线验证。

## 11. 结论

本轮完成 Flowable second stage 最小探针验证。验证范围限定为固定灰区样本 + 临时 rule fallback profile，不包含真实 Flowable smoke，不包含 GAN，不改变正式 profile。
