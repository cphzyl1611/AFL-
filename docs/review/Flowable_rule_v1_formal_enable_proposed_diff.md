# Flowable rule v1 formal enable proposed diff

## 1. 说明

本文档仅说明未来如果正式启用 Flowable `flowable_rule_v1` second stage，需要对正式 profile 做的拟变更。

本轮不实际修改 `integration/platform_profiles/flowable_v2.json`。实际启用必须另开独立 commit，并附带评审、回滚和验收记录。

## 2. 当前正式 profile

当前正式文件：

`integration/platform_profiles/flowable_v2.json`

当前 decision 配置保持：

```json
{
  "t_low": 5.8,
  "t_high": 6.3,
  "enable_second_stage": false,
  "second_stage_type": "rule",
  "second_stage_threshold": 1.0
}
```

## 3. 未来拟启用配置

如果后续正式启用，需要将 decision 配置调整为：

```json
{
  "t_low": 5.8,
  "t_high": 6.3,
  "enable_second_stage": true,
  "second_stage_type": "flowable_rule",
  "second_stage_threshold": 1.0
}
```

同时应保留候选 profile 中已经评审过的 Flowable 规则配置，例如：

- `allowed_process_definition_keys`
- `flowable_rule_allowed_root_fields`
- `flowable_rule_required_variables_by_key`
- `flowable_rule_variable_type_hints`
- `flowable_rule_max_json_depth`
- `flowable_rule_max_string_len`
- `flowable_rule_max_total_keys`
- `flowable_rule_max_variables`
- `flowable_rule_max_variable_name_len`

## 4. 拟变更摘要

未来正式启用时，核心变更为：

```diff
- "enable_second_stage": false,
- "second_stage_type": "rule",
+ "enable_second_stage": true,
+ "second_stage_type": "flowable_rule",
  "second_stage_threshold": 1.0
```

必须继续保留：

- `t_low=5.8`
- `t_high=6.3`
- `second_stage_threshold=1.0`

## 5. 本轮不执行的内容

本轮不执行：

- 不修改正式 `integration/platform_profiles/flowable_v2.json`；
- 不启用正式 Flowable second stage；
- 不修改 O2OA profile；
- 不训练或接入 Flowable-GAN；
- 不把 O2OA GAN 迁移到 Flowable；
- 不声称完整强多平台动态异构冗余全部完成。

## 6. 回滚方式

如果后续正式启用后需要回滚，最小回滚方式是恢复：

```json
{
  "enable_second_stage": false,
  "second_stage_type": "rule"
}
```

回滚后 Flowable 将回到当前正式 baseline：Flowable-AE v2 第一阶段启用，second stage 不启用。

## 7. 启用前检查

正式启用前建议检查：

- `docs/review/Flowable_rule_v1_formal_enable_change_review_package.md` 已完成评审；
- `docs/review/Flowable_rule_v1_gray_validation_report.md` 已完成受控灰度验证；
- 业务误拒样本复核完成；
- 回滚路径已验证；
- O2OA `o2oa_default.json` 不受影响；
- Flowable-GAN 未完成的边界说明已保留。
