# Human Approval Template — Phase 4 Formal Experiment Protocol

**Protocol Version:** 1.0.0  
**Review Date:** 2026-09-21  
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

**Recommended:** D (Fixed pragmatic N)

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

### D7: Fixed N (Required if D1 = D)

**Decision:** N = ________ paired blocks

**Recommended:** N = 30

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
- **D4 (α, power):** α = ________, power = ________ [if D1 = A]
- **D5 (CI width):** W = ________ [if D1 = B]
- **D6 (Blinded params):** N₁ = ________, N_max = ________, re-estimation rule: ________ [if D1 = C]

---

### D8: Execution Order Policy

**Decision:** [ ] fixed_ae_first  [ ] fixed_se_first  [ ] counterbalanced  [ ] randomized

**Recommended:** fixed_ae_first

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

### D9: Execution Budget

**Decision:**

- MAX_TEST_CASES = ________
- TIME_BUDGET = ________ seconds

**Recommended:** MAX_TEST_CASES = 5, TIME_BUDGET = 60

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

### D10: Source Baseline

**Decision:** Git commit SHA = ________________________________________

**Recommended:** 87bee5c6fa1f0a8f7d6df2a301df3b7f879aa408 (current HEAD) or next commit after protocol freeze

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

### D11: Protocol Master Seed

**Decision:** PROTOCOL_MASTER_SEED = ________

**Recommended:** 20260921

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

## Secondary Decisions (Analysis Clarification)

These decisions affect analysis and reporting but do not block execution.

### D12: Hypothesis Testing

**Decision:** [ ] Yes (perform permutation test)  [ ] No (estimation-only)

**Recommended:** Yes

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

### D13: Equivalence Testing

**Decision:** [X] No  [ ] Yes (requires equivalence margin specification)

**Recommended:** No

**Equivalence margin (if Yes):** ________

---

### D14: Secondary Endpoints

**Decision:** [ ] All exploratory  [ ] Promote some to confirmatory

**Recommended:** All exploratory

**If promoting to confirmatory, list endpoints:**

```
[Leave blank if accepting recommendation]
```

---

### D15: Multiplicity Adjustment

**Decision:** [ ] None  [ ] Bonferroni  [ ] Holm  [ ] Benjamini-Hochberg

**Recommended:** None (contingent on D14 = all exploratory)

**Justification (if deviating from recommendation):**

```
[Leave blank if accepting recommendation]
```

---

## Overall Comments and Concerns

```
[Any general comments, concerns, or conditions for approval]







```

---

## Approval Conditions

By approving this protocol design, the human reviewer confirms:

- [ ] I have read the complete Phase-4 design package
- [ ] I understand the Phase-3 freeze binding (commitment 517cd241...)
- [ ] I understand all critical decisions and their consequences
- [ ] I approve the above decisions (or have documented deviations)
- [ ] I authorize creation of the execution freeze package (Stage 2)
- [ ] I understand that no decisions can be changed after execution freeze
- [ ] I understand that formal experiment runs cannot begin until execution freeze is approved

---

## Next Steps After Approval

**If PHASE4_HUMAN_DESIGN_DECISION = APPROVE:**

1. Generate seed list using approved D11 (PROTOCOL_MASTER_SEED) and D7 (N)
2. Create execution freeze package (Stage 2) containing:
   - Frozen seed list with SHA256 commitment
   - Frozen source baseline (approved D10 git commit)
   - Frozen execution parameters (D8 order, D9 budget)
   - Frozen analysis script (incorporating D12/D14 decisions)
3. Human approval of execution freeze package
4. Begin formal experiment runs
5. Apply frozen analysis script
6. Generate final evidence package

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

**End of Human Approval Template**

**File:** `HUMAN_APPROVAL_TEMPLATE.md`  
**Protocol Version:** 1.0.0  
**Template Date:** 2026-09-21
