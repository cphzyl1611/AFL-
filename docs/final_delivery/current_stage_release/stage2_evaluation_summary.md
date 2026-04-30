# 第二阶段评估总结

## 1. 评估对象

本阶段对两套配置进行了统一比较：

- 默认基线：156 rows + AE + threshold=1.0 + rule_score-only
- 增强版实验配置：182 rows + AE + threshold=1.0 + rule_score-only

## 2. 训练侧结果

### 默认基线（156 rows）
- train_normal_recon_mean = 0.030331
- val_normal_recon_mean = 0.058080
- val_border_recon_mean = 6.070522
- val_abnormal_recon_mean = 477.441602

### 增强版实验配置（182 rows）
- train_normal_recon_mean = 0.041162
- val_normal_recon_mean = 0.072949
- val_border_recon_mean = 3.514370
- val_abnormal_recon_mean = 314.254991

## 3. 验证侧结果

### 默认基线（156 rows）
- 短时长：pass=77, reject=39
- 长时长：pass=105, reject=58
- rpc_fail=0

### 增强版实验配置（182 rows）
- 短时长：pass=82, reject=42
- 长时长：pass=93, reject=60
- rpc_fail=0

## 4. 结论

1. 两套配置均保持 `val_normal < val_border < val_abnormal` 的分层关系；
2. 两套配置在短时长与长时长场景下均保持稳定的 pass/reject 混合结果；
3. 默认基线 156 rows 更适合作为项目长期引用的标准口径；
4. 增强版实验配置 182 rows 证明了真实 AFL 中间层增强路线有效；
5. 当前项目已进入“默认基线稳定 + 增强实验可验证”的阶段。

## 5. 当前建议

- 默认汇报口径使用 156 rows；
- 需要体现增强效果时补充说明 182 rows；
- 下一阶段优先完善复现实验流程与结果展示，而不是继续加样本。
