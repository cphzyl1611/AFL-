# CURRENT_STATE — 2026-08-25

## 1. Authority hierarchy

Use source facts in this order:

```text
CURRENT WORKING-TREE SOURCE
> exact committed source snapshot
> independent audit
> historical handoff / report
```

Never infer current code from an older audit when the real file is available.

## 2. Important checkpoints

```text
OFFICIAL_RELEASE_BASELINE
= c6817ce46b0120da95ba55869b6b298e18e4cf8b

HARDENING_CHECKPOINT
= fc2866d4974de04e711f8395aac076490b68fc4f
= INDEPENDENTLY VERIFIED

HISTORICAL SOURCE / CONTENT CHECKPOINT
= 53cb2679de33d6b7737c1fa9cf8a39ef9e8b0aa1

CURRENT OFFLINE BOUNDED INTEGRATION STARTING POINT
= dbffb19312faaa6164ca6c4b7abe43ff985e2d83
```

Latest reported branch:

```text
feature/alfresco-bounded-real-feedback
```

The exact absolute worktree path was reported inconsistently in historical
handoffs (`/home//AFLplusplus-alfresco-real-feedback` versus
`/home/dministrator/AFLplusplus-alfresco-real-feedback`). The receiving AI must
run `pwd` and must not guess.

## 3. Latest known working-tree delta

Historical review recorded these untracked files:

```text
?? scripts/run_alfresco_bounded_feedback.py
?? tests/test_alfresco_bounded_feedback.py
```

Expected SHA-256:

```text
scripts/run_alfresco_bounded_feedback.py
e9a61a0160c9601460219ed7e146728614fae8ead378aaccaca15e2dd119d546

tests/test_alfresco_bounded_feedback.py
9a7103982f73950afe6f43e1750c932c6e13bd20872f235b92dfbf40087e7516
```

They are **not embedded as raw source** in this package because the active
artifact runtime did not contain those two standalone files. Read them from the
actual repo before making any implementation decision.

## 4. Representation bridge status

The currently supplied `nv_http_harness.py` contains a conditional
FULL-HTTP-to-body bridge in `body_only_mode`:

- it imports `extract_http_body`;
- it recognizes an HTTP-like request line;
- it extracts the body byte-exact before `body_validate`;
- malformed HTTP envelopes fail closed before status / exec_seq generation.

The package also contains:

```text
03_current_delta/nv_http_body_adapter.py
03_current_delta/tests/test_nv_http_harness_representation_bridge.py
```

The regression test covers:

- FULL HTTP -> byte-exact body validation;
- existing body-only JSON path;
- malformed HTTP envelope fail-closed;
- malformed body-only input fail-closed.

Status at packaging time:

```text
CB-1 IMPLEMENTATION PRESENT IN SUPPLIED CURRENT DELTA
FRESH TEST EXECUTION IN THIS PACKAGING STEP = NOT PERFORMED
```

Therefore do not call CB-1 independently verified until the receiving AI runs
the offline tests on the real repository.

## 5. Bounded runner status

Latest independent source review characterized
`scripts/run_alfresco_bounded_feedback.py:main()` as a stub:

- credential presence was checked;
- `--preflight-only` was parsed but had no operational meaning;
- run-root preparation was not wired;
- dedicated-node resolution was not wired;
- runtime target rendering was not wired;
- AFL launch was not wired.

Status:

```text
CB-2 = MUST RE-VERIFY CURRENT REPOSITORY FILE
```

Do not modify it based only on this report.

## 6. Key engineering contracts

### exec_seq

- namespace is `NV_STATUS_PATH`;
- persistent counter sidecar is `NV_STATUS_PATH + ".seq"`;
- validity rejection must not mint exec_seq;
- observer/read-back must not mint exec_seq;
- use a fresh run-root per real bounded run.

### case budget

Known source-derived accounting:

```text
C-side validity reject               -> no case
target-executed Python/body reject    -> consumes case
2xx / 4xx / 5xx / timeout / refused  -> consumes case
dry run / calibration                 -> no case
```

### seed credit

A new security state credits `queue_cur->ss_cov_cnt` and
`security_state_seed_credit`. Native AFL bitmap credit can also affect
`ss_cov_cnt`; `-n` is therefore important for the simple bounded conservation
check.

### reporting

Important post-run checks include:

```text
runtime/state total == fuzzer_stats state total == eval_report state total
sum(per-arm pulls) == nv_mab_total_pulls
```

Do not assume MAB pulls must equal `max_test_cases`; the terminating Nth case can
be state-accounted before reward update is applied.

## 7. Real-service gate

The receiving AI should begin READ-ONLY and OFFLINE.

Before any real Alfresco bounded execution, re-confirm:

- PWD / branch / HEAD / status;
- key file SHA256;
- current CB-1 offline test result;
- current CB-2 implementation;
- credential variables are nonblank without printing values;
- fresh run-root outside the git worktree;
- target/node identity through the existing Level-C preflight.

No actual credential values are included in this handoff package.
