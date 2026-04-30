# AE 与 GAN v2@1.5 固定对比结论

## 1. 对比对象

- AE 默认口径：baseline_156
- GAN v2@1.5 研究增强口径：baseline_156

## 2. 训练侧对比

### AE
- train_normal_mean = 0.034274
- val_normal_mean = 0.062106
- val_border_mean = 5.263978
- val_abnormal_mean = 456.089910

### GAN v2@1.5
- train_normal_mean = 0.423767
- val_normal_mean = 0.344221
- val_border_mean = 1.619760
- val_abnormal_mean = 5.590230

## 3. 验证侧对比

### AE
- 20 秒：pass = 79.00，reject = 42.33，rpc_fail = 0.00
- 60 秒：pass = 93.00，reject = 61.33，rpc_fail = 0.00

### GAN v2@1.5
- 20 秒：pass = 45.67，reject = 72.33，rpc_fail = 0.00
- 60 秒：pass = 61.33，reject = 101.33，rpc_fail = 0.00

## 4. 当前判断

1. AE 仍然是当前更稳的默认模型；
2. GAN v2@1.5 已具备稳定研究推进条件，但当前仍未整体超过 AE；
3. GAN 后续优化应重点围绕“降低 reject 偏高问题”和“继续改善训练侧正常样本分布关系”展开；
4. 当前不建议用 GAN v2@1.5 替代 AE 默认模型，但建议继续作为研究增强主线推进。
