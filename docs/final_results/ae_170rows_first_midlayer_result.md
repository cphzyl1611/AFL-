# AE 170条数据集第一轮真实中间层增强结果

## 实验设置
- 数据集规模：170 条
- 新增样本：第一批真实 AFL 中间层样本（border + abnormal-mid）
- 模型模式：ae
- 阈值：1.0
- 验证方式：rule_score-only
- 持续时间：60 秒

## 关键结果
- body_rule_pass = 159
- body_rule_reject = 1293
- body_score_pass = 98
- body_score_reject = 61
- body_score_rpc_ok = 159
- body_score_rpc_fail = 0

## 训练侧分层结果
- train_normal_recon_mean = 0.032800
- val_normal_recon_mean = 0.076877
- val_border_recon_mean = 4.003929
- val_abnormal_recon_mean = 312.238398

## 结论
说明在 156 条稳定 normal 基线基础上引入第一批真实 AFL 中间层样本后，AE 模型的正常 / 边界 / 异常分层关系仍然保持，且 rule_score-only 的短时长和长时长验证均保持稳定。该结果表明“真实中间层增强”路线可行，可进入下一轮样本回收与筛选。
