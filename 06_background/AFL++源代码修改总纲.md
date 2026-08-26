According to a document from  **2026-01-05** （《4-1.课题1-广义功能安全测评工具总体设计方案 v2.3@20260105》），你要把 AFL++ 改造成项目要求的 **Deep2Fuzz-ES** 模糊测试引擎：具备“高质量种子驱动—用例生成—有效性验证—执行监控—反馈优化”的闭环，并输出可量化的内生安全评估指标（覆盖/异常/恢复等），同时还要能按平台侧接口规范接收“模糊测试任务下发/查询/停止/报告查询”的参数。下面给你一套 **可落地、按文件改代码的完整流程** （我把每一步要改哪里、改什么、验什么写清楚）。

---

## 0）先把“项目要求”翻译成 AFL++ 必须新增的能力

### A. Deep2Fuzz-ES 闭环（AFL++ 内核要做的）

* **种子选择** ：按“安全状态覆盖贡献 + 历史选择次数”动态计算选择概率，优先选高价值且没被过度使用的种子。
* **变异策略选择（NC_MAB）** ：把“策略选择”建模为多臂老虎机，用“覆盖率提升”做奖励信号，自适应选择策略组合。
* **有效性验证（SE-fAnoGAN-ES）** ：对生成用例计算“异常分数”，过滤明显无效/违规语义的输入，降低无效执行开销。
* **执行监控与评估** ：采集覆盖变化、异常事件、恢复过程，输出量化指标（覆盖率/异常触发率/恢复率）用于内生安全性能评估。

### B. 电子政务 O2OA 场景的输入形态（你的变异算子要覆盖）

* 目标是 HTTP/REST 接口，输入包含  **JSON 请求体 + URL 查询参数** ，变异包括字段顺序、字符串空/超长/特殊字符、数值边界/异常值、枚举非法值等。

### C. 平台侧“工具接口参数”（你需要一个任务配置入口）

* 方案里明确了 `fuzz_test_submit` 的字段：`target_type`、`target_endpoint`、`seed_source/seed_location`、`mutation_scope`、`max_test_cases`、`time_budget` 等。
* 以及 `fuzz_test_query / fuzz_test_stop / fuzz_test_report_query` 的基本语义（状态、停止、报告列表）。

---

## 1）AFL++ 改造总体策略（别一上来就“硬改 havoc”）

我建议你把改造分两层：

### Layer-1：AFL++ 内核“调度/度量/统计”增强（必须改源码）

这层实现： **种子调度（安全状态覆盖贡献）+ NC_MAB 策略选择 + 统计指标导出** 。

### Layer-2：业务输入变异与有效性验证（优先用 AFL++ 的扩展接口挂进来）

* HTTP/JSON 的结构化变异、语义约束、以及 SE-fAnoGAN-ES 这种深度模型筛选，放进 **AFL++ custom mutator / 外部过滤器** 更稳（否则你把 C 代码写成半个 Python 框架，会非常痛苦）。

> 你问的是“怎么修改 AFL++ 源码”：Layer-1 必改；Layer-2 我会给你两种做法：
> **(推荐)** custom mutator + 外部过滤 hook（仍需要在 AFL++ 里加“过滤回调点”和统计字段）
> **(不推荐但可做)** 直接把结构化变异塞进 havoc（侵入大、难维护）

---

## 2）源码改动清单（按文件/结构体/函数落点给你）

下面按 AFL++（典型结构）给你“改哪些文件、加哪些字段、在哪些流程点插入”。

> 说明：你本地 AFL++ 版本不同，函数名可能略有差异，但“落点”基本都在：
> `include/afl-fuzz.h`（核心结构体）
> `src/afl-fuzz-queue.c`（队列与种子调度）
> `src/afl-fuzz-one.c`（单次 fuzz 循环、变异阶段）
> `src/afl-fuzz-run.c`（run_target 前后钩子）
> `src/afl-fuzz-stats.c`（统计输出）

### 2.1 新增：任务配置结构（对应 fuzz_test_submit）

 **目标** ：AFL++ 启动时能加载一个 `profile.json` / `task.json`，字段对齐方案里的 schema（最少要支持 `target_type/target_endpoint/seed_source/seed_location/mutation_scope/max_test_cases/time_budget`）。

 **改法** ：

1. `include/afl-fuzz.h`：新增结构体 `nv_task_cfg_t`（或你的命名）
   * `target_type`（枚举）
   * `target_endpoint`（string）
   * `seed_source/seed_location`
   * `mutation_scope`（bitmask：field_value/boundary/structure）
   * `max_test_cases`、`time_budget`
2. `afl_state` 里挂一个 `nv_task_cfg_t nv_task;`
3. `src/afl-fuzz.c`（或主入口解析参数文件处）：新增参数 `--nv_task <path>`，解析 JSON 填入 `state->nv_task`。

 **验收** ：

* 传入任意任务 JSON，AFL++ 能打印解析后的配置（debug log），并把 `time_budget/max_test_cases` 映射到 AFL 的停止条件（见 2.6）。

---

### 2.2 新增：种子“安全状态覆盖贡献”字段 + 调度策略

 **需求来源** ：方案要求种子选择要基于“安全状态覆盖贡献”并结合历史选择次数动态算概率。

 **改法** ：

1. `include/afl-fuzz.h`：在 `struct queue_entry` 增加字段
   * `u64 ss_cov_cnt;`（该种子触发“新安全状态/新覆盖”的累计次数）
   * `u64 ss_selected_cnt;`（被选中次数）
   * `double ss_prob;`（当前选择概率/权重）
2. `src/afl-fuzz-queue.c`：
   * 在“选下一个 queue entry”的地方（通常是 `select_next_queue_entry()` 之类）替换为：
     * 每轮更新 `ss_prob = f(ss_cov_cnt, ss_selected_cnt)`
       逻辑必须满足：`ss_cov_cnt` 越大越优先、`ss_selected_cnt` 越大越降低优先（但不能降为 0）。
   * 选择时按 `ss_prob` 做加权随机（roulette wheel）或用 alias method（性能更好）。
3. 在“发现新覆盖/新状态”的地方更新 `ss_cov_cnt++`：
   * AFL++ 原本在保存新 path（或新 coverage）时会标记 `new_bits/new_cov`，你就在那个分支把 `queue_cur->ss_cov_cnt++`，并在需要时把触发新状态的 input 作为新 seed 入队（方案也要求“触发新安全状态→加入种子池”）。

 **验收** ：

* `fuzzer_stats`/自定义日志里能看到：top seeds 的 `ss_cov_cnt` 更高、且 `ss_selected_cnt` 不会无限偏向某一个种子（避免“过度使用”）。

---

### 2.3 新增：NC_MAB 变异策略选择（替换“固定 stage schedule”）

 **需求来源** ：NC_MAB 用覆盖率提升做奖励，动态选策略组合。

**策略集合怎么定（结合政务 O2OA）**
你至少要把策略拆成两类（和文档一致）：

* **field_value** ：字段值变异（字符串空/超长/特殊、枚举非法等）
* **boundary** ：数值边界/异常值
* **structure** ：结构级变异（字段顺序、字段增删、嵌套结构扰动）

 **改法** ：

1. `include/afl-fuzz.h`：在 `afl_state` 增加一个 `nv_mab_t`：
   * `k` 个“臂”（策略），每个臂存：
     * `u64 pulls; double mean_reward; double ucb;`
   * 全局 `u64 total_pulls; double c;`
2. `src/afl-fuzz-one.c`：
   * 在每次生成用例前（进入 havoc/custom mutator 前）：
     * 调用 `nv_mab_pick(&state->nv_mab, state->nv_task.mutation_scope_mask)`，得到本轮策略（或策略组合）。
   * 执行完该用例后：
     * 计算 reward：用 **coverage delta / 新状态 delta** 做奖励信号（文档要求“覆盖率提升为奖励”）。
     * 调用 `nv_mab_update(arm_id, reward)` 增量更新均值，并更新 UCB。
3. 把选到的 `arm_id` 传给变异层：
   * 如果你用 custom mutator，就把 `arm_id` 写到共享结构/回调参数里；
   * 如果你硬改 havoc，就在 havoc 内根据 arm_id 限制/启用某些变异算子（不推荐）。

 **验收** ：

* 运行一段时间后，各 arm 的 `pulls/mean_reward` 会分化，且高 reward 的策略被更多选择（能从日志中看到）。

---

### 2.4 新增：SE-fAnoGAN-ES 有效性验证“过滤点”（run_target 前）

 **需求来源** ：用异常分数过滤无效用例，降低无效执行开销。

 **改法（推荐：外部模型服务 + AFL++ 过滤 hook）** ：

1. `include/afl-fuzz.h`：加统计字段
   * `u64 nv_invalid_cnt; u64 nv_valid_cnt;`
2. `src/afl-fuzz-run.c`（或调用 target 前的统一入口）：
   * 在 `run_target()` 前插入：
     * `if (state->nv_enable_validity && nv_validity_check(buf, len) == REJECT) { nv_invalid_cnt++; skip execution; return; }`
   * `nv_validity_check()` 的实现建议走 **Unix socket / pipe / shared memory** 调外部 Python 服务（模型在 Python 侧跑，C 侧只做 RPC）。
3. 把阈值/开关写到 `task.json`（比如 `validity_model_endpoint`, `threshold`），或者用环境变量（更像 AFL++ 风格）。

 **验收** ：

* 统计里能看到 invalid 被跳过；
* overall exec/s 上升（因为无效用例不再跑 target）；
* 同时不会把“有效但能触发异常”的用例误杀（阈值需要调）。

---

### 2.5 新增：内生安全评估指标（Cov / Err / Rec）与结果导出

 **需求来源** ：模糊测试要用于内生安全性能量化评估（覆盖、异常、恢复）。

**在 AFL++ 里怎么落地（务实版）**

* **Cov** ：用 AFL++ 的 coverage（新边/新路径/bitmap hitcount 等）作为“覆盖代理”。（文档里讲“神经元覆盖”更多是算法思想；你落地到政务接口 fuzz，直接用路径覆盖最合理。）
* **Err** ：异常触发率 = `crash + hang + 非预期 HTTP 响应（500/异常码/异常关键字）` / `valid_cases`
* crash/hang AFL++ 自带计数
* HTTP 异常需要 harness/target wrapper 回传“业务异常”标志（通常靠退出码或写文件/SHM 标记）
* **Rec** ：恢复率/恢复时间
* 你需要 harness 侧监控：异常后接口是否恢复可用（healthcheck），并把恢复成功/耗时回传给 AFL++（写到 shared file/SHM）。文档强调“异常后恢复至可用状态”的统计。

 **改法** ：

1. `include/afl-fuzz.h`：加 counters
   * `u64 nv_total_valid_exec;`
   * `u64 nv_err_exec;`
   * `u64 nv_rec_success; u64 nv_rec_total; u64 nv_rec_time_sum_ms;`
2. `src/afl-fuzz-run.c`：每次执行后读取“业务回传”：
   * 例如：harness 写一个 `status.json`（包含 http_code、is_exception、recover_ms、recovered），AFL++ 读一下并累计（只读很小的结构化数据，别读大日志）。
3. `src/afl-fuzz-stats.c`：
   * 把 `Cov/Err/Rec` 以及最终综合分写入：
     * `fuzzer_stats`（方便你跑实验对比）
     * `eval_report.json`（给平台汇总）
4. `eval_report.json` 至少包含：
   * task_id/task_name（来自 `task.json`）
   * 覆盖趋势（可选）
   * Err/Rec 统计
   * top crashes（AFL++ 原生）
   * invalid rate（SE-fAnoGAN 过滤效果）

---

### 2.6 新增：按 time_budget / max_test_cases 自动停止（对应任务参数）

 **需求来源** ：任务下发明确带 `max_test_cases`、`time_budget`。

 **改法** ：

1. time_budget：映射到 AFL++ 的“运行时长限制”
   * 在主循环里如果 `now - start_ts > time_budget`，触发 graceful stop（写 final stats + flush queue）。
2. max_test_cases：每执行一个 **valid case** 计数 `nv_total_valid_exec++`，超过就停。

---

## 3）把“工具接口（submit/query/stop/report）”落成可用的工程形态

方案里的 `fuzz_test_submit` 等接口本质是**平台侧 MCP/网关**调用的工具定义，你不应该直接把 HTTP Server 写进 AFL++ 内核（会污染代码）。正确做法：

### 推荐落地

* 写一个  **fuzz-test-runner（外层控制器）** ：
  * 接收 `fuzz_test_submit` 的 JSON（字段完全按方案）
  * 生成 `task.json` + 种子目录
  * 拉起你改造后的 `afl-fuzz --nv_task task.json ...`
  * 保存 task_id -> pid/目录 映射
* `fuzz_test_query`：读 `fuzzer_stats/eval_report.json` 返回进度描述
* `fuzz_test_stop`：按 task_id kill pid（优雅：SIGINT）
* `fuzz_test_report_query`：列出报告文件 + 下载链接（平台侧做文件服务）

> 这样做的好处：AFL++ 只负责“引擎”，平台接口由外层服务对接，符合方案的系统分层思路。

---

## 4）最小可验收版本（MVP）路线：一周内跑通 O2OA 场景

按方案的 O2OA 场景，先只做 `target_type=http_api`：

* seeds：抓正常请求（JSON body + query param）当初始种子
* mutator：实现三类 scope（field_value/boundary/structure）
* validity：先用“轻量规则 + JSON schema 校验”模拟 SE-fAnoGAN（等你模型服务 ready 再替换），过滤明显非法结构；过滤点按 2.4 留好接口。
* Err：HTTP 500/超时/关键字（Exception/Stacktrace） + crash/hang
* Rec：异常后轮询 healthcheck（例如 `/health`）直到恢复，记录耗时（harness 回传）

---

## 5）你照这个流程改完，最终应达到的“交付行为”

1. 你能用一份 `task.json`（字段对齐 `fuzz_test_submit`）启动 fuzz；
2. AFL++ 在运行中会：
   * 用“安全状态覆盖贡献”挑种子；
   * 用 NC_MAB 挑变异策略并基于覆盖提升更新奖励；
   * 在 run_target 前做有效性过滤；
   * 统计 Cov/Err/Rec 并输出报告；
3. 你能被外层 runner 做到 query/stop/report（不把 HTTP 逻辑塞进 AFL++）。

---

如果你愿意，我可以按你当前 AFL++ 的代码版本（你把 `rg` 搜到的关键函数名/文件路径发我，比如队列选择函数、写 stats 的函数）把上面每一步进一步“对号入座”到 **你仓库里的精确函数名与插入点** ，做到你直接照着改不会迷路。
