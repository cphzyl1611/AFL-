# Failure Exclusion and Interruption Rules

**Frozen:** 2026-09-21

**Approved Decisions:** D14, D11, D3

---

## Failure and Exclusion Policy

### Validity Gate Failures

**If either run (AE or SE) in a paired block fails any validity gate:**

- The entire paired block is excluded from analysis
- The failed run is documented in the evidence package
- No replacement seed is generated
- The next seed in the frozen seed list is used
- The planned denominator remains N=30

### Valid Scientific Zeros

**If `security_state_new_total = 0`:**

- This is a valid scientific observation, NOT a failure
- The run is included in analysis if all validity gates pass
- Zero outcomes contribute to the paired difference calculation

### No Replacement Policy

**Replacement is forbidden for:**

- Failed validity gate runs
- Interrupted runs (unless proven valid by bounded-timer semantics)
- Runs with undesirable outcomes
- Any seed after observing results

**The formal seed list is frozen. No post-hoc seed generation is allowed.**

---

## Interruption Semantics

### Interruption Between Completed Runs

**Allowed if:**

- No active run is affected
- All completed runs have frozen evidence packages
- Interruption is documented with timestamp

**Effect:** None (valid pause in execution)

### Interruption Overlapping an Active Run

**Default consequence:** Run is invalidated unless proven otherwise

**Exception:** Exact bounded-timer/process semantics prove the run completed validly before interruption occurred

**Burden of proof:** On the executor to demonstrate run validity

**If validity uncertain:** Exclude the entire paired block (no replacement)

---

## Run Manifest Requirements

Every run (AE or SE) must emit a JSON manifest containing:

- `run_id`
- `backend`
- `seed`
- `pair_index` (which block from 1-30)
- `execution_order` (AE-first or SE-first)
- `git_commit_sha`
- `start_timestamp_iso8601`
- `end_timestamp_iso8601`
- `max_test_cases`
- `time_budget_seconds`
- `target_endpoint`
- `security_state_new_total`
- `security_state_total`
- `body_score_rpc_ok`
- `body_score_rpc_fail`
- `trace_invocations`
- `backend_name_recorded`
- `validity_gate_results` (all gates)

### Paired Block Manifest

Each paired block produces two run manifests (AE + SE) bound by:

- Identical `pair_index`
- Identical `seed`
- Identical `git_commit_sha`
- Complementary `execution_order`

---

## Stopping Rule

**Approved:** Fixed-N design (D11)

**No interim analysis**
**No early stopping**
**No adaptive sample size**

All N=30 paired blocks must be attempted (validity gate failures excluded, but no replacement).

---

## Evidence Freeze After Failure

**If a paired block fails:**

1. Freeze both run manifests (AE and SE, even if only one failed)
2. Record exact failure reason
3. Document which validity gate(s) failed
4. Compute validity gate pass rate at campaign end
5. Report N total blocks, (N - k) valid blocks, k exclusions with reasons

**No backfill. No rerun. No seed replacement.**

---

## Denominator Integrity

**Planned denominator:** N=30

**Effective denominator after exclusions:** (N - k) where k = number of paired blocks excluded due to validity gate failures

**Analysis reports both:**
- N=30 preregistered blocks
- (N - k) valid blocks contributing to estimate
- k exclusions with documented reasons

**This preserves intent-to-treat paired block integrity.**
