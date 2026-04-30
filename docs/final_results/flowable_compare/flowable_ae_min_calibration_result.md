# Flowable-AE 最小校准结果

## 1. 平台与场景
- 平台：Flowable
- 场景：process start
- 接口：POST /flowable-rest/service/runtime/process-instances

## 2. 最小校准数据集
- normal = 30
- border = 10
- abnormal = 10
- total = 50

## 3. Flowable-AE 训练结果
- train_normal_recon_mean = 0.001182
- val_normal_recon_mean = 0.057161
- val_border_recon_mean = 87.169789
- val_abnormal_recon_mean = 21.458226

## 4. 当前工作阈值
- threshold = 12.4

## 5. 混合集评估结果
- 20 秒：pass = 259，reject = 95，rpc_fail = 0
- 60 秒：pass = 784，reject = 282，rpc_fail = 0

## 6. 当前结论
1. O2OA 平台训练得到的 AE 不能直接迁移到 Flowable；
2. 经过最小数据集校准后，Flowable-AE 已经恢复出混合型 pass/reject；
3. 这说明有效性模型需要按平台/场景做轻量校准；
4. 当前建议先固定 Flowable-AE@12.4，不急于进入 Flowable-GAN。
