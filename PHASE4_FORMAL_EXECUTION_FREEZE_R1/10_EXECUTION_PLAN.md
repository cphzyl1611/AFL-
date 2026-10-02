# Phase 4 — Formal Experiment Execution Plan

**Frozen:** 2026-09-21

**Status:** BLOCKED_PENDING_HUMAN_EXECUTION_FREEZE_APPROVAL

---

## Execution Overview

**Design:** Paired comparison study (N=30)

**Total runs:** 60 (30 AE + 30 SE)

**Estimand:** Mean paired difference θ = E[Δᵢ] for `security_state_new_total`

**Primary deliverable:** Point estimate θ̂ and 95% bootstrap confidence interval

---

## Pre-Execution Requirements

Before the first real run:

1. ✓ Human approval of D1-D15 (COMPLETED)
2. ✓ Formal seed list generated and frozen (COMPLETED)
3. ✓ Paired order schedule frozen (COMPLETED)
4. ✓ Composite source identity frozen (COMPLETED)
5. ✓ Runtime model provenance frozen (COMPLETED)
6. ✓ Execution freeze package created (COMPLETED)
7. ⏳ Human approval of execution freeze commitment (PENDING)
8. ⏳ Target baseline reset validation (PENDING)

---

## Execution Sequence

For each paired block i (i = 1, 2, ..., 30):

### Step 1: Determine execution order

```python
if i % 2 == 1:
    # Odd block: AE-first
    first_backend = "alfresco_ae_v1"
    second_backend = "sefanogan_es_reference"
else:
    # Even block: SE-first
    first_backend = "sefanogan_es_reference"
    second_backend = "alfresco_ae_v1"
```

### Step 2: Reset target baseline

- Reset target security_state to known baseline
- Validate baseline reset occurred
- Record baseline identity before first run

### Step 3: Execute first run

```bash
seed_i = FORMAL_SEED_LIST[i]
backend = first_backend

python3 scripts/run_alfresco_bounded_feedback.py \
  --seed $seed_i \
  --max_test_cases 5 \
  --timeout 60 \
  --backend $backend \
  --pair_index $i \
  --execution_order "${backend}-first"
```

- Record start timestamp
- Monitor validity gates in real-time
- Record end timestamp
- Emit run manifest JSON

### Step 4: Validate first run

Check all validity gates:
- Universal gates (8)
- Backend-specific gates (5 for SE, 2 for AE)

If any gate fails → Exclude entire paired block, continue to next seed (no replacement)

### Step 5: Execute second run

Same seed, second backend, same baseline continuation

```bash
backend = second_backend

python3 scripts/run_alfresco_bounded_feedback.py \
  --seed $seed_i \
  --max_test_cases 5 \
  --timeout 60 \
  --backend $backend \
  --pair_index $i \
  --execution_order "${first_backend}-first"
```

### Step 6: Validate second run

Check all validity gates

If any gate fails → Exclude entire paired block

### Step 7: Freeze paired block evidence

If both runs passed:
- Bind both run manifests
- Record Δᵢ = security_state_new_total(SE) - security_state_new_total(AE)
- Archive all artifacts (traces, fuzzer_stats, logs)

If either run failed:
- Bind both run manifests (even failed one)
- Document failure reason
- Mark paired block as EXCLUDED

---

## Post-Execution Requirements

After all N=30 blocks attempted:

1. Freeze execution log with timestamps
2. Compute validity gate pass rate
3. Report (N - k) valid blocks and k exclusions
4. Create run evidence freeze package with SHA256 commitment
5. NO statistical analysis until run evidence freeze approved
6. Create campaign freeze package
7. Perform statistical analysis only after campaign freeze approved

---

## Validity Gate Contract

**Full gate set:** 8 universal + 5 SE-specific + 2 AE-specific

See `08_FULL_VALIDITY_GATE_CONTRACT.json` for exact specification.

**Critical gates:**
- `body_score_rpc_ok > 0`
- `body_score_rpc_fail = 0`
- `trace_invocations > 0`
- SE: `checkpoint_sha256 = 4eace87ac7d7759a729ff98916a5acead4154c803c53884e3ca7f27570dbf20d`
- SE: `metadata_sha256 = 2a73ccc3729a3734ab9901b4474feb73d4d42f912ccbc717af48f970ab568226`

---

## Interruption Handling

**Between completed runs:** Allowed (document with timestamp)

**Overlapping active run:** Run invalidated unless proven valid by bounded semantics

**After interruption:** Continue with next seed (no backfill)

---

## No Replacement Policy

**Forbidden:**
- Replacing failed seeds
- Generating additional seeds after observing outcomes
- Reordering seed list based on results
- Adaptive sample size increase

**The formal seed list is frozen. N=30 is fixed.**

---

## Statistical Analysis (Post-Campaign Freeze Only)

**Primary analysis:**
1. Compute θ̂ = mean(Δ₁, Δ₂, ..., Δₙ₋ₖ) over valid paired blocks
2. Bootstrap 10,000 paired resamples
3. Compute 95% percentile CI

**Optional supplementary:**
- Two-sided permutation test (α=0.05)

**Exploratory:**
- Descriptive statistics for secondary endpoints (no multiplicity correction)

---

## Execution Gate Status

**Human design approval:** APPROVED_AND_MATERIALIZED

**Execution freeze:** PASS_PENDING_FINAL_HUMAN_EXECUTION_AUTHORIZATION

**Formal experiment execution gate:** BLOCKED_PENDING_HUMAN_EXECUTION_FREEZE_APPROVAL

**No real runs until execution freeze commitment approved by human reviewer.**
