# Flowable rule v1 formal enable change review package

## 1. 变更背景

Flowable 已完成 AE + `flowable_rule_v1` second stage 的多阶段验证，包括固定标签集回放、多轮真实 smoke、扩样本与多流程 key 覆盖验证、正式启用候选评审和受控灰度验证。

本评审包用于把已有证据整理为正式启用变更评审材料。当前只生成评审文档，不修改正式 `integration/platform_profiles/flowable_v2.json`，不修改 O2OA 配置，不训练 GAN，也不把 O2OA GAN 复用到 Flowable。

## 2. 当前正式基线

当前 Flowable 正式基线为：

- profile：`integration/platform_profiles/flowable_v2.json`
- `t_low=5.8`
- `t_high=6.3`
- `enable_second_stage=false`
- `second_stage_type=rule`
- `second_stage_threshold=1.0`

该基线保留 Flowable-AE v2 第一阶段能力，并预留 decision 结构，但正式 profile 尚未启用 second stage。

## 3. 候选变更内容

候选 profile 为：

`integration/platform_profiles/flowable_rule_v1_formal_candidate.example.json`

候选变更内容：

- 保持 `t_low=5.8`、`t_high=6.3`；
- 保持 `second_stage_threshold=1.0`；
- 将 `enable_second_stage` 从 `false` 调整为 `true`；
- 将 `second_stage_type` 从通用 `rule` 调整为 `flowable_rule`；
- 使用 Flowable 专用 `flowable_rule_v1`；
- 保留 `allowed_process_definition_keys` 和 Flowable process start 结构约束；
- 继续不使用 O2OA GAN，不声称 Flowable-GAN 已完成。

## 4. 已完成证据

### 固定标签集回放

- 样本规模：36
- old local rule pass / reject：35 / 1
- `flowable_rule_v1` pass / reject：16 / 20
- old `invalid_pass=19`
- new `invalid_pass=0`
- `valid_reject=0`

证据：

- `docs/review/Flowable_rule_v1_second_stage_validation_report.md`
- `docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_validation/`

### 多轮真实 smoke

- 轮次：3 轮 20s + 1 轮 60s
- task_id：`26a0a386e8b3`、`38c6c245a87b`、`428493bb37c2`、`9132783c9ea1`
- second_pass / second_reject：304/38、309/39、310/39、932/117
- `rpc_fail_total` 均为 0
- HTTP 均为 200/201
- 未观察到 crash / hang

证据：

- `docs/review/Flowable_rule_v1_multirun_smoke_report.md`
- `docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_multirun/`

### 扩样本与多流程 key 覆盖验证

- 扩展标签集规模：84
- valid / invalid / uncertain：28 / 42 / 14
- 覆盖 processDefinitionKey：`holidayRequest`、`oneTaskProcess`、`vacationRequest`、`createTimersProcess`、`fixSystemFailure`、`escalationExample`、`reviewSaledLead`
- fixed replay pass / reject：42 / 42
- `invalid_pass=0`
- `valid_reject=0`
- 多轮 smoke task_id：`9ff3b520f0fd`、`e2a017131bd7`、`c1322fcdb523`、`182a4ee1e838`
- `rpc_fail_total` 均为 0
- HTTP 均为 200/201

证据：

- `docs/review/Flowable_rule_v1_extended_validation_report.md`
- `docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_extended_validation/`

### 受控灰度验证

- baseline 4 轮：3 轮 20s + 1 轮 60s
- candidate 4 轮：3 轮 20s + 1 轮 60s
- baseline task_id：`9b2519c51f3d`、`971ca3367121`、`be394bb7b263`、`03c3035a32a9`
- candidate task_id：`843cefc1623a`、`17b1c997f48a`、`3487ac322ab9`、`16547e55b10f`
- candidate second_pass / second_reject：309/39、308/39、310/39、934/117
- `rpc_fail_total` 均为 0
- candidate HTTP 均为 201
- 未观察到 crash / hang
- candidate 稳定进入 `flowable_rule_v1` runtime

证据：

- `docs/review/Flowable_rule_v1_gray_validation_report.md`
- `docs/review/evidence/flowable_dynamic_redundancy/flowable_rule_v1_gray_validation/`

## 5. 是否满足正式启用前置条件

当前满足进入正式 profile 变更评审的主要前置条件：

- 候选规则为 Flowable 专用，不影响 O2OA GAN online 路径；
- 已完成固定标签集回放，且未观察到 valid 样本误拒；
- 扩展验证覆盖 84 条样本、7 个流程 key 和多类 invalid 输入；
- 扩展固定回放中 `invalid_pass=0`、`valid_reject=0`；
- 多轮真实 smoke 和受控灰度验证均满足 `rpc_fail_total=0`；
- candidate 在真实服务路径中稳定进入 `flowable_rule_v1` runtime；
- 未观察到 crash / hang；
- 已有候选 profile 示例和回滚基线。

仍需在正式启用前补充或评审：

- 更长时间灰度运行；
- 业务误拒样本人工复核；
- 吞吐、延迟和覆盖收益指标；
- 回滚演练；
- 部署环境差异复核；
- 正式 profile 变更单独 commit 与审批。

## 6. 风险分析

主要风险：

- 业务误拒风险：更严格的结构规则可能拒绝某些边界但业务可接受的请求；
- 流程差异风险：不同 processDefinitionKey 的变量 schema 可能随部署变化；
- 环境差异风险：本地 Tomcat Docker REST 行为不一定覆盖所有生产环境差异；
- 维护风险：流程定义更新后，白名单和变量约束需要同步维护；
- 观测不足风险：当前灰度 evidence 未覆盖完整长期吞吐、延迟和覆盖收益；
- 结论外推风险：`flowable_rule_v1` 通过不等于 Flowable-GAN 已完成，也不等于完整强多平台动态异构冗余全部完成。

## 7. 回滚方案

推荐回滚方案：

1. 正式启用前保留 `integration/platform_profiles/flowable_v2.json` 的当前基线；
2. 若后续正式启用产生业务误拒、RPC 异常、HTTP 异常、crash / hang 或运行指标异常，立即恢复 `enable_second_stage=false`；
3. 回滚后使用同一批灰度任务和 summary CSV 对比恢复效果；
4. 保留 candidate profile 和 evidence 用于追溯，不将失败样本写入正式数据目录；
5. 对误拒样本进行结构规则归因，再决定是否调整候选规则或继续保持禁用。

## 8. 变更影响范围

候选变更影响范围：

- 仅影响显式使用 Flowable profile 的 process start 判定路径；
- 仅影响 AE score 落入灰区 `5.8 < ae_score < 6.3` 的样本；
- 对低分直接 pass 和高分直接 reject 的第一阶段行为不应产生影响；
- 不影响 O2OA `o2oa_default.json`；
- 不影响 O2OA GAN online second stage；
- 不代表 Flowable-GAN online 完成。

## 9. 推荐变更策略

推荐策略：

1. 本轮只提交评审包和拟变更说明；
2. 保持正式 `flowable_v2.json` 不变；
3. 将 `flowable_rule_v1_formal_candidate.example.json` 作为正式启用候选；
4. 进入正式 profile 变更评审下一阶段；
5. 下一阶段单独提交 profile 变更 PR/commit，并绑定回滚方案；
6. 正式启用后继续进行受控灰度和业务误拒复核。

## 10. 是否建议立即修改正式 flowable_v2.json

不建议本轮立即修改正式 `integration/platform_profiles/flowable_v2.json`。

理由：

- 本轮目标是生成变更评审包，不是执行正式启用；
- 正式 profile 启用应是单独可审查、可回滚的变更；
- 仍需补充更长时灰度、吞吐/延迟、业务误拒和回滚演练；
- 当前结论支持进入变更评审，不支持绕过评审直接落入默认正式配置。

## 11. 是否建议进入正式 profile 变更 PR/commit

建议进入正式 profile 变更 PR/commit 的评审准备阶段。

建议条件：

- PR/commit 只修改 `integration/platform_profiles/flowable_v2.json` 的 second stage 启用字段；
- 同时附带本评审包和拟变更 diff 说明；
- 保留一键回滚说明；
- 合并前完成业务误拒复核和更长时灰度；
- 合并后继续监控 `rpc_fail_total`、HTTP 2xx、second_pass / second_reject、crash / hang。

## 12. 后续验收条件

后续正式启用验收建议至少包括：

- 正式 profile 启用 commit 可独立回滚；
- `enable_second_stage=true` 后多轮真实 smoke 仍满足 `rpc_fail_total=0`；
- HTTP 200/201 稳定，无 crash / hang；
- `flowable_rule_v1` 稳定进入 runtime；
- valid 样本误拒经过人工复核且处于可接受范围；
- invalid_pass 保持显著低于旧 local rule；
- 吞吐、延迟和覆盖收益无不可接受回退；
- O2OA GAN online 路径不受影响。

## 13. 结论边界

可以写：

- `flowable_rule_v1` 可以进入正式 profile 变更评审；
- `flowable_rule_v1` 已完成扩样本、多流程 key、多轮 smoke 和受控灰度验证；
- 本轮建议准备正式启用 PR/commit。

不能写：

- 正式 `flowable_v2.json` 已启用 second stage；
- 本轮已经修改正式 Flowable profile；
- Flowable-GAN 已完成；
- O2OA GAN 可以直接迁移到 Flowable；
- 完整强多平台动态异构冗余全部完成。
