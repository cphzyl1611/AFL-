# Deep2Fuzz-ES 操作与平台接入指南

> 对应河南重大专项 Task 4 模糊测试测评组件

本手册面向第一次接触仓库、不会 AFL++、不了解 Python 或 HTTP 的读者。目标是让你完成两件事：

返回项目总览与快速开始：[README_TASK4.md](../README_TASK4.md)。

1. 从一个干净目录固定 Task 4 committed source，完成官方离线复现和 sample；
2. 在你拥有授权的本地/测试 REST 平台上，从一个最小 bounded scenario 开始接入、验证 readback、cleanup、状态反馈和报告。

本手册只描述已冻结技术能力和安全的接入边界。它不修改算法、评分语义或平台场景，不启动 O2OA/Alfresco，不使用真实凭据，不执行新的科研实验，也不替代正式验收材料。

> **安全提示：** 只有在平台属于你或你明确获得自动化测试授权时才继续。所有写入都应指向 disposable 测试对象，并且必须有可验证的 cleanup。生产 URL、生产对象和无法删除的对象不适合作为第一轮接入目标。

## 0. 一小时路线

| 阅读时间 | 目标 | 主要章节 |
|---|---|---|
| 0–10 分钟 | 了解 seed、mutation、validity、target、readback 和三个指标。 | 第一部分 |
| 10–20 分钟 | 安装系统包、Python 3.12 和 venv。 | 第二、三部分 |
| 20–35 分钟 | 运行官方离线 test set。 | 第四部分 |
| 35–45 分钟 | 运行 sample 并找到 report。 | 第五、六部分 |
| 45–60 分钟 | 选择 JSON/query/text/multipart 路径，准备自己的平台接入表。 | 第七至第十五部分 |

## 1. 先建立共同语言

### 1.1 Seed（种子）

Seed 是一个已经保存的输入样例。它可以是 JSON 文件、包含 URL query 的 JSON envelope、raw text 文件，或完整 multipart/HTTP seed。一个好的 seed 结构合法、字段接近真实业务、大小适中、没有密码/token，也不指向生产对象。

仓库中可以看到例如 `in/p0_o2oa_cms_doc_list/`、`in/o2oa_body_cms_score/`、`in/alfresco_metadata_update_dataset/` 等真实目录。seed 文件不是凭据存储，也不应该包含完整 Authorization header。

### 1.2 Mutation（变异）

Mutation 是从 seed 生成 testcase 的过程。当前项目把它分为三类：

- `field_value`：改变一个字段的值；
- `boundary`：尝试空值、长度边界、数值边界等；
- `structure`：改变对象结构、列表或嵌套关系。

`nv_json_mutator.py`、`nv_url_query.py` 和 `nv_text_mutator.py` 是真实实现。multipart 的结构处理在 `nv_http_harness.py` 的 multipart 路径中完成。

### 1.3 Validity filter（有效性过滤器）

Validity filter 在目标请求前检查 testcase。规则后端读取 `validity/*.json`；可选 scorer 通过 Unix socket/RPC 参与。规则拒绝或 scorer 拒绝的 testcase 不应被当成一次真实目标执行，也不应产生错误的业务 feedback。

默认接入顺序建议是：先 rule-only，确认接口映射；再按需要启用 AE；最后才评估可选 SE reference backend。新平台不需要一开始训练模型。

### 1.4 Target、platform、scenario

Target 是实际接收请求的目标。Platform 是目标所属系统，例如 O2OA 或 Alfresco。Scenario 是一次明确的业务动作，例如 O2OA `cms_document_create_save` 或 Alfresco `document_metadata_update`。一个 scenario 应尽量只描述一种读写意图和一种结果判定方式。

### 1.5 Harness 与 adapter

Harness（执行线束）负责从 seed 解析请求、注入运行时认证、发送请求、分类响应并写状态。当前核心是 `nv_http_harness.py`。Adapter（适配器）负责把平台业务语义映射到通用 runner；当前 runner/adapter 入口在 `runner/fuzz_test_runner.py` 和 `integration/fuzz_adapter.py`。

### 1.6 Readback 与 cleanup

Readback 是在写入后用独立的 GET 或业务查询验证“写入内容确实存在且语义正确”。仅收到 2xx 不足以证明业务成功。Cleanup 是删除本次 run 创建的对象，必须按本次 run 保存的 exact ID 做，不能按模糊标题批量删除。

### 1.7 Security-state proxy、Cov、Err、Rec

Security-state proxy 是可观察的状态代理。当前规范化表示是：

```text
METHOD PATH|RESPONSE_CLASS
```

其中 method 会折叠到有限的已知集合，path 会保留可用路径或折叠到固定 malformed label，response class 归入 2xx、3xx、4xx、5xx、timeout、conn_refused 等类别。它是工程上可审计的代理，不是目标内部全部状态。

- **Cov**：新 security-state 数量除以固定 capacity；当前 capacity 是 65536。
- **Err**：在声明的 HTTP、execution 和 business-ledger 范围内的异常代理。
- **Rec**：在存在恢复机会时，平台恢复并通过后续检查的比例。
- **reward**：把新状态、异常、恢复等反馈按实现中的权重组合成 arm 的更新信号。

### 1.8 NC_MAB 与 bounded run

NC_MAB 是非平稳/有约束场景下的多臂老虎机策略选择机制。每个 arm 代表一个 mutation strategy。一次 pull 必须有选择、有效性通过、目标执行、反馈、归因和 commit，不能只把“生成过”算成 pull。Warm-up 是让各 arm 先获得最低探索次数；达到条件后才可能进入 UCB（Upper Confidence Bound，上置信界）选择。

Bounded run 指明 test case 上限、时间预算、输出目录和 cleanup 范围。它让真实平台风险可控，也让 evidence 可以复核。

### 1.9 Evidence（证据）

Evidence 是 run 产生的结构化输出：task、状态、ledger、trace、summary、report、输入 manifest 和 secret scan。它应放在仓库外的新目录，避免覆盖历史 evidence；不得存放密码、token、Cookie 或完整 Authorization header。

## 2. 环境准备

### 2.1 支持环境与内存约束

交付 evidence 使用 Ubuntu 24.04 LTS on WSL2、x86_64、Python 3.12.x、GCC/Make 和 16 GB host memory。请按顺序运行命令，不要并行编译和 live 平台服务。离线路径不启动 Docker、O2OA、Alfresco 或 model server。

### 2.2 真实依赖来源

以下不是猜测，而是 committed source 的 `requirements.txt`、`requirements-dev.txt`、`requirements-live.txt`、`docs/DEPENDENCIES.md` 和 `scripts/run_task4_offline.sh` 的交集：

| 依赖 | 是否必须 | 作用 |
|---|---:|---|
| Python 3.12 | 是 | 运行标准库路径、pytest 和脚本。 |
| `python3.12-venv` | 是 | 建立隔离虚拟环境。 |
| `python3-pip` | 是 | 安装 dev test wheels。 |
| `build-essential` | 是 | GCC、Make、libc development files。 |
| `python3.12-dev` | 是 | `Python.h`、libpython 和 C feedback probes。 |
| `zlib1g-dev` | 是 | AFL++/C 编译所需 zlib headers。 |
| `coreutils` | 是 | `timeout` safety bound。 |
| pytest 及 dev wheels | 是（离线 test set） | 执行固定测试集合。 |
| `requests` | 否 | 仅 optional live multipart harness；离线命令不需要。 |
| PyTorch/NumPy/pandas/matplotlib | 否 | 模型或分析 extras；不是官方 offline smoke 的前置条件。 |

### 2.3 验证命令

**目的：** 在安装前确认 Python、编译器和 C/Python 头文件可见。

```bash
command -v python3.12
command -v gcc
command -v make
command -v python3-config
command -v timeout
python3.12 --version
python3-config --includes
python3-config --embed --ldflags
```

**成功：** 所有 `command -v` 输出路径；Python 是 3.12.x；includes 输出包含 Python include；embed flags 能返回链接参数。

**失败排查：**

- `python3.12` 不存在：安装 `python3.12`、`python3.12-venv`、`python3.12-dev`。
- `gcc`/`make` 不存在：安装 `build-essential`。
- `python3-config` 不存在：安装对应 `python3.12-dev`，不要用另一版本的头文件混编。
- `timeout` 不存在：安装 `coreutils`。

这一步不访问 O2OA/Alfresco，也不需要任何凭据。

## 3. 从全新目录安装

### Step 1 — Obtain source（获取源码）

**目的：** 将源码放入一个不会混入旧工作树修改的新目录。

```bash
git clone <repository-url> AFL-
cd AFL-
```

**结果：** 出现 `AFL-/.git` 和源码目录。

**失败排查：** `<repository-url>` 是占位符；用项目提供的授权 Git 地址或本地镜像替换它。不要在网络不可信时把凭据嵌入 URL。

### Step 2 — Checkout exact checkpoint（固定版本）

**目的：** 防止未提交代码、别的分支或历史版本混入交付复现。

```bash
git checkout 36e7cdd69c26bffde7c047d34f116e438ba60c81
git rev-parse HEAD
git status --short
```

**成功：** HEAD 等于 `36e7cdd69c26bffde7c047d34f116e438ba60c81`；新 clone 通常没有工作树修改。`git status` 只读，不会改变文件。

**失败：** 如果提交不在本地，先确认 clone 的镜像包含该提交；不要用 `reset --hard`、`clean` 或 stash 代替版本核验。

### Step 3 — Create venv（创建虚拟环境）

**目的：** 把 pytest 和测试依赖与系统 Python 分开。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
```

**成功：** `.venv/bin/python` 和 `.venv/bin/pytest` 存在，且下面的命令返回 pytest 版本：

```bash
.venv/bin/python -c 'import pytest; print(pytest.__version__)'
```

**网络/凭据：** pip 安装可能访问 package index；这不是平台访问，不需要 O2OA/Alfresco 凭据。若你必须完全离线安装，请预先准备受信任 wheel cache，再把 pip 的安装源指向该 cache；不要把 cache 中的凭据写入仓库。

### Step 4 — Expose matching python3-config（准备 C probe）

**目的：** venv 的 Python 与系统 CPython headers 要匹配。

```bash
cp scripts/python3-config-wrapper.sh .venv/bin/python3-config
chmod 0755 .venv/bin/python3-config
.venv/bin/python3-config --includes
.venv/bin/python3-config --embed --ldflags
```

**成功：** 两个 flag 命令成功。wrapper 只转发到系统 `python3-config`，不修改源代码。

### Step 5 — Build native binary（构建 AFL++）

**目的：** 官方 offline runner 会在缺少 `afl-fuzz` 时构建它；提前构建可以让错误更早暴露。

```bash
make -j2 afl-fuzz
./afl-fuzz -h >/dev/null
```

**成功：** `afl-fuzz -h` 退出码为 0。`-j2` 是在 16 GB 主机上顺序/低并发的保守设置。

**失败排查：** 查看第一个 GCC error；`Python.h` 缺失回到 Step 4 及 `python3.12-dev`；zlib header 缺失安装 `zlib1g-dev`；不要通过删除断言或改代码绕过构建错误。

### Step 6 — Run import isolation（验证导入来源）

**目的：** 确认 Python 从当前 checkout 导入，而不是旧 worktree 或 `$HOME` 中的同名模块。

```bash
PYTHONPATH="$PWD" .venv/bin/python -c 'import nv_http_harness, nv_body_valid, nv_json_mutator; print(nv_http_harness.__file__); print(nv_body_valid.__file__); print(nv_json_mutator.__file__)'
```

**成功：** 三个路径都位于当前 checkout。若路径指向其他目录，清理当前 shell 的 `PYTHONPATH` 后重新设置为 `$PWD`，并从新 shell 重试；不要依赖旧 venv。

### Step 7 — Validate project configs（验证配置）

**目的：** 在任何 fuzz 或平台访问前检查 schema、seed、rules、模型元数据和 summary contracts。

```bash
PYTHON_BIN="$PWD/.venv/bin/python" PYTHONHASHSEED=0 "$PWD/scripts/validate_project_configs.py"
```

**成功：** 末尾输出 `PROJECT_CONFIG_VALIDATION=PASS`（具体检查行可以很多）。此命令只读本地文件，不访问真实平台或读取平台凭据。

## 4. 官方离线复现

### Step 8 — Run the official bounded test set

**目的：** 复现交付 acceptance 定义的固定 offline scope，而不是递归运行整个仓库。

```bash
PYTHON_BIN="$PWD/.venv/bin/python" ./scripts/run_task4_offline.sh
```

**执行内容：** 先验证 configs 和 delivery preflight；如缺 `afl-fuzz` 则执行 `make -j2 afl-fuzz`；然后按脚本内的显式 `TEST_FILES` 列表运行 pytest，再运行三个代表性 feedback attribution tests。脚本清除 proxy 环境变量并使用 `PYTHONHASHSEED=0`。

**成功条件：** exit code 0、末尾 `TASK4_OFFLINE=PASS`，并与 immutable acceptance 一致：235 discovered、235 passed、0 errors、0 stable failures、0 skipped、1 deselected。`1 deselected` 是脚本用 `-k "not test_filter_by_task_name"` 排除的测试，不是失败。

**失败排查：**

1. 先保存完整终端输出，不要只看最后一行；
2. 运行 `git rev-parse HEAD`，确认 checkpoint；
3. 运行 `command -v python3-config timeout make`；
4. 用 `PYTHON_BIN=... scripts/validate_project_configs.py` 单独重现配置错误；
5. 不要把历史 broad discovery count 当作本次 official scope；
6. 不要把测试脚本改成递归发现来“补齐”数量。

## 5. 第一次运行 delivery sample

### Step 9 — 运行 sample

**目的：** 生成一个全新、本地、无网络的端到端 structural smoke。

```bash
PYTHON_BIN="$PWD/.venv/bin/python" ./scripts/run_task4_sample.sh
```

sample 脚本会：

1. 在 `reproduce-results/delivery-smoke-<timestamp>/` 新建目录；
2. 写入 run-local `task.json` 和 `target.json`；
3. 使用提交的 `in/p0_o2oa_cms_doc_list/` 四个本地 seed；
4. 启动 bounded `afl-fuzz` 加 `targets/nv_p0_deterministic_target.py`；
5. 写入原始 AFL/status/summary 文件；
6. 计算 formal score；
7. 生成并校验 `sample_eval_report.json`、`sample_fuzzer_stats.txt`、`sample_summary.md`、`sample_metadata.json`。

**成功：** `TASK4_SAMPLE=PASS`，并打印 `SAMPLE_DIR=...`。sample 明确标为 `DELIVERY_SMOKE_ONLY` 和 `NOT_FOR_PERFORMANCE_CLAIM`，没有网络和 live service。

### Step 10 — 找到输出

```bash
SAMPLE_DIR=<SAMPLE_DIR_FROM_PREVIOUS_COMMAND>
find "$SAMPLE_DIR" -maxdepth 1 -type f -printf '%f\n' | sort
cat "$SAMPLE_DIR/sample_eval_report.json"
cat "$SAMPLE_DIR/sample_summary.md"
```

`<SAMPLE_DIR_FROM_PREVIOUS_COMMAND>` 必须替换成实际路径。不要把尖括号占位符直接交给 shell。

### 5.1 十个安装步骤的边界总表

下面的表把每一步会产生什么、是否可能联网以及是否需要平台凭据列在一起。这样可以区分“安装依赖时访问软件包源”和“访问真实业务平台”两种完全不同的网络行为。

| 步骤 | 会产生或修改的文件 | 网络边界 | O2OA/Alfresco 凭据 |
|---|---|---|---|
| 1 获取源码 | 新的 `AFL-/.git/` 和源码工作树 | `git clone` 可能访问项目 Git 地址 | 不需要；不要把凭据写进 clone URL |
| 2 固定 checkpoint | 当前 checkout 的工作树状态 | 只读本地提交对象；缺提交时需要回到已授权镜像 | 不需要 |
| 3 venv 和 dev 依赖 | `.venv/` 及其 site-packages | pip 可能访问配置的软件包源；可改用受信任 wheel cache | 不需要平台凭据 |
| 4 `python3-config` wrapper | `.venv/bin/python3-config` | 本地文件复制和 flag 检查 | 不需要 |
| 5 native build | `afl-fuzz` 及编译中间产物 | 本地 GCC/Make；不访问服务 | 不需要 |
| 6 import isolation | 不应产生持久业务文件；命令只打印模块路径 | 本地 Python import | 不需要 |
| 7 config validation | 只读解析 config、rules、seed 和 schema；没有固定 run root | 本地 Python；不访问服务 | 不需要 |
| 8 offline gate | 终端 pytest 结果及测试临时文件；没有固定 live evidence root | entrypoint 清除代理，不访问平台 | 不需要 |
| 9 delivery sample | 新的 `reproduce-results/delivery-smoke-<timestamp>/` 及第 6 节文件 | 本地 AFL++ 和 deterministic target；`sample_metadata.json` 应标记 `network=none` | 不需要 |
| 10 查看输出 | 只读打开 sample 文件，不产生新业务状态 | 本地文件系统 | 不需要 |

如果其中任何一步出现平台 URL、Authorization header、Cookie 或业务对象 ID，说明命令边界被错误扩大；先停止并检查是否误用了 live runner。pip 使用的私有包源凭据属于包管理器配置，也不能写入仓库或 sample evidence。

## 6. 输出文件说明

### 6.1 delivery sample 的真实 artifact

| 文件 | 谁生成 | 作用 | 新手看什么 | 是否可删 |
|---|---|---|---|---|
| `task.json` | `scripts/run_task4_sample.py` | run-local task contract。 | target type、seed、mutation scope、预算和 validity。 | 可以，sample 已归档后可删。 |
| `target.json` | `scripts/run_task4_sample.py` | run-local endpoint contract。 | endpoint path 和 method。 | 可以。 |
| `afl_console.log` | sample wrapper | AFL 控制台输出。 | 是否正常启动、是否超时退出。 | 可以保留用于排错。 |
| `fuzzer_stats` | AFL++ | 原始计数。 | valid exec、Err/Rec、security-state、MAB 字段。 | 不建议在验收前删除。 |
| `nv_http_status.json` / `.seq` | harness | 最后一次状态和 execution sequence sidecar。 | response code、method、path、state delta。 | 可由临时 sample 删除。 |
| `security_states.jsonl` | deterministic target | sample 的状态观察。 | 状态是否增长、是否重复。 | 建议保留。 |
| `eval_report.json` | sample/summary | 汇总后的结构化报告。 | `coverage_rate`、`anomaly_rate`、`recovery_rate`、`overall_score`。 | 建议保留。 |
| `summary.csv` | summary writer | 每 run 的表格化摘要。 | `summary_source`、`execution_scope`、`metric_semantics`。 | 建议保留。 |
| `sample_eval_report.json` | sample wrapper | 对外最易读的 sample report。 | 是否满足必需字段和 scope 标记。 | 建议保留。 |
| `sample_fuzzer_stats.txt` | sample wrapper | 原始 stats 的副本。 | 与 report 的计数是否一致。 | 可删但不建议。 |
| `sample_summary.md` | sample wrapper | 人类可读摘要。 | scope 和四个指标。 | 可删但不建议。 |
| `sample_metadata.json` | sample wrapper | 说明无网络、fresh output 和文件清单。 | `network=none`、`live_service=false`。 | 建议保留。 |

### 6.2 平台 runner 的 run-scoped artifact

使用 `runner/fuzz_test_runner.py` 或平台 bounded runner 时，输出根目录必须在仓库外。真实 layout 由 `runner/fuzz_test_runner.py` 创建：

```text
<run-root>/
├── tasks/<task-id>/task.json
├── tasks/<task-id>/status.json
├── tasks/<task-id>/report.json
└── runs/<task-id>/
    ├── afl_out/
    ├── evidence/status.jsonl
    ├── evidence/executions.jsonl
    ├── evidence/mab_updates.jsonl
    ├── evidence/seed_selection.jsonl
    ├── nv_state_trace.jsonl
    ├── nv_ctx.json
    ├── nv_http_status.json
    ├── nv_body_valid_stats.json
    └── stdout.log / stderr.log
```

`execution_ledger.jsonl` 是部分历史/平台脚本的描述名；当前 runner 的标准文件名是 `evidence/executions.jsonl`。不要在报告里把不存在的文件名写成必然产物。

### 6.3 新手证据审阅顺序

拿到一个新的 run root 后，按下面顺序审阅。顺序很重要：先确认目录边界，再解释指标；不要先看到一个漂亮的 overall 数值就跳过输入、有效性或 cleanup 检查。

1. **确认目录是新的。** 把 sample 或 runner 打印的绝对路径写入 `RUN_ROOT`，只使用本次命令新建的目录。历史目录只能读，不能作为本次 run 的输出目录。
2. **列出实际文件。** 先看文件名和时间，不打开可能包含业务内容的原始 body；确认没有凭据文件、浏览器导出、Cookie 或未脱敏 header。
3. **检查范围标记。** sample 必须有 `delivery_smoke_only=true`、`not_for_performance_claim=true`，以及 `network=none`、`live_service=false`。缺任何一个标记，都不能把它当作离线 delivery sample。
4. **解析结构化报告。** 先验证 JSON 能解析，再检查 `task_id`、`run_id`、`endpoint`、`seed_source`、`validity`、四个指标和 `formal_score_provenance`。报告缺字段是 schema 问题，不是“指标为零”。
5. **核对原始计数。** 将 `sample_eval_report.json` 的 `valid_exec`、security-state 计数和 MAB pull 与 `sample_fuzzer_stats.txt` 对照；任何不一致都先保留原始文件并停止解释。
6. **检查有效性分母。** `validity` 中分别看 evaluated、accepted、rejected；高 reject 率要在报告中保留，不能只报告通过样例。若所有候选都被拒，先回到 seed/rules 检查。
7. **检查状态与 ledger。** `nv_http_status.json`、state trace、`evidence/status.jsonl` 和 `evidence/executions.jsonl` 的 execution identity 应能对应。重复状态可以是 replay；它不能被重复算成 new state。
8. **检查 Err 和 Rec。** Err 必须能追溯到 HTTP、execution 或 business/readback ledger；没有 recovery opportunity 时 Rec 应为 `null`，不能把 null 改成 0 来制造 overall。
9. **检查 cleanup 和秘密。** 真实平台 run 还要核对 exact object ID 的 cleanup receipt 和 absence readback。最后扫描文件名、日志和 JSON，确认没有 token、密码、Cookie 或 Authorization value。
10. **记录审阅结论。** 在仓库外新建一份短文本，记录 source checkpoint、run root、命令、时间、通过/阻断项和限制；不要改写历史 evidence，也不要把 sample smoke 写成 live acceptance。

离线 sample 的最小检查可以这样执行；这些命令只读取本地新目录，不启动服务：

```bash
RUN_ROOT=<SAMPLE_DIR_FROM_PREVIOUS_COMMAND>
find "$RUN_ROOT" -maxdepth 1 -type f -printf '%f\n' | sort
.venv/bin/python -m json.tool "$RUN_ROOT/sample_eval_report.json" >/dev/null
cat "$RUN_ROOT/sample_metadata.json"
```

成功条件是文件清单包含 sample wrapper 的四个文件，JSON 解析退出码为 0，metadata 明确写出无网络和非性能声明。若目录中只有旧的 `fuzzer_stats` 而没有 `sample_metadata.json`，应把 run 标记为不完整，重新使用一个从未存在过的输出目录。

## 7. 如何读 Cov / Err / Rec

### 7.1 Cov 的计算和边界

当前 C Cov set 将状态规范化为 `METHOD PATH|RESPONSE_CLASS`，并使用固定容量、开放寻址、线性 probing。capacity 是 65536 个 slot，不是安全状态全集。Python `nv_state_probe.update_state` 是另一个兼容/诊断探针：它单独把 business-code bucket 和 `extra_tag` 加入内部哈希键。两者是不同实现和不同计数口径；不要把 Python probe 的 `ncov_total` 当成 C Cov set 的状态数。新手读 report 时同时查看：

- `security_state_new_total`：首次观察到的新状态数；
- `security_state_capacity`：当前容量；
- `security_state_saturated`：是否出现饱和；
- `security_state_dropped`：因满表丢弃的状态数；
- `security_state_replays`：重复 status 不重新计数。

如果 state count 为零，先检查 harness 是否写出有效 status、`NV_STATUS_PATH` 是否可写、目标是否真正执行、以及 path/response classification 是否能解析。不要把 zero state 自动解释成目标没有安全状态。

### 7.2 Err 的三层检查

接入新平台时，先分别定义：

1. **HTTP anomaly**：连接拒绝、timeout、5xx 等；
2. **execution failure**：请求没有完成、status document 丢失、解析异常；
3. **business/readback anomaly**：2xx 但数据不符合预期、readback 缺字段或对象不存在。

期望的 4xx 可能是业务拒绝，不应无条件计为 Err。反过来，2xx 也不自动是 business success；如果 readback 不匹配，应记录 semantic failure。每个 scenario 都要在 evidence 中写明分母和排除的 expected rejection。

### 7.3 Rec 的机会定义

只有下列四个观察都存在才有 recovery opportunity：

1. failure 前的 health/precondition；
2. failure 或 unavailability observation；
3. 平台重新可用的 recovery observation；
4. recovery 后的业务 readback/check。

如果没有这四步中的完整机会，`Rec=null`。这是有效结果，不是缺陷。不要用健康探针成功次数替代业务恢复，也不要把补充 availability trials 混入主 Cov pair metrics。

## 8. 使用 O2OA 场景（只按已接受契约说明）

本节说明如何阅读和准备已有场景；本手册不会启动 O2OA，也不会向它发送请求。

### 8.1 配置和运行时输入

| 项 | 来源/占位 | 作用 |
|---|---|---|
| base URL | `<O2OA_BASE_URL>`；提交配置当前固定本地 topology | O2OA HTTP 服务地址。 |
| token | `<TOKEN>`，运行时变量 `NV_TOKEN` | raw token 认证；当前 harness 也可带 `x-token` cookie。 |
| category | `<CATEGORY_ID>`，变量 `NV_O2OA_CATEGORY_ID` | write scenario 的 disposable CMS category。 |
| identity | `<IDENTITY_DN>`，变量 `NV_O2OA_CURRENT_USER_IDENTITY` | creator/read/manager 业务身份。 |
| target config | `targets/o2oa_query.json` | endpoint、auth、runtime body/path binding。 |
| rule file | `validity/o2oa_query_rules.json` | endpoint body/query validity。 |
| seed | `in/o2oa_url_query/seed_file_share_list_my_query_0.json` 或 write runner 自己的 seeds | 只读 query 或 bounded write 输入。 |

不要把 `<TOKEN>`、密码或 Cookie 写入任何 JSON。真实 O2OA 写场景的当前 entrypoint 是 `scripts/run_task4_o2oa_final_experiment.sh --with-write-scenario`；它要求明确 `--out-dir`、`--max-test-cases`、`--time-budget`，并把 run root 放在仓库外。先只做不接触平台的 dry-run：

```bash
NV_TOKEN='<TOKEN>' PYTHON_BIN="$PWD/.venv/bin/python" \
  ./scripts/run_task4_o2oa_final_experiment.sh \
  --dry-run --out-dir /tmp/task4-o2oa-dry-run
```

上面使用的是占位 token，命令不会把 token 打印出来；实际执行时不要在 shell history 中输入真实 token，改用 owner-only env file 在当前子 shell 中 source。dry-run 成功应打印 `O2OA_DRY_RUN=PASS`、`NETWORK_CONTACTED=NO` 和 `BUSINESS_STATE_MUTATION=NO`。

### 8.2 真实正式链的顺序

历史 formal scenario 的顺序是：

```text
seed → mutation → validity → create/save → authenticated readback
     → same-document content update → second readback
     → validity/feedback/MAB/report → exact cleanup
```

其中 create/save 和 update 会修改 O2OA；它们只应使用专用测试 application/category、专用 identity 和 run-owned document IDs。readback 是业务验证，cleanup 只删除本次 run 的 exact IDs。默认 entrypoint 的 read-only URL-query 路径不修改业务对象；`--with-write-scenario` 是显式危险开关。

当前历史 evidence 已证明这条 bounded chain；本轮文档不把历史证据写成当前 fresh live run，也不提供真实 token、category 或 identity 值。O2OA 的真实平台 efficacy 不能从该链宣称为 NC_MAB superiority；高 validity attrition 可能使某些 arm 没有足够有效执行。

## 9. 使用 Alfresco 场景（只按已接受契约说明）

本节同样不启动服务。三个真实 profile 如下：

| 场景 | 配置 | body | seed/rules |
|---|---|---|---|
| metadata update | `targets/alfresco_metadata_update.json` | JSON | `in/alfresco_metadata_update_dataset/`、`validity/alfresco_metadata_update_rules.json` |
| raw content update | `targets/alfresco_content_update.json` | text/plain | `in/alfresco_content_update_dataset/`、对应 rules |
| multipart upload/create-save | `targets/alfresco_multipart_upload.json` | multipart/form-data | `in/alfresco_multipart_upload_dataset/`、对应 rules |

认证由目标配置读取运行时 `ALFRESCO_USER` 与 `ALFRESCO_PASS`；它们只能来自当前 shell 或 0600 外部文件。历史真实服务证据支持 metadata/content/multipart 链，但当前 delivery acceptance 没有 fresh live run。当前 approved Alfresco 32D frozen artifact 不可用，所以不能复现 fresh 32D SE comparison，也不能把 38D 文件当成等价替代。

工程选择是：AE v1 保持 primary；SE-fAnoGAN-ES 是 optional research backend。新平台接入先 rule-only，之后可选 AE/SE，不要让模型安装阻塞最初的 request/readback/cleanup 验证。

## 10. 接入前的 12 个问题

在新建任何文件前，把答案写在本地设计草稿中：

1. base URL 是什么？是否只监听 `127.0.0.1`/`localhost`？
2. API 是否是 REST/HTTP？
3. 使用 GET、POST、PUT、PATCH、DELETE 中哪些方法？
4. body 是 JSON、URL query、raw text、multipart 还是其他格式？
5. 认证是 bearer、raw token、basic 还是无认证？token/password 从哪个环境变量读取？
6. 哪个接口是只读且安全？
7. 哪个接口可以在 disposable namespace 修改一个对象？
8. 哪个接口能 readback？返回哪些业务字段？
9. 哪个接口能 cleanup/delete？是否按 exact ID 删除？
10. 哪些 HTTP/业务结果代表 expected rejection、success、semantic failure？
11. 哪些 method/path/response class 可以作为 observable state？
12. 平台是否允许在当前测试环境执行自动化请求？

如果其中第 8 或第 9 题没有答案，先停在 read-only/parse 阶段；不要直接做写入 fuzz。

## 11. 最小接入原则和决策树

第一版只做：**一个 scenario、一个 safe write、一个 readback、一个 cleanup、一个小 seed corpus**。不要一开始覆盖全平台。

```text
输入是 JSON？
├─ 是 → JSON route：nv_json_mutator.py + body validity rules
└─ 否
   ├─ URL query？ → query route：nv_url_query.py
   ├─ raw text？ → text route：nv_text_mutator.py + body_only/full HTTP
   └─ file/form upload？ → multipart route：nv_http_harness.py multipart path
```

然后检查：有 readback 吗？有 cleanup 吗？有 health/recovery endpoint 吗？

- 有 readback、无 cleanup：只做 read-only 或 mock；
- 有 readback、有 cleanup、无 health：可做 create/readback/update/cleanup，但 Rec 通常为 null；
- 三者都有：可在极小预算下验证 Cov、Err、Rec 和 feedback contract。

## 12. 创建 scenario/profile/rules

### 12.1 task schema

`schemas/fuzz_task.schema.json` 是宽松 task schema。它接受 `task_name`、`scenario`、`platform`、`target_type`、`target_endpoint`、`seed_source`、`seed_location`、`mutation_scope`、`max_test_cases`、`time_budget`、`duration` 和 `simulate` 等字段。

### 12.2 platform profile schema

`schemas/platform_profile.schema.json` 是宽松 profile schema，真实 profile 通常包含 `profile`、`platform`、`is_mainline`、`validation_scope`、`target_semantics`、`endpoint`、`method`、`body_type`、`decision` 和 `notes`。它不是一个凭据容器。

### 12.3 一个可解析的教学 profile

下面是**教学占位示例**，不是仓库内置的新平台。它使用 `example_platform` 作为 profile 名称，目标 URL 是 `127.0.0.1`，需要你创建自己的 seed/rule/adapter：

```json
{
  "profile": "my_local_items",
  "platform": "my_local_rest",
  "is_mainline": false,
  "validation_scope": "local_items_bounded_smoke",
  "target_semantics": "item_create_readback_delete",
  "endpoint": "/api/items",
  "method": "POST",
  "body_type": "json",
  "decision": {"t_low": 0.0, "t_high": 1.0, "enable_second_stage": false},
  "notes": "USER_TO_CREATE; authorized local test service only"
}
```

这份对象符合 profile 的宽松形状，但仓库不会因为它自动获得 create/readback/delete 业务语义。你还需要 target config、validity rules、seed 和 adapter。不要把它写进正式 `integration/platform_profiles/` 直到你完成本章验收。

### 12.4 target config

真正的 HTTP harness 配置在 `targets/*.json`。它支持 `base`、`health_url`、`auth`、`body_only_mode`、`default_endpoint`、命名 `endpoints`、`biz_fields` 和 runtime body/path binding。认证支持：

- `none`；
- `basic` + `username_env`/`password_env`；
- `bearer` + `token_env`；
- `raw_token` + `token_env`，可选 `also_cookie`。

教学 config（用户创建，不是仓库内置）：

```json
{
  "base": "http://127.0.0.1:PORT",
  "health_url": "http://127.0.0.1:PORT/health",
  "auth": {"type": "bearer", "header": "Authorization", "token_env": "MY_PLATFORM_TOKEN", "prefix": "Bearer "},
  "body_only_mode": 1,
  "default_endpoint": "items_create",
  "endpoints": [
    {"name": "items_create", "method": "POST", "path": "/api/items"},
    {"name": "items_get", "method": "GET", "path": "/api/items/{itemId}", "request_body": "none",
     "runtime_path_parameter": {"placeholder": "{itemId}", "env": "MY_PLATFORM_ITEM_ID"}},
    {"name": "items_update", "method": "PUT", "path": "/api/items/{itemId}", "runtime_path_parameter": {"placeholder": "{itemId}", "env": "MY_PLATFORM_ITEM_ID"}},
    {"name": "items_delete", "method": "DELETE", "path": "/api/items/{itemId}", "request_body": "none",
     "runtime_path_parameter": {"placeholder": "{itemId}", "env": "MY_PLATFORM_ITEM_ID"}}
  ],
  "biz_fields": ["code", "message", "status"]
}
```

它展示的是 source 已支持的 endpoint/auth/runtime binding 形状；但 create 后如何从 response 保存 ID、如何比较 readback、何时执行 delete，仍需你写 scenario adapter，因为通用 harness 不会猜业务字段。

### 12.5 validity rules

参考 `validity/example_platform_rules.json`：它包含 `common` 的 `max_bytes`、`max_depth`、`max_keys`、`max_string`，以及 endpoint 的 type/required/properties。新平台第一版应只允许真实必需字段，`allow_unknown` 要有意识地选择；规则过严会让所有 seed 在请求前被 reject。

### 12.6 准备 seed

建议目录：

```text
my-platform-seeds/
├── seed_ok_0.json
├── seed_ok_1.json
├── seed_border_0.json
└── manifest.txt
```

seed 命名和目录是工程约定，不是形式化最优值。先准备少量代表性样例，确保每个样例能在本地服务上人工请求成功；去掉 token、密码、Cookie、个人数据和生产 ID。manifest 如使用 runner 的 manifest 路径，记录相对文件名以及可选 size/hash，避免变动后无法复核。

### 12.7 先写 scenario contract，再写 adapter

在执行任何自动化请求前，把下面这张表填成你平台的真实值。它是业务语义的边界，不是可有可无的说明文档。

| 合同项 | 必须写清的内容 | 示例占位 |
|---|---|---|
| create/save | method、path、body 类型、允许的成功状态、业务 ID 字段 | `POST /api/items`、`data.id`、201 |
| expected rejection | 缺少字段或非法值时的预期 status/业务 code | 400 + `validation` |
| readback | exact ID 的 GET path、必须相等的字段、服务端默认字段 | `/api/items/<OBJECT_ID>`、`name` |
| update | 是否更新同一个对象、允许的状态、更新后必须变化的字段 | `PUT`、`content` |
| cleanup | exact ID 的 DELETE 或撤销路径、absence status | 204，然后 GET 为 404 |
| health/recovery | pre-health、failure、recovery-health、post-check | `/health` + 业务 GET |
| evidence | 每一步对应的 execution、status、validity、ledger 文件 | `<RUN_ROOT>/evidence/` |

把 expected rejection 和 semantic failure 分开记录：前者是平台按合同拒绝输入，后者是请求看似成功但 readback 或业务字段不符合合同。把 ID 从 create response 原样保存到 run-local context；不要通过标题、名称或时间戳模糊搜索对象。若平台没有稳定的 exact-ID cleanup，scenario 只能停在 mock 或 read-only Level 1，不能宣称 bounded real-service smoke pass。

完成这张表后做一次人工交叉检查：create 的 ID 是否真的能拼出 readback 路径；update 是否仍指向同一个 ID；cleanup 是否不会删除 seed 中原有对象；health 是否只代表可用性而没有被误当成业务成功；每个 status 是否能找到唯一 execution identity。任一答案不明确，就先补合同或降低验收级别。审阅记录保留原始响应、时间戳和未定义项；配置能解析只说明格式正确，不能替代业务合同审阅。

## 13. 复用/实现 HTTP harness

### 13.1 已有实现位置

| 责任 | committed source 文件/函数 |
|---|---|
| 读取 target config | `nv_http_harness.py:load_target_config` |
| 命名 endpoint 和 runtime path binding | `nv_http_harness.py:resolve_named_endpoint` |
| runtime JSON body marker binding | `nv_http_harness.py:bind_runtime_body_parameter` |
| basic/bearer/raw token 注入 | `nv_http_harness.py:apply_auth_headers` |
| JSON/text/multipart validity | `nv_body_valid.py:body_validate` |
| 发送无代理 HTTP 请求 | `nv_http_harness.py:open_direct` |
| HTTP response class | `nv_http_harness.py:classify` |
| business code extraction | `nv_http_harness.py:extract_biz_code` |
| O2OA document ID/readback helpers | `nv_http_harness.py:extract_o2oa_document_id`, `verify_o2oa_document_readback`, `verify_o2oa_data_readback` |
| status and state reporting | `nv_http_harness.py:write_status`; `nv_state_probe.py:update_state` (imported and called by the harness) |
| run-scoped evidence paths | `runner/fuzz_test_runner.py:build_run_layout`, `build_launch_env` |

### 13.2 什么时候只改配置

如果你的接口只需 body 解析、认证、状态分类和普通 HTTP response，先只创建 target config、validity rule、seed 和 task/profile 文件。使用 `scripts/validate_project_configs.py` 检查结构，再用 local mock。

### 13.3 什么时候必须写 adapter

如果平台需要：

- create response 中的业务 ID 不在 `data.id`；
- readback 需要比较嵌套字段或附件内容；
- cleanup 需要专门的 delete API 或多步撤销；
- success/rejection 不能用 HTTP class 和通用 `biz_fields` 表达；
- recovery 需要平台专属 health/readback；

就必须创建**用户自己的 bounded adapter**。仓库没有 generic plugin registry、任意平台自动发现或未声明的“插件 API”。`integration/fuzz_adapter.py` 是控制面 CLI：它按名称选择已存在的 profile、加载 profile 的 template，并把 task 交给 runner；它不会因为发现一个 Python 文件就调用平台 adapter。平台专属 adapter/glue 必须由用户放进 task 的 `launch_cmd`/template 或既有 harness 入口。最小 adapter 应复用真实 helper，而不是复制一套 HTTP 栈：

```python
# USER_TO_CREATE: adapters/my_items_bounded.py
import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path
import nv_http_harness as h
from nv_state_probe import update_state

CONFIG = Path(os.environ["NV_TARGET_CONFIG"])
RUN_ROOT = Path(os.environ["RUNNER_RUN_DIR"])


def request(cfg, method, path, body=None):
    headers = h.apply_auth_headers(cfg, {"Accept": "application/json"})
    payload = None
    if body is not None:
        payload = json.dumps(body, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(cfg["base"] + path, data=payload, method=method, headers=headers)
    try:
        with h.open_direct(req, timeout=5) as response:
            code, raw = response.getcode(), response.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        code, raw = exc.code, exc.read(1024 * 1024)
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        timeout = isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(
            getattr(exc, "reason", None), (TimeoutError, socket.timeout)
        )
        code = -1 if timeout else -2
        cls = h.classify(code, timeout)
        probe = update_state(method, path, cls, biz_code=f"http_{code}_{cls}")
        h.write_status(
            method, path, code, timeout=timeout, is_exception=1,
            ncov_delta=probe["ncov_delta"], ncov_total=probe["ncov_total"],
            nall=probe["nall"],
        )
        raise RuntimeError(f"transport failure: {type(exc).__name__}") from exc
    cls = h.classify(code, False)
    biz_code = h.extract_biz_code(raw, code, cls, cfg.get("biz_fields", []))
    probe = update_state(method, path, cls, biz_code=biz_code)
    status = h.write_status(
        method, path, code, is_exception=int(cls == "5xx"),
        ncov_delta=probe["ncov_delta"], ncov_total=probe["ncov_total"],
        nall=probe["nall"],
    )
    return code, raw, status


def parse_json(raw, operation):
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid JSON in {operation}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"unexpected JSON shape in {operation}")
    return value


def save_record(record):
    evidence = RUN_ROOT / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "adapter_context.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def bounded_create_update_readback_cleanup(seed):
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    record = {"seed": seed, "created_id": None, "responses": {}, "outcome": "started"}
    save_record(record)
    code, body, status = request(cfg, "POST", "/api/items", seed)
    record["responses"]["create"] = {
        "http_code": code, "body": body.decode("utf-8", "replace"),
        "exec_seq": status["exec_seq"],
    }
    save_record(record)
    if code not in {200, 201}:
        # Replace this predicate with the platform contract. A 4xx is only
        # expected rejection when the scenario explicitly says so.
        record["outcome"] = "expected_rejection" if code == 400 else "unexpected_rejection"
        save_record(record)
        return record
    created = parse_json(body, "create")
    item_id = created.get("id")  # TODO: replace with the stable platform ID field.
    if item_id in (None, ""):
        save_record(record)
        raise RuntimeError("create response has no stable object ID")
    record["created_id"] = str(item_id)

    code2, read_body, status2 = request(cfg, "GET", f"/api/items/{record['created_id']}")
    record["responses"]["readback"] = {
        "http_code": code2, "body": read_body.decode("utf-8", "replace"),
        "exec_seq": status2["exec_seq"],
    }
    save_record(record)
    read_obj = parse_json(read_body, "readback")
    if code2 != 200 or read_obj.get("name") != seed.get("name"):
        raise RuntimeError("readback mismatch")

    updated = dict(seed, name=str(seed.get("name", "")) + "-updated")
    code3, update_body, status3 = request(cfg, "PUT", f"/api/items/{record['created_id']}", updated)
    record["responses"]["update"] = {
        "http_code": code3, "body": update_body.decode("utf-8", "replace"),
        "exec_seq": status3["exec_seq"],
    }
    save_record(record)
    if code3 not in {200, 204}:
        raise RuntimeError("same-document update failed")

    code4, update_read_body, status4 = request(cfg, "GET", f"/api/items/{record['created_id']}")
    record["responses"]["update_readback"] = {
        "http_code": code4, "body": update_read_body.decode("utf-8", "replace"),
        "exec_seq": status4["exec_seq"],
    }
    save_record(record)
    if parse_json(update_read_body, "update readback").get("name") != updated["name"]:
        raise RuntimeError("updated readback mismatch")

    code5, cleanup_body, status5 = request(cfg, "DELETE", f"/api/items/{record['created_id']}")
    record["responses"]["cleanup"] = {
        "http_code": code5, "body": cleanup_body.decode("utf-8", "replace"),
        "exec_seq": status5["exec_seq"],
    }
    save_record(record)
    if code5 not in {200, 202, 204}:
        record["outcome"] = "cleanup_failure"
        save_record(record)
        raise RuntimeError("cleanup failed; stop budget expansion and remediate exact ID")
    code6, absence_body, status6 = request(cfg, "GET", f"/api/items/{record['created_id']}")
    record["responses"]["absence_readback"] = {
        "http_code": code6, "body": absence_body.decode("utf-8", "replace"),
        "exec_seq": status6["exec_seq"],
    }
    if code6 not in {404, 410}:
        record["outcome"] = "cleanup_failure"
        save_record(record)
        raise RuntimeError("cleanup absence check failed; stop budget expansion")
    record["outcome"] = "pass"
    save_record(record)
    return record
```

这个 skeleton 是教学用的 `USER_TO_CREATE` adapter，不是已提交平台实现。每个 HTTP attempt 都调用真实 `update_state` 和 `write_status` helper，并把返回的 `exec_seq` 与业务响应一起保存在 run-scoped context；HTTPError、URLError/timeout、invalid JSON、missing ID、expected/unexpected rejection、readback mismatch 和 cleanup failure 都进入明确分支，不能吞掉异常。创建后每一步先保存 exact ID/response，再进行可能失败的比较；cleanup 失败后必须停止扩大预算并用该 ID 人工处理。示例响应可能含业务数据，正式使用前应按本地保密策略脱敏。2xx 不自动代表业务成功，4xx 也不自动代表 Err。standalone 的 `exec_seq` 由 `write_status` 生成，但它本身不是 AFL iteration/arm attribution、execution-ledger commit 或 MAB reward；这些来自现有 AFL 路径。

### 13.4 自定义平台如何真正进入 Task 4 主链

当前架构的真实关系如下；`NO_GENERIC_ENTRYPOINT_EXISTS`：仓库没有 `run_task4_platform --platform foo`、通用插件注册表或任意 Python adapter 自动发现。

| 问题 | committed source 中的事实 |
|---|---|
| `WHO_CALLS_PLATFORM_ADAPTER` | `integration/fuzz_adapter.py:action_submit` 读取请求中的 `platform/profile`，调用 `load_profile` 和 `build_runner_task`，再把 task 交给 `runner/fuzz_test_runner.py`。它不扫描 adapter 目录。平台专属 adapter/glue 必须由用户放进 task 的 `launch_cmd`/template 或既有 harness 入口。 |
| `HOW_PLATFORM_PROFILE_IS_SELECTED` | `load_profile` 从 `integration/platform_profiles/<name>.json` 读取名称；profile 的 `template` 再定位 runner template。 |
| `HOW_TARGET_CONFIG_IS_LOADED` | `build_launch_env` 把 task 的 `target_config` 解析为 `CFG`；提交的 HTTP launch scripts 再把 `CFG` 导出为 `NV_TARGET_CONFIG`，供 `nv_http_harness.py:load_target_config` 读取。用户自有 launch glue 也必须显式完成这层绑定。 |
| `HOW_RUN_LAYOUT_IS_CREATED` | `runner/fuzz_test_runner.py:build_run_layout` 在 repo 外创建 `tasks/<task_id>`、`runs/<task_id>`、`afl_out`、`evidence`、stdout/stderr 等路径。 |
| `HOW_STATUS_PATH_IS_PASSED` | `build_launch_env` 设置 `NV_STATUS_PATH`、`NV_STATUS_LEDGER_PATH`、`NV_STATE_TRACE_PATH`；harness 的 `write_status` 写状态并追加 status ledger。 |
| `HOW_LEDGER_PATHS_ARE_PASSED` | 同一个 `build_launch_env` 设置 `NV_CTX_PATH`、`NV_MAB_JOURNAL_PATH`、`NV_EXECUTION_LEDGER_PATH`、`NV_SEED_SELECTION_AUDIT_PATH`；这些是 run-scoped paths，不是用户应猜测的 `/tmp` 固定文件。 |
| `HOW_EXECUTION_IDENTITY_IS_PROPAGATED` | `write_status` 调用 `next_exec_seq` 生成 `exec_seq`；validity reject 在到达目标执行前不应计为一次真实目标 execution。C 侧把当前 AFL fuzz iteration/arm 与 status 关联，并在 ledger/MAB 事件中保留归因。 |
| `HOW_REPORT_IS_GENERATED` | `integration/fuzz_adapter.py:action_report_query` 调用 runner report，`runner/fuzz_test_runner.py:report` 读取 task status、summary、stats 和 run artifacts；它不会替代平台 adapter 的业务 readback。 |

#### 主链责任表

| 主链步骤 | 当前负责模块 | 用户需要做什么 | 输出 | 如何验证 |
|---|---|---|---|---|
| seed loading | runner `build_launch_env`、seed materialization；C queue | 准备授权、无秘密的 seed/manifest | run-local seed dir、selection audit | 检查 `NV_SEED_SELECTION_AUDIT_PATH` 和 manifest |
| mutation | `src/afl-fuzz-one.c`、`src/afl-fuzz-nv-mab.c` | 声明 mutation scope/arm 与输入形状 | testcase、arm choice | AFL log、MAB journal |
| validity | `nv_body_valid.py:body_validate`、`validity/`、可选 scorer | 提供 target config/rules，解释 reject 分母 | validity stats/decision | `NV_BODY_VALID_STATS`、reject reason |
| request serialization | `nv_http_body_adapter.py`、`nv_http_harness.py` | 选择 JSON/query/text/multipart 表示并写 scenario contract | request bytes/path | mock/read-only request capture |
| authentication | `nv_http_harness.py:apply_auth_headers` | 仅运行时提供 env/file 凭据 | headers injected in memory | 401/403 status；不记录值 |
| target execution | `nv_http_harness.py:open_direct` 或用户 adapter glue | 绑定真实 endpoint 和 bounded timeout | HTTP response/exception | status + response class |
| readback | `nv_http_harness.py:extract_o2oa_document_id`, `verify_o2oa_document_readback`, `verify_o2oa_data_readback` 或用户 adapter | 保存 exact ID，比较业务字段 | semantic pass/fail | readback ledger |
| cleanup | 平台专属 adapter/scenario | 仅删除本 run exact IDs，失败停预算 | cleanup receipt/absence check | delete response + GET absence |
| status write | `nv_http_harness.py:write_status` | wrapper/target 必须调用真实 helper | `nv_http_status.json` + `evidence/status.jsonl` | matching `exec_seq` |
| state update | `nv_state_probe.py:update_state`、C Cov set | 保持 method/path/class 可解析 | state trace/delta | `NV_STATE_TRACE_PATH`、stats |
| execution ledger | runner paths + C feedback/target glue | 不另造未归因的 ledger；写入对应 run path | `evidence/executions.jsonl` | status/ledger identity reconcile |
| Err accounting | C run/stats + scenario business ledger | 定义 expected rejection/semantic failure | Err numerator/denominator | report and source ledger |
| Rec accounting | C run/stats + recovery contract | 只有完整 recovery opportunity 才计 Rec | Rec or null | pre/failure/recovery/post records |
| reward generation | C feedback path after attributable status | 不把生成数或 reject 当 pull | reward fields | `mab_updates.jsonl` |
| MAB attribution/commit | `src/afl-fuzz-nv-mab.c`, `src/afl-fuzz-one.c` | 接入 AFL iteration/arm identity；不要伪造 commit | arm update/commit | journal commit matches execution |
| seed credit | `src/afl-fuzz-queue.c` selection audit/credit paths | 保持 queue identity 与 selected seed | `seed_selection.jsonl`/credit | selection audit reconciles |
| report generation | `runner/fuzz_test_runner.py:report`, adapter/report wrapper | 保存 run root 和 scope metadata | summary/report/artifact map | report paths exist and parse |

独立 wrapper 可以写 status、结构报告和业务 ledger，但它不能自己制造 AFL iteration、C-side arm attribution 或 MAB commit。要声称完整 Task 4 主链，平台专属 glue 必须通过 profile/template/runner 的 launch contract 进入现有 AFL/harness 路径；standalone HTTP 成功只属于 Level 2。

#### 自定义文件矩阵和最小目录

| 文件/目录 | 是否必须 | 从哪里参考 | 用户改什么 | 如何验证 |
|---|---:|---|---|---|
| `target.json` | 是 | `targets/*.json`、`nv_http_harness.py:load_target_config` | base、endpoint、auth env 名、runtime binding | JSON parse、target config validation |
| validity rules | 是（rule-only 起步） | `validity/example_platform_rules.json` | required/type/size/endpoint 规则 | `body_validate` / stats |
| seed directory | 是 | `in/p0_o2oa_cms_doc_list/` 等 | 去秘密的业务形状样例 | seed parse + selection audit |
| task/profile | Level 3 需要 | `schemas/fuzz_task.schema.json`、`integration/platform_profiles/` | platform、template、scope、budget | `load_profile`、runner dry-run |
| platform adapter/glue | 业务语义需要时是 | `nv_http_harness.py` helpers；本节 skeleton | ID、readback、update、cleanup、error rules | import/syntax + mock |
| scenario README/contract | 是 | 本指南第 12.7 节 | expected rejection、分母、cleanup | reviewer checklist |
| external run root | 是 | `build_run_layout` | repo 外 timestamped path | layout and no overwrite |
| optional mock service | Level 2 前推荐 | 用户自建 loopback service | response/ID/delete contract | health + CRUD smoke |
| optional model metadata | 仅启用 AE/SE 时 | `model_stage/`、validity profile | model route/metadata | scorer contract; rule-only 不需要 |

教学最小文件树（全部是 `USER_TO_CREATE`，不是仓库固定目录）：

```text
my-platform/                         # USER_TO_CREATE, repo 外 prototype
├── target.json                       # USER_TO_CREATE
├── rules.json                        # USER_TO_CREATE
├── seeds/                            # USER_TO_CREATE
│   ├── seed_ok_0.json
│   └── seed_ok_1.json
├── adapter.py                        # USER_TO_CREATE
├── scenario_contract.md              # USER_TO_CREATE
└── run_notes.md                      # USER_TO_CREATE
```

通过 Level 1/2 和人工审阅后，再决定是否把稳定文件映射到 `targets/`、`validity/`、`in/`、`integration/` 或 `runner/`；不要第一步就污染正式目录。

## 14. Generic REST JSON 完整教学 walkthrough

假设你在本机有一个**你自己创建的**测试服务，提供：

```text
POST   http://127.0.0.1:PORT/api/items
GET    http://127.0.0.1:PORT/api/items/{id}
PUT    http://127.0.0.1:PORT/api/items/{id}
DELETE http://127.0.0.1:PORT/api/items/{id}
GET    http://127.0.0.1:PORT/health
```

这里的 `/api/items` 是教学接口，不是仓库内置平台。

当前仓库没有通用的一键 adapter CLI。下面的 wrapper 是 `USER_TO_CREATE` glue：它展示如何调用 committed helper，但不会伪造 AFL iteration、C ledger 或 MAB commit。

### Phase 1 — offline parse/config test

**目的：** 在没有网络和凭据时发现 schema/path 错误。

1. 在仓库外创建 `my-platform/target.json`、`my-platform/rules.json`、`my-platform/seeds/seed_ok_0.json`。
2. 只在 config 中使用 `MY_PLATFORM_TOKEN` 变量名，不写 token 值。
3. 让 `target.json` 的 `base` 使用 `http://127.0.0.1:PORT`。
4. 用 committed `scripts/validate_project_configs.py` 检查仓库内复制后的临时 config，或对照 `schemas/*.json` 做本地 JSON parse。

**成功：** JSON 可解析，required fields 存在，seed 不含秘密，path 没有生产域名。

可复制的 Level 1 检查（在 repo 外 prototype 中运行；不访问网络）：

```bash
python3 -m json.tool my-platform/target.json >/dev/null
python3 -m json.tool my-platform/rules.json >/dev/null
python3 -m json.tool my-platform/seeds/seed_ok_0.json >/dev/null
PYTHONPATH="$PWD:$(dirname "$PWD")/my-platform" python3 -m py_compile \
  "$(dirname "$PWD")/my-platform/adapter.py"
PYTHONPATH="$PWD:$(dirname "$PWD")/my-platform" python3 - <<'PY'
import importlib.util
import json
from pathlib import Path
import nv_body_valid
import nv_http_harness

root = Path("../my-platform")
json.loads((root / "target.json").read_text(encoding="utf-8"))
json.loads((root / "rules.json").read_text(encoding="utf-8"))
spec = importlib.util.spec_from_file_location("my_adapter", root / "adapter.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print("LEVEL1_PARSE_CONFIG_IMPORT=PASS")
PY
```

`py_compile`/import 只证明语法和导入边界；它不证明 endpoint、业务 ID、readback 或权限正确。若正式 task 已把配置复制进 checkout，再运行 committed `PYTHON_BIN="$PWD/.venv/bin/python" scripts/validate_project_configs.py`；不要为了通过检查把用户目录或秘密复制进仓库。

### Phase 1.5 — 最小 Level 2 wrapper（用户创建）

下面的文件是 `USER_TO_CREATE: scripts/run_my_platform_bounded.py`。它加载真实 target config 和 seed，调用 `body_validate`，委托前一节的 adapter，使用 `update_state`/`write_status` 生成结构状态，并写一个 run-scoped structural report。adapter 实际发送的每一次 HTTP 请求都应各自调用 `write_status`；这里仅展示 create 结果的最小桥接。`NV_TARGET_CONFIG`、`NV_BODY_RULES`、`NV_STATUS_PATH`、`NV_STATUS_LEDGER_PATH`、`NV_STATE_TRACE_PATH` 和 `RUNNER_RUN_DIR` 应由 runner 或当前子 shell 指向本次 run；不要使用固定 `/tmp` evidence。

```python
# USER_TO_CREATE: scripts/run_my_platform_bounded.py
import json
import os
from pathlib import Path
import nv_body_valid
import nv_http_harness as harness
from adapters import my_items_bounded

seed_path = Path(os.environ["MY_PLATFORM_SEED"])
run_root = Path(os.environ["RUNNER_RUN_DIR"])
cfg = harness.load_target_config()
seed_bytes = seed_path.read_bytes()
endpoint_name = os.environ.get("NV_ENDPOINT_NAME", "items_create")
validation = nv_body_valid.body_validate(
    scenario=cfg.get("scenario", "metadata_update"),
    endpoint_name=endpoint_name,
    raw_body=seed_bytes,
    rules_path=os.environ["NV_BODY_RULES"],
)
report = {"level": 2, "validity": validation["ok"], "outcome": "not_run"}
if validation["ok"]:
    seed = json.loads(validation["norm_body"].decode("utf-8"))
    result = my_items_bounded.bounded_create_update_readback_cleanup(seed)
    report["outcome"] = result["outcome"]
    create = result["responses"].get("create", {})
    report["create_exec_seq"] = create.get("exec_seq")
    report["status_source"] = "adapter_per_http_attempt"
else:
    report["validity_reason"] = validation["reason"]
    # A validity rejection is not a target execution, but the committed
    # harness contract records a terminal validation status for attribution.
    report["status"] = harness.write_status(
        "POST", "/api/items", 0, validation_reject=1
    )
    report["status_source"] = "wrapper_validation_rejection"
report_path = run_root / "evidence" / "level2_report.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"report": str(report_path), "outcome": report["outcome"]}))
```

这个 wrapper 的成功条件是 Level 2：一个授权 loopback/test service 的 bounded create/readback/update/cleanup、有效性决定、至少一条 status/state 记录和可解析结构报告。它不是仓库内置命令，也不产生完整 C-side MAB attribution；完整 Task 4 需要把同一业务 glue 放进下一节描述的 profile/template/runner/AFL 路径。

### Phase 2 — mock/local test

启动你自己的 loopback mock 后，先只验证 POST/GET/DELETE 的业务 contract。不要使用公网目标。确认 response 中 ID、readback 字段和 delete status。

### Phase 3 — read-only real API probe

用 `<TOKEN>` 通过 owner-only env file 注入，执行 GET `/health` 和一个不改数据的 GET。成功条件是认证状态、JSON shape、超时和 proxy-free 请求都符合预期。失败时先看 401/403、URL、证书、代理和服务日志。

### Phase 4 — one bounded disposable write

只生成一个 disposable seed，设置 `MAX_TEST_CASES=1` 和短时间预算。POST 成功后立即把 exact ID 写入 run-local context；禁止按名称模糊查找并删除。

### Phase 5 — readback

用 GET exact ID 验证关键业务字段、创建者/租户边界和服务端默认字段。2xx 但 readback mismatch 必须记为 semantic failure。

### Phase 6 — cleanup

用 DELETE exact ID，随后再 GET 确认不存在或符合平台的 absence response。cleanup 失败时停止扩大预算，保存 evidence 并人工处理孤立测试对象。

### Phase 7 — tiny bounded campaign

只有单个 create/readback/update/delete 成功后，才把 seed 数量增加到很小的值；每次扩展仍保留时间、case、对象数量上限。

### Phase 8 — evidence review

检查 state trace、execution ledger、validity stats、MAB journal、seed selection audit、Cov/Err/Rec 分母和 report schema。secret scan 必须通过。

### Phase 9 — enlarge budget only after review

只有在前八步全通过、cleanup 没有孤立对象、状态和错误含义已人工确认后，才考虑扩大预算。预算扩大不是默认步骤，也不是性能结论。

### 九个阶段的执行边界

下表是一个可执行的记录模板。`curl` 行只针对用户自己监听在 loopback 的教学服务；它们不是仓库内置平台命令。Phase 4–9 的正式 runner/adapter 由用户按第 13 节创建，因此这里不虚构一个不存在的通用 CLI；在 Level 2 之前必须把真实命令写入自己的 scenario README 和 evidence manifest。

| 阶段 | 最小命令或动作 | 成功证据 | 文件/网络/凭据边界 | 失败时 |
|---|---|---|---|---|
| 1 offline parse | `python3 -m json.tool my-platform/target.json`，对 rules/seed 重复 | JSON parse 成功，路径和字段检查通过 | 只读用户目录文件；无网络、无凭据；不产生业务对象 | 修正 JSON/schema，重新 parse |
| 2 mock/local | 用户启动自己的 `<MOCK_START_COMMAND>`；随后 `curl --noproxy '' --fail --silent http://127.0.0.1:PORT/health` | health 与 POST/GET/DELETE contract 在 loopback 通过 | 仅用户 mock；不使用真实凭据；保存 mock 日志和临时对象清单 | 停止，先修 mock response/ID/delete contract |
| 3 read-only probe | `curl --noproxy '' --fail --silent -H "Authorization: Bearer ${MY_PLATFORM_TOKEN}" http://127.0.0.1:PORT/health` | health 与一个 GET 的 status、JSON shape、超时符合预期 | 只访问授权测试服务；token 只来自当前 shell/0600 文件，不写日志 | 按 401/403、URL、proxy、TLS 和服务日志排查 |
| 4 one write | 执行用户 `USER_TO_CREATE` bounded adapter 的单 case 命令，预算固定为 1 | create/save 返回 exact ID，run context 立即记录 | 只创建 disposable 对象；必须有 runtime auth；不按名称模糊删除 | 停止扩大预算并保留失败 evidence |
| 5 readback | 用 adapter 的 exact-ID GET 命令读取刚创建对象 | 关键字段、创建者/租户和服务端字段匹配 | 只读 exact ID；追加 execution/readback ledger | 2xx 但字段不符按 semantic failure 记录 |
| 6 cleanup | 用 adapter 的 exact-ID DELETE，再执行 exact-ID absence GET | delete status 和 absence response 均符合 contract | 只删除本次 run 的对象；保存 cleanup receipt | 停止，人工处理孤立对象，不继续 fuzz |
| 7 tiny campaign | 复用已通过 adapter，增加很小的 seed/case/time 上限 | 每个对象都有 ID、readback、cleanup；预算未越界 | 仍是授权测试服务；凭据只运行时注入 | 回退到单 case，检查 validity 和 attribution |
| 8 evidence review | `find <RUN_ROOT> -maxdepth 3 -type f`，逐项检查 ledger/report/secret scan | state、validity、MAB、Cov/Err/Rec 分母可相互解释 | 只读新 evidence root；不覆盖历史目录 | 标记 BLOCKED，不扩大 run |
| 9 enlarge | 只有人工审阅通过后才修改用户自己的预算配置 | 变更有记录且仍可 cleanup | 仍不接触生产对象；不要把预算扩大当性能结论 | 保持原 bounded budget |

其中 `<MOCK_START_COMMAND>`、用户 adapter 的单 case 命令和 `<RUN_ROOT>` 是 **REQUIRES_USER_PLATFORM_CUSTOMIZATION**；它们不能被本仓库的固定命令替代。命令中只出现环境变量名，不要求把 token 值写入 shell history、seed 或 evidence。

## 15. 状态反馈如何接入

每次目标执行应产生一条 status，至少包含 method、path、HTTP code/class、execution identity、state delta 和异常/恢复字段。`nv_http_harness.py:write_status` 把状态写到 `NV_STATUS_PATH`，并通过 `NV_STATUS_LEDGER_PATH` 保存 append-only ledger。

### 15.1 canonical representation

- METHOD：折叠到已知方法集合；未知值进入 `INVALID`。
- PATH：可用结构保留；畸形路径折叠到有限 label，避免每个垃圾字符串制造新状态。
- RESPONSE_CLASS：2xx、3xx、4xx、5xx、timeout、conn_refused、other。
- STATE：`METHOD PATH|RESPONSE_CLASS`。

### 15.2 replay、new、dropped、saturation

status 有 execution sequence；同一 execution 的 status 只能消费一次。相同内容的不同 execution 仍可分别计数。第一次出现的 canonical state 产生 new-state delta；已有 state 是 replay/既有状态；固定表满后新 state 被 dropped，fuzz 继续但不会制造 reward。检查 `security_state_saturated` 和 `security_state_dropped`，不要把 saturation 当作平台没有更多状态。

## 16. Err 接入规则

为新平台写 scenario contract 时明确三张表：

| 情况 | 示例 | 默认分类方向 |
|---|---|---|
| expected rejection | 缺少业务字段，平台按约返回 400 | 不自动算 Err；记为 expected rejection |
| execution failure | timeout、connection refused、status 无法写出 | Err 候选，并保存错误类别 |
| semantic failure | 201 但 readback 缺字段/值不一致 | Err 候选，需业务 ledger 证明 |

`nv_http_harness.py:classify` 负责 HTTP class；`extract_biz_code` 只提取声明的 business fields，不能替平台猜语义。scenario adapter 必须保存 expected rejection 和 semantic failure 的分母。

## 17. Rec 接入规则

先定义一次 recovery opportunity 的四个事件：pre-health、failure、recovery-health、post-recovery-business-check。若平台没有 health/readback，不能声称 Rec；报告 `Rec=null` 并解释为什么没有机会。恢复试验应是独立的、低频的、可撤销的，不要用健康探针结果填充业务恢复。

## 18. NC_MAB、reward 和 UCB

- **arm**：一个 mutation strategy，例如 field/value、boundary、structure。
- **pull**：该 arm 经过 validity、目标 execution、feedback attribution 后形成的有效更新。
- **reward**：新安全状态、异常、恢复等反馈的组合；当前实现将新状态作为主要目标之一。
- **warm-up**：每个需要探索的 arm 先达到最低 pull 数。
- **UCB**：warm-up 之后的上置信界选择阶段。
- **commit**：将可验证 feedback 写入 MAB journal 和 execution ledger。

真实平台中大量 validity reject 会使有效 pull 很少。O2OA evidence 就显示 structure arm 可能 0 pull、warm-up 未完成、UCB 未进入；这说明真实 efficacy 不可识别，而不说明 attribution 必然损坏。不能把 MAB 的目标写成“必须超过随机”。

## 19. 新平台接入的强制安全顺序

```text
Phase 1  offline parse/config test
Phase 2  mock/local test
Phase 3  read-only real API probe
Phase 4  one bounded disposable write
Phase 5  readback
Phase 6  cleanup
Phase 7  tiny bounded campaign
Phase 8  evidence review
Phase 9  only then enlarge budget
```

每一个阶段都要能停止。任何阶段的 auth、serialization、readback 或 cleanup 失败，都回到本阶段排查，不跳到大预算真实运行。

推荐的开发顺序是：

1. 在 repo 外写 prototype，不先改正式目录；
2. 用 loopback mock 固定 response、ID、readback 和 cleanup contract；
3. 通过 Level 1 parse/config/import；
4. 通过 Level 2 单 case real-service smoke；
5. 让开发者审阅状态、ledger、分母和秘密扫描；
6. 只有审阅后才决定是否把文件放入 `targets/`、`validity/`、`in/`、`integration/` 或 `runner/`，再做 Level 3 接入。

Level 3 的实际入口不是一个新的平台命令，而是既有 runner contract：准备 repo 外 task JSON，profile 的 `template` 由 `integration/fuzz_adapter.py:load_profile`/`build_runner_task` 选择，task 的 `launch_cmd` 或 `target_cmd` 显式启动 AFL/target glue；`runner/fuzz_test_runner.py:build_launch_cmd` 展开 run-scoped paths，`build_launch_env` 注入环境，然后由 AFL target/harness 调用 `nv_body_valid.body_validate`、HTTP helper 和 `write_status`。典型 control-plane 命令只有已提交的 `integration/fuzz_adapter.py` 子命令，例如：

```bash
PYTHONPATH="$PWD" .venv/bin/python integration/fuzz_adapter.py submit \
  --request-json <USER_TASK_REQUEST_JSON> \
  --repo-root "$PWD" --run-root <EXTERNAL_RUN_ROOT>
```

`<USER_TASK_REQUEST_JSON>`、profile/template、`launch_cmd`/`target_cmd` 和 adapter 都是 `USER_TO_CREATE` 或平台专属 glue；这个命令不会自动发现它们。提交后用已生成的 task id 执行 `query` 或 `report_query`，并用 `stop` 结束 bounded run；真实参数以 `integration/fuzz_adapter.py --help` 和 task/profile 为准。Level 3 必须证明 status identity、execution ledger、MAB commit、seed credit、report attribution 和 cleanup 能相互对账，不能以 standalone HTTP wrapper 的 exit code 替代。

## 20. 新平台接入验收 checklist

```text
[ ] no secret in repo
[ ] target is authorized
[ ] scenario config parses
[ ] seed is syntactically and semantically valid
[ ] adapter builds or configuration-only path is proven
[ ] request serialization is correct
[ ] auth is injected only at runtime
[ ] readback works on exact object ID
[ ] cleanup works and absence is verified
[ ] state trace is produced
[ ] Cov updates have a denominator
[ ] Err semantics are validated with expected rejection cases
[ ] Rec null policy is validated
[ ] MAB attribution and commit reconcile
[ ] sample report is generated and schema-valid
[ ] no production object was touched
[ ] bounded time/case/object budget is enforced
[ ] fresh evidence root is written without overwriting history
```

## 21. 如何判断接入成功

### Level 1 — OFFLINE INTEGRATION READY

必须满足：config/rules/seed JSON 可解析；`validate_project_configs.py` 或等价本地 schema check 通过；adapter syntax/import 通过；没有 secret；所有路径和输出目录位于允许的根；没有真实网络请求。

### Level 2 — BOUNDED REAL-SERVICE SMOKE PASS

必须满足：授权 loopback/test service；一个 safe write 成功；exact readback 匹配；exact cleanup 后 absence check 通过；至少有一条 state trace、execution record、validity decision 和结构化 summary；Err/Rec 分母解释清楚。

### Level 3 — TASK4 SCENARIO ACCEPTED

必须满足：Level 1/2 全部通过；seed/mutation/validity/execution/readback/feedback/report/cleanup 链有新 evidence；MAB attribution/seed accounting 能 reconcile；run 是 bounded、可重复、无秘密；平台场景范围和限制已被正式审阅。standalone HTTP adapter success != Task4 scenario accepted。Level 3 不自动意味着 NC_MAB superiority 或跨平台效果可比。

## 22. 常见问题排查

| 症状 | 可能原因 | 检查命令/证据 | 修复 |
|---|---|---|---|
| `ModuleNotFoundError` | venv 未激活或 PYTHONPATH 错 | `.venv/bin/python -c 'import nv_http_harness; print(nv_http_harness.__file__)'` | 使用当前 venv 和 `PYTHONPATH="$PWD"`。 |
| `python3-config missing` | dev headers 未安装 | `command -v python3-config` | 安装对应 `python3.12-dev`。 |
| compiler missing | gcc/make 不在 PATH | `command -v gcc make` | 安装 `build-essential`。 |
| zlib missing | zlib headers 缺失 | 查看第一个 GCC error | 安装 `zlib1g-dev`，再顺序构建。 |
| pytest missing | requirements-dev 未安装 | `.venv/bin/python -c 'import pytest'` | 安装 `requirements-dev.txt`。 |
| wrong `PYTHON_BIN` | 脚本回退到系统 Python | `echo "$PYTHON_BIN"; "$PYTHON_BIN" --version` | 明确传入 `.venv/bin/python`。 |
| imports from old worktree | 旧 `PYTHONPATH` 或 venv | import isolation 命令 | 清理 shell 环境，重开 shell 后指向当前 checkout。 |
| wrong source checkpoint | HEAD 不匹配 | `git rev-parse HEAD` | 在 fresh clone 中 checkout 目标 commit。 |
| offline tests <235 | 跑错脚本或递归范围 | 查看 `scripts/run_task4_offline.sh` 的 TEST_FILES | 只运行官方 entrypoint，不自行拼测试集合。 |
| unexpected deselection | `-k` 过滤器改变 | 查看 pytest 命令和输出 | 记录 1 个受控 deselection；不要称为失败。 |
| sample report missing | sample 中途退出 | `cat <sample>/afl_console.log` | 先确认 `afl-fuzz`、seed 目录和磁盘空间。 |
| report schema mismatch | stale output 或脚本版本混用 | 检查 `sample_metadata.json`、`git rev-parse HEAD` | 用新目录重跑 committed sample，不覆盖旧目录。 |
| validity rejects nearly all | seed 不符合 rules/scorer threshold | `NV_DEBUG_BODY_VALID=1`，查看 `nv_body_valid_stats.json` | 先 rule-only，修 required/type/size，再启用模型。 |
| MAB never enters UCB | warm-up 没完成 | `fuzzer_stats`、`mab_updates.jsonl` | 检查有效执行/归因/commit，不把生成数当 pull。 |
| structure arm 0 pulls | structure mutation 都被 gate 拒绝 | validity stats 和 MAB journal | 修 seed/rule 或报告不可识别，不修改算法只为进入 UCB。 |
| state count stays zero | status 不可写或响应未解析 | `NV_STATUS_PATH`、status ledger、`fuzzer_stats` | 确认 harness 执行且 method/path/class 可解析。 |
| state saturation/dropped | 固定 Cov set 满 | `security_state_saturated`、`security_state_dropped` | 降低无界 path 噪声；不要把 dropped 当新状态。 |
| Err unexpectedly high | timeout、parse、semantic mismatch | execution ledger、error cases、readback log | 分开 HTTP anomaly、execution failure、business mismatch。 |
| Rec always null | 没有完整 recovery opportunity | report 的 recovery denominator | 若确实没有机会，保留 null；不要填0。 |
| 2xx but readback fails | 业务写入没有符合预期 | response 与 readback body | 记 semantic failure，修业务 contract。 |
| 404 counted incorrectly | expected absence/rejection 未定义 | scenario contract | 明确定义 expected 4xx/absence，再计分。 |
| auth 401/403 | token/basic env 缺失或权限不足 | 只检查变量名和 HTTP status，不打印值 | 重新提供授权凭据，确认作用域；不要把 token 写日志。 |
| proxy interference | ambient proxy 改变 loopback 路径 | `env | grep -i proxy`（只看变量名） | offline/live harness 会清 proxy；必要时设置 `NO_PROXY=127.0.0.1,localhost`。 |
| connection refused | 服务未启动或端口错误 | `command -v`、本地 health URL 和服务日志 | 只启动你授权的本地服务；确认 base/health。 |
| timeout | 平台慢、预算太小或网络异常 | status latency、time budget | 先单请求/短预算，不要直接扩大并发。 |
| multipart serialization issue | boundary/file field 错 | seed parser、`Content-Type`、multipart rule | 对照 `nv_http_harness.py` multipart parser，先 mock。 |
| cleanup fails | exact ID 未保存或权限不足 | run context、cleanup response | 停止扩大预算，人工确认孤立对象后再继续。 |
| adapter imports but runner cannot call it | adapter 只是可导入文件，没有出现在 task 的 `launch_cmd`/`target_cmd` 或 template | `build_launch_cmd` 输出、runner stdout/stderr、task JSON | 在 repo 外先把 adapter 显式放入 launch contract；不要期待自动发现；重新做 Level 1/2。 |
| status file never generated | target 没有执行 `write_status`，或 `NV_STATUS_PATH` 未由 runner 注入 | `NV_STATUS_PATH`、`evidence/status.jsonl`、target stderr | 检查 `build_launch_env`、harness 调用和 run-scoped parent；没有 status 就停止，不宣称 execution。 |
| execution identity mismatch | status 的 `exec_seq` 与 execution/MAB ledger 的 source execution 不一致，或 wrapper 重用旧 status | `nv_http_status.json`、status ledger、`evidence/executions.jsonl` | 新建 run root，确保每次 target execution 只调用一次真实 `write_status`，让现有 C path 完成关联。 |
| MAB journal has no commit | validity reject、status 未消费、arm/iteration 归因缺失或只运行了 standalone wrapper | `evidence/mab_updates.jsonl`、fuzzer stats、validity stats | 检查有效 pull 和 C-side pending/commit；不要手写 MAB events 或把生成数当 reward。 |
| report exists but has no attribution | report 只汇总 HTTP/summary，没有 execution identity、seed credit 或 MAB source | report、execution ledger、seed selection audit | 标记 Level 2 或 BLOCKED；把平台 glue 接回 runner/AFL contract 后再生成 Level 3 report。 |
| stale artifact contamination | 输出目录复用旧文件 | `find <run-root> -maxdepth 2`、metadata timestamp | 使用新目录；sample/runner 会拒绝覆盖。 |
| secret scan finding | token/header 写入 seed/log/evidence | 只扫描文件名和脱敏匹配 | 删除含秘密的临时产物，轮换凭据，重新建 evidence；不要提交。 |

## 23. 完全不懂 Git

- **repository**：一组被 Git 记录的文件。
- **commit**：某一时刻的完整源码快照。
- **branch**：一条可移动的提交指针。
- **dirty worktree**：工作目录中有未提交修改。

只读检查：

```bash
git status --short
git rev-parse HEAD
git log -1 --oneline
```

固定版本：

只在刚 clone 的干净目录执行下面的版本切换。先运行 `git status --short`；如果有输出，不要在这个目录 checkout，另建一个干净 clone 再继续。

```bash
git checkout 36e7cdd69c26bffde7c047d34f116e438ba60c81
git rev-parse HEAD
```

本手册不建议用 `reset --hard`、`clean` 或 stash 解决所有问题；它们可能删除尚未保存的工作。先复制或新 clone，再处理版本差异。

## 24. 完全不懂 Python

- `python3.12` 是解释器；
- `venv` 是隔离环境；
- `pip` 安装包；
- `requirements-dev.txt` 是测试依赖清单；
- `module` 是可被 `import` 的 Python 文件/包。

最小检查：

```bash
.venv/bin/python --version
.venv/bin/python -c 'import sys; print(sys.executable)'
.venv/bin/python -c 'import pytest; print(pytest.__version__)'
```

## 25. 完全不懂 HTTP

- URL：服务地址和路径；
- method：GET/POST/PUT/DELETE 等动作；
- headers：认证、内容类型和追踪信息；
- body：JSON、文本或 multipart 数据；
- status code：例如 2xx、4xx、5xx；
- JSON：结构化对象格式；
- multipart：同时上传字段和文件的格式；
- authentication：证明调用者身份的机制；
- readback：用另一个请求验证写入；
- cleanup：删除本次测试对象。

先用本地 health 和 read-only API，确认 URL/method/body/header，再做一次写入。

## 26. 命令、路径和证据边界

文档中的命令有三类：

- **VERIFIED_EXISTS_AND_SAFE**：`scripts/run_task4_offline.sh`、`scripts/run_task4_sample.sh`、`scripts/validate_project_configs.py`、`make -j2 afl-fuzz` 等，均存在于 checkpoint；离线命令不访问真实平台。
- **ILLUSTRATIVE_PLACEHOLDER**：含 `<repository-url>`、`<TOKEN>`、`<SAMPLE_DIR_FROM_PREVIOUS_COMMAND>`、`PORT` 的教学命令，必须替换并且不能把尖括号值当秘密。
- **REQUIRES_USER_PLATFORM_CUSTOMIZATION**：`my_local_items`、`MY_PLATFORM_TOKEN`、`/api/items`、`adapters/my_items_bounded.py` 等，明确是用户自有平台示例，不是仓库内置能力。

所有源码路径都以 checkpoint 为准。`/home/cphzy/task4-evidence/...` 只是历史/交付 evidence，不是用户必须依赖的长期运行路径；新 run 应使用新的仓库外目录。

## 27. 完成前的验收清单

```text
[ ] HEAD = 36e7cdd69c26bffde7c047d34f116e438ba60c81
[ ] Python 3.12 / venv / pytest 可用
[ ] python3-config --embed 可用
[ ] afl-fuzz 已构建
[ ] validate_project_configs.py PASS
[ ] scripts/run_task4_offline.sh 输出 TASK4_OFFLINE=PASS
[ ] scripts/run_task4_sample.sh 输出 TASK4_SAMPLE=PASS
[ ] sample report 包含必需字段
[ ] 真实平台未被离线命令访问
[ ] 新平台 config/rules/seed 无秘密
[ ] readback 和 cleanup 用 exact ID 验证
[ ] Cov/Err/Rec 分母和 null policy 已写入 report
[ ] MAB attribution/commit 可 reconcile
[ ] 新 evidence 未覆盖历史目录
```

完成官方离线复现后，下一步是人工审阅 output 和新平台接入证据；不要自动 commit、push、tag，也不要把文档当成 fresh live service acceptance。
