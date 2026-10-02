# Execution Budget Decision Note

## Original Recommendation

```
D9_MAX_TEST_CASES = 5
D9_TIME_BUDGET = 60 seconds

RATIONALE = Keep Phase-3 values for direct comparability
```

## Issue: Budget Saturation Signal Assessment

**Question:** Given that Phase-3 observed `security_state_new_total = 1` for all 10 runs, does this indicate:

A) The metric saturates early (budget too small to reveal variation)?
B) The budget is insufficient (true variation exists but wasn't sampled)?
C) Insufficient evidence to determine saturation vs adequate sampling?

## Phase-3 Evidence Analysis

### What Phase-3 Observed

**Primary Endpoint Results:**

| Backend | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Mean |
|---------|-------|-------|-------|-------|-------|------|
| AE | 1 | 1 | 1 | 1 | 1 | 1.0 |
| SE | 1 | 1 | 1 | 1 | 1 | 1.0 |

**Paired Differences:** Δᵢ = [0, 0, 0, 0, 0]

**Budget Parameters:**
- MAX_TEST_CASES = 5 (testcases accepted and executed)
- TIME_BUDGET = 60 seconds (wall-clock limit)

**Accept/Reject Behavior:**
- AE: accepted 25/25 testcases per run (100% pass rate)
- SE: rejected 25/25 testcases per run (0% pass rate)

### What Phase-3 Does NOT Tell Us

**About Saturation:**

❌ Whether `security_state_new_total` would increase with longer budgets
❌ Whether the first testcase always triggers the single new coverage hit
❌ Whether subsequent testcases (beyond first) ever trigger additional coverage
❌ Whether variation exists at longer time horizons

**About Variation:**

❌ Whether different seeds would show different counts with more test budget
❌ Whether AE/SE differences would emerge with more executions
❌ Whether the tie structure (all zeros) is stable or sampling artifact

**Why Evidence is Insufficient:**

1. **N=5 is too small** to establish variance reliably
2. **All observations tied at 1** provides no variation to analyze
3. **Fixed budget** means we only observe one slice of the time-budget space
4. **No budget pilot** was performed (Phase-3 used single budget value)

## Saturation Scenarios

### Scenario A: Early Saturation (Metric Ceiling)

**Hypothesis:** The metric saturates quickly because:
- Only one "easy" security_state transition is reachable
- First testcase always triggers it
- No additional security-relevant states exist in reachable space

**Evidence For:**
- All 10 runs observed exactly 1 (perfect consistency)
- Both AE and SE converged to same count despite different accept/reject rates

**Evidence Against:**
- Cannot rule out additional coverage at longer budgets
- Only tested 5 testcases × 60 seconds (limited exploration)

### Scenario B: Adequate Sampling (True Zero Difference)

**Hypothesis:** The budget is sufficient because:
- Both models reached the same coverage plateau
- Variation would not increase with longer budget
- True paired difference is zero (or very small)

**Evidence For:**
- Perfect replication across 5 seeds suggests stable plateau

**Evidence Against:**
- Cannot rule out variation emerging at longer budgets
- N=5 too small to establish variance = 0 reliably

### Scenario C: Insufficient Evidence

**Hypothesis:** We cannot determine from Phase-3 alone whether:
- Metric saturates early, OR
- Budget is adequate, OR
- Variation exists but was not sampled

**This is the correct assessment.**

## Budget Decision Framework

### Option 1: Keep Phase-3 Budget (Recommended)

```
MAX_TEST_CASES = 5
TIME_BUDGET = 60 seconds
```

**Rationale:**
1. **Direct comparability:** Formal study data directly extends Phase-3 observations
2. **Validated feasibility:** Phase-3 demonstrated these budgets produce measurable, valid results
3. **Faster iteration:** Shorter runs allow faster campaign completion
4. **Sufficient for initial estimate:** If variation exists, N=30 may reveal it even at this budget
5. **Conservative approach:** Start with known-working budget; increase in follow-up if needed

**Risk:**
- If true variation exists at longer budgets, this budget may miss it (Type II error)
- Floor effect: if metric truly saturates at 1, no budget increase will help

### Option 2: Increase Budget Moderately

```
MAX_TEST_CASES = 10-20
TIME_BUDGET = 120-300 seconds
```

**Rationale:**
1. Provides more opportunity for variation to emerge
2. Tests whether `security_state_new_total` increases beyond 1
3. Balances exploration vs execution time

**Risk:**
- **Breaks Phase-3 comparability:** Cannot pool Phase-3 and formal study data
- Longer runs increase campaign wall-clock time
- If metric saturates early, extra budget provides no information

### Option 3: Budget Pilot Before Formal Study

**Procedure:**
1. Run small pilot (e.g., 3 seeds) at multiple budget levels (5, 10, 20, 50 testcases)
2. Observe whether `security_state_new_total` increases with budget
3. Choose budget for formal study based on pilot saturation curve

**Risk:**
- Delays formal study
- Adds operational complexity
- Pilot itself does not answer AE-vs-SE question

## Reconciled Recommendation

**Recommended: Keep Phase-3 Budget (Option 1)**

```
D9_MAX_TEST_CASES = 5
D9_TIME_BUDGET = 60 seconds
```

**Justification:**

1. **Phase-3 evidence is insufficient** to determine saturation vs adequate sampling
2. **Direct comparability** with validated Phase-3 pilot is valuable
3. **Conservative approach:** Start with known-working budget
4. **N=30 may reveal variation** even at this budget if it exists
5. **Follow-up studies** can explore longer budgets if initial results suggest floor effects

**Acknowledgment:**

This budget may be too small to detect differences if:
- True variation emerges only at longer horizons
- Metric has higher ceiling that requires more exploration

However, without evidence of saturation vs adequacy, maintaining Phase-3 continuity is the safer choice.

## Reconciled Status

```
PHASE3_BUDGET_SIGNAL_SATURATION_STATUS = INSUFFICIENT_EVIDENCE_TO_DETERMINE
PHASE3_OBSERVED_CONSISTENCY = All 10 runs observed security_state_new_total=1
VARIATION_AT_LONGER_BUDGETS = UNKNOWN
SATURATION_HYPOTHESIS = UNTESTED

RECOMMENDED_BUDGET_DECISION = Keep Phase-3 values (MAX_TEST_CASES=5, TIME=60s)
RATIONALE = Direct comparability, validated feasibility, insufficient evidence to justify change
ACKNOWLEDGED_RISK = May miss variation that emerges only at longer budgets
```

## Human Decision Required

```
D9_MAX_TEST_CASES = <integer>  (recommended: 5)
D9_TIME_BUDGET = <integer seconds>  (recommended: 60)

IF deviating from Phase-3 budget:
  JUSTIFICATION = <why increase is scientifically justified>
  PHASE3_COMPARABILITY_IMPACT = <acknowledge loss of direct comparability>
```

## Notes

- Budget increase can be justified in follow-up studies if initial results suggest floor effects
- No budget pilot is performed in this task (would delay formal study)
- Decision should balance exploration vs Phase-3 continuity vs operational feasibility
