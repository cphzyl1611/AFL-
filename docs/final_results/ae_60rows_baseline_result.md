# AE 60条数据集基线结果

## 实验设置
- 数据集规模：60 条
- 模型模式：ae
- compare 输入：in/o2oa_body_model_compare
- 阈值：1.0
- 验证方式：rule_score-only

## 关键结果
- body_rule_pass = 113
- body_rule_reject = 341
- body_score_pass = 75
- body_score_reject = 38
- body_score_rpc_ok = 113
- body_score_rpc_fail = 0

## 结论
说明在 60 条数据集重训后，AE 模型在默认阈值 1.0 下仍能稳定产生混合型 pass/reject 结果，表明当前默认配置具备阶段性稳定性，可作为后续继续扩数据集和延长验证时长的基线版本。
