# Revised Human Approval Template — Phase 4 Formal Experiment Protocol

**Protocol Version:** 1.0.0  
**Reconciliation Date:** 2026-09-21  
**Design Package Commitment:** `cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19`  
**Phase-3 Freeze Commitment:** `517cd241b85632142a8e74322bb284ce3e5832722cd5afdb2702dbac7c6415a8`

---

## Human Decision Approval

**PHASE4_HUMAN_DESIGN_DECISION:** [ ] APPROVE  [ ] REQUEST_CHANGES

**Human Reviewer Name:** ___________________________

**Approval Date:** ___________________________

**Signature/Authorization:** ___________________________

---

## Critical Decisions (Block Execution)

These decisions **must** be approved before any formal experimental runs can begin.

### D1: Sample Size Method

**Decision:** [ ] A (MPID + Power)  [ ] B (Precision-based)  [ ] C (Blinded re-estimation)  [X] D (Fixed pragmatic N)

**Reconciled Recommendation:** D (Fixed pragmatic N)

**Justification (if deviating from recommendation):**

```
Phase-3 variance=0, no justified MPID/variance assumption.
Method D is transparent about uncertainty, emphasizes estimation.
[Leave blank if accepting recommendation]
```

---

### D7: Fixed N (Required if D1 = D)

**Decision:** N = ________ paired blocks

**Reconciled Recommendation:** N = 30 (pragmatic choice, not statistically derived)

**Clarification:** N=30 is based on:
- 6× Phase-3 pilot size
- Conventional CLT heuristic (N≥30)
- Resource feasibility
- **NOT** derived from power calculation

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

### D2-D6: Method-Specific Parameters (Required only if D1 = A, B, or C)

**Status:** Not applicable (D1 = D recommended)

**If D1 ≠ D, complete below:**

- **D2 (MPID):** δ = ________ [if D1 = A]
- **D3 (Variance):** σ_Δ = ________ [if D1 = A or B]
- **D4 (α, power):** α = ________, power = ________ [if D1 = A, default: 0.05, 0.80]
- **D5 (CI width):** W = ________ [if D1 = B]
- **D6 (Blinded params):** N₁ = ________, N_max = ________, re-estimation rule: ________ [if D1 = C]

---

### D8: Execution Order Policy

**Decision:** [ ] fixed_ae_first  [ ] fixed_se_first  [X] counterbalanced  [ ] randomized

**Reconciled Recommendation:** counterbalanced (alternating AE-first / SE-first)

**Clarification:**
- Phase-3 used fixed AE-first but did NOT test order sensitivity empirically
- Counterbalanced order separates order effects from backend effects
- Implementation: Odd blocks (1,3,5,...,29) AE-first; Even blocks (2,4,6,...,30) SE-first

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

### D9: Execution Budget

**Decision:**

- MAX_TEST_CASES = ________
- TIME_BUDGET = ________ seconds

**Reconciled Recommendation:** MAX_TEST_CASES = 5, TIME_BUDGET = 60

**Clarification:**
- Phase-3 observed all runs with security_state_new_total=1
- Insufficient evidence to determine saturation vs adequate sampling
- Keeping Phase-3 budget maintains direct comparability

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

### D10: Source Baseline

**Decision:** [ ] APPROVE_COMPOSITE_4SHA256_IDENTITY

**Reconciled Recommendation:** Approve composite baseline (all four SHA256 components)

**Composite Identity:**

```json
{
  "git_head_commit": "87bee5c6fa1f0a8f7d6df2a301df3b7f879aa408",
  "runner_sha256": "7acb5192fc7c4c6fbb3f24155d94eb68809cca0306d7600855c6504444bf3650",
  "tracked_diff_sha256": "686a1e65035ac38145b606f4c765f6a1220e6f9f9f2206338354bd2a84112140",
  "canonical_12file_manifest_sha256": "26c2e4f3871d7deffb4ab7fc356f6973b8f01b5985d189ed6afcc79b251a2c5b"
}
```

**Clarification:**
- Phase-3 validated this exact dirty working tree snapshot
- HEAD alone insufficient (critical untracked files: tests, models, thresholds)
- Composite identity matches Phase-3 freeze baseline

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

### D11: Protocol Master Seed

**Decision:** [ ] commitment_derived  [ ] design_date  [ ] human_chosen

**Reconciled Recommendation:** commitment_derived

**If commitment_derived (recommended):**

```
MASTER_SEED = 3469967646  (automatically derived from design commitment)
Algorithm: int("cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19"[:8], 16)
```

**If design_date:**

```
MASTER_SEED = 20260921  (protocol design date)
```

**If human_chosen:**

```
MASTER_SEED = ________  (positive integer with justification below)
```

**Justification (if deviating from commitment_derived):**

```
[Leave blank if accepting recommendation]
```

---

## Secondary Decisions (Analysis Clarification)

These decisions affect analysis and reporting but do not block execution.

### D12: Hypothesis Testing

**Decision:** [X] Yes (perform permutation test)  [ ] No (estimation-only)

**Reconciled Recommendation:** Yes

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

### D13: Equivalence Testing

**Decision:** [X] No  [ ] Yes (requires equivalence margin specification)

**Reconciled Recommendation:** No

**Equivalence margin (if Yes):** ________

---

### D14: Secondary Endpoints

**Decision:** [X] All exploratory  [ ] Promote some to confirmatory

**Reconciled Recommendation:** All exploratory

**Clarification:**
- Primary confirmatory: `security_state_new_total`
- Secondary exploratory: `security_state_total`, `body_score_pass`, `body_score_reject`
- No multiplicity adjustment needed

**If promoting to confirmatory, list endpoints:**

```
[Leave blank if accepting recommendation]
```

---

### D15: Multiplicity Adjustment

**Decision:** [X] None  [ ] Bonferroni  [ ] Holm  [ ] Benjamini-Hochberg

**Reconciled Recommendation:** None (contingent on D14 = all exploratory)

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

## Reconciliation Changes Applied

This revised approval template corrects the following issues:

1. **Sample-size method:** Clarified N=30 is pragmatic choice, not statistically derived
2. **Execution order:** Changed recommendation to counterbalanced; corrected "no order sensitivity" claim
3. **Source baseline:** Changed from HEAD-only to composite 4-SHA256 identity
4. **Master seed:** Added deterministic derivation from design commitment (3469967646)
5. **Endpoint classification:** Verified canonical names (`body_score_pass`, `body_score_reject`)
6. **Budget decision:** Clarified Phase-3 evidence insufficient to determine saturation

---

## Overall Comments and Concerns

```
[Any general comments, concerns, or conditions for approval]







```

---

## Approval Conditions

By approving this protocol design, the human reviewer confirms:

- [ ] I have read the complete Phase-4 design package and reconciliation documents
- [ ] I understand the Phase-3 freeze binding (commitment 517cd241...)
- [ ] I understand all critical decisions and their consequences
- [ ] I understand the reconciliation changes (pragmatic N, counterbalanced order, composite baseline, deterministic seed)
- [ ] I approve the above decisions (or have documented deviations)
- [ ] I authorize creation of the execution freeze package (Stage 2)
- [ ] I understand that no decisions can be changed after execution freeze
- [ ] I understand that formal experiment runs cannot begin until execution freeze is approved

---

## Next Steps After Approval

**If PHASE4_HUMAN_DESIGN_DECISION = APPROVE:**

1. Generate seed list using approved D11 (master seed) and D7 (N)
2. Generate execution order schedule using approved D8 (counterbalanced pattern)
3. Create execution freeze package (Stage 2) containing:
   - Frozen seed list with SHA256 commitment
   - Frozen execution order schedule with SHA256 commitment
   - Frozen source baseline (approved D10 composite identity)
   - Frozen execution parameters (D8 order, D9 budget)
   - Frozen analysis script (incorporating D12/D14 decisions)
4. Human approval of execution freeze package
5. Begin formal experiment runs
6. Apply frozen analysis script
7. Generate final evidence package

**If PHASE4_HUMAN_DESIGN_DECISION = REQUEST_CHANGES:**

Document requested changes below and return to protocol design phase.

**Requested Changes:**

```
[Specific changes requested]







```

---

## Execution Gate Status

**Before Approval:**

```
FORMAL_EXPERIMENT_EXECUTION_GATE = BLOCKED_PENDING_HUMAN_DESIGN_APPROVAL
```

**After Approval (pending execution freeze):**

```
FORMAL_EXPERIMENT_EXECUTION_GATE = BLOCKED_PENDING_EXECUTION_FREEZE
```

---

**End of Revised Human Approval Template**

**File:** `08_REVISED_HUMAN_APPROVAL_TEMPLATE.md`  
**Protocol Version:** 1.0.0  
**Reconciliation Date:** 2026-09-21
