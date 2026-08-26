
# 0. 仓库拓扑：必须先理解“主仓库”和“当前 bounded 工作树”的关系

新 AI 必须知道，本项目不是只有一个目录。

```text
AFL++ 主仓库 / 正式基线仓库
/home/dministrator/AFLplusplus

    作用：
    - 保存 AFL++ 项目的正式 release / public-release 基线；
    - OFFICIAL_RELEASE_BASELINE 的权威来源；
    - 用于核对正式分支、release tag、历史 checkpoint；
    - 不应因为 bounded integration 测试而随意改动。

当前 Alfresco bounded real-feedback 工作树
/home/dministrator/AFLplusplus-alfresco-real-feedback

    作用：
    - 当前 bounded integration / Alfresco real-feedback 工作目录；
    - 当前开发分支：
      feature/alfresco-bounded-real-feedback
    - 最近一次已报告 HEAD：
      dbffb19312faaa6164ca6c4b7abe43ff985e2d83
    - 当前阶段的 Python runner / tests / representation bridge 等工作在这里核验。
```

## 主仓库与当前工作树不能混淆

新 AI 必须明确区分：

- `/home/dministrator/AFLplusplus`
  = **AFL++ 主仓库 / 正式发布基线来源**

- `/home/dministrator/AFLplusplus-alfresco-real-feedback`
  = **当前 Alfresco bounded integration 工作树**

不得把 bounded 工作树的 HEAD 当成 `OFFICIAL_RELEASE_BASELINE`，也不得因为当前工作树存在未提交文件就判断主仓库的 `public-release` 已被污染。

## 启动时必须分别只读检查两个目录

### A. 主仓库

```bash
cd /home/dministrator/AFLplusplus

pwd
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
git log -1 --oneline --decorate

git rev-parse public-release 2>/dev/null || true
git rev-parse origin/public-release 2>/dev/null || true
```

至少核对：

```text
MAIN_REPO_PATH = /home/dministrator/AFLplusplus
OFFICIAL_RELEASE_BASELINE =
  c6817ce46b0120da95ba55869b6b298e18e4cf8b
```

如果 live 主仓库状态与 handoff 不一致，必须报告差异，不得修改。

### B. 当前 bounded 工作树

```bash
cd /home/dministrator/AFLplusplus-alfresco-real-feedback

pwd
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
git log -1 --oneline --decorate

sha256sum \
  scripts/run_alfresco_bounded_feedback.py \
  tests/test_alfresco_bounded_feedback.py 2>/dev/null || true
```

然后输出：

```text
MAIN_REPO_STATE_VERIFIED = YES | NO | PARTIAL
BOUNDED_WORKTREE_STATE_VERIFIED = YES | NO | PARTIAL

MAIN_REPO_PATH = ...
MAIN_REPO_BRANCH = ...
MAIN_REPO_HEAD = ...
MAIN_REPO_STATUS_SHORT = ...

BOUNDED_WORKTREE_PATH = ...
BOUNDED_WORKTREE_BRANCH = ...
BOUNDED_WORKTREE_HEAD = ...
BOUNDED_WORKTREE_STATUS_SHORT = ...

OFFICIAL_RELEASE_BASELINE_MATCH = YES | NO | UNKNOWN
DISCREPANCIES = [...]
```

---

# 当前仓库状态快照（交给新 AI 后必须先复核）

> 注意：下面是**本项目最近一次已报告/已核对的仓库状态快照**，不是对新会话启动时 live repository 的自动保证。
> 新 AI 在回答任何项目问题之前，必须先在实际仓库中重新执行只读 Git 检查；如果 live 状态与本快照不同，必须报告差异，不能静默沿用旧状态。

```text
REPOSITORY_STATE_SNAPSHOT

PWD    = /home/dministrator/AFLplusplus-alfresco-real-feedback
BRANCH = feature/alfresco-bounded-real-feedback
HEAD   = dbffb19312faaa6164ca6c4b7abe43ff985e2d83

LAST_REPORTED_STATUS_SHORT =
  ?? AFLplusplus_other_AI_handoff_20260825.md
  ?? scripts/run_alfresco_bounded_feedback.py
  ?? tests/test_alfresco_bounded_feedback.py

RUNNER_SHA256 =
  e9a61a0160c9601460219ed7e146728614fae8ead378aaccaca15e2dd119d546

TEST_SHA256 =
  9a7103982f73950afe6f43e1750c932c6e13bd20872f235b92dfbf40087e7516

OFFICIAL_RELEASE_BASELINE =
  c6817ce46b0120da95ba55869b6b298e18e4cf8b

HARDENING_CHECKPOINT =
  fc2866d4974de04e711f8395aac076490b68fc4f

METADATA_CHECKPOINT =
  5f2d72191...   # 当前交接材料中只应在有完整 SHA 证据时补齐

CONTENT_CHECKPOINT / PRIOR COMMITTED SOURCE-OF-TRUTH =
  53cb2679de33d6b7737c1fa9cf8a39ef9e8b0aa1

CURRENT_PHASE =
  OFFLINE BOUNDED INTEGRATION — TDD PHASE

REAL_ALFRESCO_FULL_FUZZ_RUN =
  NOT COMPLETED

FULL_REAL_SERVICE_FEEDBACK_LOOP =
  NOT COMPLETED

FLOWABLE_PRIORITY =
  DE-PRIORITIZED; ALFRESCO FIRST
```

## 新 AI 启动后必须先执行的只读仓库复核

在仓库根目录执行：

```bash
pwd
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
git log -1 --oneline --decorate

sha256sum   scripts/run_alfresco_bounded_feedback.py   tests/test_alfresco_bounded_feedback.py 2>/dev/null || true
```

然后先输出：

```text
LIVE_REPO_STATE_MATCHES_HANDOFF = YES | NO | PARTIAL
LIVE_PWD = ...
LIVE_BRANCH = ...
LIVE_HEAD = ...
LIVE_STATUS_SHORT = ...
DISCREPANCIES = [...]
```

只有完成这一步，才允许继续回答下面的项目掌握度问题。

---

# AFL++ / 河南重大专项项目掌握度核验提问

> 用途：把本文件原样交给“新 AI”，判断它是否真正掌握了本项目的目标、技术路线、权威基线、已完成工作、当前阶段、关键工程契约、未完成项、下一步计划与操作边界。
>
> 作答原则：只根据已提供的项目材料和当前代码事实回答；不得靠常识补齐；无法确认的内容必须明确写 `UNKNOWN` / `NOT VERIFIED`；如果历史报告与最新 committed source 冲突，以当前指定源码为准。

---

## 一、作答规则

请先不要修改代码、不要执行 fuzz、不要访问真实 Alfresco、不要创建或切换 Git refs。

回答时必须：

1. 先给项目总览，再回答细节。
2. 所有重要结论标注验证等级：
   - `DESIGN CLAIM`
   - `IMPLEMENTED`
   - `VERIFIED BY IMPLEMENTER`
   - `INDEPENDENTLY VERIFIED`
   - `PARTIALLY VERIFIED`
   - `NOT VERIFIED`
3. 明确区分历史事实、当前权威事实、当前计划和尚未验证的假设。
4. 不同材料冲突时，指出冲突并说明采用哪个来源作为最终依据。
5. 对代码事实，优先使用当前指定 committed source / 最新上传源码，不能拿旧审计报告覆盖新源码。
6. 不允许用“应该”“大概”“看起来”替代证据。
7. 最后必须给出：
   `PROJECT_UNDERSTANDING_VERDICT = PASS / PARTIAL / FAIL`

---

# 二、项目目标与总体路线

### Q1. 请用 300～500 字说明这个项目究竟要解决什么问题。

至少覆盖：

- “河南重大专项 / AFL++ 自动化测试框架”的总体目标；
- 为什么选择在 AFL++ 上扩展；
- 当前重点测试对象为什么是 Alfresco；
- Flowable 当前处于什么优先级；
- 项目中 coverage 当前具体指什么；
- 最终希望形成怎样的自动化测试 / 反馈闭环。

### Q2. 请画出当前希望实现的完整数据流。

从：

`seed / testcase`

一直写到：

`validation -> production execution -> status / exec_seq -> security-state observation -> reward -> MAB -> scheduler -> stats/report`

至少说明这些组件的职责：

- `nv_json_mutator.py`
- `src/afl-fuzz-run.c`
- `nv_body_valid.py`
- `nv_http_harness.py`
- `nv_state_probe.py`
- `src/afl-fuzz-nv-covset.c`
- `src/afl-fuzz-nv-mab.c`
- `src/afl-fuzz-nv-sched.c`
- `fuzzer_stats`
- `eval_report.json`
- `summary.csv`

并明确：哪些段已经实现，哪些段已经独立验证，哪些段仍没有在真实 Alfresco fuzz 中闭环验证。

---

# 三、Git 基线与权威代码事实

### Q3. 请列出当前已知的关键 Git checkpoint / baseline，并解释意义。

回答前必须明确区分 `/home/dministrator/AFLplusplus` 主仓库与 `/home/dministrator/AFLplusplus-alfresco-real-feedback` 当前 bounded 工作树。

至少包括：

- `OFFICIAL_RELEASE_BASELINE`
- `HARDENING_CHECKPOINT`
- `METADATA_CHECKPOINT`
- `CONTENT_CHECKPOINT`
- 当前 bounded-real-feedback 相关分支 / HEAD（如材料中存在）

要求：

- 写出掌握的完整 SHA；若材料只给了前缀，明确说明；
- 不得把不同阶段 checkpoint 混成一个；
- 说明发生冲突时哪个 source tree 应被视为代码事实。

### Q4. 如果历史审计报告与最新 source zip 中代码不一致，你应该相信谁？为什么？

同时说明：

- 哪个 committed source 曾被指定为优先代码事实；
- “报告事实”和“代码事实”的优先级；
- 上传时间或 ModifiedAt 是否足以证明内容更新。

---

# 四、已经完成并验证的阶段

### Q5. Gate-1 做了什么？

说明：

- 最初为什么被阻断；
- credential 泄露问题；
- 后续修复 / 密码恢复 / 轮换；
- 旧凭据与新凭据最终验证状态；
- Gate-1 最终结论；
- 哪些内容属于独立验证。

不要输出任何真实凭据。

### Q6. Gate-2 做了什么？

至少说明：

- Gate-2 是执行 fuzz 还是只读审计；
- focused tests / full tests 最终结果；
- `secret_scan.py`
- `config_scan.py`
- Basic auth / bearer / raw token / Flowable 配置硬化
- public-release / origin / tag 是否被改变；
- Gate-2 最终结论。

### Q7. Alfresco Level-C metadata 与 content 两条线路目前各做到什么程度？

区分：

- committed target template；
- runtime launcher；
- credential gate；
- dedicated node resolution；
- body / content representation；
- read-back；
- version / metadata / overwrite guard；
- real service verification；
- fuzzing 是否执行。

不得把普通 Level-C smoke 与完整 AFL++ feedback loop 混为一谈。

---

# 五、exec_seq / status / state feedback

### Q8. `nv_http_status.json` 是谁写的？路径如何确定？

说明：

- production writer；
- `NV_STATUS_PATH`
- atomic write；
- run-scoped status path 为什么重要；
- 旧 `/tmp/nv_http_status.json` 是否应该被新 run 自动继承。

### Q9. `exec_seq` 的真正 namespace 是什么？

回答：

- `exec_seq` 如何生成；
- sidecar 文件路径；
- 为什么不能只用 module-level `SEQ`；
- harness 是否每次 execution 都重启；
- validity rejection 是否消耗 `exec_seq`；
- observer/read-back 是否消耗 `exec_seq`；
- replay / high-water 判定逻辑。

### Q10. 请解释 security-state coverage。

至少说明：

- 它是否等于传统 AFL edge coverage；
- security state 从哪里产生；
- 如何判重；
- `security_state_total`
- `security_state_seed_credit`
- `ss_cov_cnt`
- 哪个 queue entry 获得 credit；
- new / existing state 对 reward 与 scheduler 的意义。

---

# 六、MAB / scheduler

### Q11. 请解释当前 MAB arm 的来源与 reward attribution。

至少覆盖：

- `NV_JSON_ARM_USED`
- arm pick
- pending update / attribution
- reward 来源
- `nv_mab_update`
- per-arm pulls
- `nv_mab_total_pulls`
- 为什么 reward 不能记到错误 arm。

### Q12. 请解释 scheduler 中：

- `ss_cov_cnt`
- `ss_selected_cnt`
- `ss_prob`

分别是什么、如何变化、scheduler 如何使用。

并说明：

> 同一个 queue entry、相同 `ss_selected_cnt` 下，如果 `ss_cov_cnt` 增加，selection probability 是否应增加？

无法从源码证明时必须写 `NOT VERIFIED`。

---

# 七、bounded integration 当前阶段

### Q13. 当前阶段的正式名称 / 性质是什么？

明确回答：

- 是否是 `OFFLINE BOUNDED INTEGRATION — TDD PHASE`；
- 是否允许访问 Alfresco；
- 是否允许 real network request；
- 是否允许 real fuzz campaign；
- 是否允许 Flowable；
- 是否允许 commit / push / merge / tag / reset / rebase；
- 哪些核心 AFL++ 文件原则上不应修改。

### Q14. 请按顺序写出 bounded integration 当前要求闭环验证的 10 个阶段。

必须包含：

1. FULL HTTP testcase
2. C-side validation contract
3. FULL HTTP -> JSON body representation bridge
4. deterministic offline fixture
5. status / exec_seq
6. state accounting
7. reward attribution
8. MAB counters
9. seed counters / scheduler-visible state
10. stats / report

逐项标注当前验证等级。

---

# 八、CB-1 / CB-2 与最新进展

### Q15. 历史上识别出的两个关键 blocker 是什么？

必须解释：

- `CB-1`
- `CB-2`

以及它们为什么会阻断 bounded real run。

### Q16. 对 CB-1，请说明“旧问题”和“最新上传源码状态”是否一样。

至少检查：

- `nv_json_mutator.py` 输出的 testcase representation；
- C 侧 validation 期待的 representation；
- `body_only_mode=1` production harness 的原始行为；
- `nv_http_body_adapter.py` 的职责；
- 最新 `nv_http_harness.py` 是否已经导入并条件调用：
  - `HttpBodyAdapterError`
  - `extract_http_body`
- 是否存在离线回归测试验证：
  - FULL HTTP -> body byte-exact
  - plain body-only JSON 兼容
  - malformed envelope fail-closed
  - reject 不产生 status / exec_seq

最后给：

`CB1_CURRENT_STATUS = OPEN / FIX_PRESENT_BUT_UNVERIFIED / VERIFIED_OFFLINE / OTHER`

不得仅根据旧审计报告回答。

### Q17. 对 CB-2，请说明 bounded runner 当前是否已经是完整 runner。

检查：

- `scripts/run_alfresco_bounded_feedback.py`
- `main()`
- 是否存在 `--run-root`
- 是否创建 run-root
- 是否 resolve dedicated node
- 是否 render target config
- 是否执行 independent service GET
- 是否 launch `afl-fuzz`
- `--preflight-only` 是否真正执行完整 preflight

最后给：

`CB2_CURRENT_STATUS = ...`

---

# 九、max_test_cases 与终止语义

### Q18. `max_test_cases` 从哪里读取？哪些 execution 会消耗 case budget？

分别判断并解释原因：

- C-side validity reject
- Python/body validation reject
- real service 2xx
- 4xx
- 5xx
- timeout
- conn_refused
- dry run
- calibration
- independent observer GET

### Q19. 当第 N 个 case 达到 `max_test_cases` 时，后续 security-state accounting 和 MAB reward 是否一定都会完成？

如果源码存在“第 N 个 case 的 state accounting 已完成，但 pending MAB reward 可能因 `stop_soon` 被丢弃”的顺序问题，请说明；无法确认则写 `NOT VERIFIED`。

---

# 十、报告与守恒关系

### Q20. 当前可以检查哪些 reporting conservation identities？

至少讨论：

1. runtime `security_state_total`
2. `fuzzer_stats`
3. `eval_report.json`
4. per-arm pulls
5. `nv_mab_total_pulls`
6. `ss_cov_sum`
7. `security_state_seed_credit`
8. `ss_new_bits_any`

并回答：

> `ss_cov_sum == security_state_seed_credit` 是否无条件成立？

如果不是，写出条件或额外项。

---

# 十一、真实 Alfresco 当前状态

### Q21. 当前是否已经完成 `REAL_ALFRESCO_FULL_FUZZ_RUN`？

只能选择：

- YES
- NO
- PARTIAL

并解释证据。

### Q22. 当前是否已经完成 `FULL_REAL_SERVICE_FEEDBACK_LOOP`？

必须区分：

- real Alfresco GET / PUT / metadata/content smoke；
- AFL++ mutator；
- C validation；
- production harness；
- exec_seq；
- security-state；
- reward；
- MAB；
- scheduler；
- reporting。

不能因为真实 HTTP smoke 成功就宣布完整闭环完成。

---

# 十二、下一步计划

### Q23. 如果现在继续推进，正确的下一阶段顺序是什么？

给出：

- 先做什么；
- 为什么；
- 哪些是 offline；
- 哪些需要 human-approved real-service execution；
- 哪些步骤必须在 blocker 清零之后才能开始；
- 如何避免污染 Git baseline；
- 如何设计 run-scoped evidence。

### Q24. 真正执行 bounded real Alfresco run 前，preflight 至少应该验证哪些东西？

至少覆盖：

- credentials presence；
- target/node resolution；
- node identity；
- service reachability；
- independent authenticated GET；
- run-root；
- target config；
- status namespace；
- executable / build state；
- proxy sanitation；
- evidence directory。

---

# 十三、项目操作边界

### Q25. 以下行为当前哪些可以做，哪些不可以做？逐项解释。

- 阅读 source
- 修改 Python bridge
- 修改 `src/afl-fuzz-run.c`
- 跑 offline unit tests
- 跑 deterministic loopback integration test
- 访问真实 Alfresco
- 启动 AFL++ real fuzz
- 使用 Flowable
- commit
- push
- merge
- tag
- reset
- rebase
- 修改 public-release
- 使用旧报告替代当前 source

---

# 十四、反幻觉检查

### Q26. 请列出至少 10 个“如果新 AI 没真正读项目材料，最容易答错”的点。

例如：

- 把 edge coverage 当 security-state coverage；
- 误以为 real fuzz 已完成；
- 误以为 Gate-2 跑过 fuzz；
- 把 Level-C smoke 当完整闭环；
- 忽略 committed source 优先级；
- 误判 CB-1 最新状态；
- 误判 CB-2；
- 混淆 `SEQ` 与 `exec_seq`；
- 混淆 body-only 与 FULL HTTP；
- 混淆 metadata 与 content 路径。

---

# 十五、最终状态表

### Q27. 请输出如下状态表：

| 项目 | 当前状态 | 验证等级 | 主要证据/来源 |
|---|---|---|---|
| Official release baseline |  |  |  |
| Credential hardening |  |  |  |
| Gate-1 |  |  |  |
| Gate-2 |  |  |  |
| Alfresco Level-C metadata |  |  |  |
| Alfresco Level-C content |  |  |  |
| exec_seq |  |  |  |
| security-state covset |  |  |  |
| MAB |  |  |  |
| scheduler |  |  |  |
| reporting |  |  |  |
| offline bounded integration |  |  |  |
| CB-1 |  |  |  |
| CB-2 |  |  |  |
| real Alfresco full fuzz |  |  |  |
| full real-service feedback loop |  |  |  |
| Flowable |  |  |  |

---

# 十六、最后的“是否真正掌握项目”测试

### Q28. 请用不超过 15 条 bullet，总结：

1. 项目最终目标；
2. 为什么现在重点是 Alfresco；
3. 当前权威代码基线；
4. 已独立验证的部分；
5. 尚未独立验证的部分；
6. 当前最重要 blocker / 风险；
7. 当前阶段禁止做的事情；
8. 下一步最合理的动作。

---

## 评分规则

总分 100：

- 项目目标与整体架构：15
- Git / source-of-truth：10
- Gate-1 / Gate-2：10
- Level-C：10
- exec_seq / status：10
- security-state / reward / MAB / scheduler：15
- bounded integration：10
- CB-1 / CB-2：10
- real-service 状态与下一步：5
- 主动指出 UNKNOWN / 冲突 / 验证等级：5

### 判定

- **90–100：PASS**
  - 可以直接接手项目；
  - 对 source-of-truth、进度、边界和下一步没有关键误判。

- **75–89：PARTIAL**
  - 理解大体正确；
  - 但仍有关键工程事实需要重新读源码或审计材料。

- **<75：FAIL**
  - 不应直接继续改代码或执行真实 fuzz；
  - 应重新阅读 handoff、CURRENT_STATE、FILE_INDEX、审计报告和当前 committed source。

### 一票否决项

出现任意一项，最高只能判 `PARTIAL`；出现两项及以上，直接 `FAIL`：

- 声称完整 real Alfresco fuzz 已完成；
- 声称 Gate-2 执行过 fuzz；
- 把普通 AFL edge coverage 当成本项目的 security-state coverage；
- 不知道 committed source 优先于旧报告；
- 把旧 CB-1 结论直接当成最新源码状态；
- 把 Level-C metadata/content smoke 当作 full feedback loop；
- 把 module-level `SEQ` 当作真正跨 execution 的 `exec_seq`；
- 忽略 run-scoped `NV_STATUS_PATH` / `.seq`；
- 声称 Flowable 当前与 Alfresco 同优先级；
- 在没有证据时自行补齐未知 Git SHA / 验证结论。

---

## 最终输出格式

```text
PROJECT_UNDERSTANDING_VERDICT = PASS | PARTIAL | FAIL
CONFIDENCE = HIGH | MEDIUM | LOW
CRITICAL_UNKNOWNS = [...]
CURRENT_PROJECT_PHASE = ...
NEXT_RECOMMENDED_ACTION = ...
```

如果新 AI 不能稳定回答以上问题，就说明它还没有真正掌握该项目。
