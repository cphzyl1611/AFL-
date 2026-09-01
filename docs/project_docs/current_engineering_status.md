# 当前工程结构与后续推进说明

> **状态说明（supersession notice）**：本文档正文记录的是一个更早的工程阶段（启发式评分 → 中心距离占位模型 → AE 风格占位模型的演进），历史结果按原样保留，不作事后改写。当前最新状态请参见：
>
> - `docs/final_delivery/fuzz_component_final_acceptance_20260901.md`（最终验收报告）；
> - `docs/project_docs/sefanogan_es_reference_contract.md`（SE-fAnoGAN-ES backend 选择器契约）。
>
> 当前工程结论为：AE v1 是默认/主要的轻量统计基线模型；canonical SE-fAnoGAN-ES reference 已实现并完成正式对比（formal comparison）；SE-fAnoGAN-ES 是可选的研究后端（optional research backend），非默认；真实服务上的 AE-vs-SE four-run A/B 扩展实验尚未完成（`NOT_COMPLETED`）。

## 1. 当前阶段定位

当前项目已经完成从启发式评分、中心距离占位模型到 AE 风格占位模型的阶段性演进，建立了从数据集、特征抽取、模型训练、统一预测接口、在线 score 服务到 AFL `rule_score-only` 验证的完整链路。

当前最有代表性的阶段结果包括：

- 中心距离占位模型在 `rule_score-only` 场景下获得混合型 pass/reject 结果；
- AE 风格占位模型训练成功并完成在线接入；
- AE 模型在 `rule_score-only` 场景下获得 `83 pass / 41 reject` 的混合型结果；
- 已形成面向 `cms_doc_list` 接口的 v3 数据集，并引入真实 AFL 回收样本。

## 2. 当前核心文件

以下文件属于当前阶段的核心文件，应视为后续继续推进时的主要保留对象：

### 2.1 数据与特征
- `model_stage/data/sefanogan_dataset.jsonl`
- `model_stage/data/sefanogan_features.csv`
- `model_stage/data/sefanogan_features_summary.json`
- `model_stage/feature_extract.py`
- `model_stage/build_dataset.py`
- `model_stage/export_features.py`

### 2.2 模型训练与推理
- `model_stage/sefanogan_train.py`  
  当前中心距离占位模型训练脚本
- `model_stage/sefanogan_train_ae.py`  
  当前 AE 风格占位模型训练脚本
- `model_stage/sefanogan_predict.py`  
  当前统一预测接口，支持 `heuristic / model / ae`

### 2.3 模型文件
- `model_stage/models/sefanogan_placeholder_model.json`
- `model_stage/models/sefanogan_ae_model.pt`
- `model_stage/models/sefanogan_ae_meta.json`

### 2.4 在线服务与验证链路
- `model_stage/nv_valid_server_real.py`
- `nv_body_valid.py`
- `nv_http_harness.py`

## 3. 当前阶段性/实验性脚本

以下脚本具有阶段性价值，但不一定是长期主入口：

- `scripts/run_cms_body_valid_compare_real.sh`
- `scripts/run_cms_body_valid_compare_real_rulescore_only.sh`
- `scripts/run_cms_score_observe_real.sh`
- `model_stage/pick_v3_samples.py`

其中：

- `run_cms_body_valid_compare_real_rulescore_only.sh`  
  在当前阶段比三模式全套脚本更适合作为模型验证入口；
- `run_cms_score_observe_real.sh`  
  适合用于阈值标定和 score 分布观测；
- `pick_v3_samples.py`  
  主要用于从日志中回收 v3 样本，属于数据集扩充辅助工具。

## 4. 当前推荐主链路

在当前阶段，如果需要复现和继续推进，推荐的主链路如下：

1. 维护数据集：
   - `model_stage/build_dataset.py`
   - `model_stage/export_features.py`

2. 训练模型：
   - 中心距离模型：`model_stage/sefanogan_train.py`
   - AE 模型：`model_stage/sefanogan_train_ae.py`

3. 启动在线服务：
   - `model_stage/nv_valid_server_real.py`
   - 通过环境变量切换 `SEFANOGAN_MODE=model` 或 `SEFANOGAN_MODE=ae`

4. 验证模型：
   - 手工样本验证：`nv_http_harness.py`
   - 规则后二级 score 验证：`scripts/run_cms_body_valid_compare_real_rulescore_only.sh`
   - score 分布观测：`scripts/run_cms_score_observe_real.sh`

## 5. 当前推荐的 compare 输入种子集

当前不建议直接使用完整 `in/o2oa_body_cms_score` 作为 compare 起始种子集，因为其中混入了大量极端异常样本，会导致 AFL 后续样本分布过于偏高分，从而影响模型筛选效果判断。

当前更推荐使用：

- `in/o2oa_body_model_compare`

该目录主要包含：

- 正常样本
- 边界样本
- 少量温和异常样本

更适合用作 `rule_score-only` 场景下的平衡验证输入。

## 6. 当前阶段结论

当前项目已经不再停留在启发式评分或几何距离占位模型阶段，而是进入了“小样本神经网络异常检测模型”阶段。AE 模型已在平衡种子集和 AFL 驱动场景下表现出明显的混合型筛选能力，说明现有工程框架已足以支撑后续向类 SE-fAnoGAN-ES 方向继续推进。

## 7. 下一阶段优先改造点

如果继续向更像 SE-fAnoGAN-ES 的方向推进，优先级建议如下：

### 优先级 1：继续扩充数据集
- 增加真实 AFL 回收样本
- 增加 normal 样本覆盖
- 逐步完善标签质量和来源说明

### 优先级 2：优化 AE 训练与阈值策略
- 增加训练/验证划分
- 对 AE 模型做更系统的阈值标定
- 观察不同阈值下的 pass/reject 平衡

### 优先级 3：升级模型结构
- 从简单 AE 过渡到更复杂的异常检测网络
- 逐步向类 SE-fAnoGAN-ES 结构靠拢

### 优先级 4：整理最终交付入口
- 明确长期保留的主脚本
- 下沉临时实验脚本
- 形成更清晰的 README 与运行说明

## 8. 当前最值得保留的阶段成果

当前阶段最值得保留和展示的成果包括：

1. `docs/final_results/model_comparison_summary.md`
2. `docs/final_results/ae_rulescore_only_result.md`
3. `docs/final_results/ae_score_distribution_note.md`
4. `docs/final_results/model_rulescore_only_v3_result.md`
5. `docs/project_docs/model_evolution_plan.md`

这些文件共同构成了当前阶段从启发式评分向 AE 异常检测模型演进的完整证据链。

---

## 9. Alfresco multipart bounded closure amendment (2026-08-31)

本次 fuzzing 收口新增并验证：

```text
canonical multipart positive manifest = PASS
one-shot reproduction script = PASS
real validation-reject = PASS
multipart field_value real arm = PASS
multipart boundary real arm = PASS
multipart structure real arm = PASS
multipart multi-arm real validation = PASS
```

最终真实运行目录：

```text
/tmp/alfresco-multipart-closure-final-20260831
```

每个 arm 均完成 21 次 HTTP 201、21/21 创建节点 metadata/content read-back、2 个不同 queue seed 选择、execution ledger/MAB reconciliation 和 runner exit 0。负样本阶段验证了 `HTTP_SENT=0`、`NODES_CREATED=0` 且 parent children 数量不变。

正式 canonical 资产：

```text
in/alfresco_multipart_upload_bounded/manifest.txt
scripts/reproduce_alfresco_multipart_bounded.py
```

长期稳定性和规模化验证按范围保持：

```text
LONG_TERM_STABILITY = NOT_RUN_BY_SCOPE
SCALE_VALIDATION = NOT_RUN_BY_SCOPE
```
