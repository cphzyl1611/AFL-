# Flowable second stage formal enable candidate review

## 1. 评审目的

本报告用于对 Flowable `flowable_rule_v1` second stage 是否可以进入正式启用候选进行工程评审。

本轮不跑新实验，不修改 AFL++ 主链，不修改正式 `integration/platform_profiles/flowable_v2.json`，不修改 O2OA 配置，不训练 GAN。

## 2. 当前 Flowable rule_v1 已完成证据

已完成证据包括：

- Flowable-AE v2 接入；
- Flowable fixed sample second stage probe；
- `flowable_rule_v1` 固定标签集回放；
- `flowable_rule_v1` 多轮真实 smoke；
- `flowable_rule_v1` 扩样本与多流程 key 覆盖验证。

核心扩展验证结果：

| 项目 | 结果 |
| --- | --- |
| 扩展标签集规模 | 84 |
| valid / invalid / uncertain | 28 / 42 / 14 |
| 覆盖 processDefinitionKey | 7 个 |
| fixed replay pass / reject | 42 / 42 |
| invalid_pass | 0 |
| valid_reject | 0 |
| 多轮 smoke | 3 轮 20s + 1 轮 60s |
| task_id | `9ff3b520f0fd`、`e2a017131bd7`、`c1322fcdb523`、`182a4ee1e838` |
| second_pass / second_reject | 308/39、309/39、310/39、928/116 |
| rpc_fail_total | 均为 0 |
| HTTP | 均为 200/201 |
| crash / hang | 未观察到 |

关键 evidence：

- `docs/review/Flowable_rule_v1_extended_validation_report.md`
- `docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_extended_validation/flowable_rule_v1_extended_summary.csv`
- `docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_extended_validation/multirun/flowable_rule_v1_extended_multirun_summary.csv`

## 3. 为什么可以进入正式启用候选

`flowable_rule_v1` 可以进入正式启用候选，原因如下：

1. 它是显式 opt-in 的 Flowable 专用规则，不影响 O2OA 的 GAN second stage 路径；
2. 扩展固定回放覆盖 84 条样本和 7 个真实流程定义 key；
3. 扩展固定回放中 `invalid_pass=0`，显著优于旧 `local_rule`；
4. 扩展固定回放中 `valid_reject=0`，未观察到 valid 样本被规则误拒；
5. 多轮真实 smoke 中 `flowable_rule_v1` 稳定进入 runtime；
6. 多轮真实 smoke 均满足 `rpc_fail_total=0`，HTTP 末态为 201，未观察到 crash / hang。

因此，工程上可以把 `flowable_rule_v1` 作为 Flowable second stage 正式启用候选进行下一轮评审和受控验证。

## 4. 为什么仍不建议直接修改正式 flowable_v2.json

暂不建议直接修改正式 `integration/platform_profiles/flowable_v2.json`。

理由：

- 当前标签集规模仍有限，尚不足以覆盖复杂 Flowable 业务输入空间；
- 当前规则主要覆盖 process start 通用结构和少量流程变量约束；
- `createTimersProcess` 在本地 REST 回放中出现 5xx，说明服务行为仍需独立分析；
- 尚未完成覆盖收益、延迟影响、长期稳定性和误拒成本评估；
- Flowable-GAN 未完成，不能把 local rule 候选结论扩展为 Flowable GAN online 结论；
- 正式启用应经过候选 profile、灰度运行和可回滚发布流程。

## 5. 正式启用需要满足的前置条件

正式启用前建议至少满足：

1. 候选 profile 在受控环境中完成更大样本回放；
2. 覆盖更多流程定义 key 和变量 schema；
3. 明确各流程的必需变量、可选变量和类型约束；
4. 对 HTTP 5xx 样本进行服务侧原因归因；
5. 完成更长时长、多轮次真实 smoke；
6. 补充覆盖率收益、执行吞吐、延迟影响和误拒成本指标；
7. 完成正式 profile 变更评审和回滚预案；
8. 确认 O2OA profile 与 O2OA GAN online 路径不受影响。

## 6. 启用风险

主要风险：

- valid 样本误拒：更严格的 schema 可能拒绝真实业务可接受的边界输入；
- 流程差异风险：不同 processDefinitionKey 的变量要求可能不同；
- 服务侧差异风险：本地 REST 行为不能完全代表其他部署环境；
- 维护风险：流程定义更新后，白名单和变量约束需要同步更新；
- 观测风险：如果只看 HTTP 2xx/4xx，可能无法准确区分业务可接受性和规则过滤有效性；
- 结论外推风险：local rule 有效不等于 Flowable-GAN 完成，也不等于完整强多平台动态异构冗余完成。

## 7. 回滚策略

推荐回滚策略：

1. 保持正式 `flowable_v2.json` 当前 `enable_second_stage=false` 作为基线；
2. 候选阶段仅通过显式 profile 选择启用 `flowable_rule_v1`；
3. 如出现误拒、服务异常、RPC 异常或业务回归，立即切回正式 `flowable_v2.json`；
4. 保留 run summary、decision debug excerpt 和 HTTP 状态用于追溯；
5. 将新增流程 key 或变量约束作为可审查配置变更，而不是临时改代码。

## 8. 推荐候选 profile 策略

新增候选 profile 示例：

`integration/platform_profiles/flowable_rule_v1_formal_candidate.example.json`

该 profile：

- 保持 `t_low=5.8`、`t_high=6.3`；
- 设置 `enable_second_stage=true`；
- 设置 `second_stage_type=flowable_rule`；
- 保留 `flowable_rule_v1` 白名单、root 字段和变量类型约束；
- 明确标注为正式启用候选，不是默认正式 profile；
- 不替代 `integration/platform_profiles/flowable_v2.json`。

## 9. 后续必须补充的验证

后续必须补充：

1. 更大规模 valid / invalid / uncertain 标签集；
2. 更多流程定义 key 和变量 schema；
3. 针对 `createTimersProcess` 等 5xx 样本的服务侧原因分析；
4. 长时多轮真实 smoke；
5. 覆盖率收益与吞吐、延迟影响；
6. 误拒样本人工复核流程；
7. 候选 profile 灰度启用和回滚演练；
8. Flowable-GAN 独立模型、阈值定标和在线验证。

## 10. 最终评审结论

评审结论：

- 可以建议：`flowable_rule_v1` 进入 Flowable second stage 正式启用候选；
- 不建议：直接修改正式 `integration/platform_profiles/flowable_v2.json`；
- 不能声称：正式 `flowable_v2.json` 已启用 second stage；
- 不能声称：Flowable-GAN 已完成；
- 不能声称：完整强多平台动态异构冗余全部完成。

当前最稳妥路线是：保留正式 `flowable_v2.json` 不变，新增候选 profile 示例，并在下一轮受控灰度验证中评估是否具备正式启用条件。
