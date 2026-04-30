# AE 136条数据集长时长验证结果

## 实验设置
- 数据集规模：136 条
- 模型模式：ae
- compare 输入：in/o2oa_body_model_compare
- 阈值：1.0
- 验证方式：rule_score-only
- 持续时间：60 秒

## 关键结果
- body_rule_pass = 156
- body_rule_reject = 1295
- body_score_pass = 99
- body_score_reject = 57
- body_score_rpc_ok = 156
- body_score_rpc_fail = 0

## 结论
说明在 136 条数据集、AE 模型和默认阈值 1.0 的配置下，长时长 rule_score-only 验证仍能稳定产生混合型 pass/reject 结果，且在线 score 服务保持稳定。该结果表明当前默认配置已具备较强的阶段性稳定性，可作为后续继续扩充数据集、开展更长时间验证或升级模型结构的默认基线。
