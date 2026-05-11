# Flowable电子公文替代场景验证报告

## 背景与目的

由于当前本地实验环境中 O2OA 电子公文创建/保存和内容更新接口复现不稳定，本阶段使用 Flowable 构建流程型电子公文替代场景，用于最小校准数据、规则和 profile 的静态准备。

该场景只用于 Flowable REST JSON 最小校准和替代验证准备，不表示 Flowable 原生具备电子公文接口，也不表示 Flowable 替代了 O2OA 原生电子公文接口。

## 创建/保存映射

电子公文创建与保存动作映射为启动 `documentProcess` 流程实例。

REST 映射为：

```text
POST /flowable-rest/service/runtime/process-instances
```

静态 seed 使用 Flowable process start body，核心字段包括 `processDefinitionKey=documentProcess`、`businessKey`、`returnVariables=true` 和 `variables`。其中 `variables` 承载 `docTitle`、`docContent`、`drafter`、`department`、`securityLevel`、`docStatus` 等公文字段。

本地批量 smoke summary：

```text
nv_total_valid_exec=4
nv_err_exec=0
nv_err_rate=0.000000
last_http_code=201
body_rule_pass=3
body_rule_reject=1
body_score_rpc_ok=4
body_score_rpc_fail=0
execution_scope=flowable_document_create_min_calibration
```

结论：创建/保存替代场景批量 smoke 通过。

## 内容更新映射

电子公文内容更新动作映射为流程实例变量更新。

REST 映射为：

```text
PUT /flowable-rest/service/runtime/process-instances/{processInstanceId}/variables
```

静态 seed 使用 Flowable process variables update body，即变量数组。变量数组承载 `docTitle`、`docContent`、`modifyReason`、`docStatus` 等更新字段。

本地批量 smoke summary：

```text
nv_total_valid_exec=4
nv_err_exec=1
nv_err_rate=0.250000
last_http_code=201
body_rule_pass=3
body_rule_reject=1
body_score_rpc_ok=4
body_score_rpc_fail=0
execution_scope=flowable_document_update_min_calibration
```

逐 seed 定位结果：

| seed | start_http | update_http | 结果 |
| --- | --- | --- | --- |
| `seed_bad_0.json` | 201 | 400 | Flowable 返回 `Bad request` / `Converter can only convert strings` |
| `seed_border_0.json` | 201 | 201 | 更新成功 |
| `seed_ok_0.json` | 201 | 201 | 更新成功 |
| `seed_ok_1.json` | 201 | 201 | 更新成功 |

结论：内容更新主链可用，1 个异常来自预设非法样本 `seed_bad_0.json`，符合负样本验证预期。

## 当前边界

当前是 Flowable 建模的流程型电子公文替代场景，不是 O2OA 原生电子公文接口覆盖。

当前是 `python_static_loop` / `min_calibration` 验证，不是完整 AFL++ mutation-chain 执行。

本报告不宣称 Flowable-GAN 完成，不宣称 Flowable 完整 AFL++ mutation-chain 完成，也不宣称完整拟态系统级动态异构冗余完成。

## 验证状态

- `documentProcess` 已成功部署到 Flowable。
- 查询 `process-definitions?key=documentProcess` 可看到 `documentProcess`。
- 创建/保存替代场景批量 smoke 已通过。
- 内容更新替代场景主链可用，预设非法样本按负样本预期被拒绝。

## 后续工作

如果后续要求严格对齐 6.3 章节或 O2OA 原生电子公文接口能力，仍需补充 O2OA 原生创建/保存和内容更新接口的可复现实验路径。
