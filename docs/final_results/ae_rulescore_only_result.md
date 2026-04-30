# AE 模式在 rule_score-only 场景下的验证结果

## 实验设置
- 模型模式：ae
- 模型文件：model_stage/models/sefanogan_ae_model.pt
- 元信息文件：model_stage/models/sefanogan_ae_meta.json
- 输入种子集：in/o2oa_body_model_compare
- 阈值：1.0
- 运行方式：rule_score-only

## 关键结果
- body_rule_pass = 124
- body_rule_reject = 318
- body_score_pass = 83
- body_score_reject = 41
- body_score_rpc_ok = 124
- body_score_rpc_fail = 0

## 结论
说明 AE 风格占位模型已成功接入在线评分服务，并能在 AFL 驱动的 rule_score-only 场景下对通过一级规则的样本产生混合型 pass/reject 分层结果。与此前中心距离占位模型相比，AE 模型已表现出更明显的神经网络式异常检测特征，标志着项目已从启发式评分阶段推进到可训练、可部署、可在线验证的异常检测模型阶段。
