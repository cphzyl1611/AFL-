# 当前阶段最终总结

## 1. 当前阶段总体定位

本阶段围绕 O2OA `cms_doc_list` 接口的二级 body score 能力建设，完成了从启发式评分、中心距离占位模型到 AE 风格占位模型的阶段性演进，建立了从数据集构建、特征抽取、模型训练、统一预测接口、在线 score 服务到 AFL `rule_score-only` 验证的完整链路。

与前期“证明链路能跑通”的目标不同，当前阶段的核心工作分成两个连续子阶段：

1. 以补充 `normal` 样本为主，建立稳定默认基线；
2. 在稳定默认基线基础上，引入真实 AFL 中间层样本，验证边界层增强是否有效。

## 2. 第一阶段：默认基线构建（156 rows）

### 2.1 数据集扩充与 normal 基线建立

第一阶段主要围绕 `normal` 样本扩充展开，将数据集逐步扩充到 156 条，并持续保持 `normal / border / abnormal` 三层结构。

截至第一阶段收口时，数据集规模为：

- 数据集规模：156 条

在该阶段中，AE 模型训练与验证结果为：

- train_normal_count = 79
- val_normal_count = 34
- val_border_count = 20
- val_abnormal_count = 23

重建误差均值为：

- train_normal_recon_mean = 0.030331
- val_normal_recon_mean = 0.058080
- val_border_recon_mean = 6.070522
- val_abnormal_recon_mean = 477.441602

说明第一阶段已经形成清晰分层关系：

> train_normal < val_normal << val_border << val_abnormal

### 2.2 默认阈值确定

结合前期阈值对比实验以及第一阶段 train/val 分层结果，阈值 `1.0` 继续表现为最平衡的默认工作阈值：

- 高于 `val_normal_recon_mean`
- 明显低于 `val_border_recon_mean`

因此，第一阶段默认阈值仍确定为：

> `1.0`

### 2.3 第一阶段默认基线验证

在 `156 rows + AE + threshold=1.0 + rule_score-only` 配置下，已完成短时长与长时长验证。

#### 短时长验证
- body_rule_pass = 116
- body_rule_reject = 335
- body_score_pass = 77
- body_score_reject = 39
- body_score_rpc_ok = 116
- body_score_rpc_fail = 0

#### 长时长验证（60 秒）
- body_rule_pass = 163
- body_rule_reject = 1281
- body_score_pass = 105
- body_score_reject = 58
- body_score_rpc_ok = 163
- body_score_rpc_fail = 0

说明第一阶段默认基线在短时长与长时长场景下都能够稳定产生混合型 pass/reject 结果，并保持在线 score 服务稳定。

### 2.4 第一阶段稳定性分析

在 `156 rows` 数据集下，多次随机种子划分结果分别为：

- `20260319`: val_normal = 0.073306, val_border = 3.577930, val_abnormal = 398.261070
- `20260320`: val_normal = 0.088393, val_border = 6.791559, val_abnormal = 269.022717
- `20260321`: val_normal = 0.043257, val_border = 4.116919, val_abnormal = 287.413081

三次结果均满足：

> val_normal_mean < val_border_mean < val_abnormal_mean

因此，第一阶段可以正式收口为：

> `156 rows + AE + threshold=1.0 + rule_score-only`

作为当前项目的默认验证基线。

## 3. 第二阶段：真实中间层增强实验（182 rows）

### 3.1 阶段目标

第二阶段不再继续大量补充 `normal` 样本，而是转向从真实 AFL 日志中回收：

- `0.2 ~ 2` 的边界样本
- `2 ~ 20` 的中异常样本

目标是验证：在第一阶段稳定默认基线基础上，加入真实中间层样本后，是否能够进一步增强边界层建模，同时不破坏原有分层与判定链路稳定性。

### 3.2 数据集增强

第二阶段共引入两轮真实 AFL 中间层样本，新增内容主要为：

- 结构仍完整但存在轻中度值层偏移的 `border` 样本
- 保留业务骨架、但具有多点扰动的 `abnormal-mid` 样本

增强后数据集规模变为：

- 数据集规模：182 条

### 3.3 第二阶段训练结果

在 `182 rows` 数据集下，训练与验证结果为：

- train_normal_count = 79
- val_normal_count = 34
- val_border_count = 32
- val_abnormal_count = 37

重建误差均值为：

- train_normal_recon_mean = 0.041162
- val_normal_recon_mean = 0.072949
- val_border_recon_mean = 3.514370
- val_abnormal_recon_mean = 314.254991

说明在引入两轮真实中间层样本后，AE 模型仍保持清晰分层关系：

> train_normal < val_normal < val_border << val_abnormal

这表明真实中间层增强并未破坏现有 normal 基线，且边界层仍稳定处于中间位置。

### 3.4 第二阶段验证结果

在 `182 rows + AE + threshold=1.0 + rule_score-only` 配置下，已完成短时长与长时长验证。

#### 短时长验证
- body_rule_pass = 124
- body_rule_reject = 330
- body_score_pass = 82
- body_score_reject = 42
- body_score_rpc_ok = 124
- body_score_rpc_fail = 0

#### 长时长验证（60 秒）
- body_rule_pass = 153
- body_rule_reject = 1313
- body_score_pass = 93
- body_score_reject = 60
- body_score_rpc_ok = 153
- body_score_rpc_fail = 0

说明第二阶段在加入真实中间层样本后，`rule_score-only` 链路仍保持稳定，在线服务未出现异常。

### 3.5 第二阶段结论

第二阶段结果说明：

- 真实 AFL 中间层样本回收路线有效；
- 引入两轮真实中间层样本后，模型分层关系仍保持；
- 短时长与长时长验证仍稳定；
- 边界层建模得到了增强，而未破坏现有默认链路。

因此，可以将：

> `182 rows + AE + threshold=1.0 + rule_score-only`

定义为当前项目的增强版实验配置。

## 4. 当前阶段最重要的技术结论

综合两个阶段的结果，可以得出以下结论：

### 结论 1：AE 路线已经成为当前项目稳定主线
相比前期占位模型，AE 模型已经表现出清晰、稳定且可验证的正常 / 边界 / 异常分层能力，并能够在实际 AFL 驱动场景中稳定运行。

### 结论 2：默认基线与增强版实验配置应分层管理
当前项目已经形成两层清晰口径：

- 默认基线：`156 rows + AE + threshold=1.0 + rule_score-only`
- 增强版实验配置：`182 rows + AE + threshold=1.0 + rule_score-only`

其中前者适合作为默认项目口径，后者适合作为边界增强实验口径。

### 结论 3：真实中间层增强路线已被验证有效
连续两轮真实 AFL 中间层样本增强后，模型训练侧分层与验证侧 pass/reject 关系均保持稳定，说明下一阶段可以继续围绕真实中间层样本开展更系统的实验设计与材料整理。

## 5. 当前推荐使用方式

### 默认项目基线
推荐统一使用：

- 数据集：156 条
- 模型：ae
- 阈值：1.0
- 输入：`in/o2oa_body_model_compare`
- 验证：`rule_score-only`

### 增强版实验配置
在需要体现“真实中间层增强效果”时，可使用：

- 数据集：182 条
- 模型：ae
- 阈值：1.0
- 输入：`in/o2oa_body_model_compare`
- 验证：`rule_score-only`

## 6. 下一阶段最优先任务

下一阶段不建议继续盲目加样本，而应优先围绕当前两层配置开展更系统工作：

1. 整理项目材料，明确默认基线与增强版实验配置的关系；
2. 做更规范的 `156 rows` 与 `182 rows` 对比分析；
3. 视需要再决定是否开展第三轮真实样本增强或模型结构升级。

## 7. 当前阶段总结语

当前阶段已成功完成两步关键推进：

1. 建立了以 `156 rows + AE + threshold=1.0 + rule_score-only` 为核心的默认验证基线；
2. 在该基线基础上引入两轮真实 AFL 中间层样本，形成 `182 rows` 的增强版实验配置，并验证其仍保持稳定。

说明项目已从“原型模型可运行”推进到“默认基线稳定 + 增强实验可验证”的状态。后续工作将从继续堆样本，转向更规范的对比分析、实验组织和项目材料整理。
