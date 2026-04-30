# AE 68条数据集基线结果

## 实验设置
- 数据集规模：68 条
- 模型模式：ae
- compare 输入：in/o2oa_body_model_compare
- 阈值：1.0
- 验证方式：rule_score-only

## 关键结果
- body_rule_pass = 118
- body_rule_reject = 333
- body_score_pass = 77
- body_score_reject = 41
- body_score_rpc_ok = 118
- body_score_rpc_fail = 0

## 结论
说明在 68 条数据集、AE 模型和默认阈值 1.0 的配置下，rule_score-only 场景仍能稳定产生混合型 pass/reject 结果，且在线 score 服务保持稳定。该结果表明当前默认配置在引入更多真实 AFL 回收样本后仍具阶段性稳定性，可作为下一轮继续扩 normal 样本和延长验证时长的默认基线。
