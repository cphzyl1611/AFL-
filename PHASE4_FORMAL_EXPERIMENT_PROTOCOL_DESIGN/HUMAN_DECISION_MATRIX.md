# Human Decision Matrix — Phase 4 Formal Experiment Protocol

**Protocol Version:** 1.0.0  
**Review Date:** 2026-09-21  
**Design Package Commitment:** `cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19`

---

## Decision Summary

| ID | Decision | Blocks Execution? | Status | Recommendation |
|----|----------|-------------------|--------|----------------|
| **D1** | Sample size method | YES | UNDECIDED | D (Fixed pragmatic N) |
| **D2** | MPID | YES (if D1=A) | N/A | — |
| **D3** | Variance assumption | YES (if D1=A/B) | N/A | — |
| **D4** | α and power | YES (if D1=A) | Default available | α=0.05, power=0.80 |
| **D5** | Target CI width | YES (if D1=B) | N/A | — |
| **D6** | Blinded stage params | YES (if D1=C) | N/A | — |
| **D7** | Fixed N | YES (if D1=D) | UNDECIDED | N=30 |
| **D8** | Execution order | YES | UNDECIDED | Fixed (AE first) |
| **D9** | Execution budget | YES | UNDECIDED | Keep Phase-3 (5, 60s) |
| **D10** | Source baseline | YES | UNDECIDED | Current HEAD |
| **D11** | Protocol master seed | YES | UNDECIDED | 20260921 |
| **D12** | Hypothesis testing | NO | UNDECIDED | Yes (permutation) |
| **D13** | Equivalence testing | NO | DECIDED | No |
| **D14** | Secondary confirmatory | NO | UNDECIDED | No (all exploratory) |
| **D15** | Multiplicity adjustment | NO | N/A | None needed |

**Total Decisions:** 15  
**Critical (Block Execution):** 11  
**Secondary (Analysis Clarification):** 4

---

## D1: Sample Size Method

**Question:** Which sample-size determination method should be used?

**Available Options:**

- **A: MPID + Power** — conventional power analysis
- **B: Precision-based** — target confidence interval width
- **C: Blinded variance re-estimation** — two-stage adaptive design
- **D: Fixed pragmatic N** — resource-constrained fixed N

**Protocol Constraints:**

- Phase-3 observed paired differences: [0, 0, 0, 0, 0]
- Phase-3 sample variance: 0 (cannot support conventional power calculation)
- Primary endpoint: `security_state_new_total` (discrete count)
- Paired design removes between-seed variance

**Scientific Consequence:**

- **Method A/B:** Requires justified MPID or precision target + variance assumption (no empirical variance from Phase-3)
- **Method C:** Requires two-stage design with strict blinding (complex infrastructure)
- **Method D:** Simple, honest about uncertainty; study may be underpowered for small effects

**Operational Consequence:**

- **Method A/B:** N depends on unjustified assumptions → risk of under/over-sizing
- **Method C:** Requires N₁ initial stage + re-estimation rule + N_max cap → more operational complexity
- **Method D:** Fixed N chosen based on feasibility → simpler execution, emphasis on estimation

**Recommended Option:** **D (Fixed pragmatic N)**

**Why Recommended:**

1. Phase-3 variance = 0 provides no empirical basis for Methods A or B
2. No external data available to justify variance assumption independently
3. MPID is subjective and domain-specific (no clear "meaningful difference" threshold established)
4. Method C adds substantial operational complexity (blinding infrastructure, two stages)
5. Method D is transparent: acknowledge uncertainty, choose feasible N, emphasize estimation over hypothesis testing
6. Aligns with exploratory nature of this initial formal comparison

**Fallback Option:** **C (Blinded variance re-estimation)** if resources allow two-stage design and variance uncertainty is the primary concern

**Exact Human Input Required:**

```
D1_CHOICE = [A | B | C | D]
```

**If D1 = D, then also decide:**

```
D7_FIXED_N = <integer>  (recommended: 30)
```

---

## D2-D7: Method-Specific Parameters

These decisions are **conditional** on D1 choice:

### D2: MPID (If D1 = A)

**Required:** YES (if D1 = A)  
**Current Status:** Not applicable (recommendation is D1 = D)

**If chosen:** Must specify minimum practically important paired difference δ (e.g., 0.5, 1.0, 2.0 events)

---

### D3: Variance Assumption (If D1 = A or B)

**Required:** YES (if D1 = A or B)  
**Current Status:** Not applicable (recommendation is D1 = D)

**If chosen:** Must specify assumed standard deviation σ_Δ of paired differences, justified independently of Phase-3 pilot

---

### D4: α and Power (If D1 = A)

**Required:** YES (if D1 = A)  
**Current Status:** Default available (α = 0.05, power = 0.80)  
**Not applicable:** (recommendation is D1 = D)

---

### D5: Target CI Width (If D1 = B)

**Required:** YES (if D1 = B)  
**Current Status:** Not applicable (recommendation is D1 = D)

**If chosen:** Must specify maximum acceptable 95% CI width (e.g., 0.5, 1.0, 2.0 events)

---

### D6: Blinded Stage Parameters (If D1 = C)

**Required:** YES (if D1 = C)  
**Current Status:** Not applicable (recommendation is D1 = D)

**If chosen:** Must specify N₁ (initial stage), N_max (maximum allowed), and re-estimation rule

---

### D7: Fixed N (If D1 = D)

**Required:** YES (if D1 = D)  
**Current Status:** UNDECIDED

**Available Options:**

- N = 20 (4× Phase-3 pilot)
- N = 30 (6× Phase-3 pilot, conventional "minimum for CLT")
- N = 50 (10× Phase-3 pilot, higher precision)

**Protocol Constraints:**

- Must be feasible given time, compute, and human resources
- Study may be underpowered for small effects
- Emphasis on estimation and confidence intervals

**Scientific Consequence:**

- Smaller N: wider confidence intervals, less precision, more uncertainty
- Larger N: narrower confidence intervals, better precision, more resource investment
- N=30 often cited as conventional minimum for approximate normality of sample mean

**Operational Consequence:**

- N=20: ~40 runs (20 AE + 20 SE), faster completion
- N=30: ~60 runs (30 AE + 30 SE), moderate resource requirement
- N=50: ~100 runs (50 AE + 50 SE), substantial resource investment

**Recommended Option:** **N = 30**

**Why Recommended:**

1. Represents 6× increase over Phase-3 pilot (N=5)
2. Conventional threshold for approximate CLT applicability
3. Balances precision with feasibility
4. Provides reasonable initial estimate for future studies
5. Not so small that study is guaranteed to be inconclusive, not so large that resource constraints dominate

**Exact Human Input Required:**

```
D7_FIXED_N = <integer>  (recommended: 30)
```

---

## D8: Execution Order Policy

**Question:** Should within-pair execution order be fixed (AE always first) or randomized/counterbalanced?

**Available Options:**

- **Fixed AE-first:** AE(seed_i) → validate → reset → SE(seed_i) → validate
- **Fixed SE-first:** SE(seed_i) → validate → reset → AE(seed_i) → validate
- **Deterministic counterbalanced:** Half pairs AE-first, half SE-first (balanced, preregistered)
- **Deterministic randomized:** Order per pair drawn from preregistered randomization

**Protocol Constraints:**

- Both runs reset target baseline between executions
- Phase-3 pilot used fixed AE-first order successfully
- Order must be frozen before first run
- Order recorded in every run manifest

**Scientific Consequence:**

- **Fixed order:** Assumes baseline reset is effective and order effects are negligible
- **Randomized/counterbalanced:** Protects against order effects if reset is incomplete or temporal drift exists
- If order effects exist but fixed order used → bias in estimated difference
- If no order effects exist but randomized → slight loss of power from added variability

**Operational Consequence:**

- **Fixed:** Simple protocol, no randomization infrastructure
- **Randomized/counterbalanced:** Requires deterministic randomization seed, balance tracking, order recording infrastructure

**Recommended Option:** **Fixed order (AE first)**

**Why Recommended:**

1. Phase-3 pilot validated baseline reset protocol successfully
2. No evidence of order sensitivity observed in Phase-3
3. Simpler operational execution
4. Both runs reset target baseline explicitly
5. If order effects are later suspected, can be tested in follow-up study

**Alternative:** If temporal drift, carryover effects, or incomplete reset are scientific concerns, choose **deterministic counterbalanced** (requires additional infrastructure)

**Exact Human Input Required:**

```
D8_ORDER = [fixed_ae_first | fixed_se_first | counterbalanced | randomized]

(recommended: fixed_ae_first)
```

---

## D9: Execution Budget

**Question:** What are MAX_TEST_CASES and TIME_BUDGET for the formal experiment?

**Available Options:**

- **Keep Phase-3 values:** MAX_TEST_CASES=5, TIME_BUDGET=60s
- **Increase moderately:** MAX_TEST_CASES=10-20, TIME_BUDGET=120-300s
- **Increase substantially:** MAX_TEST_CASES=50+, TIME_BUDGET=600+s

**Protocol Constraints:**

- Phase-3 used MAX_TEST_CASES=5, TIME_BUDGET=60s
- Both runs within a pair must use identical budget
- Cannot combine Phase-3 observations with formal study if budgets differ

**Scientific Consequence:**

- **Keep Phase-3 budget:** Direct comparability with Phase-3 pilot; maintains continuity
- **Increase budget:** May improve sensitivity to differences; changes experiment context
- Risk of floor effect (budget too small to detect differences) vs ceiling effect (saturation)

**Operational Consequence:**

- **Keep Phase-3:** Shorter per-run time, faster campaign completion
- **Increase budget:** Longer per-run time, slower campaign completion, more resource consumption

**Recommended Option:** **Keep Phase-3 values (MAX_TEST_CASES=5, TIME_BUDGET=60s)**

**Why Recommended:**

1. Maintains direct comparability with Phase-3 validated pilot
2. Phase-3 demonstrated these budgets produce measurable, valid results
3. Shorter runs allow faster iteration if issues arise
4. Budget increase can be justified in follow-up studies if initial results suggest floor effects
5. No evidence from Phase-3 that budget was insufficient

**Alternative:** If Phase-3 results suggest both models saturated quickly or budget was too restrictive, consider moderate increase (MAX_TEST_CASES=10, TIME_BUDGET=120s)

**Exact Human Input Required:**

```
D9_MAX_TEST_CASES = <integer>  (recommended: 5)
D9_TIME_BUDGET = <integer>  (recommended: 60)
```

---

## D10: Source Baseline

**Question:** Which git commit SHA becomes the formal experiment source baseline?

**Available Options:**

- **Current HEAD:** 87bee5c6fa1f0a8f7d6df2a301df3b7f879aa408
- **Phase-3 final commit:** (if no source changes since Phase-3)
- **New commit:** Protocol documentation added, no fuzzer/harness changes

**Protocol Constraints:**

- All formal experiment runs must execute from same git commit SHA
- Commit must be frozen before first run
- Every run manifest records git commit SHA

**Scientific Consequence:**

- Using current HEAD: Includes all post-Phase-3 fixes and improvements
- Using Phase-3 commit: Maximum continuity with Phase-3 pilot (if no changes needed)
- Any source differences between Phase-3 and formal study must be documented

**Operational Consequence:**

- Current HEAD: Ready to use immediately
- Phase-3 commit: Requires verification that no source changes are needed
- New commit: Requires creating commit with protocol docs only

**Recommended Option:** **Current HEAD (87bee5c6fa1f0a8f7d6df2a301df3b7f879aa408)**

**Why Recommended:**

1. Represents most recent validated state
2. Includes post-Phase-3 refinements
3. Ready for immediate use
4. Can be frozen as-is with protocol documentation added to separate directory

**Alternative:** Create new commit that adds Phase-4 protocol design directory (already created) to current HEAD and use that commit

**Exact Human Input Required:**

```
D10_SOURCE_BASELINE = <40-character git SHA>

(recommended: 87bee5c6fa1f0a8f7d6df2a301df3b7f879aa408 or next commit after protocol freeze)
```

---

## D11: Protocol Master Seed

**Question:** What integer should be used as the protocol master seed for deterministic seed generation?

**Available Options:**

- Date-based: 20260921 (today's date YYYYMMDD)
- Arbitrary memorable integer
- Random large integer

**Protocol Constraints:**

- Must be positive integer
- Once frozen, determines entire seed list via deterministic PRNG
- Cannot be changed after seed list generation
- Recorded in protocol manifest

**Scientific Consequence:**

- Choice of master seed does not affect statistical validity (all seeds equally valid)
- Different master seeds produce different seed lists
- Reproducibility requires exact master seed value

**Operational Consequence:**

- Date-based seed is memorable and documents protocol freeze date
- Arbitrary seed requires documentation

**Recommended Option:** **20260921** (protocol design date)

**Why Recommended:**

1. Memorable and meaningful (protocol design completion date)
2. Documents temporal context
3. Easy to verify and reproduce
4. Conventional practice in computational experiments

**Exact Human Input Required:**

```
D11_PROTOCOL_MASTER_SEED = <positive integer>  (recommended: 20260921)
```

**Note:** This decision must be made **after** D1/D7 determine N, but can be preselected pending N determination

---

## D12: Hypothesis Testing

**Question:** Should a formal hypothesis test be performed, or is estimation-only sufficient?

**Available Options:**

- **Estimation-only:** Report point estimate and 95% CI, no p-value
- **Hypothesis test:** Perform permutation test and report p-value alongside CI

**Protocol Constraints:**

- Decision does not block execution (can be deferred to analysis script freeze)
- Primary emphasis remains on estimation and confidence intervals

**Scientific Consequence:**

- **Estimation-only:** Clearer focus on effect size and uncertainty
- **Hypothesis test:** Provides conventional p-value for hypothesis H₀: θ = 0
- With small N, p-value may be uninformative (low power)

**Operational Consequence:**

- **Estimation-only:** Simpler analysis script
- **Hypothesis test:** Slightly more complex analysis script (permutation test implementation)

**Recommended Option:** **Yes (perform permutation test)**

**Why Recommended:**

1. Provides complete statistical inference (point estimate + CI + p-value)
2. Permutation test is exact and makes no distributional assumptions
3. Allows formal hypothesis testing if readers expect it
4. Report should still emphasize estimation and CI over p-value

**Exact Human Input Required:**

```
D12_HYPOTHESIS_TEST = [yes | no]  (recommended: yes)
```

---

## D13: Equivalence Testing

**Question:** Is equivalence testing an objective?

**Status:** **DECIDED — No**

**Rationale:**

- Equivalence testing requires preregistered equivalence margin
- Current protocol focuses on estimating difference, not proving equivalence
- Failure to reject H₀ does not imply equivalence
- If equivalence becomes objective, requires separate protocol with TOST or equivalence CI

**No Human Input Required** (already decided)

---

## D14: Secondary Endpoints

**Question:** Are any secondary endpoints confirmatory, or are all exploratory?

**Available Options:**

- **All exploratory:** Only `security_state_new_total` is confirmatory
- **Some confirmatory:** Promote one or more secondary endpoints

**Protocol Constraints:**

- Primary endpoint: `security_state_new_total` (confirmatory)
- Secondary endpoints: `security_state_total`, `body_score_pass`, `body_score_reject` (currently exploratory)
- If promoted to confirmatory, requires multiplicity adjustment

**Scientific Consequence:**

- **All exploratory:** Single confirmatory comparison, no multiplicity adjustment needed
- **Some confirmatory:** Multiple confirmatory comparisons require Bonferroni/Holm/other adjustment → reduced power per comparison

**Operational Consequence:**

- **All exploratory:** Simpler analysis, clearer primary endpoint
- **Some confirmatory:** More complex analysis, multiplicity correction

**Recommended Option:** **All exploratory (only primary endpoint confirmatory)**

**Why Recommended:**

1. Single primary endpoint maintains statistical clarity
2. Secondary endpoints are mechanistic/descriptive (accept/reject behavior)
3. No strong scientific justification to promote secondary endpoints to confirmatory status
4. Exploratory reporting allows full transparency without multiplicity penalty

**Exact Human Input Required:**

```
D14_SECONDARY_CONFIRMATORY = [all_exploratory | list_confirmatory_endpoints]

(recommended: all_exploratory)
```

---

## D15: Multiplicity Adjustment

**Question:** If multiple confirmatory tests are performed, what adjustment method?

**Status:** **Not applicable if D14 = all_exploratory (recommended)**

**Available Options (if needed):**

- Bonferroni
- Holm
- Benjamini-Hochberg

**Exact Human Input Required:**

```
D15_MULTIPLICITY_METHOD = [none | bonferroni | holm | bh]

(recommended: none, contingent on D14 = all_exploratory)
```

---

## Summary of Recommendations

| Decision | Recommended Value | Rationale |
|----------|-------------------|-----------|
| **D1** | D (Fixed pragmatic N) | Phase-3 variance=0, no justified MPID/variance assumption |
| **D7** | N = 30 | 6× Phase-3, conventional CLT threshold, feasible |
| **D8** | Fixed AE-first | Phase-3 validated, simpler, no order sensitivity observed |
| **D9** | MAX_TEST_CASES=5, TIME_BUDGET=60 | Phase-3 continuity, validated budgets |
| **D10** | Current HEAD (87bee5c6...) | Most recent validated state |
| **D11** | 20260921 | Protocol design date, memorable |
| **D12** | Yes (permutation test) | Complete inference, robust method |
| **D13** | No | Not current objective |
| **D14** | All exploratory | Single primary endpoint, statistical clarity |
| **D15** | None | Contingent on D14 |

**Dependencies:**

- D7 depends on D1 (if D1=D, then D7 required)
- D11 depends on D7 (need N before generating seed list)
- D15 depends on D14 (only needed if secondary endpoints promoted)

**Decision Path:**

1. Approve D1 = D (Fixed pragmatic N)
2. Approve D7 = 30 (fixed N value)
3. Approve D8 = fixed_ae_first (execution order)
4. Approve D9 = MAX_TEST_CASES=5, TIME_BUDGET=60 (budget)
5. Approve D10 = 87bee5c6... or new commit after protocol freeze (source baseline)
6. Approve D11 = 20260921 (protocol master seed)
7. Approve D12 = yes (hypothesis testing)
8. Confirm D13 = no (equivalence testing)
9. Approve D14 = all_exploratory (secondary endpoints)
10. Confirm D15 = none (multiplicity adjustment)

---

## What Happens Next

**After All Critical Decisions (D1-D11) Are Approved:**

1. **Generate seed list:** Run deterministic seed generation script with PROTOCOL_MASTER_SEED and N
2. **Create execution freeze package (Stage 2):**
   - Frozen seed list with SHA256 commitment
   - Frozen source baseline (git commit)
   - Frozen execution parameters (order, budget, thresholds)
   - Frozen analysis script (with D12/D14 decisions applied)
3. **Final human approval:** Human reviewers approve execution freeze package
4. **Begin formal runs:** Execute N paired blocks according to frozen protocol
5. **Apply frozen analysis:** Run frozen analysis script on collected data
6. **Generate final evidence package:** Complete formal study report with SHA256 commitments

---

## Notes

- All recommendations are evidence-based and justified above
- Human reviewers may override any recommendation with documented rationale
- Any deviation from recommendations must be documented in execution freeze package
- No decisions can be changed after execution freeze (Stage 2)
- Post-hoc decision changes invalidate the protocol and require new preregistration
