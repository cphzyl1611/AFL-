# Flowable 第二平台最终模型路线

## 1. 当前结论
当前第二平台最终工作口径为：

- 模型：Flowable-AE v2
- 阈值：6.3

## 2. 选择依据

### Flowable-AE v2 @ 6.3
- 20 秒：pass = 287，reject = 65，rpc_fail = 0
- 60 秒：pass = 887，reject = 181，rpc_fail = 0

### Flowable-AE v3 @ 6.6
- 20 秒：pass = 283，reject = 68，rpc_fail = 0
- 60 秒：pass = 870，reject = 199，rpc_fail = 0

## 3. 最终判断
1. v3 已经证明数据扩展、模型训练与阈值定标流程可行；
2. 但当前结果未优于 v2；
3. 因此当前第二平台最终口径仍保留为 Flowable-AE v2 @ 6.3；
4. v3 作为后续数据整理与模型再训练参考版本保留。

## 4. 阶段性建议
1. 当前阶段不进入 Flowable-GAN；
2. 当前阶段不继续扩展第三平台；
3. 第二平台到此收口。
