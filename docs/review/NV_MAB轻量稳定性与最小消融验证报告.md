# NV_MAB轻量稳定性与最小消融验证报告

## 1. 验证目的

本轮是在 NV_MAB 工程闭环基本完成后，补充轻量稳定性和最小多轮消融证据。

验证目标包括：

- 验证 `mutation_scope` 对 `field_value`、`boundary`、`structure` 三类 JSON 变异 arm 的限制能力；
- 验证 MAB 统计字段在多轮短运行中稳定输出；
- 验证本地短运行中无 crash、无 hang；
- 验证固定单 arm 与 all arms 自适应选择的多轮统计可比性。

本轮不是完整 NC_MAB 理论闭环，不是长时间稳定性实验，也不是完整论文级消融实验。

## 2. 轻量稳定性验证

验证设置：

| 项目 | 内容 |
|---|---|
| case | `nv_mab_all_stability` |
| mutation_scope | `["field_value","boundary","structure"]` |
| repeat | 3 |
| 输出目录 | `out/nv_mab_stability_run_1/`、`out/nv_mab_stability_run_2/`、`out/nv_mab_stability_run_3/` |
| 汇总文件 | `out/nv_mab_stability_summary.csv` |

每轮均保存：

- `task.json`
- `cmdline`
- `fuzzer_stats`
- `plot_data`
- `afl.log`

关键结果：

| run_id | exit_code | execs_done | saved_crashes | saved_hangs | total_pulls | arm0 | arm1 | arm2 | 判定 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0 | 67 | 0 | 0 | 59 | 57 | 1 | 1 | 通过 |
| 2 | 0 | 67 | 0 | 0 | 59 | 57 | 1 | 1 | 通过 |
| 3 | 0 | 67 | 0 | 0 | 59 | 57 | 1 | 1 | 通过 |

三轮均满足：

- exit_code 为正常退出；
- `saved_crashes=0`；
- `saved_hangs=0`；
- `nv_mab_total_pulls > 0`；
- 三个 arm 均有 pulls；
- `fuzzer_stats` 存在；
- `plot_data` 存在；
- NV_MAB 字段未缺失。

结论：NV_MAB 轻量稳定性验证通过。

该结论仅表示多轮本地短运行稳定通过，不表示长时间稳定性验证完成。

## 3. 最小多轮消融验证

验证设置：

| 实验组 | mutation_scope | repeat |
|---|---|---:|
| `fixed_field_value` | `["field_value"]` | 3 |
| `fixed_boundary` | `["boundary"]` | 3 |
| `fixed_structure` | `["structure"]` | 3 |
| `nv_mab_all` | `["field_value","boundary","structure"]` | 3 |

汇总文件：

- `out/nv_mab_ablation_summary.csv`

关键结果：

| group | run_id | total_pulls | arm0 | arm1 | arm2 | 判定 |
|---|---:|---:|---:|---:|---:|---|
| fixed_field_value | 1 | 48 | 48 | 0 | 0 | 通过 |
| fixed_field_value | 2 | 47 | 47 | 0 | 0 | 通过 |
| fixed_field_value | 3 | 58 | 58 | 0 | 0 | 通过 |
| fixed_boundary | 1 | 48 | 0 | 48 | 0 | 通过 |
| fixed_boundary | 2 | 47 | 0 | 47 | 0 | 通过 |
| fixed_boundary | 3 | 57 | 0 | 57 | 0 | 通过 |
| fixed_structure | 1 | 48 | 0 | 0 | 48 | 通过 |
| fixed_structure | 2 | 47 | 0 | 0 | 47 | 通过 |
| fixed_structure | 3 | 59 | 0 | 0 | 59 | 通过 |
| nv_mab_all | 1 | 48 | 46 | 1 | 1 | 通过 |
| nv_mab_all | 2 | 47 | 45 | 1 | 1 | 通过 |
| nv_mab_all | 3 | 59 | 57 | 1 | 1 | 通过 |

结论：

- `fixed_field_value` 仅 arm0 增长；
- `fixed_boundary` 仅 arm1 增长；
- `fixed_structure` 仅 arm2 增长；
- `nv_mab_all` 中三个 arm 均获得 pulls；
- 各组均可通过相同字段进行横向比较。

NV_MAB 最小多轮消融验证通过。

该结论只证明多轮消融框架和统计可比性成立，不表示完整消融实验完成，也不要求证明 `nv_mab_all` 一定优于所有固定 arm。

## 4. 阶段性结论

当前 NV_MAB 已完成工程闭环，并通过轻量稳定性与最小多轮消融验证。该结果进一步证明 `field_value`、`boundary`、`structure` 三类 JSON 变异 arm 可以受 `mutation_scope` 控制，并能在多轮本地运行中稳定输出 MAB 统计。

该验证可支撑 NV_MAB 作为 NC_MAB 的工程化阶段性实现。

## 5. 边界

仍不能宣称：

- 完整 NC_MAB 理论闭环完成；
- 完整自动化语义种子生成完成；
- 长时间稳定性实验完成；
- 完整论文级消融实验完成；
- reward 已经是严格理论收益函数或完整代码覆盖率；
- 完整拟态系统级 DHR 完成。

当前 reward 仍是工程化覆盖代理和 HTTP 状态反馈。本轮验证适合支撑阶段性工程验收和总项目集成联调，不应被过度解释为最终理论模型闭环。
