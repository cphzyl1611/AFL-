# Alfresco_AE_v1二阶段有效性判定验证报告

## 1. 背景

Alfresco 已作为后续主验证平台，当前三类标准文档接口均已有真实 smoke evidence：

- metadata update；
- text/plain content update；
- multipart upload 创建/保存。

本轮在不重跑 Alfresco 服务、不启动长时间 fuzz 的前提下，补充 Alfresco AE v1 工程化二阶段有效性判定链路，用于对三类文档接口输入进行统一 rule + score 判定。

## 2. 为什么先做 AE v1 而不是 GAN

当前阶段优先目标是形成稳定、可复现、可纳入 CI/本地检查的二阶段有效性判定链路。GAN / fAnoGAN 需要更多训练样本、模型训练配置和稳定评估口径，当前不适合作为最小工程闭环。

因此本轮先实现 Alfresco AE v1 engineering scorer，即基于特征均值、标准差和归一化距离的 AE-like statistical baseline。该实现用于阶段性有效性判定，不宣称完整 SE-fAnoGAN 或完整深度 AE。

## 3. 特征设计

新增特征抽取模块：

```text
model_stage/alfresco_feature_extractor.py
```

三类输入统一映射到固定长度向量：

- metadata update：字段数量、`name`、`properties`、标题长度、描述长度、类型异常计数等；
- text/plain content update：字节长度、字符长度、行数、可打印比例、中文字符比例、空白比例、熵、NUL 字节、UTF-8 合法性等；
- multipart upload：文件名长度、`.txt` 后缀、内容大小、`nodeType=cm:content`、`autoRename=true`、`filedata` 存在性，并复用文本内容特征。

## 4. 模型/score 设计

新增构建脚本：

```text
scripts/build_alfresco_ae_v1.py
```

输出：

```text
model_stage/models/alfresco_ae_v1_meta.json
```

当前模型类型：

```text
model_type=ae_like_statistical_baseline
```

训练来源为三类 Alfresco 合法/边界 seed，共 9 个样本。score 采用 root mean square z-distance：

```text
score = sqrt(mean(((x - mean) / std)^2))
```

本轮 meta 关键字段：

```text
model_name=alfresco_ae_v1
model_type=ae_like_statistical_baseline
train_sample_count=9
scenario_coverage.metadata_update=3
scenario_coverage.content_update=3
scenario_coverage.multipart_upload=3
threshold_low=0.933776
threshold_high=1.623614
```

## 5. profile

新增 profile：

```text
integration/platform_profiles/alfresco_ae_v1.json
```

关键配置：

```text
validation_scope=standard_document_platform_ae_v1
decision.enable_second_stage=true
decision.second_stage_type=ae_v1
decision.model_meta=model_stage/models/alfresco_ae_v1_meta.json
```

## 6. summary 结果

本轮本地 score compare 输出：

```text
out/alfresco_ae_v1_score_compare/summary.csv
out/alfresco_ae_v1_score_compare/details.csv
```

summary 关键字段：

```text
mode=rule_score
nv_total_valid_exec=12
nv_err_exec=0
nv_err_rate=0.000000
saved_hangs=0
saved_crashes=0
last_http_code=0
body_rule_pass=9
body_rule_reject=3
body_score_pass=9
body_score_reject=3
body_score_rpc_ok=12
body_score_rpc_fail=0
summary_source=python_static_loop
execution_scope=alfresco_ae_v1_score_min_calibration
```

## 7. details 结果

逐 seed 结果概况：

- metadata update：`seed_ok_0.json`、`seed_ok_1.json`、`seed_border_0.json` 通过；`seed_bad_0.json` 规则拒绝；
- content update：`seed_ok_0.txt`、`seed_ok_1.txt`、`seed_border_0.txt` 通过；`seed_bad_0.txt` 规则拒绝；
- multipart upload：`seed_ok_0.txt`、`seed_ok_1.txt`、`seed_border_0.txt` 通过；`seed_bad_0.txt` 规则拒绝。

3 个预设非法样本均不计为主链失败。details 中保留 `ae_score`、`ae_pass`、`decision`、`reason` 和 `feature_vector`。

## 8. 阶段性结论

当前已完成 Alfresco AE v1 工程化二阶段有效性判定最小闭环。该链路可对 Alfresco metadata update、text/plain content update、multipart upload 三类输入执行统一特征抽取、规则过滤和 AE-like score 判定。

该结果可支撑后续 Alfresco score profile 和更完整的二阶段判定联调。

## 9. 边界

- 这是 Alfresco AE v1 工程化二阶段有效性判定；
- 不等同于完整 SE-fAnoGAN；
- 不等同于完整 GAN；
- 不等同于 O2OA 原生接口覆盖；
- 不是完整 AFL++ mutation-chain；
- 不是系统级 DHR；
- 当前 scorer 是 AE-like statistical baseline，不宣称完整深度 AE 模型训练已完成。
