# 默认基线与增强版实验配置对比分析

## 1. 对比目的

为明确当前项目中“默认基线”和“增强版实验配置”的定位差异，本节对以下两套配置进行对比分析：

- 默认基线：`156 rows + AE + threshold=1.0 + rule_score-only`
- 增强版实验配置：`182 rows + AE + threshold=1.0 + rule_score-only`

其中，默认基线主要用于描述项目当前最稳定、最干净、最适合长期引用的标准配置；增强版实验配置则用于验证在默认基线基础上引入真实 AFL 中间层样本后，边界层建模能力是否得到增强，以及整体链路是否仍保持稳定。

## 2. 两套配置定义

### 2.1 默认基线（156 rows）

默认基线配置如下：

- 数据集规模：156 条
- 模型模式：ae
- 默认阈值：1.0
- compare 输入：`in/o2oa_body_model_compare`
- 验证方式：`rule_score-only`

该配置是在完成以补充 `normal` 样本为主的数据扩充后形成的阶段收口版本，具有以下特点：

- `normal` 样本分布更完整；
- train/val 分层关系清晰；
- 短时长与长时长验证结果稳定；
- 多次随机划分稳定性分析成立。

因此，该配置被确定为当前项目的默认验证基线。

### 2.2 增强版实验配置（182 rows）

增强版实验配置如下：

- 数据集规模：182 条
- 模型模式：ae
- 默认阈值：1.0
- compare 输入：`in/o2oa_body_model_compare`
- 验证方式：`rule_score-only`

该配置是在默认基线 156 条数据集基础上，进一步引入两轮真实 AFL 中间层样本后形成的实验增强版本，新增样本主要包括：

- 结构仍完整、但存在轻中度偏移的 `border` 样本；
- 保留业务骨架、但具有多点扰动的 `abnormal-mid` 样本。

该配置主要用于验证“真实中间层增强”路线是否有效。

## 3. 训练侧分层结果对比

### 3.1 默认基线（156 rows）

训练与验证结果为：

- train_normal_recon_mean = 0.030331
- val_normal_recon_mean = 0.058080
- val_border_recon_mean = 6.070522
- val_abnormal_recon_mean = 477.441602

说明默认基线下 AE 模型形成了清晰分层关系：

> train_normal < val_normal << val_border << val_abnormal

### 3.2 增强版实验配置（182 rows）

训练与验证结果为：

- train_normal_recon_mean = 0.041162
- val_normal_recon_mean = 0.072949
- val_border_recon_mean = 3.514370
- val_abnormal_recon_mean = 314.254991

同样保持了清晰分层关系：

> train_normal < val_normal < val_border << val_abnormal

### 3.3 对比分析

从训练侧结果看：

1. `156 rows` 配置下，`val_border_recon_mean` 和 `val_abnormal_recon_mean` 更高，层次差距较大，适合作为“干净且稳定”的默认基线；
2. `182 rows` 配置下，引入真实中间层样本后，`val_border_recon_mean` 更靠近中间层，说明边界层建模更贴近真实 fuzz 产生的中间态样本；
3. `182 rows` 配置下，`val_normal_recon_mean` 虽略高于 `156 rows`，但仍保持在低位，并未破坏 normal 基线。

因此可以认为：

- `156 rows` 更适合作为稳定默认基线；
- `182 rows` 更适合作为边界层增强后的实验配置。

## 4. 短时长验证结果对比

### 4.1 默认基线（156 rows，20 秒）

- body_score_pass = 77
- body_score_reject = 39
- body_score_rpc_fail = 0

### 4.2 增强版实验配置（182 rows，20 秒）

- body_score_pass = 82
- body_score_reject = 42
- body_score_rpc_fail = 0

### 4.3 对比分析

从短时长结果看：

- 两套配置都能稳定产生混合型 pass/reject 结果；
- 两套配置下 RPC 均保持稳定；
- `182 rows` 的 pass/reject 规模略高，但整体关系没有失衡。

这说明引入真实中间层样本后，短时长 `rule_score-only` 链路仍保持稳定。

## 5. 长时长验证结果对比

### 5.1 默认基线（156 rows，60 秒）

- body_score_pass = 105
- body_score_reject = 58
- body_score_rpc_fail = 0

### 5.2 增强版实验配置（182 rows，60 秒）

- body_score_pass = 93
- body_score_reject = 60
- body_score_rpc_fail = 0

### 5.3 对比分析

从长时长结果看：

- 两套配置均保持稳定的 pass/reject 混合关系；
- 两套配置均未出现 RPC 故障；
- `182 rows` 配置下 reject 稍高，但整体仍保持稳定区间。

说明在长时长场景下，真实中间层增强并未破坏现有链路。

## 6. 为什么保留 156 作为默认基线，而不是直接切换到 182

虽然 `182 rows` 配置在实验上证明了真实中间层增强路线有效，但当前仍建议将 `156 rows` 作为默认基线，而将 `182 rows` 作为增强版实验配置，原因如下：

1. `156 rows` 是以补充 `normal` 样本为主完成收口的标准版本，数据结构更干净、口径更统一；
2. `156 rows` 已完成 train/val 分层、短时长验证、长时长验证和多次划分稳定性分析，是最适合长期引用的基线；
3. `182 rows` 的核心价值在于验证“真实中间层增强是否可行”，更适合作为实验增强口径，而非直接替代默认基线；
4. 将两者分层管理，更有利于后续汇报、对比分析和材料写作。

因此，推荐的项目口径应为：

- 默认基线：`156 rows + AE + threshold=1.0 + rule_score-only`
- 增强版实验配置：`182 rows + AE + threshold=1.0 + rule_score-only`

## 7. 当前阶段结论

综合训练侧与验证侧结果，可以得出以下结论：

1. 当前项目已建立稳定默认基线；
2. 在默认基线基础上引入真实 AFL 中间层样本后，增强版实验配置仍保持稳定；
3. 真实中间层增强路线已被验证有效，但当前仍应保持“默认基线”和“增强版实验配置”两层管理方式。

## 8. 下一阶段建议

下一阶段建议不再盲目继续加样本，而应优先开展以下工作：

1. 继续整理项目材料，明确默认基线与增强版实验配置之间的关系；
2. 基于 `156 rows` 与 `182 rows` 开展更规范的对比分析；
3. 视需要再决定是否开展第三轮真实中间层增强或模型结构升级。

## 9. 总结语

当前项目已从“先建立稳定基线”推进到“在稳定基线基础上验证增强路线”的阶段。`156 rows` 提供了默认基线，`182 rows` 提供了增强版实验配置，两者共同构成了当前项目最重要的实验与工程基础。
