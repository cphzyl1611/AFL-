# AFL++ / Alfresco Bounded Real Feedback — AI Handoff

Date: 2026-08-25

## 1. Project identity and authorization

This is the user's authorized/self-controlled security research environment for the “河南重大专项 / AFL++ 自动化测试框架” project.

The immediate target is the user's local Alfresco test instance. The work should be treated as authorized security engineering/testing, but still respect normal safety boundaries.

The current objective is **not** a full fuzz campaign and **not** vulnerability exploitation. The objective is to verify a very small, bounded, auditable real-service feedback chain for the already-validated Alfresco metadata target.

## 2. Authority hierarchy

Use these as the project checkpoints:

- OFFICIAL_RELEASE_BASELINE  
  `c6817ce46b0120da95ba55869b6b298e18e4cf8b`

- HARDENING_CHECKPOINT  
  `fc2866d4974de04e711f8395aac076490b68fc4f`  
  Status: independently verified.

- HISTORICAL SOURCE / CONTENT CHECKPOINT  
  `53cb2679de33d6b7737c1fa9cf8a39ef9e8b0aa1`

- CURRENT OFFLINE BOUNDED INTEGRATION CHECKPOINT / CURRENT STARTING POINT  
  `dbffb19312faaa6164ca6c4b7abe43ff985e2d83`

Do **not** restart implementation from `53cb267`. It is ancestry/source context. Continue from `dbffb193...`.

Current branch:
`feature/alfresco-bounded-real-feedback`

Current worktree reported by the user:
`/home//AFLplusplus-alfresco-real-feedback`

(The double slash is harmless on Linux; preserve/normalize as appropriate.)

## 3. Current Git state reported by the user

The user confirmed:

- branch matches `feature/alfresco-bounded-real-feedback`
- HEAD matches `dbffb19312faaa6164ca6c4b7abe43ff985e2d83`

`git status --short`:

```text
?? scripts/run_alfresco_bounded_feedback.py
?? tests/test_alfresco_bounded_feedback.py
```

The user also confirmed these two untracked files have not changed from the previously reviewed versions.

Previously recorded file identities:

### scripts/run_alfresco_bounded_feedback.py
SHA256:
`e9a61a0160c9601460219ed7e146728614fae8ead378aaccaca15e2dd119d546`

Size:
`168 lines / 4284 bytes`

### tests/test_alfresco_bounded_feedback.py
SHA256:
`9a7103982f73950afe6f43e1750c932c6e13bd20872f235b92dfbf40087e7516`

Size:
`748 lines / 24548 bytes`

Important prior observation:
`run_alfresco_bounded_feedback.py` parses `--preflight-only`, but in the previously inspected version this flag was not actually wired into a real Alfresco/node preflight path. Do not assume `--preflight-only` performs the desired real-service checks without inspecting the source.

## 4. Completed evidence / status

The project has already passed earlier hardening and offline review stages.

Relevant accepted history:

- Gate-1 credential leakage remediation: PASS after independent verification.
- Gate-2 independent read-only hardening audit: PASS.
- Focused tests at Gate-2: 48/48 PASS.
- Full test suite at Gate-2: 197/197 PASS.
- No real fuzz campaign was run during Gate-1/Gate-2.
- Alfresco metadata Level-C target has already had independent audit evidence.
- Alfresco content Level-C also has independent audit evidence, but **content is not in scope for the immediate bounded-real task**.
- Offline bounded integration / Phase-3 feedback chain has already reached:
  `PHASE3_INDEPENDENT_AUDIT_PASS`.

The next task is therefore a **bounded real Alfresco metadata gate**, not another offline redesign.

## 5. Immediate task

Goal:

Prove, with a tiny real-service run, a causal chain approximately:

```text
mutated FULL HTTP testcase
-> C-side validation contract
-> FULL HTTP -> JSON-body representation bridge
-> production Alfresco metadata harness
-> real local Alfresco execution
-> fresh status / exec_seq
-> independent service read-back
-> security-state accounting
-> reward attribution
-> MAB accounting
-> queue-entry/scheduler-visible state
-> final stats/report reconciliation
```

This is a validation of the feedback pipeline, not a vulnerability hunt.

Acceptable outcome can be all HTTP 2xx, with no crash / no 5xx.

## 6. Real-gate scope constraints

Keep the next real run intentionally small:

- metadata target only
- use an already-approved dedicated Alfresco metadata resource
- do not create a new node unless separately authorized
- one initial seed
- one mutation arm (prefer the already-designed FIELD_VALUE arm if the source confirms that is still appropriate)
- small single-digit `max_test_cases`
- `time_budget` is only a safety fuse, not the experiment's primary budget
- no Flowable
- no content binary
- no multipart
- no unrestricted campaign
- no long-running fuzz
- no destructive Git operations
- no reset/rebase/merge/tag/push
- do not overwrite prior evidence

## 7. Core invariants to preserve

### R1 — Target identity / pre-run observer

Resolve the approved Alfresco metadata resource once and keep the same target for the whole bounded run.

Capture:
- target identity (stable redacted alias is fine, e.g. `NODE_A`)
- method/path
- independent PRE-RUN GET/read-back

The observer GET must not produce AFL++ feedback/status or consume the case budget.

### R2 — exec_seq high-water / replay isolation

Before the first production execution, identify the **authoritative sequence namespace for the exact run being started**.

Record:
`PRE_RUN_EXEC_SEQ_HIGH_WATER = H`

Every new status-producing production execution must satisfy:
`exec_seq > H`

Within the run:
`seq_1 < seq_2 < ... < seq_K`

A duplicate/stale/replayed status must not create:
- new state
- seed credit
- reward
- MAB update

**Do not infer H from the maximum exec_seq found anywhere under /tmp.**
There are multiple old audit/scratch namespaces, and the large values seen in those historical directories are not automatically the high-water for the new run.

### R3 — Representation boundary

Preserve the already-tested representation chain:

```text
FULL HTTP testcase
-> C-side validation
-> FULL HTTP -> JSON-body bridge
-> body-only production harness
```

Do not redesign this chain without a concrete failing test.

### R4 — Case budget

Let `max_test_cases = N`.

Only a genuine accepted/status-producing production execution consumes one case.

Do not count:
- validation rejects
- observer GET/read-back
- administrative/preflight requests

### R5 — Indicated source queue entry

For each testcase, identify the actual source queue entry that produced it.

If and only if a fresh observation inserts a genuinely new security-state hash:

- that source queue entry's `ss_cov_cnt += 1` exactly once
- global seed-credit accounting increments exactly once
- other queue entries remain unchanged for that credit event

If no new state is produced, seed-credit proof is `INCONCLUSIVE`, not fabricated PASS.

### R6 — Reward / MAB attribution

If reward is attributed, its source sequence must equal the fresh production `exec_seq`.

The updated arm must match the confirmed arm actually used by the mutator (`NV_JSON_ARM_USED` or equivalent runtime evidence), not merely the arm that was selected before mutation.

Conservation:
`sum(all arm pulls) == nv_mab_total_pulls`

### R7 — Scheduler visibility

If a queue entry receives state credit, show that the same queue entry field is visible to the scheduler's deterministic weighting/probability logic.

Do not require a random subsequent scheduler draw to select the seed.

### R8 — Independent post-execution read-back

After each accepted status-producing production execution, use an independent Alfresco GET/read-back observer.

The observer must not affect:
- exec_seq
- feedback
- reward
- MAB
- state accounting
- case budget

Correlate:
`testcase -> production exec_seq -> HTTP result -> actual Alfresco metadata state`

Do not treat HTTP 2xx alone as proof that service state changed.

### R9 — Final report reconciliation

At the end reconcile at least:

```text
runtime security_state_total
== fuzzer_stats security_state_total
== eval_report.json security_state_total
```

and:

```text
sum(arm pulls) == nv_mab_total_pulls
```

Under the fixed-queue bounded conditions, also reconcile live queue state-credit counters with the run's seed-credit accounting where the implementation semantics support that equality.

## 8. User's latest local pre-check results

Credential presence check:

```text
ALFRESCO_USER=UNSET_OR_BLANK
ALFRESCO_PASS=UNSET_OR_BLANK
```

Therefore a real Alfresco request/run is currently blocked until the user loads the already-approved runtime credentials into environment variables or another existing approved runtime mechanism.

Do not ask the user to paste real credentials into chat.

The user also searched `/tmp` for historical `nv_http_status.json` files and found many old audit/scratch outputs, including examples:

```text
/tmp/aflpp-phase3-independent-audit.../p01_alfresco_metadata_update_repro_run1/nv_http_status.json
exec_seq=427

/tmp/aflpp-phase3-independent-audit.../p01_alfresco_metadata_update_repro_run2/nv_http_status.json
exec_seq=428

/tmp/.../p01_m3_replay/nv_http_status.json
exec_seq=35946

/tmp/.../p01_m2_status_attribution/nv_http_status.json
exec_seq=42374

/tmp/levelc-content-audit.../run/nv_http_status.json
exec_seq=3
seq=1
```

Interpretation rule:
these are **historical, distinct run namespaces**. Do not use a global `/tmp` maximum such as 42374 as the new run's high-water unless source inspection proves the new run deliberately reuses that exact sequence namespace.

## 9. Files the user should provide to the next AI

The safest/highest-value handoff is:

### A. Handoff/context package
`AFLplusplus_new_chat_handoff_20260821(3).zip`

Use it for project history, audits, current-state documents, and background.

Important documents inside / associated with the handoff:
- `README_START_HERE.md`
- `01_context/CURRENT_STATE.md`
- `01_context/FILE_INDEX.md`
- `02_audits/levelc/metadata_independent_audit.txt`
- `02_audits/levelc/content_independent_audit.txt`
- `02_audits/gate2/gate2_final_audit_and_hardening_log.txt`
- `04_project_background/AFL++源代码修改总纲.md`

### B. Authoritative committed source export
`AFLplusplus-newchat-source-20260821-161133(2).zip`

This is the important committed-source package around the `53cb267` source checkpoint.
Where reports disagree with source, source wins.

However, the current implementation starting point is now `dbffb193...`, so the next AI must also inspect the live/current worktree or receive the files changed since 53cb267.

### C. Supplemental source/evidence package
`AFLplusplus-feedback-source-supplement-20260821-201920.zip`

Provide this because it may contain the bounded-feedback additions/evidence needed after the earlier source export.

### D. The two current untracked files from the live worktree
These are especially important and should be uploaded individually if possible:

- `scripts/run_alfresco_bounded_feedback.py`
- `tests/test_alfresco_bounded_feedback.py`

The next AI should verify their SHA256 values against the identities above.

### E. If the AI cannot access the live repo, also provide the exact current versions of the relevant implementation files

At minimum:

- `nv_json_mutator.py`
- `nv_body_valid.py`
- `nv_state_probe.py`
- `nv_http_harness.py`
- `targets/alfresco_metadata_update.json`
- `src/afl-fuzz-run.c`
- `src/afl-fuzz-nv-mab.c`
- `src/afl-fuzz-nv-sched.c`
- `src/afl-fuzz-nv-covset.c`
- `test/unittests/unit_nv_sched.c`
- `tests/test_nv_mab_unit.py`
- `tests/test_p0_mab_feedback_evidence.py`
- `scripts/run_p0_mab_feedback_experiment.sh`
- `scripts/summarize_p0_mab_feedback.py`

Prefer an exact `git archive`/committed-tree export or source collection script output rather than copied snippets.

## 10. What the next AI should do first

Do **not** immediately run fuzzing or make network requests.

First:

1. Read the handoff documents.
2. Inspect the exact current source and the two untracked bounded-real files.
3. Confirm the current starting point is `dbffb193...`.
4. Confirm no redesign of the offline feedback architecture is necessary.
5. Determine exactly how the current code chooses:
   - run root
   - status file
   - sequence sidecar / exec_seq namespace
   - output directory
   - target definition
   - case-budget accounting
6. Produce a **PRE-RUN LOCAL GATE** verdict:
   - PASS
   - BLOCKED
   - NEEDS_MINIMAL_FIX
7. If blocked only by credentials or target identity, give the user short manual commands for those steps.
8. Do not ask the user to disclose secrets.
9. Do not start a broad/full fuzz campaign.

## 11. Desired next response from the AI

The user prefers direct operational guidance.

A good next response should contain:

```text
PRE-RUN LOCAL GATE = PASS / BLOCKED / NEEDS_MINIMAL_FIX
```

Then explain the exact blocker(s), followed by the smallest next set of shell commands.

The commands should be separated into:
- local/read-only checks
- user-executed real-service preflight
- bounded run
- post-run evidence extraction

Do not combine everything into one giant automation step.

## 12. Important evidence-handling rule

The user may sanitize output with another model before sending it back.

Stable pseudonyms are acceptable:
- node -> `NODE_A`
- host -> `ALFRESCO_HOST_A`

But preserve exact causal/accounting fields when possible:
- HEAD
- branch
- exit code
- HTTP status
- exec_seq
- arm used
- validation result
- insertion result (`INSERTED` / `EXISTING` / `SATURATED`)
- state counts
- seed-credit counts
- MAB pulls / totals
- queue-entry `ss_cov_cnt`
- scheduler-visible probability/weight
- report totals
- ordering/timestamps where needed

Never require:
- plaintext password
- Authorization header
- session token
- reset token
- API key

## 13. Short instruction to the next AI

Use the exact source/evidence files above as authority.
Do not guess current implementation from old reports.
Do not restart from 53cb267.
Do not expand the scope beyond the bounded metadata real-service gate.
Inspect first, then issue the smallest safe/manual next step.
