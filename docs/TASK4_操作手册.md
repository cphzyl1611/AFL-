# 任务4模糊测试组件操作手册

## 1. 手册目的

本手册用于指导项目成员从干净 Git clone 开始，完成任务4模糊测试组件的环境准备、代码构建、自包含验收验证、任务配置、平台接口调用、正式评分、复现材料生成和常见问题排查。

当前任务4核心冻结版本：

```text
tag: task4-final-20261005
commit: 2ca3c6c660ab78f90422abe90a04b33840297ee6
```

## 2. 与项目任务书对应关系

### 2.1 任务4.1：基于模糊测试的内生安全性能评估模型

主要实现：

```text
scripts/compute_formal_security_score.py
src/afl-fuzz-run.c
src/afl-fuzz-stats.c
include/afl-fuzz.h
```

正式公式：

```text
P_sec = β1 × Cov + β2 × (1 / (1 + Err)) + β3 × R_rec
```

指标来源：

```text
Cov   = security_state_new_total / security_state_capacity
Err   = nv_err_exec / nv_total_valid_exec
R_rec = nv_rec_success / nv_rec_total
```

Cov 表示项目定义的安全状态覆盖，不等同于 AFL++ 原生 edge coverage。

### 2.2 任务4.2：高质量种子文件和模糊测试用例生成方法

主要实现：

```text
nv_json_mutator.py
nv_url_query.py
src/afl-fuzz-one.c
src/afl-fuzz-queue.c
include/afl-fuzz.h
in/
task_configs/
```

当前能力包括 JSON body 结构化变异、URL query 表示/编码/变异、`field_value / boundary / structure` 三类 mutation scope、MAB 策略选择、安全状态贡献 seed 调度以及有效性过滤接口。

### 2.3 任务4.3：基于模糊测试的内生安全性能测评方法

主要实现：

```text
nv_http_harness.py
nv_body_valid.py
nv_state_probe.py
src/afl-fuzz-run.c
src/afl-fuzz-stats.c
integration/fuzz_api.py
integration/api_server.py
```

执行闭环：

```text
任务配置
  ↓
种子选择
  ↓
变异策略选择
  ↓
结构化用例生成
  ↓
有效性检查
  ↓
目标执行
  ↓
安全状态 / 异常 / 恢复统计
  ↓
反馈到 seed / MAB
  ↓
fuzzer_stats / eval_report / formal score
```

## 3. 关键目录

| 路径 | 用途 |
|---|---|
| `include/` | AFL++ 核心数据结构和 NV 扩展状态 |
| `src/` | 调度、执行、统计等 C 代码 |
| `nv_json_mutator.py` | JSON / 结构化变异 |
| `nv_url_query.py` | URL query 解析、构造和变异 |
| `nv_http_harness.py` | HTTP 执行、认证、状态反馈 |
| `nv_body_valid.py` | 输入有效性判定 |
| `nv_state_probe.py` | 安全状态记录 |
| `integration/fuzz_api.py` | submit/query/stop/report_query |
| `integration/api_server.py` | 本地轻量集成 API |
| `scripts/compute_formal_security_score.py` | 正式三项指标评分 |
| `task_configs/` | 任务模板 |
| `targets/` | O2OA / Alfresco 目标配置 |
| `in/` | seed / 数据集 |
| `tests/` | 回归和验收测试 |
| `out/` | 运行输出与已有 evidence |

## 4. 首次安装

```bash
git clone https://github.com/cphzyl1611/AFL-.git
cd AFL-
python3 --version
python3 -m pip install -U pytest
make -j"$(nproc)"
```

确认：

```bash
test -x ./afl-fuzz
git status --short
```

如使用虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip pytest
```

不要提交 `.venv/`。

## 5. 一键操作

### 5.1 快速交付验证

```bash
./scripts/run_task4.sh
```

特点：默认离线、不要求 O2OA/Alfresco 在线、不读取真实凭据。

### 5.2 正式生成复现记录

```bash
./scripts/reproduce_task4.sh
```

输出示例：

```text
reproduce-results/task4-YYYYmmdd-HHMMSS/
├── git.txt
├── environment.txt
├── build.log
├── focused-tests.log
├── query-integration.log
├── api-server.log
├── api-smoke.log
├── RESULT.txt
└── SHA256SUMS.txt
```

### 5.3 完整历史回归

```bash
./scripts/reproduce_task4.sh --full
```

full mode 用于记录整体历史测试状态，不作为唯一任务4合格判据。

## 6. Focused acceptance gate

默认运行：

```bash
python3 -m pytest \
  tests/test_formal_security_score.py \
  tests/test_api_formal_schema_compliance.py \
  tests/test_delivery_platform_interfaces.py \
  tests/test_fuzz_api.py \
  tests/test_url_query.py \
  -k "not test_filter_by_task_name" \
  -q
```

并运行：

```bash
python3 -m pytest tests/test_query_integration.py -q
```

`test_filter_by_task_name` 为已知历史挂起测试，因此在 focused gate 中显式排除。

## 7. 任务配置

推荐使用仓库相对路径：

```json
{
  "target_type": "http_api",
  "target_endpoint": "calendar_filter",
  "seed_source": "seed_file",
  "seed_location": "in/o2oa_body",
  "mutation_scope": ["field_value", "boundary", "structure"],
  "max_test_cases": 20,
  "time_budget": 120,
  "task_name": "calendar_filter_demo"
}
```

正式枚举：

```text
target_type:    http_api | file_upload | protocol_message
seed_source:    captured_traffic | seed_file | manual
mutation_scope: field_value | boundary | structure
```

formal schema 支持不代表当前 runtime 一定已实现。实际 dispatch 能力以 `integration/fuzz_api.py` 中 `TARGET_TYPE_CAPABILITY` 和 `SEED_SOURCE_CAPABILITY` 为准。

### 7.1 路径要求

不要使用本机旧 worktree 绝对路径，例如：

```text
/home/<user>/old-worktree/in/o2oa_body
```

应使用：

```text
in/o2oa_body
```

## 8. O2OA 实际运行

目标配置：

```text
targets/o2oa_query.json
```

当前配置要求运行时 token：

```bash
export NV_TOKEN='<runtime token>'
export NV_TARGET_CONFIG="$PWD/targets/o2oa_query.json"
export NV_ENDPOINT_NAME=calendar_filter
```

真实 token 只放在当前 shell 环境，不写入 Git。

运行前可做服务预检查：

```bash
python3 - <<'PY'
import urllib.request
for u in ("http://127.0.0.1:80/", "http://127.0.0.1:20020/"):
    try:
        with urllib.request.urlopen(u, timeout=3) as r:
            print(u, r.status)
    except Exception as e:
        print(u, "UNAVAILABLE", type(e).__name__)
PY
```

服务不可用时，应先区分服务未启动、网络、认证和配置问题，不自动解释为组件算法失败。

## 9. 平台接口

Python 入口：

```python
from integration.fuzz_api import (
    fuzz_test_submit,
    fuzz_test_query,
    fuzz_test_stop,
    fuzz_test_report_query,
)
```

提交示例：

```python
from integration.fuzz_api import fuzz_test_submit

result = fuzz_test_submit({
    "target_type": "http_api",
    "target_endpoint": "calendar_filter",
    "seed_source": "seed_file",
    "seed_location": "in/o2oa_body",
    "mutation_scope": ["field_value", "boundary", "structure"],
    "max_test_cases": 20,
    "time_budget": 120,
    "task_name": "calendar_filter_demo",
})
print(result)
```

本地 HTTP API：

```bash
python3 integration/api_server.py --host 127.0.0.1 --port 18081
```

检查：

```bash
python3 - <<'PY'
import json, urllib.request
for path in ("/health", "/capabilities"):
    with urllib.request.urlopen("http://127.0.0.1:18081" + path, timeout=3) as r:
        print(path, r.status, json.loads(r.read().decode()))
PY
```

## 10. 输出与评分

典型运行目录：`out/`。

`fuzzer_stats` 重点字段：

```text
nv_total_valid_exec
nv_err_exec
nv_err_rate
nv_rec_total
nv_rec_success
nv_rec_rate
security_state_new_total
security_state_capacity
nv_mab_total_pulls
```

正式评分：

```bash
python3 scripts/compute_formal_security_score.py \
  <fuzzer_stats> \
  <beta1> <beta2> <beta3>
```

权重必须由项目配置明确给出，不得自行假设。

## 11. URL Query 支持

实现：`nv_url_query.py`。

测试：

```bash
python3 -m pytest \
  tests/test_url_query.py \
  tests/test_query_integration.py \
  -q
```

当前 O2OA 配置中的 5 个 endpoint 主要使用 POST/PUT JSON body；URL-query framework 已实现，但是否在真实 O2OA endpoint 中触发取决于部署接口形态。

## 12. 常见问题

### `afl-fuzz not found`

```bash
make -j"$(nproc)"
```

### `seed_location does not exist`

```bash
ls -la in/o2oa_body
```

并使用相对路径 `in/o2oa_body`。

### `NV_TOKEN must be supplied`

```bash
export NV_TOKEN='...'
```

只放环境变量，不写入配置。

### 本地 API 端口占用

```bash
ss -ltnp | grep 18081
```

可改为：

```bash
TASK4_API_PORT=18082 ./scripts/run_task4.sh
```

### Full regression 有历史失败

先运行：

```bash
./scripts/run_task4.sh
```

如果 focused gate PASS，而 full regression 仅出现已记录的历史/环境依赖测试债，不应自动解释为任务4当前实现回归。

## 13. 版本建议

核心冻结 tag 保留：

```text
task4-final-20261005
```

补充 README、操作手册和脚本后，建议另打交付 tag：

```text
task4-delivery-20261005
```

这样核心代码冻结点与最终用户可操作交付点可以同时保留。

## 14. 安全边界

- 不在 Git 中保存真实 token、password、cookie、private key；
- 真实服务测试前确认目标为项目授权环境；
- 默认一键脚本只做自包含验证，不自动访问真实业务系统；
- live 运行必须显式提供 target config 和环境变量；
- `out/` 中若含真实业务数据，交付前按项目要求脱敏。
