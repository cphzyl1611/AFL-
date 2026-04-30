# 真实 score 服务骨架验证结果

## 验证目标
验证基于 `feature_extract.py` 与 `score_json_offline.py` 封装得到的在线服务骨架 `model_stage/nv_valid_server_real.py` 是否能够在 AFL 驱动的批量实验场景下稳定工作。

## 验证方式
采用最小 AFL 复现实验，对 `in/o2oa_body_cms_score/` 中样本进行短时间 fuzz，二级 score 服务使用：

- socket: unix:///tmp/nv_valid_real.sock
- 阈值: 1.5

## 关键结果
- body_rule_pass = 109
- body_rule_reject = 342
- body_score_pass = 63
- body_score_reject = 46
- body_score_rpc_ok = 109
- body_score_rpc_fail = 0

## 结论
说明 `nv_valid_server_real.py` 已可在 AFL 驱动的批量场景下稳定处理请求，并能对通过一级规则的样本产生 pass / reject 分层效果。当前该服务已具备替代旧 mock score 服务的能力。后续仅需将 `score_from_features(feat)` 替换为真实 SE-fAnoGAN-ES 推理，即可完成真实模型后端接入。
