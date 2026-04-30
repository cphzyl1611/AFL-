# 模糊测试组件快速使用说明

## 1. 组件定位

当前模糊测试组件包含：

- 改造版 AFL++ 主链
- AE 默认有效性模型
- GAN v2 研究增强模型（t17_ab9010）
- O2OA 公文接口场景种子集
- fuzz_test_runner 外层控制器
- 20/60 秒两段式真实执行脚本

---

## 2. 当前两条推荐口径

### 默认口径

- 模型：AE
- 阈值：1.0
- 模板：`runner/templates/task_ae_default.json`

### 研究增强口径

- 模型：GAN v2（t17_ab9010）
- 阈值：1.7
- 标定：alpha=0.90，beta=0.10
- 模板：`runner/templates/task_gan_v2_default.json`

---

## 3. 启动 AE 服务

在项目根目录执行：

```bash
cd ~/AFLplusplus

export SEFANOGAN_MODE=ae
export SEFANOGAN_MODEL_PATH=$PWD/model_stage/models/sefanogan_ae_model.pt
export SEFANOGAN_AE_META_PATH=$PWD/model_stage/models/sefanogan_ae_meta.json

python3 model_stage/nv_valid_server_real.py

## 4. 启动 GAN v2 服务

在项目根目录执行：

```bash
cd ~/AFLplusplus

export SEFANOGAN_MODE=sefanogan_es
export SEFANOGAN_MODEL_PATH=$PWD/model_stage/models/sefanogan_gan_model.pt
export SEFANOGAN_GAN_META_PATH=$PWD/model_stage/models/sefanogan_gan_meta.json

python3 model_stage/nv_valid_server_real.py
```

## 5. 使用 runner 提交 AE 默认任务

另开一个终端：

```bash
cd ~/AFLplusplus
export NV_TOKEN='你的token'

python3 runner/fuzz_test_runner.py submit --task-json runner/templates/task_ae_default.json
```

记录返回的 `task_id`，然后查询：

```bash
python3 runner/fuzz_test_runner.py query --task-id <task_id>
python3 runner/fuzz_test_runner.py report --task-id <task_id>
```

## 6. 使用 runner 提交 GAN v2 任务

另开一个终端：

```bash
cd ~/AFLplusplus
export NV_TOKEN='你的token'

python3 runner/fuzz_test_runner.py submit --task-json runner/templates/task_gan_v2_default.json
```

记录返回的 `task_id`，然后查询：

```bash
python3 runner/fuzz_test_runner.py query --task-id <task_id>
python3 runner/fuzz_test_runner.py report --task-id <task_id>
```

## 7. 运行结果位置

每次 runner 提交任务后，会在：

* `runner/tasks/<task_id>/`
* `runner/runs/<task_id>/`

生成对应目录。

重点结果文件包括：

* `summary_dur20.csv`
* `summary_dur60.csv`
* `body_valid_stats_dur20.json`
* `body_valid_stats_dur60.json`
* `stdout.log`
* `stderr.log`

## 8. 当前模型路线说明

当前统一口径如下：

* AE：默认模型，当前稳定交付使用
* GAN 第一轮：中间过渡版本，不再继续扩展
* GAN v2(t17_ab9010)：后续研究增强主线，当前不替代 AE 默认模型

## 9. 当前建议

若目标是稳定执行模糊测试任务，优先使用：

* AE 默认口径

若目标是继续研究 SE-fAnoGAN-ES 增强效果，可使用：

* GAN v2(t17_ab9010) 口径

---

## 10. 第二平台最小校准说明（Flowable）

当前已完成 Flowable 第二平台的最小校准验证：

- 平台：Flowable
- 场景：process start
- 接口：POST /flowable-rest/service/runtime/process-instances
- 专用模型：Flowable-AE
- 当前工作阈值：12.4

当前结论：

- O2OA 训练得到的 AE 不能直接迁移到 Flowable
- 经过最小数据集校准后，Flowable-AE 已恢复稳定混合型 pass/reject
- 说明有效性模型需要按平台/场景做轻量校准

---

## 11. 第二平台 Flowable 校准结果（v2）

当前已完成 Flowable 第二平台的 v2 校准验证：

- 平台：Flowable
- 场景：process start
- 接口：POST /flowable-rest/service/runtime/process-instances
- 专用模型：Flowable-AE v2
- 当前工作阈值：6.3

当前结论：

- O2OA 训练得到的有效性模型不能直接迁移到 Flowable
- Flowable 第二平台需要平台专用小数据集校准
- Flowable-AE v2@6.3 已恢复稳定混合型 pass/reject
- 当前阶段不建议立即进入 Flowable-GAN

---

## 12. 第二平台最终口径（Flowable）

第二平台当前最终工作口径如下：

- 平台：Flowable
- 场景：process start
- 模型：Flowable-AE v2
- 阈值：6.3

说明：

- v3 已完成训练、定标和验证；
- 但当前 20/60 结果未优于 v2；
- 因此当前第二平台最终口径仍保留为 Flowable-AE v2 @ 6.3。
