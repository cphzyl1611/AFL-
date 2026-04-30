# Flowable-AE@12.4 重复实验最终结论

## 1. 平台与场景
- 平台：Flowable
- 场景：process start
- 接口：POST /flowable-rest/service/runtime/process-instances

## 2. 最小校准数据集
- normal = 30
- border = 10
- abnormal = 10
- total = 50

## 3. 训练侧结果
- train_normal_mean = 0.001182
- val_normal_mean = 0.057161
- val_border_mean = 87.169789
- val_abnormal_mean = 21.458226

## 4. 当前工作阈值
- threshold = 12.4

## 5. 3 次重复实验结果

### run1
- 20 秒：pass = 259，reject = 92，rpc_fail = 0
- 60 秒：pass = 784，reject = 282，rpc_fail = 0

### run2
- 20 秒：pass = 260，reject = 97，rpc_fail = 0
- 60 秒：pass = 784，reject = 286，rpc_fail = 0

### run3
- 20 秒：pass = 260，reject = 97，rpc_fail = 0
- 60 秒：pass = 786，reject = 286，rpc_fail = 0

## 6. 平均结果
- 20 秒：pass = 259.67，reject = 95.33，rpc_fail = 0.00
- 60 秒：pass = 784.67，reject = 284.67，rpc_fail = 0.00

## 7. 最终结论
1. Flowable-AE@12.4 已经具备稳定工作条件；
2. O2OA 上训练得到的有效性模型不能直接迁移到 Flowable；
3. 第二平台需要做小规模平台专用校准；
4. 当前阶段不建议立即进入 Flowable-GAN；
5. 下一步优先考虑扩 normal 样本和整理 border 样本，而不是继续扫阈值。
