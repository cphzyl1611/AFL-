# 模糊测试组件交付目录

## 当前默认口径
- 模型：AE
- 阈值：1.0
- 模板：task_ae_default.json
- 状态：O2OA 默认模型权重以 `model_stage/models/sefanogan_ae_model.pt` 为 source-of-truth，sha256=`5de67e66e28af65fdf6adb5c506c91148fcc356accd49113c267896bbd69d3dc`；配套 meta 为 `model_stage/models/sefanogan_ae_meta.json`，sha256=`208daf66d82873dec8c19923d9c0a5a6b82ca36c512de52b0ff16b24ecb7acf2`。

## 当前研究增强口径
- 模型：O2OA GAN online 二阶段增强模型
- 阈值：1.0（online 二阶段 profile）；离线研究比较保留 GAN v2 t17_ab9010 / threshold=1.7 作为研究证据
- 标定：alpha=0.90，beta=0.10
- 模板：`integration/platform_profiles/o2oa_default.json` 的 `decision.second_stage_type=gan`；`task_gan_v2_default.json` 仅作为研究模板
- source-of-truth：`model_stage/models/sefanogan_gan_model.pt`，sha256=`205a6a20a499a39b994a7ea5a770d0f701fcaba37cd9328da7e71d4aaf856624`；`model_stage/models/sefanogan_gan_meta.json`，sha256=`87d189dde54ac578d170850d090032d3268887517d259ad5fc96855a15b9c495`

## Flowable 支线口径
- 模型：Flowable-AE v2
- 阈值：6.3
- 二阶段：`flowable_rule_v1`
- socket：`unix:///tmp/nv_valid_flowable.sock`
- source-of-truth：`model_stage/models/flowable_ae_v2_model.pt`，sha256=`72780ccf24401f20e5ae7127955c0b192ec6cbd5d88099ce3c4dc9ab03053bee`；`model_stage/models/flowable_ae_v2_meta.json`，sha256=`b3728ec4340a18b6abdeffdce3213778bde4cedbaf6ec048efd497866d510e80`

## 关键文件
- fuzz_test_runner.py：外层控制器
- run_runner_real_fuzz.sh：单次真实执行脚本
- run_runner_real_fuzz_plan.sh：20/60 两段式执行脚本
- task_ae_default.json：AE 默认任务模板
- task_gan_v2_default.json：GAN v2 研究任务模板
- fuzz_component_quickstart.md：快速使用说明
- gan_v2_t15_vs_t17_final_decision.md：GAN 阈值 1.5 与 1.7 比较结论
- gan_v2_t17_vs_t17_ab9010_final_decision.md：GAN v2@1.7 旧版与 ab9010 标定版比较结论

## 场景口径边界
- O2OA 主线当前以 O2OA HTTP/REST JSON 数据接口为阶段验收口径，证据集中在 `cms_doc_list` 并辅以多接口配置；不要表述为已完整覆盖电子公文创建、保存、更新全业务流程。
- Flowable 是第二平台最小校准验证，最终工作口径为 Flowable-AE v2 @ 6.3；当前 Flowable 链路不是完整 AFL++ 变异模糊测试主链。
- 当前动态异构冗余仅指模糊测试有效性验证链路中的二阶段判定机制；不要表述为完整拟态系统级执行体调度、自愈或重构机制。

## 当前结论
- AE 作为默认模型
- GAN v2（t17_ab9010）作为后续研究增强模型
- 模糊测试组件主体已完成，当前进入后续优化阶段
