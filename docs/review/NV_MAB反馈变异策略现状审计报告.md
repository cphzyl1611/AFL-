# NV_MAB反馈变异策略现状审计报告

## 1. 审计范围

本报告只做只读审计，目标是确认当前仓库中 NV_MAB / NC_MAB 反馈变异策略实现到底做到什么程度，并给出最小修复计划。

本轮未修改 C 代码，未运行 `make`，未运行 fuzz，未访问网络，未启动服务，未删除 evidence。

重点检查文件：

- `include/afl-fuzz.h`
- `src/afl-fuzz-one.c`
- `src/afl-fuzz-run.c`
- `src/afl-fuzz-stats.c`
- `nv_json_mutator.py`
- `docs/review/种子质量与测试用例生成说明.md`
- `docs/review/模糊测试模块项目要求完成证明与复现说明.md`
- `docs/review/evidence/seed_quality_summary.json`
- `docs/review/evidence/seed_quality_summary.csv`

## 2. 逐项审计结论

| 问题 | 当前结论 |
| --- | --- |
| 1. 当前是否存在 `nv_mab_t` 或等价结构？ | 存在。`include/afl-fuzz.h` 中定义了 `nv_arm_t`、`nv_mab_t`，`afl_state_t` 中包含 `nv_mab`。 |
| 2. 当前 MAB arm 有哪些？ | 共有 3 个显式 arm：`NV_ARM_FIELD_VALUE=0`、`NV_ARM_BOUNDARY=1`、`NV_ARM_STRUCTURE=2`。对应 Python mutator 中的 `_mutate_field_value`、`_mutate_boundary`、`_mutate_structure`。未发现其他正式 arm。 |
| 3. 当前是否存在 `nv_mab_pick`？ | 存在。`src/afl-fuzz-one.c` 和 `src/afl-fuzz-run.c` 中均有 `nv_mab_pick`，逻辑为冷启动探索、最小探索次数、UCB 选择。 |
| 4. 当前是否存在 `nv_mab_update`？ | 存在。`src/afl-fuzz-one.c` 和 `src/afl-fuzz-run.c` 中均有 `nv_mab_update`，更新 pulls、sum_reward、pos_cnt、mean_reward。 |
| 5. pick 在哪里调用？ | `src/afl-fuzz-one.c` 的 custom mutator 循环中调用一次，用于设置 `NV_CUR_ARM`；`src/afl-fuzz-run.c` 的 `common_fuzz_stuff` 中也调用一次，并再次设置 `NV_CUR_ARM`。 |
| 6. update 在哪里调用？ | 活跃调用位于 `src/afl-fuzz-run.c` 的 `common_fuzz_stuff` 执行目标后：读取 status JSON 计算 reward，然后 `nv_mab_update(&afl->nv_mab, afl->nv_mab.last_arm, reward)`。`src/afl-fuzz-one.c` 中定义了 update，但未发现实际调用。 |
| 7. reward 从哪里来？ | 活跃 reward 来自 `src/afl-fuzz-run.c::nv_http_reward` 读取 `NV_STATUS_PATH` 或 `/tmp/nv_http_status.json`。主要包含 `ncov_delta`、HTTP class/timeout/conn_refused、recovered、method+path+class 新状态哈希和 4xx 小惩罚。 |
| 8. `mutation_scope` 是否能限制可用 arms？ | C 侧 `nv_mab_pick` 支持 bitmask 限制；`src/afl-fuzz.c::nv_parse_scope` 支持数字和字符串形式。但当前常见 submit/task 中 `mutation_scope` 是 JSON 数组，C 侧未解析数组，会退回默认 `0x7`，因此数组形式限制可能失效。 |
| 9. `fuzzer_stats` 是否输出 MAB 字段？ | 输出。`src/afl-fuzz-stats.c` 写出 `nv_mab_total_pulls`、`nv_mab_last_arm`、各 arm 的 pulls/mean/pos/sum。`plot_data` 也追加了 MAB 和 HTTP status 相关字段。 |
| 10. `src/afl-fuzz-one.c` 和 `src/afl-fuzz-run.c` 是否存在重复、未用或死代码？ | 存在。两个文件重复定义 MAB pick/update 和 reward 相关 helper；`src/afl-fuzz-one.c` 中 `nv_http_reward` 被 `#if 0` 包裹，`nv_mab_update` 未调用，`ss_new_bits_any` / `queued_items` delta 计算后未进入 update。 |
| 11. 当前实现能否支撑“工程化 UCB/MAB 反馈变异策略”？ | 部分支撑。已有 arm 结构、UCB pick、reward update、stats 输出、Python JSON arm mutator。但 arm 选择和 reward 更新存在归因风险，`mutation_scope` 数组形式限制不完整，因此只能说工程雏形或阶段性实现。 |
| 12. 当前为什么还不能说成完整 NC_MAB 理论闭环？ | 还缺少严格的 arm-变异-reward 一一归因、NC_MAB 理论定义和参数验证、语义种子自动选择闭环、有效性/覆盖/错误的规范化 reward 设计、消融实验和长时间稳定性验证。 |
| 13. 最小修复计划是什么？ | 见第 5 节。核心是统一 MAB 实现、修复 pick/update 归因、支持数组 `mutation_scope`、明确 reward 公式并补最小验证。 |
| 14. 哪些文件需要改？ | 最小涉及 `include/afl-fuzz.h`、`src/afl-fuzz.c`、`src/afl-fuzz-one.c`、`src/afl-fuzz-run.c`、`src/afl-fuzz-stats.c`、`nv_json_mutator.py`、相关 docs。若在 adapter 层转换 scope，还需改 `integration/fuzz_adapter.py` 或 runner 任务生成逻辑。 |
| 15. 需要哪些最小验证？ | `make -j2 afl-fuzz`；`py_compile nv_json_mutator.py`；用单 arm scope 跑最小本地 harness，确认只有对应 arm pulls 增长；用三 arm scope 跑最小 harness，确认 pulls/mean_reward 更新；检查 `fuzzer_stats`、`plot_data`、summary 不回退。 |
| 16. 最终报告应如何表述？ | 可表述为“已具备工程化 UCB/MAB 反馈变异策略雏形，完成 arm 定义、UCB 选择、HTTP reward 更新和统计输出；仍需修复归因和 scope 解析后，才能作为稳定工程能力；不能称为完整 NC_MAB 理论闭环”。 |

## 3. 已完成

### 3.1 数据结构

`include/afl-fuzz.h` 已定义：

- `nv_arm_id_t`
- `nv_arm_t`
- `nv_mab_t`
- `afl_state_t.nv_mab`

三类 arm：

- `field_value`
- `boundary`
- `structure`

### 3.2 选择与更新函数

`nv_mab_pick` 已实现冷启动、最小探索和 UCB 选择。

`nv_mab_update` 已实现 pull 计数、正 reward 计数、累计 reward 和增量均值更新。

### 3.3 Python 变异 arm

`nv_json_mutator.py` 已通过 `NV_CUR_ARM` 选择三类 JSON 结构保持型变异：

- 字段值变异；
- 边界值变异；
- 结构增删变异。

### 3.4 reward 来源

活跃 reward 来自 HTTP harness status JSON：

- `ncov_delta`：作为主权重；
- `method + path + class` 新状态：作为小额新状态奖励；
- timeout / 5xx / conn_refused：作为异常类信号；
- `recovered`：作为恢复信号；
- 4xx：小额惩罚。

这能支撑工程化 HTTP/REST 场景的反馈变异雏形。

### 3.5 统计输出

`src/afl-fuzz-stats.c` 已输出：

- `nv_mab_total_pulls`
- `nv_mab_last_arm`
- `nv_mab_arm0_pulls`
- `nv_mab_arm0_mean`
- `nv_mab_arm0_pos`
- `nv_mab_arm0_sum`
- `nv_mab_arm1_*`
- `nv_mab_arm2_*`

`plot_data` 也追加了 arm pulls、positive count、mean reward 和 HTTP status 统计。

### 3.6 种子质量 evidence

`docs/review/evidence/seed_quality_summary.json` 和 `.csv` 已能证明当前 seed 体系包含 O2OA、Flowable、Alfresco 多目录，且包含正常、边界、预设非法样本和文档业务字段。

## 4. 需修复

### 4.1 arm 归因不严格

当前存在两个 pick 点：

- `src/afl-fuzz-one.c` custom mutator 调用前 pick，并设置 `NV_CUR_ARM`；
- `src/afl-fuzz-run.c` `common_fuzz_stuff` 执行前再次 pick，并覆盖 `last_arm`。

风险：Python mutator 实际使用的是第一个 arm，但 reward update 使用的是 `common_fuzz_stuff` 中第二次 pick 后的 `last_arm`。这会导致 reward 归因到错误 arm。

### 4.2 非 custom mutation 也会更新 MAB

`common_fuzz_stuff` 是 AFL++ 多类变异路径共用函数。当前在该函数中全局 pick/update，意味着 deterministic/havoc 等非 `nv_json_mutator.py` 产生的样本也可能被分配到 NV_MAB arm 并更新 reward。

风险：MAB 统计可能混入非三类 JSON arm 的效果，削弱“arm -> 变异策略 -> reward”的解释性。

### 4.3 `mutation_scope` 数组形式未解析

`src/afl-fuzz.c::nv_parse_scope` 支持：

- 数字 bitmask，例如 `7`；
- 字符串，例如 `"field_value,boundary,structure"`。

但 adapter 和示例任务常见形式是：

```json
"mutation_scope": ["field_value", "boundary", "structure"]
```

数组形式当前会落入默认值 `0x7`。因此如果用户只传 `["boundary"]`，C 侧可能仍启用全部 arm。

### 4.4 重复与死代码

`src/afl-fuzz-one.c` 和 `src/afl-fuzz-run.c` 重复定义：

- `nv_fnv1a64`
- `nv_covset_init`
- `nv_covset_insert`
- `nv_http_reward`
- `nv_arm_enabled`
- `nv_mab_pick`
- `nv_mab_update`

其中 `src/afl-fuzz-one.c` 的 `nv_http_reward` 被 `#if 0` 包裹，`nv_mab_update` 未调用，`ss_new_bits_any` delta 和 `queued_items` delta 计算后未接入 reward update。

### 4.5 reward 设计仍是工程启发式

当前 reward 以 HTTP harness 状态和覆盖代理为主。它不是完整 NC_MAB 理论定义下的标准 reward。

特别是：

- AFL edge coverage `new_bits` 未作为活跃 MAB reward 输入；
- `ss_new_bits_any` delta 在 `src/afl-fuzz-one.c` 中出现，但当前未形成活跃 update；
- validity reject 是执行前 skip，不作为显式负 reward；
- 4xx 有小额惩罚，但 5xx/timeout/conn_refused 当前作为异常发现信号给正奖励，这更像测试发现导向，不是安全等级导向。

## 5. 最小修复计划

### 5.1 统一 MAB 实现

建议把 `nv_arm_enabled`、`nv_mab_pick`、`nv_mab_update` 保留为单一实现，避免 `src/afl-fuzz-one.c` 和 `src/afl-fuzz-run.c` 双份漂移。

可选方案：

- 放到一个新的 `src/nv_mab.c` / `include/nv_mab.h`；
- 或保留在一个 C 文件中，另一个文件只调用声明，不复制实现。

### 5.2 修复 pick/update 归因

最小目标：哪个 arm 生成了输入，就用哪个 arm 接收 reward。

建议：

- 在 custom mutator 调用前 pick arm；
- 设置 `NV_CUR_ARM`；
- 将选中的 arm 保存在本次 trial 的字段中，例如 `afl->nv_mab.last_arm` 或更明确的 `pending_arm`；
- `common_fuzz_stuff` 不再无条件重新 pick；
- 执行后 update 使用该 pending arm。

如果需要覆盖 AFL 原生 mutation，可新增单独 arm，例如 `NV_ARM_AFL_NATIVE`，不要混入三类 JSON arm。

### 5.3 支持数组形式 `mutation_scope`

在 `src/afl-fuzz.c::nv_parse_scope` 增加数组解析：

- `"field_value"` -> `0x1`
- `"boundary"` -> `0x2`
- `"structure"` -> `0x4`

或在 `integration/fuzz_adapter.py` / runner 任务生成时，把数组转换为 bitmask 或逗号字符串。

推荐 C 侧和 adapter 侧都兼容，避免任务来源变化导致限制失效。

### 5.4 明确 reward v1 公式

建议形成可审计的 reward v1：

```text
reward = w_cov * ncov_delta
       + w_state * new_http_state
       + w_valid * validity_pass
       - w_invalid * validity_reject
       - w_error * unexpected_error
       + w_recovery * recovered
```

如果目标是漏洞发现，可保留 5xx/timeout 正奖励；如果目标是稳定性/安全性能评分，则应把异常作为惩罚。两类语义需要在文档中分开。

### 5.5 输出和报告补齐

最小补齐：

- `fuzzer_stats` 保留 MAB 字段；
- `plot_data` header 或说明补充 MAB 字段名称；
- `eval_report.json` 可选增加 `mab` 节点；
- 文档明确该机制是工程化 UCB/MAB 反馈变异，不是完整 NC_MAB 理论闭环。

## 6. 最小验证建议

不在本轮执行，只列出后续验证项：

1. 编译验证：

```text
make -j2 afl-fuzz
```

2. Python mutator 语法验证：

```text
python3 -m py_compile nv_json_mutator.py
```

3. 单 arm scope 验证：

- `mutation_scope=["field_value"]` 时，只允许 arm0 pulls 增长；
- `mutation_scope=["boundary"]` 时，只允许 arm1 pulls 增长；
- `mutation_scope=["structure"]` 时，只允许 arm2 pulls 增长。

4. 三 arm scope 验证：

- 三个 arm 都应有 pulls；
- mean_reward / sum_reward 应随执行更新；
- `NV_CUR_ARM` 与实际 Python mutator 分支一致。

5. 归因验证：

- 在最小本地 harness 中记录本次 pick arm；
- 确认 reward update 的 arm 与实际变异 arm 一致。

6. 统计验证：

- `fuzzer_stats` 中 MAB 字段存在且非异常；
- `plot_data` 追加字段格式稳定；
- summary/eval report 不回退。

## 7. 不能宣称

当前不能宣称：

- 完整 NC_MAB 理论闭环已完成；
- 完整自动化语义种子生成已完成；
- MAB reward 已严格绑定到每一次实际 JSON arm 变异；
- `mutation_scope` 数组形式已经可靠限制可用 arms；
- 当前 reward 等同于完整安全性能理论评价函数；
- 当前 MAB 已经过长时间稳定性和消融实验验证；
- Flowable 完整 AFL++ mutation-chain 已完成；
- 完整拟态系统级动态异构冗余已完成。

## 8. 最终表述建议

建议最终报告采用如下表述：

> 当前仓库已具备工程化 UCB/MAB 反馈变异策略雏形：实现了 field_value、boundary、structure 三类 JSON 变异 arm，具备 UCB 选择、HTTP 状态 reward 更新和 fuzzer_stats 统计输出；该机制可作为模糊测试组件的反馈变异增强基础。当前仍需修复 arm 归因、`mutation_scope` 数组解析和重复实现问题，因此不能宣称完整 NC_MAB 理论闭环已经完成。
