# 广义功能安全模糊测试组件（任务4）

## 1. 项目说明

本仓库面向“任务4：广义鲁棒控制构造内生安全性测试评估研究”，实现三项任务：

1. 基于模糊测试的内生安全性能评估模型；
2. 高质量种子文件和模糊测试用例生成方法；
3. 基于模糊测试的内生安全性能测评方法。

当前正式主线为 `main`。任务4核心代码冻结版本：

- Tag：`task4-final-20261005`
- Core freeze commit：`2ca3c6c660ab78f90422abe90a04b33840297ee6`

后续如仅增加 README、操作手册或复现脚本，可继续提交到 `main`；上述 tag 用于固定任务4核心代码版本。

## 2. 项目要求与代码对应

| 项目要求 | 主要实现文件 |
|---|---|
| 内生安全性能评估模型 | `scripts/compute_formal_security_score.py`、`src/afl-fuzz-run.c`、`src/afl-fuzz-stats.c` |
| 高质量种子与测试用例生成 | `nv_json_mutator.py`、`nv_url_query.py`、`src/afl-fuzz-one.c`、`src/afl-fuzz-queue.c`、`include/afl-fuzz.h` |
| 有效性验证与执行反馈 | `nv_body_valid.py`、`nv_http_harness.py`、`nv_state_probe.py` |
| 平台任务接口 | `integration/fuzz_api.py`、`integration/api_server.py` |
| 任务配置 | `task_configs/`、`task_calendar_filter_bounded.json`、`targets/` |
| 验收测试 | `tests/test_formal_security_score.py`、`tests/test_api_formal_schema_compliance.py`、`tests/test_delivery_platform_interfaces.py`、`tests/test_fuzz_api.py`、`tests/test_url_query.py`、`tests/test_query_integration.py` |

正式安全评分公式：

```text
P_sec = β1 × Cov + β2 × (1 / (1 + Err)) + β3 × R_rec
```

其中：

```text
Cov   = security_state_new_total / security_state_capacity
Err   = nv_err_exec / nv_total_valid_exec
R_rec = nv_rec_success / nv_rec_total
β1 + β2 + β3 = 1
```

权重必须显式提供，不在程序中虚构默认项目权重。

## 3. 快速开始

```bash
git clone https://github.com/cphzyl1611/AFL-.git
cd AFL-
git switch main
chmod +x scripts/run_task4.sh scripts/reproduce_task4.sh
./scripts/run_task4.sh
```

默认的一键脚本只执行自包含验证，不访问真实 O2OA / Alfresco 服务。

如需严格复现任务4核心冻结版本：

```bash
git checkout task4-final-20261005
```

## 4. 一键验证

```bash
./scripts/run_task4.sh
```

默认执行：

1. 环境检查；
2. 必要时构建 `afl-fuzz`；
3. 任务4 focused acceptance tests；
4. URL-query 集成测试；
5. 本地 API smoke；
6. 输出最终 PASS/FAIL。

## 5. 生成复现记录

```bash
./scripts/reproduce_task4.sh
```

复现结果写入：

```text
reproduce-results/task4-<timestamp>/
```

完整历史回归为诊断模式：

```bash
./scripts/reproduce_task4.sh --full
```

历史完整测试集包含已知的前置/历史测试债，因此正式任务4复核优先看 focused acceptance gate。

## 6. 平台接口

`integration/fuzz_api.py` 提供：

- `fuzz_test_submit`
- `fuzz_test_query`
- `fuzz_test_stop`
- `fuzz_test_report_query`

正式 submit 字段：

```text
target_type
target_endpoint
seed_source
seed_location
mutation_scope
max_test_cases
time_budget
task_name (optional)
```

正式枚举：

```text
target_type:    http_api | file_upload | protocol_message
seed_source:    captured_traffic | seed_file | manual
mutation_scope: field_value | boundary | structure
```

“schema 可接受”和“当前 runtime 可实际调度”是两个概念，具体能力状态以 `integration/fuzz_api.py` 中 capability table 为准。

## 7. 本地集成 API

```bash
python3 integration/api_server.py --host 127.0.0.1 --port 18081
```

常用入口：

```text
GET  /health
GET  /capabilities
GET  /reports
POST /score/alfresco_ae_v1
POST /fuzz/submit
```

该 API 用于本地/集成验证，不等同于完整生产网关。

## 8. 真实 O2OA 运行

真实 O2OA 场景需要：

- O2OA 服务已启动；
- `targets/o2oa_query.json` 中目标地址可达；
- 运行时提供 `NV_TOKEN`；
- 不在配置文件或脚本中硬编码 token。

示例：

```bash
export NV_TOKEN='<runtime-token>'
export NV_TARGET_CONFIG="$PWD/targets/o2oa_query.json"
export NV_ENDPOINT_NAME=calendar_filter
```

默认一键脚本不会自动访问真实业务服务。

## 9. 正式评分

已有 `fuzzer_stats` 后：

```bash
python3 scripts/compute_formal_security_score.py \
  out/<run>/fuzzer_stats \
  <beta1> <beta2> <beta3>
```

三个权重必须位于 `[0,1]` 且总和约等于 `1.0`。

## 10. 操作手册

完整说明见：

```text
docs/TASK4_操作手册.md
```

## 11. 交付边界

README、操作手册和复现工具用于降低交付、复核和后续集成成本，不重新定义任务4算法口径。真实平台运行受外部服务、凭据、网络和部署状态影响；真实服务测试应在已授权环境中执行，并通过环境变量提供凭据。
