# 真实 score 服务骨架 compare 流程验证结果

## 验证对象
- 接口：cms_doc_list
- 服务：model_stage/nv_valid_server_real.py
- 特征层：model_stage/feature_extract.py
- 离线评分层：model_stage/score_json_offline.py
- 阈值：1.5

## 关键结果
- body_rule_pass = 233
- body_rule_reject = 2650
- body_score_pass = 114
- body_score_reject = 119
- body_score_rpc_ok = 233
- body_score_rpc_fail = 0

## 结论
说明真实 score 服务骨架已成功接回标准 compare 流程，并可在自动 fuzz 场景下稳定处理二级评分请求，产生 pass / reject 分层结果。后续仅需将 score_from_features(feat) 替换为真实 SE-fAnoGAN-ES 模型推理，即可完成真实模型后端接入。
