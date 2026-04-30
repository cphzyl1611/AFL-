# GAN v2@1.7 旧版与 ab9010 标定版最终比较结论

## 1. 对比对象
- 旧版：GAN v2 @ 1.7
- 新版：GAN v2 @ 1.7 + alpha=0.90 + beta=0.10

## 2. 旧版 GAN v2 @ 1.7 平均结果
- train_normal_mean = 0.426030
- val_normal_mean = 0.367059
- val_border_mean = 1.509427
- val_abnormal_mean = 5.465204
- 20 秒：pass = 57.67，reject = 45.33，rpc_fail = 0.00
- 60 秒：pass = 82.00，reject = 57.33，rpc_fail = 0.00

## 3. ab9010 标定版平均结果
- train_normal_mean = 0.406244
- val_normal_mean = 0.335390
- val_border_mean = 1.348456
- val_abnormal_mean = 5.070270
- 20 秒：pass = 80.33，reject = 37.33，rpc_fail = 0.00
- 60 秒：pass = 103.00，reject = 53.67，rpc_fail = 0.00

## 4. 最终结论
1. ab9010 标定版在 20 秒与 60 秒验证中均优于旧版 GAN v2 @ 1.7；
2. ab9010 标定版在保持 rpc_fail=0 的前提下，实现了更高 pass 和更低 reject；
3. 因此，GAN v2 的研究增强口径应由“旧 t17”正式更新为“t17_ab9010”；
4. 当前仍建议 AE 保持默认模型，GAN v2(t17_ab9010) 作为新的研究增强模型继续推进。
