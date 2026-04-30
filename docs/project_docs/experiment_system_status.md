# 当前实验系统状态说明

## 1. 当前状态

项目当前已完成实验系统工程化改造，不再依赖手工修改 `build_dataset.py` 和临时命令组合来组织实验，而是已经支持：

- manifest 化数据集管理；
- 一键实验重建；
- 一键验证；
- 标准实验目录归档。

## 2. 已支持的数据集版本

当前已固定两套标准数据集 manifest：

- `model_stage/manifests/dataset_manifest_156.txt`
- `model_stage/manifests/dataset_manifest_182.txt`

其中：

- `156 rows` 用于默认基线实验；
- `182 rows` 用于增强版实验配置。

## 3. 已支持的自动化脚本

### 3.1 一键实验重建

脚本：

- `scripts/run_stage2_experiment.sh`

支持：

```bash
bash scripts/run_stage2_experiment.sh baseline_156
bash scripts/run_stage2_experiment.sh enhanced_182
```


功能包括：

* 按 manifest 构建数据集；
* 导出特征；
* 进行 train/val 划分；
* 训练 AE 模型；
* 自动归档结果到实验目录。

### 3.2 一键验证

脚本：

* `scripts/run_stage2_validation.sh`

支持：

<pre class="overflow-visible! px-0!" data-start="2027" data-end="2254"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼd">bash</span><span> scripts/run_stage2_validation.sh baseline_156 </span><span class="ͼb">20</span><br/><span class="ͼd">bash</span><span> scripts/run_stage2_validation.sh baseline_156 </span><span class="ͼb">60</span><br/><span class="ͼd">bash</span><span> scripts/run_stage2_validation.sh enhanced_182 </span><span class="ͼb">20</span><br/><span class="ͼd">bash</span><span> scripts/run_stage2_validation.sh enhanced_182 </span><span class="ͼb">60</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

功能包括：

* 调用现有 `rule_score-only` 验证链路；
* 自动保存 summary 与 body_valid_stats 到对应实验目录。

## 4. 当前标准实验目录

当前已形成两套完整目录化实验结果：

### 默认基线

* `docs/final_results/experiments/baseline_156_20260320_153239`

### 增强版实验配置

* `docs/final_results/experiments/enhanced_182_20260320_153402`

每个目录均包含：

* 数据集文件；
* 特征文件；
* train/val 文件；
* 模型与 meta；
* README；
* 20 秒验证结果；
* 60 秒验证结果。

## 5. 当前建议

后续如需继续开展实验，建议统一采用当前自动化系统，而不再使用手工修改脚本和零散命令方式。

推荐流程为：

1. 选择 manifest；
2. 运行一键实验重建；
3. 运行 20 秒与 60 秒验证；
4. 直接使用实验目录中的结果进行对比分析与材料整理。

## 6. 结论

当前项目已完成从“零散实验”到“标准实验系统”的转变。后续工作重点应从继续搭建工程能力，转向结果分析、材料输出与必要的后续模型/样本策略决策。
