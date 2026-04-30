# 当前默认基线说明

## 1. 默认基线配置

当前阶段推荐使用以下默认基线配置：

- 数据集规模：156 条
- 模型模式：ae
- 模型文件：`model_stage/models/sefanogan_ae_model.pt`
- 元信息文件：`model_stage/models/sefanogan_ae_meta.json`
- 默认阈值：`1.0`
- compare 输入：`in/o2oa_body_model_compare`
- 推荐验证脚本：`scripts/run_cms_body_valid_compare_real_rulescore_only.sh`

## 2. 默认基线依据

当前默认基线建立在以下结果基础上：

1. AE 模型在 train/val 划分下保持清晰分层：
   - train_normal_recon_mean = 0.030331
   - val_normal_recon_mean = 0.058080
   - val_border_recon_mean = 6.070522
   - val_abnormal_recon_mean = 477.441602

2. AE 阈值对比实验表明：
   - `0.8` 偏严格
   - `1.0` 更平衡
   - `1.5` 偏宽松

3. 在 156 条数据集下，阈值 `1.0` 的短时长验证结果为：
   - body_score_pass = 77
   - body_score_reject = 39

4. 在 156 条数据集下，阈值 `1.0` 的长时长验证结果为：
   - body_score_pass = 105
   - body_score_reject = 58
   - body_score_rpc_fail = 0

5. 在 156 条数据集下，多次随机划分结果始终满足：
   - `val_normal_mean < val_border_mean < val_abnormal_mean`

## 3. 当前阶段结论

因此，当前阶段建议将：

- `156 rows + AE + threshold=1.0 + rule_score-only`

作为当前项目默认验证基线。后续继续扩数据集、延长验证时长或升级模型结构时，应优先基于该默认基线向前推进，而不建议频繁切换模型后端、输入集和阈值配置。

## 4. 增强版实验配置说明

在当前默认基线 `156 rows + AE + threshold=1.0 + rule_score-only` 的基础上，项目进一步引入了两轮真实 AFL 中间层样本，形成了 `182 rows` 的增强版实验配置。

增强版实验配置的主要特点为：

- 数据集规模：182 条
- 在默认 normal 基线基础上增加了真实 AFL 回收的 border / abnormal-mid 样本
- 用于验证“真实中间层增强”是否能够进一步提升边界层建模效果

当前实验结果表明：

- train_normal_recon_mean = 0.041162
- val_normal_recon_mean = 0.072949
- val_border_recon_mean = 3.514370
- val_abnormal_recon_mean = 314.254991

同时在 `threshold=1.0` 下，增强版配置的 `rule_score-only` 长时长验证结果为：

- body_score_pass = 93
- body_score_reject = 60
- body_score_rpc_fail = 0

说明真实中间层增强路线有效，且未破坏现有默认链路稳定性。

但从项目文档和阶段管理角度，当前仍建议：

- 将 `156 rows + AE + threshold=1.0 + rule_score-only` 作为默认基线；
- 将 `182 rows + AE + threshold=1.0 + rule_score-only` 作为增强版实验配置。
