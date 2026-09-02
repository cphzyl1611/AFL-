# 模糊测试组件最终验收报告

## 1. 项目任务与验收目标

本组件面向河南重大专项自动化测试框架中的模糊测试任务，形成基于模糊测试的内生安全性能评估模型。验收目标限定于 fuzzing 组件本身，具体包括：

- 生成和维护高质量种子与测试用例；
- 通过变异、有效性过滤和目标执行开展基于模糊测试的内生安全性能测评；
- 验证框架在不同真实业务平台上的迁移能力；
- 建立自动执行、反馈、评价和报告闭环，为工程验收和后续研究提供可追溯证据。

本报告不扩展到其他课题子系统，也不将 bounded engineering validation 表述为所有平台上的普适性证明。

## 2. 仓库身份与冻结口径

本报告对应的 bounded worktree 为：

`/home/dministrator/AFLplusplus-alfresco-real-feedback`

正式 baseline 为 AFL++ main repository `/home/dministrator/AFLplusplus` 中的 `public-release` 快照：

- `OFFICIAL_RELEASE_BASELINE = c6817ce46b0120da95ba55869b6b298e18e4cf8b`
- `CURRENT_BOUNDED_HEAD = fe5a89480d1ae5cd17e44f8bb4bde7f139c2cfc5`（历史记录，早于下方 reconciliation HEAD）
- `PRE_RECONCILIATION_INTEGRATION_HEAD = e6d17ad211b3fb522932ae812cf8f6310d55904f`

`PRE_RECONCILIATION_INTEGRATION_HEAD` 为本次 SE backend selector 文档/测试 reconciliation 开始前，`integration/final-fuzzing-component` 分支已推送到 GitHub 的 HEAD。本次 reconciliation 完成后会产生新的提交，其确切 SHA 在本文档写入时尚未存在；最终交付提交（final delivery commit）定义为“包含本次已 reconciled 文档的提交”——读者应以 `git log` / `git rev-parse HEAD` 解析该分支当前 HEAD，而不是依赖本文档中写死的某个 SHA 作为最新值。

当前 bounded HEAD 与 official baseline 的差异属于本组件 bounded worktree 的提交范围，不改变 official baseline 的身份和基准结论。证据权威顺序为：current source / final frozen evidence > committed source snapshot > independent audit > historical handoff/report。

## 3. 最终技术链路

组件形成如下闭环：

```text
seed / testcase
    -> mutation
    -> validity
    -> production execution
    -> status / exec_seq
    -> business/security-state observation
    -> reward
    -> MAB
    -> scheduler
    -> stats / report
```

核心职责如下：

- `seed / testcase`：提供可复用的高质量初始输入和受控测试样本。
- `mutation`：按字段值、边界和结构三个变异臂生成候选输入。
- `validity`：先执行规则过滤，并可接入 AE 或 SE-fAnoGAN-ES 评分后端，减少明显无效输入对目标服务的干扰。
- `production execution`：通过 HTTP JSON、文本或 multipart 目标适配器执行真实或受控目标请求。
- `status / exec_seq`：记录 HTTP 状态、执行身份和案例序号，支持执行与观察结果对账。
- `business/security-state observation`：读取业务对象或安全状态变化，区分请求返回与业务后置状态。
- `reward`：将新覆盖、有效执行和业务反馈归因到具体测试案例及变异臂。
- `MAB`：根据奖励更新多臂老虎机状态，动态选择更有价值的变异臂。
- `scheduler`：使用种子级覆盖和选择信用参与后续调度。
- `stats / report`：输出统计、反馈、奖励、调度和验收报告。

实现状态与证据等级区分如下：核心 C/Python 组件、harness、MAB、调度器、统计和报告链路为 `implemented`；Gate-1、Gate-2、表示桥、C validity、exec_seq/accounting、状态覆盖、reward attribution、MAB 和 scheduler 均有独立证据，标记为 `independently verified`；Alfresco 与 O2OA 的列明场景标记为 `real-platform verified`，但仅在本报告声明的 bounded 范围内成立。

## 4. 主要变异与调度机制

框架提供三个 NV JSON 变异臂：

- `field_value`：保持请求结构，改变字段值、枚举、字符串或数值内容；
- `boundary`：围绕长度、范围、空值、极值和边界类型生成测试用例；
- `structure`：增加、删除、重排或改变嵌套结构及字段形态。

变异臂使用情况由 `NV_JSON_ARM_USED` 标识，并进入 reward attribution。每次有效生产执行的业务反馈、状态覆盖或安全状态变化，按案例和当前 arm 归因，更新 `nv_mab_t`；该 MAB 再用于后续 arm 选择。

种子调度侧维护：

- `ss_cov_cnt`：种子产生新覆盖或覆盖信用的累计计数；
- `ss_selected_cnt`：种子被选择的累计计数；
- `ss_prob`：基于种子覆盖信用和选择次数计算的选择权重。

这些字段构成 scheduler-visible seed credit，使变异反馈能够影响后续种子选择，而不只停留在单次执行统计中。

## 5. `exec_seq`、案例预算与 accounting

最终冻结口径如下：

- `exec_seq namespace = NV_STATUS_PATH`；
- sidecar 为 `NV_STATUS_PATH + ".seq"`；
- C-side validity reject 不消耗 case；
- Python/body reject 若发生在 target 内，则消耗 case；
- observer/read-back 不消耗 case；
- 第 N 个 case 的 state accounting 与 pending MAB update 存在 stop boundary 顺序差异。

因此，不作无条件的 `nv_mab_total_pulls == max_test_cases` 声明。案例预算、目标执行、状态回读和待处理 MAB 更新必须按各自语义解释，并以 `NV_STATUS_PATH` 及其 seq sidecar 对账。

## 6. Alfresco real validation

冻结的 Alfresco bounded real validation 最终状态为：

| 场景 | 最终状态 |
|---|---|
| metadata real feedback | PASS |
| content real update | PASS |
| multipart full bounded feedback | PASS |
| multi-arm real | PASS |
| multi-seed all-arms real | PASS |

multipart bounded closure 覆盖 validation reject、`field_value`、`boundary`、`structure` 以及多臂反馈。该证据为 bounded real validation，不等同于长时间稳定性或规模验证；本轮不重跑实验。

## 7. O2OA real validation

`O2OA final post-fix bounded real gate = PASS`。

O2OA 的最终 post-fix bounded real gate 与 Alfresco 的 metadata、content、multipart 真实反馈证据共同支撑跨平台 bounded engineering validation。该结论限于已冻结的接口、种子、执行预算和反馈范围，不扩大为 O2OA 全量接口或所有平台适用性证明。

## 8. SE-fAnoGAN-ES 与 AE 最终模型选择

冻结状态为：

- `SE_FANOGAN_ES_REFERENCE_IMPLEMENTATION = COMPLETE`
- `SE_FANOGAN_ES_FORMAL_COMPARISON = COMPLETE`
- `MODEL_EFFECTIVENESS_VERDICT = SCENARIO_DEPENDENT`
- `ENGINEERING_MODEL_SELECTION = AE_V1_RETAINS_PRIMARY`
- `SE_FANOGAN_ES_ROLE = OPTIONAL_RESEARCH_BACKEND`

冻结 holdout 结果：

| 模型 | false_accept | false_reject | F1 | balanced_accuracy | AUROC | AUPRC |
|---|---:|---:|---:|---:|---:|---:|
| AE v1 | 7 | 0 | 0.872727 | 0.650000 | 0.637500 | 0.556600 |
| SE-fAnoGAN-ES mean | 5.0 | 0.0 | 0.905660 | 0.750000 | 0.912500 | 0.878639 |

场景结论为：metadata 场景 `SE_BETTER`，content 场景 `AE_BETTER`，multipart 场景 `SE_BETTER`。完整 canonical SE-fAnoGAN-ES 在冻结的 Alfresco holdout 上总体检测指标优于当前 AE v1 lightweight statistical baseline，并在 metadata 与 multipart 场景表现更好；content 场景由 AE 更优。由于结果具有场景依赖性，同时 SE 推理约慢 3.36 倍，因此当前工程继续采用 AE v1 作为默认轻量有效性判定机制，并保留 SE-fAnoGAN-ES 作为可选研究后端。

效率冻结值为：

- AE warm latency 约 `0.074284 ms`，throughput 约 `13461.870 samples/s`；
- SE warm latency mean 约 `0.249722 ms`，throughput mean 约 `4007.317 samples/s`。

```text
REAL_AE_VS_SE_FOUR_RUN_AB = EXECUTED_BUT_NOT_VALID_FOR_MODEL_COMPARISON / POST_FREEZE_RESEARCH_EXTENSION
```

round-c-final 已实际执行全部四个计划中的真实服务运行（`4/4 runs executed`，明细见下方 §8.1）；该 four-run 协议属于 post-freeze research extension，非阻塞项。执行完成本身属实，但不等于产出了有效证据：复核确认两个场景在本轮运行中均未发生真实 scorer 参与（详见 §8.1），因此无法从这四次运行得出任何有效的 real-service model-effectiveness 结论，不得表述为 PASS，也不得作为 AE 与 SE 孰优孰劣的依据。已完成并冻结的是本节上方基于 holdout 数据集的 formal training/holdout comparison（`SE_FANOGAN_ES_FORMAL_COMPARISON = COMPLETE`），两者范围不同，不可互相替代。

### 8.1 Four-run 协议口径澄清（human protocol decision, 2026-09-02）

round-c-final 已实际执行全部四个计划中的真实服务运行（`4/4 runs executed`）：该 four-run 协议由两个场景 × 两个 backend 构成（`metadata_update` × {AE, SE}，`multipart_upload` × {AE, SE}）。执行完成本身不等于产出有效的 model-effectiveness 证据——复核确认两个场景均未发生真实 scorer 参与，但原因各不相同：

- `multipart_upload`：`enable_validity=0`（见 `scripts/run_alfresco_bounded_feedback.py` 的 `build_task_payload`：`"enable_validity": 0 if scenario == "multipart_upload" else 1`，并由 `tests/test_alfresco_bounded_feedback.py::MultipartProfileTest` 断言保持），C 侧 `if (afl->nv_task.enable_validity)` gate（见 `src/afl-fuzz-run.c`）直接屏蔽 validity 调用。即使传播了 `alfresco_ae_v1` / `sefanogan_es_reference` backend label（供 orchestration/config 兼容），也不代表该 backend 在 multipart 执行期间实际参与了打分决策；此前带 AE/SE 标签的 multipart 运行不构成 model-effectiveness 证据。multipart_upload 的 execution/readback 验证结果（见 §6、§12 中 "Alfresco multipart" = PASS）是独立的工程有效性证据，不因排除 model-AB denominator 而失效。
- `metadata_update`：任务配置 `enable_validity=1`，C 侧 `if (afl->nv_task.enable_validity)` gate 本身未屏蔽 validity/score 调用路径；但 round-c-final 实际运行记录显示该调用从未真正发生：`body_score_rpc_ok = 0`、`body_score_rpc_fail = 0`（RPC 既未成功也未失败，即从未被发起），且当轮 `task.json` 未配置 `validity_endpoint`，运行时也未设置 `NV_BODY_SCORE_ENDPOINT`，score server 未被调用。因此 `enable_validity=1` 仅说明 gate 未被屏蔽，不等于 scorer 已实际参与评分；此前带 AE/SE 标签的 metadata_update 运行同样不构成有效的 model-effectiveness 证据（此前版本曾写作 `REAL_METADATA_MODEL_SIGNAL = SE_BETTER`，现已确认该表述不成立并撤回）。

```text
FOUR_RUN_EXECUTION_STATUS = 4/4_RUNS_EXECUTED
METADATA_SCORER_PARTICIPATION = NONE
REAL_METADATA_MODEL_SIGNAL = NOT_SUPPORTED_BY_EVIDENCE
MULTIPART_MODEL_AB_DENOMINATOR = EXCLUDED
MULTIPART_SCORER_PARTICIPATION = NONE
MULTIPART_MODEL_COMPARISON = NOT_APPLICABLE_AS_MODEL_AB
```

不得从 round-c-final 的任一场景推广出有效的 real-service model-effectiveness 结论。本条澄清不改写上方 §8 基于冻结 holdout 数据集的 formal training/holdout comparison，两者范围不同、彼此独立、均保持不变。`AE v1` 仍为工程默认 backend，`SE-fAnoGAN-ES` 仍为可选研究 backend；本次澄清未引入任何新的训练、阈值或模型产物变更。

## 9. 跨平台验证

```text
CROSS_PLATFORM_FUZZING_FRAMEWORK_VALIDATED = YES
SCOPE = BOUNDED_ENGINEERING_VALIDATION_ON_ALFRESCO_AND_O2OA
```

该结论表示框架已在 Alfresco 与 O2OA 的冻结 bounded 场景中完成迁移和反馈闭环验证，不表示所有平台普适性已经证明。

## 10. Final regression、build 与 evidence integrity

最终冻结回归与完整性状态如下：

- `TARGETED_C_PROBE_RERUN = PASS`；
- `ATTRIBUTION_MODULE_RERUN = PASS`：discovered 17，passed 17，failed 0，errors 0，skipped 0；
- `FULL_OFFLINE_REGRESSION = PASS`：728 / 728，0 failures，0 errors，0 skips（历史 final-freeze 计数，保留为历史证据，不作事后改写）；
- `AFL_BUILD = PASS`；
- `SECRET_SCAN = PASS`；
- `RUNTIME_SECRET_ALLOWLIST_REVIEW = PASS`；
- `EVIDENCE_HASH_MANIFEST = PASS`。

最终环境问题已解决：根因是 Python interpreter / CPython 3.12 development-tooling environment mismatch；最终方案为 project venv 使用 ABI-compatible Python 3.12 development tooling。该历史环境问题不属于当前 blocker，且不需要 source change 或 model change。

### 10.1 Verification chronology

本文档涉及三轮独立离线回归验证，按时间顺序记录，互不覆盖：

1. **historical final freeze**：`728 / 728`，0 failures，0 errors，0 skips（见上文，历史证据，保留原始计数）。
2. **pre-delivery verification（`e6d17ad` 之前）**：`744 / 744`，`FULL_OFFLINE_REGRESSION = OK`；`AFL_BUILD_EXIT = 0`；`STAGED_SECRET_GATE = PASS`。
3. **post-reconciliation verification（本次 SE backend selector reconciliation 之后）**：`745 / 745`，0 failures，0 errors，0 skips（`python -m unittest discover -s tests`，未过滤/跳过任何测试；相对 pre-delivery 的 744 增加 1，对应新增的 `test_legacy_se_fanogan_mode_reaches_canonical_reference_scorer` RED→GREEN 回归测试）。

### 10.2 SE backend selector reconciliation（本次变更）

本次 reconciliation 修复并记录了 SE-fAnoGAN-ES backend selector 的一个遗留缺陷：

- 生产模块 `model_stage/nv_valid_server_real.py` 中，legacy 兼容选择器 `SEFANOGAN_MODE=se_fanogan_es_reference` 在 `build_infer_engine()` 内直接引用 `ReferenceScorer`，但该名称在该函数作用域内未被导入，导致该路径即便配置了有效的 checkpoint/metadata 也会在初始化阶段抛出 `NameError`，而不是产出真实评分结果。
- 该缺陷此前未被现有测试覆盖：既有测试仅验证 legacy 路径在 artifacts 缺失时 fail closed（NameError 恰好也会导致非零退出码，从而掩盖了根因）。
- 修复方式：legacy 路径改为复用 `load_validity_backend()`（与 `NV_VALIDITY_BACKEND=sefanogan_es_reference` canonical 路径完全相同的 loader），因此两条路径现在保证解析到同一个 `model_stage.sefanogan_es_reference.ReferenceScorer` 实现，且都在 artifacts 缺失/损坏时 fail closed。
- 新增 RED→GREEN 回归测试：`tests/test_sefanogan_backend_wiring.py::BackendSelectorTest::test_legacy_se_fanogan_mode_reaches_canonical_reference_scorer`，使用既有的冻结 SE reference checkpoint + metadata（未训练新模型），验证生产 legacy selector 路径能够真正初始化并到达 canonical scorer。
- AE v1 default 行为、canonical selector 行为、fail-closed 语义均未改变。详见 `docs/project_docs/sefanogan_es_reference_contract.md`。

## 11. Non-blocking / future extension

以下项目明确归类为 `NON-BLOCKING / FUTURE EXTENSION`，不构成当前项目失败项：

- Flowable full real feedback；
- multipart long-term / scale validation；
- additional O2OA scenarios；
- third-platform validation；
- larger SE-fAnoGAN-ES generalization study。

## 12. Final acceptance matrix

| 项目 | 最终状态 | 验证等级 | 主要证据 | 是否阻塞 |
|---|---|---|---|---|
| Official baseline | PASS | COMMITTED BASELINE | `/home/dministrator/AFLplusplus`, `c6817ce46b0120da95ba55869b6b298e18e4cf8b` | 否 |
| Gate-1 | PASS | INDEPENDENTLY VERIFIED | final freeze evidence root / Gate-1 record | 否 |
| Gate-2 | PASS | INDEPENDENTLY VERIFIED | final freeze evidence root / Gate-2 record | 否 |
| representation bridge | PASS | INDEPENDENTLY VERIFIED | representation bridge acceptance artifact | 否 |
| C validity | PASS | INDEPENDENTLY VERIFIED | targeted C probe and validity evidence | 否 |
| production harness | PASS | INDEPENDENTLY VERIFIED | production harness acceptance artifact | 否 |
| exec_seq | PASS | INDEPENDENTLY VERIFIED | `NV_STATUS_PATH` and `.seq` accounting evidence | 否 |
| state coverage | PASS | INDEPENDENTLY VERIFIED | state coverage attribution record | 否 |
| reward | PASS | INDEPENDENTLY VERIFIED | reward attribution record | 否 |
| MAB | PASS | INDEPENDENTLY VERIFIED | MAB journal and attribution record | 否 |
| scheduler | PASS | INDEPENDENTLY VERIFIED | scheduler-visible seed credit evidence | 否 |
| reporting | PASS | INDEPENDENTLY VERIFIED | stats/report reconciliation record | 否 |
| Alfresco metadata | PASS | REAL-PLATFORM VERIFIED | existing Alfresco metadata acceptance artifacts | 否 |
| Alfresco content | PASS | REAL-PLATFORM VERIFIED | existing Alfresco content acceptance artifacts | 否 |
| Alfresco multipart | PASS | REAL-PLATFORM VERIFIED | `docs/final_delivery/fuzz_component_release/alfresco_multipart_bounded_final.md` and bounded closure artifact | 否 |
| multi-arm | PASS | REAL-PLATFORM VERIFIED | Alfresco multi-arm real evidence | 否 |
| multi-seed | PASS | REAL-PLATFORM VERIFIED | Alfresco multi-seed all-arms real evidence | 否 |
| O2OA final bounded real | PASS | REAL-PLATFORM VERIFIED | O2OA final post-fix bounded real gate artifact | 否 |
| SE-fAnoGAN-ES reference | PASS | INDEPENDENTLY VERIFIED | SE Round 3 frozen evidence root | 否 |
| SE vs AE comparison | PASS | INDEPENDENTLY VERIFIED | SE Round 3 formal comparison record | 否 |
| model selection | PASS | INDEPENDENTLY VERIFIED | frozen model selection decision | 否 |
| cross-platform validation | PASS | REAL-PLATFORM VERIFIED | Alfresco/O2OA bounded engineering evidence | 否 |
| full offline regression | PASS | INDEPENDENTLY VERIFIED | final 728/728 reconciliation record | 否 |
| AFL build | PASS | INDEPENDENTLY VERIFIED | final freeze build record | 否 |
| secret scan | PASS | INDEPENDENTLY VERIFIED | final freeze secret scan record | 否 |
| allowlist review | PASS | INDEPENDENTLY VERIFIED | runtime secret allowlist review record | 否 |
| evidence hash freeze | PASS | INDEPENDENTLY VERIFIED | evidence SHA256 manifest | 否 |

## 13. Evidence references

本报告只引用冻结证据类别和现有归档 artifact，不复制大型输出，不打印 credential、token 或 raw business IDs：

- final freeze evidence root；
- SE Round 3 frozen evidence root；
- existing Alfresco metadata/content/multipart acceptance artifacts；
- existing O2OA final post-fix bounded real gate artifact；
- `docs/final_delivery/fuzz_component_release/alfresco_multipart_bounded_final.md`；
- `docs/final_delivery/fuzz_component_release/alfresco_multipart_integration_result.md`；
- final 728/728 reconciliation record；
- evidence SHA256 manifest。

## 14. Final conclusion

```text
FINAL_FUZZING_COMPONENT_ACCEPTANCE = PASS_WITH_NON_BLOCKING_GAPS
BLOCKING_ITEMS = []
READY_FOR_FINAL_EVIDENCE_FREEZE = YES
READY_FOR_PROJECT_ACCEPTANCE_WRITEUP = YES
CORE_DEVELOPMENT_CAN_STOP = YES
FINAL_FREEZE_STATUS = PASS
```

模糊测试组件核心研发、真实平台闭环、跨平台 bounded 验证、multi-arm/multi-seed、报告与反馈对账、有效性模型比较及最终 release regression 均已完成。现有剩余项属于非阻塞扩展，不影响当前工程验收。项目可停止核心功能开发，转入正式验收、论文/报告撰写和后续扩展研究阶段。
