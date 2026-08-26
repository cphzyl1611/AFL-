# 河南重大专项 / AFL++ 工程交接 — 当前权威状态

更新时间：2026-08-21（用户侧 Git 实测结果为准）

## 1. 核心工程目标

当前项目目标是建立一个基于输入变异、有效性过滤、真实执行、领域/安全状态观测、奖励更新和调度反馈的闭环自动化测试框架。

核心闭环：

seed
→ mutation
→ validity/filter
→ production target driver
→ status/state observation
→ state-coverage delta
→ reward
→ policy/scheduler update
→ seed counters
→ stats/report

项目 Cov 定义为“领域/安全状态覆盖（security-state coverage）”，不能直接等同于 AFL++ 原生 edge coverage。

## 2. 结论分级规范

所有后续报告必须严格区分：
- DESIGN CLAIM
- IMPLEMENTED
- VERIFIED BY IMPLEMENTER
- INDEPENDENTLY VERIFIED
- PARTIALLY VERIFIED
- NOT VERIFIED

代码存在 ≠ 已验证。
单元测试成功 ≠ 真实平台路径已验证。
mock 成功 ≠ 生产执行链已验证。
共享 harness 可用 ≠ 完整反馈闭环已完成。

## 3. Git / checkpoint 权威谱系

OFFICIAL_RELEASE_BASELINE
= c6817ce46b0120da95ba55869b6b298e18e4cf8b

HARDENING_CHECKPOINT
= fc2866d4974de04e711f8395aac076490b68fc4f
parent = c6817ce46b0120da95ba55869b6b298e18e4cf8b
classification = INDEPENDENTLY VERIFIED

METADATA_CHECKPOINT
= 5f2d72191cdcad1801907bf5cb33aa8da61b5adb
parent = fc2866d4974de04e711f8395aac076490b68fc4f
classification = INDEPENDENTLY VERIFIED

CONTENT_CHECKPOINT
= 53cb2679de33d6b7737c1fa9cf8a39ef9e8b0aa1
parent = 5f2d72191cdcad1801907bf5cb33aa8da61b5adb
tree = 58ea9a8bbd445824aab5e643307b88bc544441ad
classification = INDEPENDENTLY VERIFIED

LATEST_VERIFIED_DEVELOPMENT_BASE
= 53cb2679de33d6b7737c1fa9cf8a39ef9e8b0aa1

## 4. 最新开发 worktree

/home/dministrator/AFLplusplus-alfresco-levelc-content
branch = feature/alfresco-level-c-content-http
HEAD = 53cb2679de33d6b7737c1fa9cf8a39ef9e8b0aa1
status = CLEAN

Metadata worktree：
/home/dministrator/AFLplusplus-alfresco-levelc
branch = feature/alfresco-level-c-metadata-http
HEAD = 5f2d72191cdcad1801907bf5cb33aa8da61b5adb
status = CLEAN

public-release 主工作区：
/home/dministrator/AFLplusplus
HEAD = c6817ce...
status = DIRTY（存在历史硬化/证据修改）
原则：不要从这个 dirty worktree 开始下一阶段开发，也不要 reset/clean 它。

## 5. 历史 branch containment

用户侧只读验证显示以下 branch HEAD 均为 53cb267 的祖先：
- public-release
- feature/alfresco-real-platform-calibration
- feature/alfresco-gate2-hardening
- feature/alfresco-level-c-metadata-http
- feature/alfresco-level-c-content-http
- fix/p0-mab-feedback-validation
- fix/p0.1-release-hardening
- feature/v0.7.1-real-harness-exec-seq
- feature/credential-hardening-remediation

因此下一阶段无需先 cherry-pick P0 / P0.1；以 53cb267 为基线。

## 6. 最新独立验证结论

FULL_REGRESSION
= 361 tests
= 0 failures
= 0 errors
= 0 skips
= INDEPENDENTLY VERIFIED

METADATA_PATH
= INDEPENDENTLY VERIFIED

CONTENT_PATH
= INDEPENDENTLY VERIFIED

DYNAMIC_RESOURCE_RESOLUTION
= INDEPENDENTLY VERIFIED

RUNTIME_PARAMETER_FAIL_CLOSED
= INDEPENDENTLY VERIFIED

LOCAL_DIRECT_CONNECTION_ISOLATION
= INDEPENDENTLY VERIFIED

EXEC_SEQ_MULTI_RUN
= INDEPENDENTLY VERIFIED

PERSISTENT_STATE_STABILITY
= INDEPENDENTLY VERIFIED

ACTIVE_STATIC_SCANNER
= scripts/secret_scan.py

scripts/config_scan.py
= ABSENT at current authoritative checkpoint

CONTENT_TEXT_OVERWRITE
= INDEPENDENTLY VERIFIED

ARBITRARY_BINARY_CONTENT_INPUT
= NOT SUPPORTED
Reason: current .http seed path is UTF-8/LF text only and launcher rejects payloads that the harness would transform.

FULL_REAL_SERVICE_FEEDBACK_LOOP
= NOT YET VERIFIED

LONG_RUNNING_CAMPAIGN
= NO

SECOND_PLATFORM_FULL_CHAIN
= NOT INTEGRATED

## 7. Content checkpoint exact diff

Commit:
53cb2679de33d6b7737c1fa9cf8a39ef9e8b0aa1
subject:
checkpoint: Alfresco Level-C content path self-tested

Relative to parent 5f2d721:
A scripts/run_alfresco_levelc_content.py
A targets/alfresco_content_update.json
A tests/test_alfresco_levelc_content.py

3 files changed, 1235 insertions(+)

## 8. Scanner historical intermediate worktree

/tmp/AFLplusplus-credential-hardening-remediation

这是历史中间实现，不是当前权威实现。
其 19 个 scanner tests 对自身实现：19/19 PASS。
把该 19-test 契约直接跑到 FINAL 实现：12 PASS / 6 FAIL / 1 test-layout error。
MAIN 旧 10-test 契约跑到 FINAL：10/10 PASS。

TMP 的 flowable_query.json 与 FINAL 的结构差异已定位：
TMP = FINAL + auth.required
删除 required 后语义 JSON 完全相等。

该 TMP worktree 的独有状态已由用户归档到：
/home/dministrator/AFLplusplus-worktree-archives/credential-hardening-remediation-20260821-155854

归档完整性：
- manifest entries = 23
- archive files excluding manifest = 23
- 23/23 checksum OK
- HEAD_MATCH = YES
- BRANCH_MATCH = YES
- STATUS_MATCH = YES
- PATCH_MATCH = YES
- live_untracked_count = 19
- archived_untracked_count = 19
- content_mismatches = []
- extra_archive_files = []
- UNTRACKED_PARITY = PASS

该历史归档不是下一阶段功能开发的阻塞项。

## 9. Git 操作边界

除非用户明确授权：
- NO merge
- NO push
- NO tag
- NO reset
- NO rebase
- NO history rewrite
- NO git clean

开发应继续：
- TDD
- isolated worktree
- clean-checkout verification
- curated evidence
- independent read-only audit

## 10. 下一阶段明确目标

不要直接做长时间 campaign。
先做 bounded full-feedback-loop integration。

目标是用非常小、确定性的执行数证明：

seed
→ mutation
→ validity/filter
→ production driver
→ status/state
→ coverage delta
→ reward
→ scheduler/policy update
→ seed state counter
→ stats/report

真实执行结果确实进入状态反馈与调度闭环。

建议阶段：
A. offline TDD
B. bounded real integration
C. independent clean-checkout audit

不能提前把完整 feedback loop 标成 VERIFIED。
