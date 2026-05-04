# Flowable 动态异构冗余 second stage 可行性审查报告

## 1. 审查目的

本报告评估 Flowable `process_start` 场景从现有 Flowable-AE v2 单阶段判定迁移到动态 second stage 的可行性。目标是形成最小迁移设计，不修改 AFL++ 主链，不修改 O2OA 已完成口径，不修改正式 `integration/platform_profiles/flowable_v2.json`，也不声称 Flowable 动态冗余已经完成。

## 2. Flowable 当前状态

审查对象：

- `integration/platform_profiles/flowable_v2.json`
- `runner/templates/task_ae_flowable_eval_v2.json`
- `scripts/run_flowable_process_start_compare.py`
- `model_stage/models/flowable_ae_v2_model.pt`
- `model_stage/models/flowable_ae_v2_meta.json`
- `docs/final_results/flowable_compare/`
- `docs/final_delivery/fuzz_component_release/flowable/`

当前 Flowable 主体状态如下：

| 项目 | 结论 |
| --- | --- |
| 当前模型 | Flowable-AE v2 |
| 当前工作阈值 | `threshold=6.3` |
| 正式 profile 是否有 `decision` 字段 | 有 |
| 正式 profile 是否启用 second stage | 否，`enable_second_stage=false` |
| 预留灰区 | `5.8 < ae_score < 6.3` |
| second stage 类型 | 预留为 `rule` |
| Flowable 数据集 | `in/flowable_process_start_dataset_v2/`，共 80 个 JSON 样本 |
| Flowable AE v2 模型 | `model_stage/models/flowable_ae_v2_model.pt` 存在 |
| Flowable AE v2 meta | `model_stage/models/flowable_ae_v2_meta.json` 存在 |
| Flowable score service | 可复用 `model_stage/nv_valid_server_real.py` 启动 AE score service，但本轮未启动验证 |
| Flowable 服务环境 | 仓库内未发现可直接启动的 compose；既有报告记录默认端口检查不能视为服务就绪 |

## 3. Flowable-AE v2 现有结果

既有 Flowable 结果来自：

- `docs/final_results/flowable_compare/flowable_ae_v2_final_result.md`
- `docs/final_results/flowable_compare/flowable_final_model_route.md`
- `docs/final_delivery/fuzz_component_release/flowable/`

已记录的 Flowable-AE v2@6.3 结果：

| 项目 | 结果 |
| --- | --- |
| 数据集 normal | 50 |
| 数据集 border | 10 |
| 数据集 abnormal | 20 |
| 数据集 total | 80 |
| 20 秒 | pass=287，reject=65，rpc_fail=0 |
| 60 秒 | pass=887，reject=181，rpc_fail=0 |

既有结论明确：第二平台有效性模型需要按平台/场景做专用校准，当前阶段不建议立即进入 Flowable-GAN。

## 4. second stage 当前是否启用

当前正式 Flowable profile：

```json
"decision": {
  "t_low": 5.8,
  "t_high": 6.3,
  "enable_second_stage": false,
  "second_stage_type": "rule",
  "second_stage_threshold": 1.0
}
```

因此 Flowable 当前未启用 second stage。灰区分支在结构上已预留，但 `DecisionEngine.decide()` 遇到 `5.8 < ae_score < 6.3` 时不会进入 `second_pass` 或 `second_reject`，而是返回未启用 second stage 的 fallback 判定。

## 5. 可复用组件判断

### DecisionEngine

可以复用。

`scripts/run_flowable_process_start_compare.py` 已经导入：

```python
from integration.decision_engine import DecisionEngine, load_profile_decision_config
```

脚本也支持通过 `NV_DECISION_PROFILE_PATH` 加载 profile decision 配置。因此最小迁移不需要改 AFL++ 主链，可以通过临时 profile 探针验证 Flowable second stage 调度。

### rule fallback

可以作为第一阶段最小迁移的优先方案。

理由：

- rule fallback 是本地结构风险函数，不依赖 GAN 服务；
- 与 Flowable 当前“先保留结构、暂不进入 GAN”的既有路线一致；
- 能最小化跨平台模型域迁移风险；
- 可以先验证 `stage=second_pass` / `stage=second_reject` 是否在 Flowable 灰区触发。

限制是：当前 rule fallback 是通用 JSON 结构风险函数，不等同于 Flowable 业务真值规则，需要后续用 Flowable 标签集定标。

### O2OA GAN socket

不建议直接复用为 Flowable GAN 结论。

O2OA GAN 已验证的范围是 O2OA `cms_doc_list` 灰区 body；Flowable 场景是 `process_start`，请求结构、字段语义、训练域、阈值分布和服务行为均不同。即使 socket 协议相同，也不能因为 O2OA GAN 可以在线运行，就声称 Flowable GAN 有效。

只有在证明以下条件后，才可考虑 Flowable GAN：

1. Flowable 与 O2OA 使用一致且可解释的输入特征；
2. GAN 训练样本覆盖 Flowable `process_start` 域；
3. Flowable 灰区样本完成独立阈值扫描；
4. Flowable 在线 smoke 出现 `second_stage_source=gan_rpc`；
5. 有 Flowable valid / invalid 标签或覆盖收益证据。

当前不具备这些证据。

## 6. 是否建议马上启用 Flowable second stage

不建议直接修改正式 `integration/platform_profiles/flowable_v2.json` 并启用。

建议先使用临时 profile 做只针对 Flowable 的 second stage 探针：

`/tmp/flowable_v2_second_stage_probe.json`

推荐临时配置基于正式 profile 复制，仅修改：

```json
"decision": {
  "t_low": 5.8,
  "t_high": 6.3,
  "enable_second_stage": true,
  "second_stage_type": "rule",
  "second_stage_threshold": 1.0
}
```

注意：这只是临时探针，不替代正式 `flowable_v2.json`。

## 7. 最小迁移路线

推荐路线分四步：

1. 保持正式 `flowable_v2.json` 不变；
2. 生成临时 profile `/tmp/flowable_v2_second_stage_probe.json`，保持 `t_low=5.8`、`t_high=6.3`，只启用 `second_stage_type=rule`；
3. 离线扫描 `in/flowable_process_start_dataset_v2/` 的 AE score，筛选 `5.8 < ae_score < 6.3` 的灰区样本；
4. 对灰区样本调用 `DecisionEngine`，确认是否出现 `stage=second_pass` / `stage=second_reject`；
5. 若 Flowable REST 服务和 Flowable-AE v2 score service 均可用，再做 20 秒 smoke；
6. smoke 通过后，再固化轻量 evidence，仍不能直接声称 Flowable 动态冗余完成；
7. 如需 GAN，必须训练或确认 Flowable 域 GAN，并完成独立阈值定标和在线验证。

## 8. 所需环境和阻塞项

当前阻塞项：

- Flowable REST 服务未被本轮确认可用；
- 仓库内未发现可直接启动 Flowable 的 compose 文件；
- Flowable-AE v2 score service 需要按 Flowable 模型单独启动；
- 尚未固化 Flowable 灰区样本清单；
- 尚未建立 Flowable valid / invalid 标签集；
- 尚未完成 Flowable rule fallback 阈值定标；
- 尚无 Flowable GAN 模型、meta、阈值扫描和在线 smoke 证据。

Flowable 最小验证需要：

- 可访问的 `FLOWABLE_BASE`；
- Flowable 认证配置通过环境变量注入，不写入报告或证据；
- Flowable-AE v2 score service；
- 临时 decision profile；
- 灰区样本列表；
- 20 秒 smoke 的 summary 与脱敏 debug evidence。

## 9. 为什么不能声称 Flowable 动态冗余完成

当前不能声称 Flowable 动态冗余完成，原因是：

- 正式 Flowable profile 中 `enable_second_stage=false`；
- 未完成 Flowable 灰区样本固定回放；
- 未看到 Flowable runtime 出现 `stage=second_pass` / `stage=second_reject` 的 evidence；
- 未完成 Flowable 真实服务 20 秒 second stage smoke；
- 未完成 Flowable second stage 的阈值定标；
- 未完成 Flowable GAN 独立验证；
- O2OA 的 GAN online 证据不能外推为 Flowable GAN 证据。

## 10. 工程结论

当前可行性判断：

- Flowable 具备迁移 second stage 的结构基础；
- `DecisionEngine` 可以复用；
- rule fallback 可以作为 Flowable 最小迁移第一阶段；
- 不建议直接复用 O2OA GAN；
- 不建议马上修改正式 Flowable profile；
- Flowable 动态异构冗余仍处于可行性审查与迁移设计阶段，不能声称完成。

推荐交付口径：

> Flowable 侧已经具备 AE v2 模型、预留 decision 结构、数据集和 DecisionEngine 接入点，具备开展 second stage 最小迁移验证的基础。下一步应先用临时 profile 启用 rule fallback 探针，筛选 Flowable 灰区样本并验证 `second_pass` / `second_reject` 路径；GAN 仅作为后续增强，不应直接复用 O2OA GAN 并声称 Flowable GAN 有效。
