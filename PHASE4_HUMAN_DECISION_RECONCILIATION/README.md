# Phase 4 Human Decision Reconciliation — README

**Protocol Version:** 1.0.0  
**Reconciliation Date:** 2026-09-21  
**Status:** RECONCILIATION_COMPLETE_AWAITING_HUMAN_APPROVAL

---

## Purpose

This directory contains reconciliation materials that correct design issues identified before human approval of the Phase-4 formal experiment protocol.

**Original Design Package:** `PHASE4_FORMAL_EXPERIMENT_PROTOCOL_DESIGN/`  
**Original Design Commitment:** `cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19`

**This reconciliation does NOT replace the original design package.** It provides corrected decision materials for human approval.

---

## Issues Reconciled

### 1. Sample-Size Method Labeling and N=30 Justification

**Issue:** N=30 recommendation appeared statistically derived but is actually pragmatic choice.

**Reconciliation:**
- Verified method labels A/B/C/D are consistent (no mismatch)
- Clarified N=30 is **pragmatic choice** based on:
  - 6× Phase-3 pilot size
  - Conventional CLT heuristic (N≥30)
  - Resource feasibility
- **NOT** derived from power calculation (Phase-3 variance=0)

**Document:** `02_SAMPLE_SIZE_METHOD_RECONCILIATION.md`

---

### 2. Execution Order Recommendation

**Issue:** Original stated "no order sensitivity observed" but Phase-3 used fixed order (did not test sensitivity).

**Reconciliation:**
- Corrected empirical claim: Phase-3 validated baseline reset, NOT order-effect absence
- Evaluated four order strategies:
  - Fixed AE-first (Phase-3 pattern, confounds order with backend)
  - Fixed SE-first (reverse, still confounds)
  - **Counterbalanced alternating (recommended):** Odd blocks AE-first, even SE-first
  - Randomized balanced
- Changed recommendation from **fixed AE-first** to **counterbalanced alternating**

**Document:** `03_ORDER_STRATEGY_RECONCILIATION.md`

---

### 3. Source Baseline Identity

**Issue:** Original proposed HEAD-only; actual baseline is composite dirty working tree.

**Reconciliation:**
- Changed from HEAD-only to **composite 4-SHA256 identity:**
  - `git_head_commit`: 87bee5c6fa1f0a8f7d6df2a301df3b7f879aa408
  - `runner_sha256`: 7acb5192fc7c4c6fbb3f24155d94eb68809cca0306d7600855c6504444bf3650
  - `tracked_diff_sha256`: 686a1e65035ac38145b606f4c765f6a1220e6f9f9f2206338354bd2a84112140
  - `canonical_12file_manifest_sha256`: 26c2e4f3871d7deffb4ab7fc356f6973b8f01b5985d189ed6afcc79b251a2c5b
- Matches Phase-3 validated baseline exactly
- Critical untracked files (tests, models, thresholds) not in Git history

**Document:** `04_SOURCE_BASELINE_COMPOSITE_IDENTITY.json`

---

### 4. Master Seed Selection Rule

**Issue:** Date-based seed (20260921) is reproducible but introduces post-hoc discretion.

**Reconciliation:**
- Added **deterministic derivation from design commitment:**
  ```python
  design_commitment = "cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19"
  master_seed = int(design_commitment[:8], 16)  # 3469967646
  ```
- Minimizes post-hoc discretion (cannot be gamed)
- Algorithmically justified: one-to-one mapping from frozen protocol
- Changed recommendation from **design date** to **commitment-derived**

**Document:** `05_MASTER_SEED_SELECTION_RULE.md`

---

### 5. Endpoint Nomenclature

**Issue:** Verify endpoint names match actual artifacts.

**Reconciliation:**
- Verified canonical names:
  - Primary confirmatory: `security_state_new_total`
  - Secondary exploratory: `security_state_total`, `body_score_pass`, `body_score_reject`
  - Validity gates: `body_score_rpc_ok`, `body_score_rpc_fail`, `trace_invocations`
  - Diagnostic: `counted_execution_count`, `wall_clock_seconds`, `target_baseline_identity`
- No incorrect names used (e.g., no "sec_pass" or ambiguous names)

**Document:** `06_ENDPOINT_CLASSIFICATION.json`

---

### 6. Budget Decision

**Issue:** Does Phase-3 evidence indicate saturation vs adequate sampling?

**Reconciliation:**
- Phase-3 observed `security_state_new_total = 1` for all 10 runs
- **Insufficient evidence** to determine:
  - Whether metric saturates early (ceiling effect)
  - Whether budget is adequate (true variation exists but not sampled)
  - Whether variation emerges at longer budgets
- Recommendation unchanged: **Keep Phase-3 budget (MAX_TEST_CASES=5, TIME=60s)**
- Rationale: Direct comparability, validated feasibility, insufficient saturation evidence

**Document:** `07_BUDGET_DECISION_NOTE.md`

---

## Reconciliation Package Contents

| File | Description |
|------|-------------|
| `00_RECONCILIATION_STATUS.json` | Reconciliation metadata and status |
| `01_DECISION_MATRIX_REVISED.md` | Complete revised decision matrix with corrected recommendations |
| `02_SAMPLE_SIZE_METHOD_RECONCILIATION.md` | Method label verification, N=30 pragmatic clarification |
| `03_ORDER_STRATEGY_RECONCILIATION.md` | Order sensitivity empirical basis correction, counterbalanced recommendation |
| `04_SOURCE_BASELINE_COMPOSITE_IDENTITY.json` | Composite 4-SHA256 baseline identity |
| `05_MASTER_SEED_SELECTION_RULE.md` | Deterministic derivation from design commitment |
| `06_ENDPOINT_CLASSIFICATION.json` | Canonical endpoint names and classification |
| `07_BUDGET_DECISION_NOTE.md` | Phase-3 saturation evidence assessment |
| `08_REVISED_HUMAN_APPROVAL_TEMPLATE.md` | Ready-to-use revised approval form |
| `README.md` | This file |
| `FILE_LIST.txt` | Complete file listing |
| `SHA256SUMS.txt` | SHA256 hashes for all reconciliation files |

---

## Key Reconciliation Changes

| Issue | Original | Reconciled |
|-------|----------|------------|
| **N=30 status** | Appeared statistical | Clarified as **pragmatic choice** |
| **Order strategy** | Fixed AE-first | **Counterbalanced alternating** |
| **Order sensitivity** | "No sensitivity observed" | Corrected: **Not tested in Phase-3** |
| **Source baseline** | HEAD-only | **Composite 4-SHA256 identity** |
| **Master seed** | Design date (20260921) | **Commitment-derived (3469967646)** |
| **Budget saturation** | Ambiguous | Clarified: **Insufficient evidence** |

---

## Reconciled Recommendations Summary

| Decision | Reconciled Value | Rationale |
|----------|------------------|-----------|
| **D1: Sample size method** | D (Fixed pragmatic N) | Phase-3 variance=0, transparent about uncertainty |
| **D7: Fixed N** | 30 (pragmatic) | 6× Phase-3, conventional heuristic, feasible |
| **D8: Order** | Counterbalanced alternating | Separates order from backend, balanced, deterministic |
| **D9: Budget** | MAX_TEST_CASES=5, TIME=60s | Phase-3 continuity, insufficient saturation evidence |
| **D10: Source baseline** | Composite 4-SHA256 | Matches Phase-3 validated snapshot, includes untracked files |
| **D11: Master seed** | Commitment-derived (3469967646) | Minimizes discretion, algorithmically justified |
| **D12: Hypothesis test** | Yes (permutation) | Complete inference, robust method |
| **D14: Secondary endpoints** | All exploratory | Single primary, no multiplicity adjustment |

---

## Human Approval Process

**Current Status:** Reconciliation complete, awaiting human approval

**Next Steps:**

1. Human reviewers read reconciliation documents
2. Compare reconciled recommendations to original design
3. Complete revised approval template (`08_REVISED_HUMAN_APPROVAL_TEMPLATE.md`)
4. Make final decisions on all D1-D15 parameters
5. Approve or request further changes

**After Approval:**

1. Generate seed list (N seeds from approved master seed)
2. Generate execution order schedule (counterbalanced pattern)
3. Create execution freeze package (Stage 2)
4. Human approval of execution freeze
5. Begin formal experiment runs

---

## Phase-3 Binding

This reconciliation maintains binding to Phase-3 evidence freeze:

```
PHASE3_FREEZE_COMMITMENT = 517cd241b85632142a8e74322bb284ce3e5832722cd5afdb2702dbac7c6415a8
```

All reconciliation changes are compatible with Phase-3 validated baseline.

---

## Execution Gate

```
FORMAL_EXPERIMENT_EXECUTION_GATE = BLOCKED_PENDING_HUMAN_DESIGN_APPROVAL
```

No formal experiment runs permitted until:
1. Human approval of reconciled design
2. All critical decisions (D1-D11) resolved
3. Execution freeze package (Stage 2) created and approved

---

## Reproducibility

All reconciliation decisions are:
- Scientifically justified
- Documented with evidence
- Compatible with Phase-3 baseline
- Frozen before execution begins

**Reconciliation Package Commitment:** (See `SHA256SUMS.txt`)

---

## Contact

For questions about reconciliation changes:

- Sample-size/N=30: `02_SAMPLE_SIZE_METHOD_RECONCILIATION.md`
- Order strategy: `03_ORDER_STRATEGY_RECONCILIATION.md`
- Source baseline: `04_SOURCE_BASELINE_COMPOSITE_IDENTITY.json`
- Master seed: `05_MASTER_SEED_SELECTION_RULE.md`
- Endpoints: `06_ENDPOINT_CLASSIFICATION.json`
- Budget: `07_BUDGET_DECISION_NOTE.md`
- Approval form: `08_REVISED_HUMAN_APPROVAL_TEMPLATE.md`

---

## Version History

- **1.0.0** (2026-09-21): Initial reconciliation package
  - Corrected N=30 pragmatic status
  - Changed order recommendation to counterbalanced
  - Added composite source baseline identity
  - Added deterministic master seed derivation
  - Verified endpoint nomenclature
  - Assessed Phase-3 budget saturation evidence
