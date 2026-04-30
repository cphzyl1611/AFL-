# AE 182条数据集第二阶段真实中间层增强结果

## 实验设置
- 数据集规模：182 条
- 新增样本：第二轮真实 AFL 中间层样本（border + abnormal-mid）
- 模型模式：ae
- 阈值：1.0
- 验证方式：rule_score-only
- 持续时间：60 秒

## 关键结果
- body_rule_pass = 153
- body_rule_reject = 1313
- body_score_pass = 93
- body_score_reject = 60
- body_score_rpc_ok = 153
- body_score_rpc_fail = 0

## 训练侧分层结果
- train_normal_recon_mean = 0.041162
- val_normal_recon_mean = 0.072949
- val_border_recon_mean = 3.514370
- val_abnormal_recon_mean = 314.254991

## 结论
说明在 156 条稳定 normal 基线基础上，连续引入两轮真实 AFL 中间层样本后，AE 模型的正常 / 边界 / 异常分层关系仍然保持，且 rule_score-only 的短时长与长时长验证均保持稳定。该结果表明“真实中间层增强”路线有效，可作为下一阶段评估与材料整理的实验增强版基线。