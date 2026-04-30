# 当前阶段版本说明

## 阶段定位
当前版本为：O2OA 真实场景 body-only 模糊测试与两级有效性验证框架阶段性完成版本。

## 当前正式主实验
- 主入口脚本：scripts/run_main_baseline_rule_generic.sh
- 正式接口：
  - person_detail
  - review_count
  - hotpic_list
  - cms_doc_list
- 实验模式：
  - baseline
  - rule_only

## 当前增强实验
- 接口：cms_doc_list
- 敏感种子目录：in/o2oa_body_cms_score
- 二级 score 阈值：1.5
- score 后端：当前增强版 nv_valid_server_mock.py

## 当前敏感接口
- calendar_filter
说明：当前作为敏感接口专项分析对象，不纳入本阶段正式主实验基线。

## 当前阶段关键结果
- 主实验正式结果：docs/final_results/summary_main_baseline_rule_generic_fixed.csv
- 增强实验结果：docs/final_results/summary_cms_body_valid_compare_fixed.csv
- body-valid 统计：docs/final_results/last_body_valid_stats_fixed.json
