# v3 placeholder model 在 rule_score-only 模式下的验证结果

## 实验设置
- 模型模式：model
- 模型文件：model_stage/models/sefanogan_placeholder_model.json
- 输入种子集：in/o2oa_body_model_compare
- 阈值：20
- 运行方式：rule_score-only

## 关键结果
- body_rule_pass = 120
- body_rule_reject = 306
- body_score_pass = 112
- body_score_reject = 8
- body_score_rpc_ok = 120
- body_score_rpc_fail = 0

## 结论
说明 v3 数据集扩充与模型重训后，placeholder model 已可在平衡种子集驱动的 AFL 场景中对通过一级规则的样本产生混合型 pass/reject 分层结果，表明当前模型已具备初步筛选能力。
