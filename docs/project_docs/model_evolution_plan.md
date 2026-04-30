# 模型演进计划（从 placeholder model 到类 SE-fAnoGAN-ES 模型）

## 1. 当前模型阶段

当前系统已完成基于接口级 JSON body 的特征抽取、数据集构建、模型训练、在线服务和 compare 验证流程。现阶段使用的模型为 `placeholder_center_distance`，其核心思想为：仅利用 `normal` 样本建立特征均值、标准差和标准化中心，在推理阶段计算待测样本到正常中心的距离，并将该距离作为异常分数。

该模型的优点是结构简单、训练代价低、便于快速接入现有 `model` 模式在线服务框架；其缺点是表达能力有限，本质上更接近静态几何距离模型，对复杂非线性模式、局部结构扰动和更高阶特征关联的表达不足。

## 2. 当前阶段成果

在当前 placeholder model 基础上，项目已完成以下工作：

- 构建 `cms_doc_list` 接口的小样本原型数据集，并逐步扩充到包含手工种子与真实 AFL 回收样本的 v3 数据集；
- 完成特征抽取模块 `feature_extract.py`；
- 完成统一预测接口 `sefanogan_predict.py`；
- 完成在线评分服务 `nv_valid_server_real.py`；
- 在 `rule_score-only` 的 AFL 验证场景下，已获得 `112 pass / 8 reject` 的混合型结果，说明模型已具备初步筛选能力。

## 3. 当前模型的局限

虽然 placeholder_center_distance 已经能够完成初步分层，但其不足主要体现在：

1. 对真实 AFL 样本分布仍较敏感，阈值需要依赖观测结果反复校准；
2. 模型只能表达“离正常中心远近”，难以学习复杂非线性正常模式；
3. 对结构相近但局部扰动明显的样本，区分能力仍有限；
4. 与项目后续计划中的 SE-fAnoGAN-ES 思路相比，当前模型仍偏工程占位性质。

## 4. 下一阶段目标

下一阶段不再停留在中心距离模型，而是推进到更接近异常检测网络的模型形式。综合当前数据规模、工程复杂度与可落地性，建议先实现一个 Autoencoder-style placeholder model，作为从中心距离模型向更正式 SE-fAnoGAN-ES 模型过渡的中间阶段。

## 5. 选择 Autoencoder 作为下一阶段过渡模型的原因

选择 Autoencoder（AE）作为下一阶段模型，主要基于以下考虑：

1. AE 属于典型的“仅用正常样本学习正常模式”的异常检测模型，和当前项目问题匹配；
2. AE 使用重建误差作为异常分数，比中心距离模型具有更强的非线性表达能力；
3. 在当前已有的特征表基础上，AE 训练和推理都容易接入现有框架；
4. AE 作为中间阶段模型，可以为后续向更接近 SE-fAnoGAN-ES 的模型结构推进提供平滑过渡。

## 6. 预期工程结构

下一阶段建议新增如下文件：

- `model_stage/sefanogan_train_ae.py`：AE 训练脚本
- `model_stage/models/sefanogan_ae_model.pt`：AE 权重文件
- `model_stage/models/sefanogan_ae_meta.json`：AE 元信息文件

同时保留现有：

- `model_stage/sefanogan_predict.py`
- `model_stage/nv_valid_server_real.py`

并在 `sefanogan_predict.py` 中增加新的模型加载和推理分支，使系统能够在 `center_distance` 和 `AE` 两类模型之间切换。

## 7. 下一阶段总体路线

下一阶段计划按以下顺序推进：

1. 完成 AE 版训练脚本，实现仅基于 `normal` 样本的训练；
2. 输出 AE 权重文件和元信息文件；
3. 在 `sefanogan_predict.py` 中接入 AE 模型推理；
4. 用少量样本重新标定 AE 模式阈值；
5. 在 `rule_score-only` 和 compare 场景下验证 AE 模型；
6. 视数据规模和效果，再决定是否进一步推进到更接近 SE-fAnoGAN-ES 的模型结构。

## 8. 当前定位

因此，当前项目阶段可以表述为：

> 已完成从启发式评分到小样本异常检测 placeholder model 的过渡，并建立了从数据集、特征、模型训练、在线服务到 compare 验证的完整链路。下一阶段将在现有工程框架基础上，进一步推进到 Autoencoder-style placeholder model，并逐步向类 SE-fAnoGAN-ES 方向演进。