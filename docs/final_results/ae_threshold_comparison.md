# AE 阈值对比实验结果

## 1. 实验目的

为评估 AE 模型在不同阈值下的筛选行为，本阶段在相同工程配置下，对阈值 `0.8`、`1.0` 和 `1.5` 进行了 `rule_score-only` 对比实验。

实验设置保持一致：

- 模型模式：ae
- 输入种子集：`in/o2oa_body_model_compare`
- 验证方式：`scripts/run_cms_body_valid_compare_real_rulescore_only.sh`

## 2. 实验结果

### 阈值 0.8
- body_rule_pass = 117
- body_rule_reject = 333
- body_score_pass = 76
- body_score_reject = 41
- body_score_rpc_ok = 117
- body_score_rpc_fail = 0

### 阈值 1.0
- body_rule_pass = 119
- body_rule_reject = 332
- body_score_pass = 85
- body_score_reject = 34
- body_score_rpc_ok = 119
- body_score_rpc_fail = 0

### 阈值 1.5
- body_rule_pass = 115
- body_rule_reject = 327
- body_score_pass = 91
- body_score_reject = 24
- body_score_rpc_ok = 115
- body_score_rpc_fail = 0

## 3. 结果分析

从对比结果看，AE 模型在不同阈值下表现出清晰且符合预期的变化趋势：

1. 阈值越低，筛选越严格，拒绝样本越多；
2. 阈值越高，筛选越宽松，放行样本越多；
3. 三组实验中 `body_score_rpc_fail` 始终为 0，说明 AE 在线服务在阈值对比过程中保持稳定。

具体来看：

- 阈值 `0.8` 时，模型表现偏严格，更强调异常拦截；
- 阈值 `1.5` 时，模型表现偏宽松，更强调样本放行；
- 阈值 `1.0` 时，pass/reject 关系更居中，兼顾一定筛选能力与放行能力。

## 4. 阶段结论

综合当前数据规模、平衡种子集验证结果和 train/val 分层情况，当前阶段建议将：

- `1.0` 作为 AE 模型默认工作阈值；
- `0.8` 作为偏严格备选阈值；
- `1.5` 作为偏宽松备选阈值。

这说明 AE 模型不仅能够在线工作，而且其筛选强度已具备一定可调性和可解释性，能够为后续更大规模数据集和更正式模型结构提供良好基础。
