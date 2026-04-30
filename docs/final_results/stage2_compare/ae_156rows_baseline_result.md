# AE 156条数据集基线结果

## 实验设置
- 数据集规模：156 条
- 模型模式：ae
- compare 输入：in/o2oa_body_model_compare
- 阈值：1.0
- 验证方式：rule_score-only
- 持续时间：20 秒

## 关键结果
- body_rule_pass = 116
- body_rule_reject = 335
- body_score_pass = 77
- body_score_reject = 39
- body_score_rpc_ok = 116
- body_score_rpc_fail = 0

## 结论
说明在 156 条数据集、AE 模型和默认阈值 1.0 的配置下，短时长 rule_score-only 验证能够稳定产生混合型 pass/reject 结果，且在线 score 服务保持稳定。
