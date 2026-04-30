# Flowable-AE v2@6.3 最终结果

## 1. 平台与场景
- 平台：Flowable
- 场景：process start
- 接口：POST /flowable-rest/service/runtime/process-instances

## 2. v2 数据集
- normal = 50
- border = 10
- abnormal = 20
- total = 80

## 3. 训练侧结果
- train_normal_recon_mean = 0.003447
- val_normal_recon_mean = 0.017804
- val_border_recon_mean = 1.924386
- val_abnormal_recon_mean = 238.717620

## 4. 运行时真实分数定标
- normal: min = 4.414, max = 6.205
- border: min = 3.912, max = 17.397
- abnormal: min = 0.613, max = 4577.829

## 5. 当前工作阈值
- threshold = 6.3

## 6. v2 混合集评估结果
- 20 秒：pass = 287，reject = 65，rpc_fail = 0
- 60 秒：pass = 887，reject = 181，rpc_fail = 0

## 7. 最终结论
1. Flowable-AE v2@6.3 已恢复稳定混合型 pass/reject；
2. 第二平台有效性模型需要按平台/场景做专用校准；
3. 阈值必须依据服务侧真实分数定标，不能直接用训练侧 recon 值猜测；
4. 当前阶段不建议立即进入 Flowable-GAN；
5. 下一步优先考虑继续扩 normal 样本并细化 border，而不是继续扫阈值。
