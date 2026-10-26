# Deep2Fuzz-ES — 内生安全模糊测试测评组件

> 河南重大专项 Task 4 技术实现与交付文档

> 面向第一次接触本项目的老师、学生、研发人员、验收人员和平台接入工程师。
>
> 组件源码权威 checkpoint：`36e7cdd69c26bffde7c047d34f116e438ba60c81`

如果你只想快速验证组件，请从 [Quick Start](#quick-start) 开始；如果你想从零安装、理解输出、接入自己的 REST 平台，请阅读完整的 [操作与平台接入指南](docs/TASK4_OPERATION_AND_PLATFORM_INTEGRATION_GUIDE.md)。已有的短版交付复现说明仍在 [docs/DELIVERY_GUIDE.md](docs/DELIVERY_GUIDE.md)。

## 项目是什么

Task 4 的正式主题是“基于模糊测试的内生安全性能测评组件”。它包含三项相互连接的工作：

1. 基于模糊测试的内生安全性能评估模型；
2. 高质量种子文件和模糊测试用例生成方法；
3. 基于模糊测试的内生安全性能测评方法。

这里的“种子”（seed）是一个可以作为变异起点的输入样例；“变异”（mutation）是在保留必要结构的前提下改变字段值、边界或结构；“有效性筛选”（validity filtering）是在访问目标前拒绝明显不符合接口规则或配置的输入。组件将这些步骤连成一个有界、可审计的流程：

```text
高价值种子
   ↓
种子选择与记账
   ↓
NC_MAB 变异策略选择
   ↓
字段/边界/结构分层变异
   ↓
规则或模型有效性筛选
   ↓
HTTP/表示层适配与目标执行
   ↓
状态、异常、恢复、业务 readback 反馈
   ↓
Cov / Err / Rec 记账
   ↓
reward、MAB commit、种子 credit
   ↓
summary、ledger、trace、formal report
```

它是一个 AFL++ 扩展和 Python HTTP/表示层适配集合，不是一个带前端的完整生产网关。默认离线路径不会启动 O2OA、Alfresco、Docker 或真实认证会话。

## 它能做什么

| 能力 | 用普通话说明 | 主要代码位置 |
|---|---|---|
| Seed management | 读取固定目录或 manifest 中的业务形状输入，并保留选择、credit 与来源记账。 | `src/afl-fuzz-queue.c`、`src/afl-fuzz-nv-sched.c`、`runner/fuzz_test_runner.py` |
| Mutation | 对 JSON、URL query、文本和 multipart 输入进行字段值、边界和结构变异。 | `nv_json_mutator.py`、`nv_url_query.py`、`nv_text_mutator.py` |
| NC_MAB | 根据可归因的执行反馈，在变异策略之间平衡探索和利用。 | `src/afl-fuzz-nv-mab.c`、`src/afl-fuzz-one.c` |
| Validity filtering | 在目标请求前执行规则检查，并可接入 AE 或 SE 参考 scorer。 | `nv_body_valid.py`、`validity/`、`model_stage/nv_valid_server_real.py` |
| HTTP/representation bridge | 把 JSON、URL query、raw text 和 multipart seed 变成实际 HTTP 请求。 | `nv_http_body_adapter.py`、`nv_http_harness.py` |
| Bounded target execution | 在明确的测试用例数量和时间预算内执行目标。 | `scripts/run_task4_offline.sh`、`runner/fuzz_test_runner.py` |
| Security-state feedback | 从方法、规范化路径和响应类别形成可观察状态并交给 Cov/MAB。 | `nv_http_harness.py`、`include/afl-fuzz.h`、`src/afl-fuzz-nv-covset.c` |
| Cov / Err / Rec | 分别记录状态代理覆盖、异常代理和恢复代理，并保存分母。 | `src/afl-fuzz-run.c`、`src/afl-fuzz-stats.c` |
| Overall score | 使用调用方显式给出的权重计算有界工程指标。 | `scripts/compute_formal_security_score.py` |
| O2OA 场景 | 已有电子公文 create/save、readback、content update、再次 readback 和 cleanup 契约。 | `targets/o2oa_query.json`、`scripts/run_task4_o2oa_final_experiment.sh` |
| Alfresco 场景 | 已有 metadata、raw content 和 multipart 的历史服务场景契约。 | `targets/alfresco_*.json`、`scripts/run_task4_alfresco_final_experiment.sh` |
| Offline reproducibility | 在提交源码上执行固定的离线交付集合和 deterministic sample。 | `scripts/run_task4_offline.sh`、`scripts/run_task4_sample.sh` |
| Report generation | 生成 `eval_report.json`、`fuzzer_stats`、summary 和 execution/feedback evidence。 | `scripts/run_task4_sample.py`、`runner/fuzz_test_runner.py` |

## 它不能证明什么

这些边界是正式交付口径的一部分：

- Cov 是固定容量哈希集合上的 **bounded observable security-state proxy**，不是绝对安全覆盖率，也不是完整内部状态覆盖率。
- Rec 是存在明确恢复机会时的外部平台可用性恢复代理，不是事务恢复证明，也不是内生自愈证明。
- overall 是按公开权重计算的、场景局部的工程评价指标，不是通用安全等级。
- 受控实验中的 NC_MAB 结果不能直接扩展为每一个真实平台都优于随机选择；真实 O2OA 场景的 efficacy 不可识别，因为 validity attrition 使结构 arm 没有完成 warm-up/UCB 条件。
- Seed Scheduler 的稳定结论只覆盖已经测试的 family；不能把测试结果扩大成普遍无效或普遍有害。
- SE-fAnoGAN-ES 是可选研究后端和项目参考/契约实现；AE v1 仍是主要工程路径。批准的 Alfresco 32D 冻结 artifact 不可用，因此不能声称精确外部等价或 fresh 32D 对比完成。
- O2OA 和 Alfresco 的真实服务 PASS 是历史证据，不等于当前交付验收期间重新运行；当前交付复现验证的是 committed source 的离线能力。

## 当前正式版本

- Source checkpoint：`36e7cdd69c26bffde7c047d34f116e438ba60c81`
- Official bounded offline delivery test set：`235/235 PASS`
- Full offline suite repeat：`2/2 PASS`
- Deterministic/flaky regression：`20/20 PASS`
- Fresh import isolation、delivery sample、stranger-path reproduction：PASS
- Formal component archive：尚未由项目档案核验

`235` 是交付验收定义的 official bounded offline test set，不是整个仓库的测试总数。

## 目录结构

下面的目录来自上述 checkpoint 的真实 tree；输出目录和用户创建的外部 run root 不在源码树中。

```text
repo/
├── src/                         AFL++ C 主链和 Task 4 反馈实现
├── include/                     C 头文件、Cov/MAB/Scheduler 数据结构
├── scripts/                     离线验收、sample、平台 runner 和评分脚本
├── runner/                      有界任务 runner、模板和 run 控制器
├── integration/                 平台 profile 和 adapter 级 submit/query/stop/report
├── nv_http_harness.py           HTTP 请求、认证、状态和 readback 边界
├── nv_body_valid.py             JSON/text/multipart 有效性规则与 scorer RPC
├── nv_json_mutator.py           JSON body 变异
├── nv_url_query.py              URL query 变异与序列化
├── nv_text_mutator.py            raw text/HTTP body 变异
├── targets/                     目标配置，例如 O2OA 和 Alfresco
├── validity/                    有效性规则文件
├── schemas/                     task/profile/validity/summary 结构 schema
├── in/                          已提交的示例和平台 seed 数据
├── model_stage/                 AE/SE 参考模型服务和元数据
├── tests/                       离线和契约测试
├── docs/DELIVERY_GUIDE.md       短版交付复现说明
└── docs/TASK4_OPERATION_AND_PLATFORM_INTEGRATION_GUIDE.md
                               本次新增的完整新手与接入手册
```

## Quick Start

以下步骤使用新目录和提交源码；命令中的 `<repository-url>` 是占位符，不能原样当作真实地址。

### 1. 获取并固定源码

```bash
git clone <repository-url> AFL-
cd AFL-
git checkout 36e7cdd69c26bffde7c047d34f116e438ba60c81
git rev-parse HEAD
```

成功条件：最后一行正好是 `36e7cdd69c26bffde7c047d34f116e438ba60c81`。如果 clone 地址不可用，请使用项目提供的受信任本地镜像；不要用工作树中的未知未提交修改代替这个 checkpoint。

### 2. 准备 Ubuntu/WSL 依赖

在 Ubuntu 24.04/WSL2 中执行：

```bash
sudo apt-get update
sudo apt-get install -y build-essential python3.12 python3.12-dev python3.12-venv python3-pip zlib1g-dev coreutils
```

这一步可能访问系统软件包源；后续离线验收脚本会主动清除代理变量。成功条件是 `gcc`、`make`、`python3-config`、`timeout` 都能找到。

### 3. 建立虚拟环境并安装测试工具

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
cp scripts/python3-config-wrapper.sh .venv/bin/python3-config
chmod 0755 .venv/bin/python3-config
```

`requirements.txt` 的离线运行时只依赖 Python 标准库；`requirements-dev.txt` 安装 pytest 及其测试依赖。`requirements-live.txt` 的 `requests` 只用于可选 live multipart harness，不安装也不影响离线路径。

如果 venv 或 pytest 命令失败，先确认 `python3.12-venv` 已安装，并在当前 checkout 重新执行 pip 命令；不要把系统 Python 和旧 worktree 的包混用。

### 4. 检查并构建 AFL++ 二进制

```bash
command -v gcc make python3-config timeout
.venv/bin/python --version
python3-config --includes
python3-config --embed --ldflags
make -j2 afl-fuzz
```

成功条件：`afl-fuzz` 可执行，`python3-config --includes` 能找到 Python 头文件。若缺 `Python.h`，安装 `python3.12-dev`；若缺 zlib 头文件，安装 `zlib1g-dev`。

### 5. 执行官方离线交付集合

```bash
PYTHON_BIN="$PWD/.venv/bin/python" ./scripts/run_task4_offline.sh
```

成功条件：退出码为 0，并看到 `TASK4_OFFLINE=PASS`。权威结果是 235 discovered、235 passed、0 errors、0 stable failures、0 skipped；脚本明确排除了一个不适用于该 gate 的测试，所以 1 deselected 不是失败。

如果失败，先保存终端输出，核对 `git rev-parse HEAD`、`PYTHON_BIN` 和 `python3-config`，再单独运行配置验证；不要修改测试集合来凑到 235。

### 6. 运行 delivery sample

```bash
PYTHON_BIN="$PWD/.venv/bin/python" ./scripts/run_task4_sample.sh
```

成功条件：看到 `TASK4_SAMPLE=PASS` 和 `SAMPLE_DIR=...`。sample 输出位于新建的 `reproduce-results/delivery-smoke-<timestamp>/` 目录；它是结构 smoke，不是性能实验，也不访问网络或真实平台。

如果 sample 失败，查看该目录中的 `afl_console.log` 和 `summary_writer.log`；确认 `afl-fuzz` 已构建、seed 目录存在，并换用一个从未存在过的新输出目录。

### 7. 查看报告

```bash
SAMPLE_DIR=<the-directory-printed-by-the-previous-command>
find "$SAMPLE_DIR" -maxdepth 1 -type f -printf '%f\n' | sort
cat "$SAMPLE_DIR/sample_summary.md"
```

不要把 `<the-directory-printed-by-the-previous-command>` 原样当路径；替换成命令上一行打印出的目录。详细安装、输出和接入说明见 [完整指南](docs/TASK4_OPERATION_AND_PLATFORM_INTEGRATION_GUIDE.md)。

如果找不到报告，先确认 `SAMPLE_DIR` 指向本次命令打印的目录，而不是历史目录；离线 sample 不会向 O2OA、Alfresco 或 Docker 请求数据。

## 五分钟理解输出

| artifact | 产生位置/组件 | 新手先看什么 |
|---|---|---|
| `eval_report.json` | sample 或平台 runner | JSON 中的 validity、coverage、anomaly、recovery、overall 和 task identity。 |
| `fuzzer_stats` | AFL++ run | valid execution、Err、Rec、security-state counter、MAB pull 等原始计数。 |
| `execution_ledger.jsonl` / `executions.jsonl` | runner 的 `run/evidence/` | 每次执行是否完成、是否有反馈和归因；实际文件名由 runner layout 决定。 |
| `nv_state_trace.jsonl` / `state_trace.jsonl` | harness/runner run root | 方法、规范化路径、响应类别形成的状态观察。 |
| `mab_updates.jsonl` | runner 的 `evidence/` | arm、reward、commit、source execution 等安全记账字段。 |
| `seed_selection.jsonl` | runner 的 `evidence/` | seed selection、queue identity 和 credit 记账。 |
| `sample_summary.md` | delivery sample | 用最短文字确认 sample scope 和四个指标。 |

## 指标解释

### Cov

- 通俗解释：这次执行观察到多少种新的、被规范化的安全状态。
- 工程定义：`security_state_new_total / security_state_capacity`，当前固定容量为 65536 个 slot。
- `METHOD PATH|RESPONSE_CLASS` 是状态的可解释形式；方法、路径和响应类别会先规范化，再进入固定容量集合。
- 如果没有解析到状态，或状态集合容量已经饱和，新增状态不会被伪造；饱和、dropped 和 replay 会单独记账。
- 不能把它解释成绝对安全覆盖率或完整内部状态覆盖率。

### Err

- 通俗解释：目标执行或已定义业务/readback 检查中出现的异常比例。
- 工程定义：声明范围内的 HTTP/execution/business-ledger anomaly proxy；期望的业务拒绝不自动等于 Err。
- HTTP 2xx 也不自动等于业务成功，必须结合 readback 或业务字段；4xx 也不自动等于错误，取决于 scenario 规则。
- 没有有效执行分母时，Err 为 null，而不是把空结果当作零。

### Rec

- 通俗解释：在明确发生一次可恢复机会后，平台是否恢复到可用并通过后续业务检查。
- 工程定义：恢复成功数除以恢复机会数；恢复机会必须包含 failure/unavailability observation、health/recovery observation 和 post-recovery business check。
- 没有恢复机会时 `Rec = null`，因此 `overall = null`；不能对 null 零填充或偷偷重归一化权重。
- Rec 是外部可用性恢复代理，不是事务恢复或内生自愈证明。

### overall

它是调用方显式提供 β1、β2、β3 后形成的场景局部工程指标。只要必需分母未定义，overall 就保持 null。它不是跨平台通用安全等级。

## 两个既有平台

### O2OA

O2OA 是正式电子公文场景。历史 bounded PASS 覆盖：seed/mutation、validity、create/save、认证 readback、同文档 content update、第二次 readback、feedback/MAB accounting、Cov/Err/Rec/overall reporting 和 cleanup。真实写入只允许显式 opt-in，并且必须绑定专用 disposable category、identity 和外部新 evidence 目录。

当前目标配置为 `targets/o2oa_query.json`，真实 token 的环境变量名为 `NV_TOKEN`；写场景还需要 `NV_O2OA_CATEGORY_ID` 和 `NV_O2OA_CURRENT_USER_IDENTITY`。本 README 不提供真实值，也不建议对生产对象运行。完整的 dry-run、写入边界、readback 和 cleanup 说明见指南的 O2OA 章节。

### Alfresco

Alfresco 是跨平台工程验证场景。历史真实服务证据覆盖：

- metadata update：`targets/alfresco_metadata_update.json`；
- raw content update：`targets/alfresco_content_update.json`；
- multipart upload/create-save：`targets/alfresco_multipart_upload.json`。

当前交付 acceptance 没有 fresh live Alfresco run；需要的环境、凭据和批准的 32D frozen artifact 不应被假设存在。AE v1 是默认/主要工程后端，SE 是可选研究后端。

## 我怎么接入自己的平台

README 只给路线；完整指南给出每个字段、命令、检查结果和故障处理。

新平台接入分为配置级接入和平台专属 adapter/glue 接入；当前仓库不提供任意平台自动注册机制。需要进入 Task 4 主链时，请按指南中的 runner/harness contract 接入，而不要把教学 adapter 当成内置插件。

1. 只在你有授权的本地或测试平台上工作。
2. 写下 base URL、方法、body 类型、认证方式、read-only API、safe write API、readback、cleanup 和 health API。
3. 先创建一个最小 profile 和 validity rule；优先 rule-only。
4. 准备不含秘密、指向测试对象的少量合法 seed。
5. 先跑 config/schema/offline parse，再跑 local mock。
6. 做 read-only probe，确认认证、路径和 response parsing。
7. 只写一个 disposable object，立刻 readback，再按 exact ID cleanup。
8. 查看 state trace、Err 分母、Rec opportunity 和 MAB attribution。
9. 用极小预算通过后才增加时间或样例数量。
10. 在新 evidence 目录保留 config、seed manifest、summary 和 secret scan。

详见 [Platform Integration Guide](docs/TASK4_OPERATION_AND_PLATFORM_INTEGRATION_GUIDE.md)。

## 凭据与安全

- 密码和 token 只通过运行时环境或 owner-only（0600）文件注入；不要写进 seed、profile、task JSON 或 Git。
- 文档示例只使用 `<BASE_URL>`、`<USERNAME>`、`<PASSWORD>`、`<TOKEN>`、`<OBJECT_ID>` 等占位符。
- evidence 只保存脱敏的状态、计数、hash 或结构；不要保存 Authorization header、Cookie、密码或完整 token。
- 不要对未授权平台、生产对象或不可清理对象运行写场景。
- 默认离线命令不读取真实凭据、不访问网络、不启动平台。

## 常见问题

- **为什么不是普通 AFL edge coverage？** Cov 记录的是项目定义的可观察安全状态，不是 AFL 的原生 edge map。
- **为什么 Cov 数值很小？** 分母是固定 65536 slot capacity；小数反映观察到的新状态相对于该容量的比例。
- **为什么 Rec 是 null？** 当前 run 没有明确 recovery opportunity，null 是正确的未定义状态。
- **为什么请求几乎都被 validity reject？** seed 可能不符合 endpoint rule，或 scorer threshold 太严格；先用 rule-only 和合法 seed 验证。
- **为什么 MAB 没进入 UCB？** 必须先形成足够的有效、可归因、可 commit 的 pulls；validity attrition 会阻止 warm-up。
- **为什么 structure arm 可能没有 pull？** 没有足够有效执行，不代表 attribution 失效。
- **为什么 235 不是整个仓库 tests？** 它是 official bounded offline delivery set。
- **为什么没有 fresh Alfresco？** 当前交付 evidence 明确没有重新启动 live Alfresco；历史 PASS 仍单独保留。
- **为什么 SE 不是默认 primary？** AE v1 是主要工程路径，SE 是可选研究增强；32D approved artifact 当前不可用。

## 下一步

- 只做离线复现：阅读 [docs/DELIVERY_GUIDE.md](docs/DELIVERY_GUIDE.md)。
- 想从零安装或接入自己的系统：阅读 [docs/TASK4_OPERATION_AND_PLATFORM_INTEGRATION_GUIDE.md](docs/TASK4_OPERATION_AND_PLATFORM_INTEGRATION_GUIDE.md)。
- 想审计实现边界：固定使用 source checkpoint `36e7cdd69c26bffde7c047d34f116e438ba60c81` 和交付 evidence；不要把未提交工作树修改当成最终组件能力。
