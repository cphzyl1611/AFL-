# 批量对比实验结果总结

## 1. 实验对象

本次批量对比实验共包含 6 次运行：

- baseline_156_run1
- baseline_156_run2
- baseline_156_run3
- enhanced_182_run1
- enhanced_182_run2
- enhanced_182_run3

其中：

- `baseline_156` 表示默认基线配置；
- `enhanced_182` 表示增强版实验配置。

## 2. baseline_156 平均结果

### 训练侧平均值
- train_normal_mean = 0.034274
- val_normal_mean = 0.062106
- val_border_mean = 5.263978
- val_abnormal_mean = 456.089910

### 验证侧平均值
- short_pass = 79.00
- short_reject = 42.33
- long_pass = 93.00
- long_reject = 61.33

## 3. enhanced_182 平均结果

### 训练侧平均值
- train_normal_mean = 0.032222
- val_normal_mean = 0.055160
- val_border_mean = 3.712541
- val_abnormal_mean = 168.484067

### 验证侧平均值
- short_pass = 78.33
- short_reject = 39.00
- long_pass = 91.33
- long_reject = 58.33

## 4. 结论

1. 两套配置在 3 次重复实验下都保持了稳定的训练侧分层关系；
2. 两套配置在短时长和长时长验证下均能稳定产生混合型 pass/reject 结果；
3. `baseline_156` 更适合作为默认项目基线；
4. `enhanced_182` 证明了真实中间层增强路线可行，可作为增强版实验配置持续使用。
