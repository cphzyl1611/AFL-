# AE 116条数据集基线结果

## 实验设置
- 数据集规模：116 条
- 模型模式：ae
- compare 输入：in/o2oa_body_model_compare
- 阈值：1.0
- 验证方式：rule_score-only

## 关键结果
- body_rule_pass = 114
- body_rule_reject = 341
- body_score_pass = 74
- body_score_reject = 40
- body_score_rpc_ok = 114
- body_score_rpc_fail = 0

## 结论
说明在 116 条数据集、AE 模型和默认阈值 1.0 的配置下，rule_score-only 场景仍能稳定产生混合型 pass/reject 结果，且在线 score 服务保持稳定。该结果表明当前默认配置在继续扩充 normal 样本后仍具阶段性稳定性，可作为后续继续扩充数据集或开展更长时长验证的默认基线。
