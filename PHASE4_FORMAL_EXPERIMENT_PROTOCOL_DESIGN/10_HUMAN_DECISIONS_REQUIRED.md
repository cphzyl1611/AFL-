# Human Decisions Required

This document consolidates all human decisions that must be made before the formal experiment can proceed.

## Critical Decisions (Block Execution)

These decisions **must** be made before any formal experimental runs can begin:

### D1: Sample Size Method

**Question:** Which sample-size determination method should be used?

**Options:**

- **A: MPID + Power** — conventional power analysis based on minimum practically important difference
- **B: Precision-based** — target confidence interval width
- **C: Blinded variance re-estimation** — two-stage adaptive design
- **D: Fixed pragmatic N** — resource-constrained fixed N

**Current Status:** UNDECIDED

**Reference:** See `05_SAMPLE_SIZE_PLAN.md`

**Dependencies:** D2, D3, D4, D5, D6, D7 depend on this choice

---

### D2: Minimum Practically Important Difference (MPID) [If D1 = A]

**Question:** What is the smallest mean paired difference in `security_state_new_total` that would be scientifically or practically meaningful?

**Example Values:**

- δ = 0.5 (detecting half an event per run on average)
- δ = 1.0 (detecting one full event per run on average)
- δ = 2.0 (detecting two events per run on average)

**Considerations:**

- What difference would change a decision about which model to use?
- What difference is large enough to matter given the engineering context?

**Current Status:** UNDECIDED

**Required If:** D1 = A (MPID + Power)

---

### D3: Variance Assumption [If D1 = A or B]

**Question:** What is a reasonable assumption for the standard deviation σ_Δ of paired differences?

**Considerations:**

- Phase-3 pilot observed σ_Δ = 0 (all five paired differences were 0), so this cannot be used directly
- Must come from:
  - External data (prior experiments)
  - Conservative worst-case reasoning
  - Domain expert judgment
  - Simulation under plausible assumptions

**Example Values:**

- σ_Δ = 1.0 (low variance: most pairs have differences within ±1 event)
- σ_Δ = 2.0 (moderate variance)
- σ_Δ = 4.0 (high variance: large spread in paired differences)

**Current Status:** UNDECIDED

**Required If:** D1 = A or D1 = B

---

### D4: Significance Level and Power [If D1 = A]

**Question:** What significance level α and power (1 - β) should be used?

**Standard Choices:**

- α = 0.05 (two-sided), power = 0.80
- α = 0.01 (two-sided), power = 0.90 (more stringent)

**Current Status:** α = 0.05, power = 0.80 (standard default) — **confirm or override**

**Required If:** D1 = A (MPID + Power)

---

### D5: Target CI Width [If D1 = B]

**Question:** What is the maximum acceptable 95% confidence interval width for the paired mean difference?

**Example Values:**

- Width = 0.5 (very precise: ± 0.25 events)
- Width = 1.0 (precise: ± 0.5 events)
- Width = 2.0 (moderate: ± 1.0 event)

**Current Status:** UNDECIDED

**Required If:** D1 = B (Precision-based)

---

### D6: Blinded Stage Parameters [If D1 = C]

**Question:** What are N₁, N_max, and the re-estimation rule?

**Subquestions:**

- N₁ = initial blinded stage size (e.g., 10, 15, 20)
- N_max = maximum allowed total N (e.g., 50, 100)
- Re-estimation rule: how to compute N₂ from observed variance and preregistered MPID/power

**Current Status:** UNDECIDED

**Required If:** D1 = C (Blinded variance re-estimation)

---

### D7: Fixed N [If D1 = D]

**Question:** What fixed N is feasible and reasonable?

**Considerations:**

- Resource constraints (time, compute, human effort)
- Qualitative judgment about what N provides a reasonable initial estimate
- Acknowledgment that the study may be underpowered for small effects

**Example Values:**

- N = 20 (4× Phase-3 pilot)
- N = 30 (6× Phase-3 pilot, often cited as "minimum for CLT")
- N = 50 (10× Phase-3 pilot)

**Current Status:** UNDECIDED

**Required If:** D1 = D (Fixed pragmatic N)

---

### D8: Execution Order Policy

**Question:** Should within-pair execution order be fixed (AE always first) or randomized/counterbalanced?

**Options:**

- **Fixed:** AE always runs first, then SE (simpler, matches Phase-3 pilot)
- **Randomized/Counterbalanced:** Order determined by preregistered randomization (protects against order effects, requires additional infrastructure)

**Considerations:**

- Phase-3 pilot used fixed order (AE first) successfully
- Both runs reset target baseline, so order effects should be minimal if reset is effective
- Randomization adds complexity but provides formal protection against order bias

**Recommendation:** Fixed order (AE first) unless there is specific evidence of order sensitivity

**Current Status:** UNDECIDED (recommendation: fixed)

**Required:** YES

---

### D9: Execution Budget

**Question:** What are MAX_TEST_CASES and TIME_BUDGET for the formal experiment?

**Phase-3 Values:**

- MAX_TEST_CASES = 5
- TIME_BUDGET = 60 seconds

**Considerations:**

- Keeping Phase-3 values maintains continuity but limits execution
- Increasing budget may improve sensitivity to differences but changes the experiment context
- Cannot combine Phase-3 observations with formal study observations if budgets differ

**Options:**

- **Keep Phase-3 values:** MAX_TEST_CASES = 5, TIME_BUDGET = 60
- **Increase moderately:** MAX_TEST_CASES = 10-20, TIME_BUDGET = 120-300
- **Increase substantially:** MAX_TEST_CASES = 50+, TIME_BUDGET = 600+

**Current Status:** UNDECIDED

**Required:** YES

---

### D10: Source Baseline

**Question:** Which git commit SHA becomes the formal experiment source baseline?

**Options:**

- Current HEAD at protocol freeze time
- Phase-3 final commit (if no source changes are needed)
- A new commit that includes protocol documentation only (no fuzzer/harness changes)

**Requirement:** All formal experiment runs must execute from this exact commit

**Current Status:** UNDECIDED (likely current HEAD or Phase-3 final commit)

**Required:** YES

---

### D11: Protocol Master Seed

**Question:** What integer should be used as the protocol master seed for deterministic seed generation?

**Considerations:**

- Can be any positive integer
- Should be memorable or meaningful (e.g., 20260921 for today's date)
- Once chosen and frozen, it determines the entire seed list

**Current Status:** UNDECIDED

**Required:** YES (but only after D1-D7 determine N)

---

## Secondary Decisions (Clarify Analysis Plan)

These decisions affect analysis and reporting but do not block execution:

### D12: Hypothesis Testing

**Question:** Should a formal hypothesis test be performed, or is estimation-only sufficient?

**Options:**

- **Estimation-only:** Report point estimate and CI, no p-value
- **Hypothesis test:** Perform preregistered test (permutation or bootstrap) and report p-value

**Recommendation:** Perform hypothesis test for completeness, but emphasize estimation and CI

**Current Status:** UNDECIDED (recommendation: yes, use permutation test)

**Required:** NO (can be deferred to analysis script freeze)

---

### D13: Equivalence Testing

**Question:** Is equivalence testing an objective?

**If YES:**

- Must preregister equivalence margin (e.g., ±0.5 events)
- Must perform TOST or equivalence CI

**If NO:**

- Failure to reject H₀ does not imply equivalence
- Only report whether a difference was detected, not whether equivalence was proven

**Recommendation:** Defer equivalence testing to a separate protocol if it becomes an objective

**Current Status:** NO (not an objective for this protocol)

**Required:** NO

---

### D14: Secondary Endpoints

**Question:** Are any secondary endpoints confirmatory, or are all exploratory?

**Options:**

- **All exploratory:** Only `security_state_new_total` is confirmatory; all others descriptive
- **Some confirmatory:** Promote one or more secondary endpoints (requires multiplicity adjustment)

**Recommendation:** Keep all secondary endpoints exploratory

**Current Status:** UNDECIDED (recommendation: all exploratory)

**Required:** NO (but must be decided before analysis script freeze)

---

### D15: Multiplicity Adjustment

**Question:** If multiple confirmatory tests are performed, what adjustment method should be used?

**Options:**

- Bonferroni
- Holm
- Benjamini-Hochberg (for many comparisons)
- None (if only one confirmatory test)

**Current Status:** UNDECIDED (not applicable if D14 keeps all secondary endpoints exploratory)

**Required:** Only if D14 promotes secondary endpoints to confirmatory

---

## Decision Summary Table

| ID | Decision | Status | Blocks Execution? | Depends On |
|----|----------|--------|-------------------|------------|
| D1 | Sample size method | UNDECIDED | YES | — |
| D2 | MPID | UNDECIDED | YES if D1=A | D1 |
| D3 | Variance assumption | UNDECIDED | YES if D1=A or B | D1 |
| D4 | α and power | Default (0.05, 0.80) | YES if D1=A | D1 |
| D5 | Target CI width | UNDECIDED | YES if D1=B | D1 |
| D6 | Blinded stage params | UNDECIDED | YES if D1=C | D1 |
| D7 | Fixed N | UNDECIDED | YES if D1=D | D1 |
| D8 | Execution order | UNDECIDED (rec: fixed) | YES | — |
| D9 | Execution budget | UNDECIDED | YES | — |
| D10 | Source baseline | UNDECIDED | YES | — |
| D11 | Protocol master seed | UNDECIDED | YES | D1-D7 (determines N) |
| D12 | Hypothesis testing | UNDECIDED (rec: yes) | NO | — |
| D13 | Equivalence testing | NO | NO | — |
| D14 | Secondary confirmatory | UNDECIDED (rec: no) | NO | — |
| D15 | Multiplicity adjustment | UNDECIDED | NO | D14 |

## Recommended Decision Path

**Step 1:** Convene human reviewers to discuss:

- Scientific context: What difference would be meaningful (MPID)?
- Variance uncertainty: Can we justify a variance assumption?
- Resource constraints: What N is feasible?

**Step 2:** Choose sample size method (D1) based on Step 1 discussion:

- If MPID and variance can be justified → D1 = A
- If variance is truly unknown and resources allow two stages → D1 = C
- If neither can be justified but some N is feasible → D1 = D

**Step 3:** Resolve D2-D7 based on D1 choice

**Step 4:** Resolve execution parameters (D8, D9, D10)

**Step 5:** Generate seed list (D11) using chosen N

**Step 6:** Freeze execution package (Stage 2 of evidence freeze)

**Step 7:** Resolve analysis decisions (D12, D14, D15)

**Step 8:** Freeze analysis script

**Step 9:** Human approval to begin formal experiment runs

## Current Blocker

**FORMAL_EXPERIMENT_EXECUTION_GATE = BLOCKED_PENDING_HUMAN_DESIGN_APPROVAL**

At minimum, decisions **D1, D8, D9, D10** must be made before execution can begin.

After D1 is chosen, the dependent decisions (D2-D7) must also be resolved.

## Notes

- These decisions are preregistered and frozen before execution
- No decisions can be changed after the execution freeze (Stage 2)
- Post-hoc decision changes invalidate the protocol and require a new preregistration
- All decisions and their rationale must be documented in the execution freeze package
