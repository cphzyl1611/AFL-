# 模糊测试项目阶段性最终收口总结

## 1. 项目范围说明

当前阶段模糊测试部分的工作范围主要包括：

1. 基于改造版 AFL++ 的模糊测试主链建设；
2. 面向 O2OA 场景的有效性验证模型接入与实验；
3. 面向第二平台 Flowable 的最小校准与可迁移性验证；
4. 模糊测试组件的 runner、模板、执行脚本、结果汇总与交付目录整理。

本阶段目标不是无限扩展平台数量或模型数量，而是完成：

- 主平台可交付；
- 第二平台可迁移性验证；
- 当前阶段模型路线收敛；
- 形成可复用的平台校准流程。

口径边界：

- O2OA 主线当前以 O2OA HTTP/REST JSON 数据接口为阶段验收口径，证据集中在 `cms_doc_list`，并辅以 `calendar_filter`、`review_count`、`hotpic_list`、`person_detail` 等接口配置。该口径可支撑“O2OA 数据接口场景”阶段收口，但不能扩大表述为已经完整覆盖电子公文创建、保存、更新全业务流程。
- Flowable 第二平台当前仅完成“最小校准验证”：基于静态混合数据集进行模型打分、pass/reject 统计和 REST POST 验证。该验证证明新平台需要专用小数据集校准，但不等同于完整 AFL++ 变异模糊测试主链已迁移到 Flowable。

---

## 2. O2OA 主线成果

### 2.1 主体完成内容

O2OA 主线当前已完成：

- 改造版 AFL++ 主链；
- AE 默认有效性模型接入；
- GAN v2 增强模型接入；
- runner 外层控制器；
- 20/60 秒两段式真实执行脚本；
- 结果自动归档与报告输出；
- 模板任务与快速使用说明；
- 交付目录整理。

### 2.2 O2OA 当前模型路线

当前 O2OA 口径已经固定为：

#### 默认模型
- AE

#### 研究增强模型
- GAN v2（t17_ab9010）

其中：
- AE 作为当前稳定默认模型；
- GAN v2（t17_ab9010）作为研究增强模型；
- 已完成对旧版 GAN 与不同阈值路线的比较与收敛；
- 当前不再继续扩展旧 GAN 路线。

### 2.3 O2OA 阶段结论

O2OA 主线已经具备以下状态：

1. 模糊测试组件主体完成；
2. 默认模型口径明确；
3. 增强模型路线明确；
4. 执行脚本、模板与报告链完整；
5. 当前阶段可以视为封板收口。

---

## 3. Flowable 第二平台成果

## 3.1 第二平台验证目标

引入 Flowable 第二平台的目的，不是替代 O2OA 主线，而是验证：

- 当前模糊测试框架是否具备跨平台迁移能力；
- 有效性模型是否能够直接迁移；
- 若不能直接迁移，是否可以通过小规模平台专用校准恢复工作能力。

### 3.2 第二平台场景

当前第二平台验证场景为：

- 平台：Flowable
- 场景：process start
- 接口：POST /flowable-rest/service/runtime/process-instances

### 3.3 Flowable 最小校准过程

Flowable 第二平台已完成以下工作：

1. Flowable REST 服务部署与连通性验证；
2. holidayRequest 流程定义部署；
3. process start 正常请求样本构造；
4. Flowable 最小数据集构建；
5. Flowable-AE 训练；
6. 服务侧真实分数扫描；
7. 工作阈值定标；
8. 20/60 秒两段式 runner 验证；
9. 重复实验与路线比较。

### 3.4 Flowable 关键结论

第二平台实验明确证明：

1. O2OA 上训练得到的有效性模型不能直接迁移到 Flowable；
2. runner、score 服务、结果回收和平台校准流程可以迁移；
3. Flowable 需要平台专用小规模数据集校准；
4. 经过校准后，第二平台可以恢复稳定混合型 pass/reject；
5. 阈值必须依据服务侧真实分数定标，不能直接依据训练侧 recon 值猜测。

边界说明：当前 Flowable 结论仅覆盖最小校准验证，不覆盖完整 AFL++ 变异执行闭环。

---

## 4. Flowable 模型路线收敛结果

### 4.1 Flowable-AE v2

当前 Flowable-AE v2 最终工作口径为：

- 模型：Flowable-AE v2
- 阈值：6.3

关键结果如下：

- 20 秒：pass = 287，reject = 65，rpc_fail = 0
- 60 秒：pass = 887，reject = 181，rpc_fail = 0

说明：
- 已恢复稳定混合型 pass/reject；
- rpc_fail 始终为 0；
- 可作为当前第二平台最终工作口径。

### 4.2 Flowable-AE v3

Flowable-AE v3 已完成：

- 数据扩展；
- 模型训练；
- 服务侧真实分数扫描；
- 工作阈值定标；
- 20/60 秒验证。

其结果为：

- 20 秒：pass = 283，reject = 68，rpc_fail = 0
- 60 秒：pass = 870，reject = 199，rpc_fail = 0

结论：
- v3 可训练、可运行、可定标；
- 但当前结果未优于 v2；
- 因此 v3 不作为当前最终工作口径。

### 4.3 第二平台最终口径

当前第二平台最终口径固定为：

- 平台：Flowable
- 模型：Flowable-AE v2
- 阈值：6.3

v3 保留为后续数据整理与再训练参考版本。

---

## 5. 当前阶段最终模型路线

当前整个模糊测试部分的模型路线可以统一表述为：

### 第一平台（O2OA）
- 默认模型：AE
- 研究增强模型：GAN v2（t17_ab9010）

### 第二平台（Flowable）
- 最终工作模型：Flowable-AE v2
- 工作阈值：6.3

---

## 6. 当前阶段最重要结论

本阶段模糊测试部分已经得出以下核心结论：

1. 改造版 AFL++ + 有效性验证 + runner + 两段式执行脚本的整体框架已经成熟；
2. O2OA 主线已完成并收口；
3. 模糊测试的 runner、score、结果回收和校准流程具备跨平台迁移能力；
4. 但有效性模型不具备直接跨平台通用性；
5. 新平台需要通过小规模专用数据集进行校准；
6. 平台校准后，第二平台可以恢复稳定工作；
7. 当前阶段不需要继续扩展更多平台或更复杂模型。

---

## 7. 当前交付物状态

当前阶段已形成的关键交付物包括：

### O2OA 主线
- fuzz_test_runner.py
- run_runner_real_fuzz.sh
- run_runner_real_fuzz_plan.sh
- task_ae_default.json
- task_gan_v2_default.json
- fuzz_component_quickstart.md
- O2OA 模型路线与结果文档

### Flowable 第二平台
- flowable_ae_v2_model.pt
- flowable_ae_v2_meta.json
- task_ae_flowable_eval_v2.json
- flowable_ae_min_calibration_result.md
- flowable_ae_repeat_final_result.md
- flowable_ae_v2_final_result.md
- flowable_ae_v2_vs_v3_final_decision.md
- flowable_final_model_route.md

### 总体文档
- 模糊测试阶段成果与下一阶段优化方案.docx
- 本收口总结文档

---

## 8. 当前阶段不再继续推进的事项

为了避免项目范围失控，当前阶段明确不再继续：

1. 不进入 Flowable-GAN；
2. 不继续扩展 Flowable-AE v4；
3. 不继续扩展第三平台；
4. 不再回头折腾 O2OA 第二场景；
5. 不再修改 AFL++ 主链核心路线。

---

## 9. 后续建议

若后续确有新增任务需求，建议按以下优先顺序推进：

### 第一优先级
进一步整理 Flowable 数据集，提高第二平台数据分层质量。

### 第二优先级
在明确有必要提升第二平台效果时，再考虑重开 Flowable-AE 数据整理线。

### 第三优先级
只有在明确提出“需要继续研究增强模型”时，才考虑 Flowable-GAN。

在没有明确新增目标前，不建议继续扩线。

---

## 10. 当前阶段结束说明

综上，当前模糊测试部分已经完成：

- O2OA 主线封板；
- Flowable 第二平台可迁移性验证；
- 第二平台模型路线收敛；
- 组件、模板、脚本、报告与交付目录整理。

因此，本阶段可以正式视为：

# 模糊测试部分阶段性收口完成

后续如无新的明确任务要求，建议当前阶段在此结束，不再继续扩展研发范围。
