# AFL++ / 河南重大专项 —— 新 AI 交付清单与继续工作说明
日期：2026-08-25

> 目的：把当前项目交给一个完全没有上下文的新 AI，并尽量避免它根据旧报告猜代码、重复已完成工作、误用旧凭据或直接跳到真实 fuzz。

---

## 0. 交付原则

新 AI 必须先区分三类事实：

1. **Committed source facts**：以明确 commit 导出的 source zip 为准。
2. **Current working-tree delta**：以当前工作树中尚未 commit 的 runner / tests / harness 修改为准。
3. **Audit / handoff conclusions**：用于解释“为什么这样做”，不能替代源码。

如果三者冲突：
**当前实际源码 > 最新工作树文件 > 最新独立审计 > 历史交接文档。**

任何真实服务执行前，必须重新确认：
- 当前 PWD
- branch
- HEAD
- `git status --short`
- 关键文件 SHA256
- 当前 runtime credential 仅通过环境变量注入
- 当前 run-root 为工作树外的独立目录

不要向新 AI 提供任何实际账号密码、Authorization、token、reset id/key、SMTP 捕获内容。

---

# 1. 必须交付（Minimum Required Package）

## 1.1 `README_START_HERE.md`
这是新 AI 第一份要读的文件。

必须写清：

- 项目名称：河南重大专项 / AFL++ 自动化测试框架
- 当前目标：Alfresco bounded real-feedback integration
- 当前阶段的 precise task
- 当前 repo / branch / HEAD / worktree 状态
- committed baseline 与 current delta 的关系
- 已完成验证等级
- 当前 blockers
- 下一步允许做什么 / 不允许做什么
- 阅读顺序
- “源码优先，不要根据历史报告猜代码”

建议第一行直接写：

```text
DO NOT EXECUTE REAL ALFRESCO / AFL FUZZ UNTIL YOU HAVE RE-VERIFIED THE
CURRENT SOURCE, CURRENT WORKTREE DELTA, CREDENTIAL GATE, RUN-ROOT, AND
THE REPRESENTATION-BRIDGE TEST STATUS.
```

---

## 1.2 `CURRENT_STATE.md`

至少包含以下状态：

### 公开发布 / 历史 checkpoint
```text
OFFICIAL_RELEASE_BASELINE =
c6817ce46b0120da95ba55869b6b298e18e4cf8b

HARDENING_CHECKPOINT =
fc2866d4974de04e711f8395aac076490b68fc4f
= INDEPENDENTLY VERIFIED

CONTENT / source-snapshot checkpoint =
53cb2679de33d6b7737c1fa9cf8a39ef9e8b0aa1
```

### 当前 bounded-real 工作分支（必须由接手 AI 重新验证）
最近审计记录为：

```text
BRANCH = feature/alfresco-bounded-real-feedback
HEAD   = dbffb19312faaa6164ca6c4b7abe43ff985e2d83
```

最近工作树曾包含：

```text
?? AFLplusplus_other_AI_handoff_20260825.md
?? scripts/run_alfresco_bounded_feedback.py
?? tests/test_alfresco_bounded_feedback.py
```

**注意：这些值属于最近一次审计记录。新 AI 必须运行只读命令重新确认，不能直接假定仍然成立。**

---

## 1.3 `FILE_INDEX.md`

列出所有交付文件，至少分成：

```text
01_context/
02_source/
03_current_delta/
04_audits/
05_tests_and_evidence/
06_background/
07_prompts/
```

每个文件写：
- 用途
- authoritative / historical / evidence
- 对应 commit 或工作树状态
- SHA256（最好全部生成）

---

## 1.4 完整 committed source zip

必须优先交付从明确 commit 导出的源码包。

推荐保留原始：
```text
AFLplusplus-newchat-source-*.zip
```

并在 README 写明：
```text
CODE FACTS MUST BE RESOLVED FROM THE SOURCE ZIP FIRST.
DO NOT INFER CURRENT CODE FROM OLD AUDIT TEXT.
```

如果 source zip 对应 `53cb2679de33d6b7737c1fa9cf8a39ef9e8b0aa1`，明确写入 manifest。

---

# 2. 当前工作树增量（非常重要）

因为 bounded-real 工作不一定已经 commit，所以仅有旧 source zip 不够。

建议单独提供 `03_current_delta/`，至少包含：

```text
nv_http_harness.py
nv_http_body_adapter.py
tests/test_nv_http_harness_representation_bridge.py

scripts/run_alfresco_bounded_feedback.py
tests/test_alfresco_bounded_feedback.py
```

如果还有其它本轮修改文件，全部加入。

## 当前已看到的 representation bridge 状态

当前 `nv_http_harness.py` 已出现：

- `HttpBodyAdapterError`
- `extract_http_body`
- body-only 模式下先判断输入是否像 FULL HTTP
- FULL HTTP 时抽取 body 后再交给 `body_validate`
- malformed envelope 时 fail-closed，不写 status / exec_seq

这意味着此前的 **CB-1（FULL HTTP -> body-only representation bridge 未接入）在源码层面已经出现修复实现**。

但必须明确：
**本交付清单没有替代 fresh test execution。新 AI 应重新运行对应 offline tests 后，才能把 CB-1 标记为 VERIFIED。**

当前 regression test：
```text
tests/test_nv_http_harness_representation_bridge.py
```

覆盖：
- FULL HTTP -> byte-exact body
- 原 body-only JSON 路径不回归
- malformed HTTP envelope fail-closed
- malformed body-only input fail-closed

---

# 3. 当前仍需重点确认的 blocker

## CB-1 — Representation bridge
历史状态：
```text
FULL HTTP testcase
    -> C-side validity
    -> production harness body_only_mode=1
```
之间缺 bridge。

当前源码中已看到 bridge 实现，但：
```text
IMPLEMENTED IN CURRENT FILES
TEST EXECUTION STATUS = MUST RE-VERIFY
```

新 AI 第一轮应先做：
```bash
python3 -m unittest tests.test_nv_http_harness_representation_bridge -v
```
或使用仓库实际测试入口。

---

## CB-2 — `run_alfresco_bounded_feedback.py` runner 主流程

最近独立审查结论：
`main()` 仍然只是 credential-presence stub。

历史观察：
- `build_run_layout()` 存在
- `resolve_existing_dedicated_node()` 存在
- `render_runtime_target_config()` 存在
- 但 `main()` 没有把它们串起来
- `--preflight-only` 曾被 parse 后丢弃
- 没有真正准备 run root / target / AFL execution

因此：

```text
CB-2 STATUS = RE-VERIFY CURRENT FILE
```

新 AI 不应直接根据历史结论修改；先读当前 `scripts/run_alfresco_bounded_feedback.py`。

---

# 4. 必须交付的独立审计 / 历史结论

建议放入：

```text
04_audits/
  metadata_independent_audit.txt
  content_independent_audit.txt
  gate2_final_audit_and_hardening_log.txt
  AFLplusplus_other_AI_handoff_20260825.md
  claude_reply.md
```

用途：

- metadata/content Level-C 证明真实 harness 和 credential / containment 设计的历史验证状态
- Gate-2 证明 credential hardening、secret scanner、env-only、fail-closed 的独立审计历史
- latest handoff / Claude review 记录 bounded feedback 的源代码推导、blocker、case-budget、exec_seq、MAB、reporting 等分析

**不要让新 AI 把这些审计文本当成源码。**

---

# 5. 必须交付的项目背景

```text
06_background/AFL++源代码修改总纲.md
```

它用于帮助新 AI理解：
- 为什么修改 AFL++
- security-state coverage 与普通 AFL edge coverage 的区别
- mutator / validity / harness / state / reward / MAB / scheduler / reporting 的总体关系

如果有论文/项目需求说明、河南重大专项验收指标，也建议放在这个目录。

---

# 6. 建议额外交付的核心源码清单

若不想让新 AI 每次解压全仓库，建议同时提供一个 `source_focus/`：

```text
nv_json_mutator.py
nv_body_valid.py
nv_http_harness.py
nv_http_body_adapter.py
nv_state_probe.py

src/afl-fuzz-run.c
src/afl-fuzz-nv-covset.c
src/afl-fuzz-nv-mab.c
src/afl-fuzz-nv-sched.c
src/afl-fuzz-one.c
src/afl-fuzz-stats.c
src/afl-fuzz-queue.c
src/afl-fuzz-bitmap.c
src/afl-fuzz.c
include/afl-fuzz.h

targets/alfresco_metadata_update.json

scripts/run_alfresco_levelc_metadata.py
scripts/run_alfresco_levelc_content.py
scripts/run_alfresco_bounded_feedback.py
scripts/run_p0_mab_feedback_experiment.sh
scripts/summarize_p0_mab_feedback.py

tests/test_nv_http_harness_representation_bridge.py
tests/test_alfresco_bounded_feedback.py
tests/test_nv_mab_unit.py
tests/test_p0_mab_feedback_evidence.py
test/unittests/unit_nv_sched.c
```

---

# 7. 新 AI 必须知道的关键工程事实

## 7.1 数据表示链

当前目标链路：

```text
FULL HTTP testcase
  -> C-side nv_validity_check()
  -> FULL HTTP -> body extraction bridge
  -> body_validate()
  -> production HTTP request
  -> nv_http_status.json
  -> exec_seq freshness
  -> security-state observation
  -> state-set insertion
  -> source queue credit
  -> reward attribution
  -> MAB update
  -> scheduler-visible counters
  -> fuzzer_stats / eval_report.json / summary
```

---

## 7.2 `exec_seq`

- status namespace 由 `NV_STATUS_PATH` 决定
- sidecar 为：
  ```text
  NV_STATUS_PATH + ".seq"
  ```
- 每次真实 target execution 通过 sidecar 分配单调 exec_seq
- validity reject 不应 mint exec_seq
- observer/read-back 不应 mint exec_seq
- run-root 必须每次独立，否则旧 status 可能污染新 AFL process 的 freshness 判定

---

## 7.3 Case budget

`max_test_cases` 来自 task JSON。

已审查的核心语义：

```text
C-side validity reject      -> 不消耗 case
target 已执行后 Python reject -> 消耗 case
真实 2xx/4xx/5xx/timeout     -> 消耗 case
dry run / calibration       -> 不消耗 case
```

因此 representation bridge 如果坏了，会出现危险的“预算被消耗但反馈为零”的假运行。

---

## 7.4 Scheduler / seed credit

security-state 新状态会 credit 当前 `queue_cur`：
```text
queue_cur->ss_cov_cnt++
security_state_seed_credit++
```

但 `ss_cov_cnt` 还可能受到 native AFL bitmap new_bits 的影响。

因此在 `-n` 非 instrumented bounded run 中，才适合使用简化 conservation：

```text
ss_cov_sum == security_state_seed_credit
```

并应先确认：
```text
ss_new_bits_any == 0
```

---

## 7.5 MAB

至少需要核对：

- mutator 通过 `NV_JSON_ARM_USED` 与 fuzzer 做 arm attribution
- reward 必须绑定 fresh exec_seq
- `nv_mab_total_pulls == sum(per-arm pulls)`
- bounded run 最后一例达到 stop condition 时，可能已经做 state accounting，但不一定完成 MAB reward update

不要简单假定：
```text
nv_mab_total_pulls == max_test_cases
```

---

# 8. Credential / Secret 安全要求

新 AI 应只知道变量名：

```text
ALFRESCO_USER
ALFRESCO_PASS
```

不要交付值。

禁止包含：
- Basic / Bearer header
- plaintext password
- old exposed password
- reset password id/key
- SMTP capture
- token
- runtime owner-only secret file 内容

真实运行时只检查：
```text
SET_NONBLANK / UNSET_OR_BLANK
```

不要打印值。

---

# 9. 新 AI 第一轮应该做什么

建议严格按以下顺序：

### Step 1 — READ ONLY identity
```bash
pwd
git branch --show-current
git rev-parse HEAD
git status --short
```

### Step 2 — hashes
```bash
sha256sum \
  nv_http_harness.py \
  nv_http_body_adapter.py \
  tests/test_nv_http_harness_representation_bridge.py \
  scripts/run_alfresco_bounded_feedback.py \
  tests/test_alfresco_bounded_feedback.py
```

### Step 3 — source audit
确认：
- representation bridge 当前源码究竟是什么
- bounded runner `main()` 当前究竟是什么
- 不根据 handoff 猜

### Step 4 — offline tests
优先跑：
```text
representation bridge tests
bounded runner unit tests
相关 MAB / evidence tests（若本轮需要）
```

### Step 5 — 更新状态表
输出：
```text
CB-1 = IMPLEMENTED / VERIFIED / FAILED
CB-2 = STUB / PARTIAL / IMPLEMENTED / VERIFIED
```

### Step 6 — 只有通过门禁后，再进入 real preflight / bounded run
不要直接执行真实 fuzz。

---

# 10. 建议新 AI 使用的验证等级

统一使用：

```text
DESIGN CLAIM
IMPLEMENTED
VERIFIED BY IMPLEMENTER
INDEPENDENTLY VERIFIED
PARTIALLY VERIFIED
NOT VERIFIED
```

不要把：
- “代码里有”
- “测试文件存在”
- “旧报告说 PASS”

自动写成：
```text
INDEPENDENTLY VERIFIED
```

---

# 11. 推荐交付目录

```text
AFLplusplus-new-ai-handoff-20260825/
├── README_START_HERE.md
├── SHA256SUMS
├── 01_context/
│   ├── CURRENT_STATE.md
│   └── FILE_INDEX.md
├── 02_source/
│   └── AFLplusplus-newchat-source-<commit>.zip
├── 03_current_delta/
│   ├── nv_http_harness.py
│   ├── nv_http_body_adapter.py
│   ├── test_nv_http_harness_representation_bridge.py
│   ├── run_alfresco_bounded_feedback.py
│   └── test_alfresco_bounded_feedback.py
├── 04_audits/
│   ├── metadata_independent_audit.txt
│   ├── content_independent_audit.txt
│   ├── gate2_final_audit_and_hardening_log.txt
│   ├── AFLplusplus_other_AI_handoff_20260825.md
│   └── claude_reply.md
├── 05_tests_and_evidence/
│   ├── latest_test_output.txt
│   ├── git_identity.txt
│   └── key_file_sha256.txt
├── 06_background/
│   └── AFL++源代码修改总纲.md
└── 07_prompts/
    └── NEW_AI_CONTINUATION_PROMPT.md
```

---

# 12. 可直接给新 AI 的首条 Prompt

```text
你现在继续执行“河南重大专项 / AFL++ 自动化测试框架”项目。

先不要修改代码，也不要执行真实 Alfresco 请求或 fuzz。

请按顺序阅读：

1. README_START_HERE.md
2. 01_context/CURRENT_STATE.md
3. 01_context/FILE_INDEX.md
4. 02_source/ 中的 committed source zip
5. 03_current_delta/ 中当前未提交/新增文件
6. 04_audits/ 中最新独立审计与 handoff
7. 06_background/AFL++源代码修改总纲.md

代码事实优先级：

CURRENT WORKING-TREE SOURCE
> exact committed source snapshot
> independent audit
> historical handoff/report

不要根据旧报告猜当前文件内容。

第一轮只做 READ-ONLY REVALIDATION：

A. 输出：
- PWD
- branch
- HEAD
- git status --short
- 5 个关键 current-delta 文件 SHA256

B. 独立确认 representation bridge：
- FULL HTTP testcase 是否在 body_only_mode=1 下 byte-exact 提取 body
- plain body-only JSON 是否保持原路径
- malformed envelope 是否 fail-closed
- validity reject 是否不写 status、不 mint exec_seq

C. 独立确认 bounded runner：
- build_run_layout 是否真正被 main 使用
- --preflight-only 是否真正有语义
- 是否执行 node resolution
- 是否准备 fresh run-root
- 是否 render runtime target
- 是否已经具备 AFL launch
- 如果仍是 stub，明确指出，不要猜

D. 运行允许的 offline tests 后，给出：
CB-1 =
CB-2 =

验证等级仅允许：
DESIGN CLAIM / IMPLEMENTED / VERIFIED BY IMPLEMENTER /
INDEPENDENTLY VERIFIED / PARTIALLY VERIFIED / NOT VERIFIED

第一轮结束前：
- 不访问真实 Alfresco
- 不执行 fuzz
- 不 commit/push/merge/tag/reset/rebase
- 不修改核心 AFL++ C 文件
- 不输出任何 credential 值

最后给出下一步最小动作建议。
```

---

# 13. 交付前最后检查

发送给其它 AI 前确认：

- [ ] 没有 secret
- [ ] source zip 的 commit 写清
- [ ] current delta 单独提供
- [ ] SHA256SUMS 已生成
- [ ] README 写明 source precedence
- [ ] README 写明 current task
- [ ] README 写明禁止行为
- [ ] 最新测试输出已包含
- [ ] 旧报告明确标记为 historical evidence
- [ ] 新 AI Prompt 已包含 READ-ONLY first pass
