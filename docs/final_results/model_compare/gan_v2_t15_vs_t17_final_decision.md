# GAN v2 阈值 1.5 与 1.7 最终比较结论

## 1. 对比对象

- GAN v2 @ 1.5
- GAN v2 @ 1.7

## 2. GAN v2 @ 1.5 平均结果

### 训练侧
- train_normal_mean = 0.423767
- val_normal_mean = 0.344221
- val_border_mean = 1.619760
- val_abnormal_mean = 5.590230

### 验证侧
- 20 秒：pass = 45.67，reject = 72.33，rpc_fail = 0.00
- 60 秒：pass = 61.33，reject = 101.33，rpc_fail = 0.00

## 3. GAN v2 @ 1.7 平均结果

### 训练侧
- train_normal_mean = 0.426030
- val_normal_mean = 0.367059
- val_border_mean = 1.509427
- val_abnormal_mean = 5.465204

### 验证侧
- 20 秒：pass = 57.67，reject = 45.33，rpc_fail = 0.00
- 60 秒：pass = 82.00，reject = 57.33，rpc_fail = 0.00

## 4. 最终结论

1. GAN v2 @ 1.7 在 20 秒和 60 秒验证中均明显优于 GAN v2 @ 1.5；
2. GAN v2 @ 1.7 在保持 rpc_fail=0 的前提下，实现了更高 pass 和更低 reject；
3. 因此，后续研究增强口径应由 GAN v2 @ 1.5 更新为 GAN v2 @ 1.7；
4. 当前仍建议 AE 保持默认模型，GAN v2 @ 1.7 作为研究增强模型继续推进。
