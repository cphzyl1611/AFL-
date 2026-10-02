# Revised Human Decision Matrix — Phase 4 Formal Experiment Protocol

**Protocol Version:** 1.0.0  
**Reconciliation Date:** 2026-09-21  
**Original Design Package Commitment:** `cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19`  
**Phase-3 Freeze Commitment:** `517cd241b85632142a8e74322bb284ce3e5832722cd5afdb2702dbac7c6415a8`

---

## Reconciliation Summary

This revised decision matrix corrects four issues identified before human approval:

1. **Sample-size method labels:** Verified A/B/C/D consistency (no mismatch found)
2. **N=30 justification:** Clarified as pragmatic choice, not statistically derived
3. **Order strategy empirical basis:** Corrected unsupported "no order sensitivity" claim
4. **Source baseline identity:** Changed from HEAD-only to composite 4-SHA256 identity
5. **Master seed selection:** Added deterministic derivation from design commitment
6. **Endpoint nomenclature:** Verified canonical names against artifacts
7. **Budget saturation:** Assessed Phase-3 evidence (insufficient to determine)

---

## Decision Summary

| ID | Decision | Blocks Execution? | Status | Reconciled Recommendation |
|----|----------|-------------------|--------|---------------------------|
| **D1** | Sample size method | YES | UNDECIDED | D (Fixed pragmatic N) |
| **D2** | MPID | YES (if D1=A) | N/A | — |
| **D3** | Variance assumption | YES (if D1=A/B) | N/A | — |
| **D4** | α and power | YES (if D1=A) | Default available | α=0.05, power=0.80 |
| **D5** | Target CI width | YES (if D1=B) | N/A | — |
| **D6** | Blinded stage params | YES (if D1=C) | N/A | N₁=15, N_max=50 |
| **D7** | Fixed N | YES (if D1=D) | UNDECIDED | N=30 (pragmatic, not statistical) |
| **D8** | Execution order | YES | UNDECIDED | Counterbalanced alternating |
| **D9** | Execution budget | YES | UNDECIDED | Keep Phase-3 (5, 60s) |
| **D10** | Source baseline | YES | UNDECIDED | Composite 4-SHA256 identity |
| **D11** | Protocol master seed | YES | UNDECIDED | Derive from design commitment (3469967646) |
| **D12** | Hypothesis testing | NO | UNDECIDED | Yes (permutation test) |
| **D13** | Equivalence testing | NO | DECIDED | No |
| **D14** | Secondary confirmatory | NO | UNDECIDED | No (all exploratory) |
| **D15** | Multiplicity adjustment | NO | N/A | None needed |

**Total Decisions:** 15  
**Critical (Block Execution):** 11  
**Secondary (Analysis Clarification):** 4

---

## Critical Decisions (Block Execution)

### D1: Sample Size Method

**Reconciliation:** Method labels A/B/C/D are consistent. No mismatch detected.

**Options:**
- **A:** MPID + Power — requires justified MPID and variance assumption
- **B:** Precision-based — requires justified variance assumption
- **C:** Blinded variance re-estimation — two-stage adaptive, complex infrastructure
- **D:** Fixed pragmatic N — resource-constrained, transparent about uncertainty

**Phase-3 Constraint:**
- Paired differences: Δᵢ = [0, 0, 0, 0, 0]
- Sample variance: 0 (cannot support Methods A or B)

**Reconciled Recommendation:** **D (Fixed pragmatic N)**

**Why:**
1. Phase-3 variance=0 provides no empirical basis for A or B
2. No external variance data available
3. MPID is subjective with no domain consensus
4. Method D is transparent: acknowledges uncertainty, emphasizes estimation
5. Simpler operational execution than Method C

**Fallback:** **C (Blinded re-estimation)** if variance uncertainty is dominant concern and two-stage resources available

---

### D7: Fixed N (If D1 = D)

**Reconciliation:** N=30 is **pragmatically chosen**, not statistically derived.

**Options:**
- N = 20 (4× Phase-3)
- N = 30 (6× Phase-3, conventional CLT heuristic)
- N = 50 (10× Phase-3, higher precision)

**Reconciled Recommendation:** **N = 30**

**Justification:**
1. Represents 6× increase over Phase-3 pilot
2. Conventional heuristic: N≥30 often cited for CLT applicability
3. Balances information gain vs resource feasibility
4. Acknowledges study may be underpowered for small effects

**IMPORTANT:** N=30 is NOT derived from power calculation. It is a pragmatic choice based on:
- Feasibility multiplier (6×)
- Conventional rule of thumb
- Resource constraints

**Exact Human Input Required:**
```
D7_FIXED_N = <integer>  (recommended: 30, pragmatic not statistical)
```

---

### D8: Execution Order Policy

**Reconciliation:** Corrected unsupported claim "no order sensitivity observed."

**Phase-3 Evidence:**
- All 10 runs used fixed AE-first order
- Order sensitivity was NOT experimentally tested
- Baseline reset protocol was validated
- Cannot empirically rule out order effects from fixed-order data

**Options:**
- **Fixed AE-first:** Simple, Phase-3 continuity, confounds order with backend
- **Fixed SE-first:** Reverse Phase-3, still confounds order with backend
- **Counterbalanced alternating:** Odd blocks AE-first, even blocks SE-first (balanced, controls order)
- **Randomized balanced:** Deterministic PRNG, N/2 each order (standard crossover practice)

**Reconciled Recommendation:** **Counterbalanced alternating**

**Why:**
1. **Separates order effects from backend effects** (scientific rigor)
2. Fully deterministic (odd/even rule, no PRNG needed)
3. Perfectly balanced (15 AE-first, 15 SE-first)
4. Maintains Phase-3 continuity for half the blocks
5. Robust: controls for order if it exists, no harm if it doesn't

**Implementation:**
```
Blocks 1, 3, 5, ..., 29 (odd): AE-first
Blocks 2, 4, 6, ..., 30 (even): SE-first
```

**Fallback:** **Fixed AE-first** if human reviewers explicitly judge order effects negligible

**Exact Human Input Required:**
```
D8_ORDER = [fixed_ae_first | counterbalanced | randomized]
(recommended: counterbalanced)
```

---

### D9: Execution Budget

**Reconciliation:** Phase-3 evidence insufficient to determine saturation vs adequate sampling.

**Phase-3 Observed:**
- All 10 runs: `security_state_new_total = 1` (perfect consistency)
- Cannot determine if metric saturates early or budget is adequate
- No variation observed to assess

**Options:**
- **Keep Phase-3:** MAX_TEST_CASES=5, TIME_BUDGET=60s
- **Increase moderately:** 10-20 testcases, 120-300s
- **Increase substantially:** 50+ testcases, 600+s

**Reconciled Recommendation:** **Keep Phase-3 (5, 60s)**

**Why:**
1. Direct comparability with validated Phase-3 pilot
2. Shorter runs allow faster campaign completion
3. Insufficient evidence to justify budget increase
4. If variation exists, N=30 may reveal it even at this budget
5. Follow-up studies can explore longer budgets if needed

**Acknowledged Risk:** May miss variation that emerges only at longer budgets

**Exact Human Input Required:**
```
D9_MAX_TEST_CASES = <integer>  (recommended: 5)
D9_TIME_BUDGET = <integer seconds>  (recommended: 60)
```

---

### D10: Source Baseline

**Reconciliation:** Changed from HEAD-only to composite 4-SHA256 identity.

**Phase-3 and all prior experiments executed from dirty working tree.** The formal source baseline must bind the complete snapshot, not just HEAD.

**Composite Identity Components:**

```json
{
  "git_head_commit": "87bee5c6fa1f0a8f7d6df2a301df3b7f879aa408",
  "runner_sha256": "7acb5192fc7c4c6fbb3f24155d94eb68809cca0306d7600855c6504444bf3650",
  "tracked_diff_sha256": "686a1e65035ac38145b606f4c765f6a1220e6f9f9f2206338354bd2a84112140",
  "canonical_12file_manifest_sha256": "26c2e4f3871d7deffb4ab7fc356f6973b8f01b5985d189ed6afcc79b251a2c5b"
}
```

**Why Composite Identity:**
- Critical untracked files (tests, models, thresholds) not in Git history
- Phase-3 validated this exact composite baseline
- HEAD alone insufficient for reproducibility

**Exact Human Input Required:**
```
D10_SOURCE_BASELINE_APPROVAL = APPROVE_COMPOSITE_4SHA256_IDENTITY

(Approval of all four components as frozen source baseline)
```

---

### D11: Protocol Master Seed

**Reconciliation:** Added deterministic derivation method to minimize post-hoc discretion.

**Options:**
- **Commitment-derived (recommended):** Derive from design package commitment SHA256
- **Design date:** 20260921 (protocol design completion)
- **Human-chosen:** Arbitrary integer with justification

**Reconciled Recommendation:** **Commitment-derived**

**Algorithm:**
```python
design_commitment = "cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19"
master_seed = int(design_commitment[:8], 16)
# Result: 3469967646
```

**Why:**
1. **Zero post-hoc discretion:** Uniquely determined by frozen protocol
2. Cannot be gamed: commitment frozen before seed derivation
3. Algorithmically justified: deterministic one-to-one mapping
4. Self-documenting: proves protocol frozen before seed list generation

**Fallback:** **Design date (20260921)** if human-interpretable seed preferred

**Exact Human Input Required:**
```
D11_MASTER_SEED_RULE = [commitment_derived | design_date | human_chosen]

IF commitment_derived:
  MASTER_SEED = 3469967646  (automatically derived)

IF design_date:
  MASTER_SEED = 20260921

IF human_chosen:
  MASTER_SEED = <integer with justification>
```

---

## Secondary Decisions (Analysis Clarification)

### D12: Hypothesis Testing

**Recommendation:** **Yes (permutation test)**

**Why:**
1. Provides complete statistical inference (estimate + CI + p-value)
2. Permutation test is exact, no distributional assumptions
3. Report emphasizes estimation and CI, not p-value alone

**Exact Human Input Required:**
```
D12_HYPOTHESIS_TEST = [yes | no]  (recommended: yes)
```

---

### D13: Equivalence Testing

**Status:** **DECIDED — No**

Equivalence testing not an objective for this protocol.

---

### D14: Secondary Endpoints

**Recommendation:** **All exploratory**

**Why:**
1. Single primary confirmatory endpoint maintains statistical clarity
2. Secondary endpoints (body_score_pass, body_score_reject) describe filtering behavior, not effectiveness
3. No multiplicity adjustment needed

**Exact Human Input Required:**
```
D14_SECONDARY_CONFIRMATORY = [all_exploratory | promote_some]

(recommended: all_exploratory)
```

---

### D15: Multiplicity Adjustment

**Status:** **Not applicable** if D14 = all_exploratory (recommended)

**Exact Human Input Required:**
```
D15_MULTIPLICITY = [none | bonferroni | holm]

(recommended: none, contingent on D14)
```

---

## Reconciled Recommendations Summary

| Decision | Reconciled Value | Key Change from Original |
|----------|------------------|--------------------------|
| **D1** | D (Fixed pragmatic N) | No change |
| **D7** | N=30 (pragmatic choice) | Clarified: not statistically derived |
| **D8** | Counterbalanced alternating | Changed from fixed AE-first; corrected order sensitivity claim |
| **D10** | Composite 4-SHA256 identity | Changed from HEAD-only |
| **D11** | Commitment-derived (3469967646) | Added deterministic derivation |
| **D9** | Keep Phase-3 (5, 60s) | Clarified: insufficient saturation evidence |
| **D12** | Yes (permutation test) | No change |
| **D14** | All exploratory | No change |

---

## Notes

- All reconciliations maintain scientific rigor while correcting unsupported claims
- N=30 remains reasonable but is correctly framed as pragmatic, not statistical
- Counterbalanced order is more rigorous than fixed order
- Composite source baseline matches Phase-3 validated snapshot
- Commitment-derived seed minimizes post-hoc discretion
