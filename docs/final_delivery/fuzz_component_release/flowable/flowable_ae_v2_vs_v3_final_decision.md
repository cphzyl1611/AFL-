# Flowable-AE v2 与 v3 最终比较结论

## 1. 对比对象
- Flowable-AE v2 @ 6.3
- Flowable-AE v3 @ 6.6

## 2. v2 结果
- 20 秒：pass = 287，reject = 65，rpc_fail = 0
- 60 秒：pass = 887，reject = 181，rpc_fail = 0

## 3. v3 结果
- 20 秒：pass = 283，reject = 68，rpc_fail = 0
- 60 秒：pass = 870，reject = 199，rpc_fail = 0

## 4. 最终结论
1. v3 已经证明可训练、可运行、可定阈值；
2. 但从当前 20/60 结果看，v3 未优于 v2；
3. 因此当前第二平台最终口径仍保留为 Flowable-AE v2 @ 6.3；
4. v3 保留为后续数据整理与再训练参考版本，不作为当前最终工作口径。
