# 当前阶段交付索引

## 1. 当前阶段定位

当前阶段已完成从启发式评分、中心距离占位模型到 AE 风格占位模型的演进，并建立了从数据集、特征抽取、模型训练、统一预测接口、在线 score 服务到 AFL `rule_score-only` 验证的完整链路。

当前阶段最核心的成果是：AE 模型已在平衡种子集驱动的 `rule_score-only` 场景下获得混合型 pass/reject 结果，说明项目已进入“小样本神经网络异常检测模型”阶段。

## 2. 建议优先阅读顺序

### 第一层：先看总体说明
1. `docs/project_docs/current_engineering_status.md`
2. `docs/project_docs/model_evolution_plan.md`

### 第二层：再看阶段结果
3. `docs/final_results/model_comparison_summary.md`
4. `docs/final_results/ae_rulescore_only_result.md`
5. `docs/final_results/ae_score_distribution_note.md`

### 第三层：需要复现时再看
6. `docs/project_docs/targets文件设置.md`
7. `docs/project_docs/validity文件设置.md`
8. `docs/project_docs/最终复现命令清单.md`

## 3. 当前推荐主入口

### 数据集维护
- `model_stage/build_dataset.py`
- `model_stage/export_features.py`

### 模型训练
- 中心距离模型：`model_stage/sefanogan_train.py`
- AE 模型：`model_stage/sefanogan_train_ae.py`

### 在线服务
- `model_stage/nv_valid_server_real.py`

### 当前推荐验证入口
- 手工样本验证：`nv_http_harness.py`
- score 分布观测：`scripts/run_cms_score_observe_real.sh`
- AE / model 验证：`scripts/run_cms_body_valid_compare_real_rulescore_only.sh`

## 4. 当前关键模型文件

- `model_stage/models/sefanogan_placeholder_model.json`
- `model_stage/models/sefanogan_ae_model.pt`
- `model_stage/models/sefanogan_ae_meta.json`

## 5. 当前关键数据文件

- `model_stage/data/sefanogan_dataset.jsonl`
- `model_stage/data/sefanogan_features.csv`
- `model_stage/data/sefanogan_features_summary.json`

## 6. 当前关键结果文件

- `docs/final_results/model_rulescore_only_v3_result.md`
- `docs/final_results/ae_rulescore_only_result.md`
- `docs/final_results/model_comparison_summary.md`
- `docs/final_results/ae_score_distribution_note.md`

## 7. 当前推荐 compare 输入

- `in/o2oa_body_model_compare`

该目录是当前阶段更适合的平衡种子集，不建议直接用完整 `in/o2oa_body_cms_score` 做 compare 起始输入。

## 8. 下一阶段建议

下一阶段优先考虑：

1. 继续扩充数据集，增加真实 AFL 回收样本；
2. 对 AE 模型做更系统的阈值与训练/验证划分；
3. 逐步向更接近 SE-fAnoGAN-ES 的模型结构推进；
4. 进一步整理长期保留入口与最终 README。
