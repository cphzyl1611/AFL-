# 项目复现实验流程说明

## 1. 目标

本文档用于说明当前项目中两套主要实验配置的复现方式：

1. 默认基线：
   - `156 rows + AE + threshold=1.0 + rule_score-only`
2. 增强版实验配置：
   - `182 rows + AE + threshold=1.0 + rule_score-only`

本文档覆盖：

- 数据集生成
- 特征导出
- 数据集划分
- AE 模型训练
- 在线 score 服务启动
- 短时长 / 长时长验证
- 结果文件位置
- 通过标准

---

## 2. 环境要求

建议在项目根目录下，并确保 Python 虚拟环境已激活：

```bash
cd ~/AFLplusplus
source venv/bin/activate
```

很好，关键对比表已经落下来了，说明第二阶段结果归档已经成型。

你现在下一步就该做我前面说的最关键那份：

# 标准复现实验流程文档

新建：

* `docs/project_docs/repro_runbook.md`

这份文档的作用很大，它会把你的项目从“你自己会跑”变成“别人照着也能复现”。

## 3. 默认基线（156 rows）复现流程

### 3.1 数据集准备

默认基线对应的标准数据集规模为：

* 156 条

先确认 `build_dataset.py` 中未加入第二阶段新增的真实中间层增强样本，或者准备一份专门的 156 rows 版本清单。

然后执行：

```bash
cd ~/AFLplusplus
python3 model_stage/build_dataset.py
```

确认输出数据集规模为：

* `156 rows`

### 3.2 特征导出、划分与训练

执行：

```bash
cd ~/AFLplusplus
python3 model_stage/export_features.py
python3 model_stage/split_dataset.py
python3 model_stage/sefanogan_train_ae.py
```

训练完成后，重点查看：

* `model_stage/models/sefanogan_ae_model.pt`
* `model_stage/models/sefanogan_ae_meta.json`

### 3.3 启动在线 score 服务

执行：

```bash
cd ~/AFLplusplus
export SEFANOGAN_MODE=ae
export SEFANOGAN_MODEL_PATH=$PWD/model_stage/models/sefanogan_ae_model.pt
export SEFANOGAN_AE_META_PATH=$PWD/model_stage/models/sefanogan_ae_meta.json

python3 nv_valid_server_real.py
```

若服务正常，将监听本地 Unix Socket。

### 3.4 短时长验证（20 秒）

另开终端，执行：

```bash
cd ~/AFLplusplus
export NV_TOKEN='你的token'
export NV_BODY_SCORE_ENDPOINT='unix:///tmp/nv_valid_real.sock'
export NV_BODY_SCORE_THRESHOLD='1.0'
export NV_DEBUG_BODY_VALID=1

IN_DIR=$HOME/AFLplusplus/in/o2oa_body_model_compare DUR=20 ./scripts/run_cms_body_valid_compare_real_rulescore_only.sh
```

验证结束后查看：

```bash
cat ~/AFLplusplus/out/cms_body_valid_compare_real/summary.csv
cat /tmp/nv_body_valid_stats.json
```

### 3.5 长时长验证（60 秒）

执行：

```bash
cd ~/AFLplusplus
export NV_TOKEN='你的token'
export NV_BODY_SCORE_ENDPOINT='unix:///tmp/nv_valid_real.sock'
export NV_BODY_SCORE_THRESHOLD='1.0'
export NV_DEBUG_BODY_VALID=1

IN_DIR=$HOME/AFLplusplus/in/o2oa_body_model_compare DUR=60 ./scripts/run_cms_body_valid_compare_real_rulescore_only.sh
```

验证结束后查看：

```bash
cat ~/AFLplusplus/out/cms_body_valid_compare_real/summary.csv
cat /tmp/nv_body_valid_stats.json
```

### 3.6 默认基线通过标准

默认基线复现时，建议至少满足以下条件：

1. 训练侧仍保持：
   * `train_normal < val_normal < val_border << val_abnormal`
2. 短时长验证满足：
   * `body_score_pass > 0`
   * `body_score_reject > 0`
   * `body_score_rpc_fail = 0`
3. 长时长验证满足：
   * `body_score_pass > 0`
   * `body_score_reject > 0`
   * `body_score_rpc_fail = 0`

---

## 4. 增强版实验配置（182 rows）复现流程

### 4.1 数据集准备

增强版实验配置对应数据集规模为：

* 182 条

要求 `build_dataset.py` 中包含两轮真实 AFL 中间层样本。

执行：

```bash
cd ~/AFLplusplus
python3 model_stage/build_dataset.py
```

确认输出数据集规模为：

* `182 rows`

### 4.2 特征导出、划分与训练

执行：

```bash
cd ~/AFLplusplus
python3 model_stage/export_features.py
python3 model_stage/split_dataset.py
python3 model_stage/sefanogan_train_ae.py
```

训练完成后查看：

* `model_stage/models/sefanogan_ae_model.pt`
* `model_stage/models/sefanogan_ae_meta.json`

### 4.3 启动在线 score 服务

执行：

```bash
cd ~/AFLplusplus
export SEFANOGAN_MODE=ae
export SEFANOGAN_MODEL_PATH=$PWD/model_stage/models/sefanogan_ae_model.pt
export SEFANOGAN_AE_META_PATH=$PWD/model_stage/models/sefanogan_ae_meta.json

python3 nv_valid_server_real.py
```

### 4.4 短时长验证（20 秒）

另开终端执行：

```bash
cd ~/AFLplusplus
export NV_TOKEN='你的token'
export NV_BODY_SCORE_ENDPOINT='unix:///tmp/nv_valid_real.sock'
export NV_BODY_SCORE_THRESHOLD='1.0'
export NV_DEBUG_BODY_VALID=1

IN_DIR=$HOME/AFLplusplus/in/o2oa_body_model_compare DUR=20 ./scripts/run_cms_body_valid_compare_real_rulescore_only.sh
```

### 4.5 长时长验证（60 秒）

执行：

```bash
cd ~/AFLplusplus
export NV_TOKEN='你的token'
export NV_BODY_SCORE_ENDPOINT='unix:///tmp/nv_valid_real.sock'
export NV_BODY_SCORE_THRESHOLD='1.0'
export NV_DEBUG_BODY_VALID=1

IN_DIR=$HOME/AFLplusplus/in/o2oa_body_model_compare DUR=60 ./scripts/run_cms_body_valid_compare_real_rulescore_only.sh
```

### 4.6 增强版实验配置通过标准

建议满足以下条件：

1. 训练侧仍保持：
   * `train_normal < val_normal < val_border << val_abnormal`
2. 短时长验证满足：
   * `body_score_pass > 0`
   * `body_score_reject > 0`
   * `body_score_rpc_fail = 0`
3. 长时长验证满足：
   * `body_score_pass > 0`
   * `body_score_reject > 0`
   * `body_score_rpc_fail = 0`

---

## 5. 主要结果文件位置

### 默认基线相关

* `docs/final_results/ae_156rows_baseline_result.md`
* `docs/final_results/ae_156rows_dur60_result.md`
* `docs/final_results/ae_split_stability_156rows.md`

### 增强版实验配置相关

* `docs/final_results/ae_182rows_second_midlayer_result.md`

### 对比分析相关

* `docs/final_results/baseline_156_vs_enhanced_182.md`
* `docs/final_results/stage2_compare/baseline_vs_enhanced_metrics.csv`
* `docs/final_results/stage2_compare/stage2_evaluation_summary.md`

### 当前项目口径文档

* `docs/project_docs/current_default_baseline.md`
* `docs/project_docs/current_stage_final_summary.md`

---

## 6. 当前推荐使用方式

当前推荐采用“两层配置”方式管理项目：

### 默认项目口径

* 使用 `156 rows + AE + threshold=1.0 + rule_score-only`

### 增强实验口径

* 使用 `182 rows + AE + threshold=1.0 + rule_score-only`

前者用于日常汇报与长期引用，后者用于展示真实 AFL 中间层增强效果。

---

## 7. 下一阶段建议

在完成当前复现流程固化后，下一阶段建议优先进行：

1. 更规范的 `156 rows` 与 `182 rows` 对比分析；
2. 汇报材料与阶段总结整理；
3. 视需要再决定是否开展第三轮真实中间层增强或模型结构升级。
   EOF

```

---

# 然后确认文件

执行：

```bash
ls -l docs/project_docs/repro_runbook.md
```
