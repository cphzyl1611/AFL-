# NV_MAB反馈变异策略阶段性收口报告

## 1. 本次修复内容

本轮围绕 NV_MAB 最小工程闭环进行收口，目标是让“实际生成样本的 arm”和“后续 reward 更新的 arm”严格对应。

已完成的修复包括：

| 修复项 | 结果 |
|---|---|
| arm 归因修复 | custom mutator 阶段 pick arm，并通过 `NV_CUR_ARM` 传递给 Python JSON mutator；Python mutator 写回 `NV_JSON_ARM_USED`；C 侧仅在二者匹配时设置 `pending_arm/pending_update`。 |
| reward 更新修复 | `common_fuzz_stuff` 不再无条件 pick；reward 只更新 `pending_arm`，非 NV JSON arm 生成的输入不更新三类 NV_MAB arm。 |
| mutation_scope 解析 | 已支持数字 bitmask、字符串形式和 JSON 数组形式，例如 `["field_value"]`、`["boundary"]`、`["structure"]`、`["field_value","boundary","structure"]`。 |
| 重复/死代码清理 | 收敛到 C 侧可信 pick/update 实现，避免 `common_fuzz_stuff` 与 custom mutator 阶段重复 pick/update。 |
| Python mutator 兼容 | `nv_json_mutator.py` 增加 AFL++ Python wrapper 入口，并通过 libc `getenv` 读取 C 侧实时 `NV_CUR_ARM`，避免 Python `os.environ` 缓存导致 arm 不一致。 |
| 编译验证 | `make -j2 afl-fuzz` 通过；`python3 -m py_compile nv_json_mutator.py` 通过。 |

## 2. 本次 smoke 结果

本次只运行本地最小 AFL++ smoke，不访问外部网络，不启动 O2OA、Flowable、Alfresco 服务，不修改已有真实服务 evidence。

输出目录：

| case | 输出目录 |
|---|---|
| field_value | `out/nv_mab_smoke_field_value/afl_scope_final/` |
| boundary | `out/nv_mab_smoke_boundary/afl_scope_final/` |
| structure | `out/nv_mab_smoke_structure/afl_scope_final/` |
| all | `out/nv_mab_smoke_all/afl_scope_final/` |

汇总文件：

- `out/nv_mab_smoke_summary.csv`

### 2.1 单 arm scope 结果

| case | mutation_scope | total_pulls | arm0 | arm1 | arm2 | 判定 |
|---|---:|---:|---:|---:|---:|---|
| field_value | `["field_value"]` | 47 | 47 | 0 | 0 | 通过 |
| boundary | `["boundary"]` | 49 | 0 | 49 | 0 | 通过 |
| structure | `["structure"]` | 48 | 0 | 0 | 48 | 通过 |

结论：单 arm scope 能限制可用 arm，且 reward 只回写到实际生成样本的 arm。

### 2.2 三 arm scope 结果

| case | mutation_scope | total_pulls | arm0 | arm1 | arm2 | 判定 |
|---|---:|---:|---:|---:|---:|---|
| all | `["field_value","boundary","structure"]` | 47 | 45 | 1 | 1 | 通过 |

结论：三 arm scope 下三个 arm 均获得 pulls，`mean_reward` 和 `sum_reward` 随执行更新，`nv_mab_total_pulls` 大于 0。

### 2.3 fuzzer_stats 字段检查

四组 smoke 的 `fuzzer_stats` 均包含以下字段：

- `nv_mab_total_pulls`
- `nv_mab_last_arm`
- `nv_mab_pending_arm`
- `nv_mab_pending`
- `nv_mab_update_src`
- `nv_mab_arm0_pulls`
- `nv_mab_arm1_pulls`
- `nv_mab_arm2_pulls`
- `nv_mab_arm0_mean`
- `nv_mab_arm1_mean`
- `nv_mab_arm2_mean`

### 2.4 plot_data 字段检查

四组 smoke 的 `plot_data` 均保留 NV_MAB 字段：

- `nv_mab_a0_pos`
- `nv_mab_a1_pos`
- `nv_mab_a2_pos`
- `nv_mab_a0_mean`
- `nv_mab_a1_mean`
- `nv_mab_a2_mean`
- `nv_mab_a0_pulls`
- `nv_mab_a1_pulls`
- `nv_mab_a2_pulls`

本轮没有修改 O2OA、Flowable、Alfresco 的既有 summary/eval_report evidence。

## 3. 阶段性结论

NV_MAB 工程闭环基本完成。

当前实现已经支持：

- `field_value`、`boundary`、`structure` 三类 JSON 变异 arm；
- `mutation_scope` 对可用 arms 的限制；
- custom mutator 生成样本时记录实际使用的 arm；
- C 侧按 `pending_arm` 对 reward 做归因更新；
- `fuzzer_stats` 和 `plot_data` 输出 NV_MAB 统计字段；
- 本地最小 smoke 验证单 arm 和三 arm 场景均通过。

因此，NV_MAB 可以从“工程雏形”调整为“工程闭环基本完成”。

## 4. 边界

仍不能宣称：

- 完整 NC_MAB 理论闭环已经完成；
- 完整自动化语义种子生成已经完成；
- 已完成长时间稳定性实验或消融实验；
- reward 已经是严格代码覆盖率或严格理论收益函数；
- Flowable 完整 AFL++ mutation-chain 已完成；
- 完整拟态系统级动态异构冗余已经完成。

当前 reward 仍是工程化覆盖代理和 HTTP 状态反馈，适合支撑阶段性工程验收和后续集成联调，但不应过度解释为最终理论模型闭环。
