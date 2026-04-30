# 模糊测试组件交付目录

## 当前默认口径
- 模型：AE
- 阈值：1.0
- 模板：task_ae_default.json
- 状态：O2OA 默认模型权重需要在交付前人工核验，确保 `model_stage/models/sefanogan_ae_model.pt` 与 O2OA AE@1.0 一致。

## 当前研究增强口径
- 模型：GAN v2（t17_ab9010）
- 阈值：1.7
- 标定：alpha=0.90，beta=0.10
- 模板：task_gan_v2_default.json

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

## 当前结论
- AE 作为默认模型
- GAN v2（t17_ab9010）作为后续研究增强模型
- 模糊测试组件主体已完成，当前进入后续优化阶段
