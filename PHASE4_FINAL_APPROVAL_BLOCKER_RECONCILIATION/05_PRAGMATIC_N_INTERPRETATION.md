# Pragmatic N=30 Interpretation

## BLOCKER 5: N=30 Inferential Status

**Issue:** Clarify that N=30 is pragmatically chosen, not power/precision-justified.

**Prior Reconciliation (CORRECT):**

```
N30_STATISTICALLY_DERIVED = NO
```

This is accurate and must be preserved.

## N=30 Role Classification

**N=30 is an OPERATIONAL/FEASIBILITY-DRIVEN choice**, not a statistical derivation.

**Justification Basis:**
1. **Feasibility multiplier:** 6× Phase-3 pilot size (N=5 → N=30)
2. **Resource constraints:** Balances information gain vs execution cost (60 runs total: 30 AE + 30 SE)
3. **Conventional heuristic reference:** N≥30 often cited for CLT applicability (descriptive, not prescriptive)

**What N=30 is NOT:**
- NOT derived from power calculation (Phase-3 variance=0 precludes this)
- NOT derived from precision-based calculation (no justified variance assumption)
- NOT statistically guaranteed to provide adequate power or precision

## Inferential Limitations

**Power Justification:**

```
N30_POWER_JUSTIFIED = NO
```

**Why:** Power calculation requires:
- Justified minimum practically important difference (MPID)
- Justified variance assumption
- Neither is available from Phase-3 pilot or external data

**Consequence:** Study may be underpowered for small effect sizes.

**Precision Justification:**

```
N30_PRECISION_JUSTIFIED = NO
```

**Why:** Precision-based calculation requires:
- Target confidence interval width
- Justified variance assumption
- Neither is available

**Consequence:** Confidence interval width is unknown in advance; will be data-driven.

## CLT Heuristic Is NOT a Power Guarantee

**Conventional heuristic:** "N≥30 is sufficient for approximate normality of sample mean"

**Important clarifications:**
1. CLT asymptotic approximation improves with larger N
2. N=30 is a conventional rule of thumb, not a mathematical threshold
3. **CLT does NOT imply adequate power** for hypothesis testing
4. **CLT does NOT imply adequate precision** for estimation
5. CLT only addresses sampling distribution shape, not study power

**Correct framing:**

✓ "N=30 is conventionally cited as a threshold where CLT approximation becomes reasonable"

✗ "N=30 guarantees adequate power because of CLT"

## Human Acceptance Required

**Pragmatic N requires explicit human acceptance of inferential limitations:**

```
HUMAN_ACCEPTANCE_OF_PRAGMATIC_N_REQUIRED = YES
```

**Human reviewer must acknowledge:**
1. N=30 is chosen for feasibility, not statistical power
2. Study may be underpowered for small effects
3. Confidence intervals may be wide
4. Primary emphasis is on **estimation** (point estimate + CI), not hypothesis testing
5. Results may be inconclusive if true effect size is small relative to variance
6. Follow-up studies may be needed if initial results are underpowered

## Recommended Approval Language

**Human approval template must include:**

```
I acknowledge that N=30 is a pragmatic choice based on feasibility, not statistical derivation.

I understand:
- The study may be underpowered for small effect sizes
- Confidence intervals may be wide
- Power and precision are not guaranteed
- Primary emphasis is on estimation and confidence intervals
- Results should be interpreted as exploratory if inconclusive

I accept these limitations and approve N=30 as the fixed sample size.

[ ] APPROVED
```

## Corrected Status

```
N30_ROLE = OPERATIONAL_FEASIBILITY_DRIVEN
N30_POWER_JUSTIFIED = NO
N30_PRECISION_JUSTIFIED = NO
N30_CLT_HEURISTIC_REFERENCE = DESCRIPTIVE_ONLY (not prescriptive)
HUMAN_ACCEPTANCE_OF_PRAGMATIC_N_REQUIRED = YES

STUDY_EMPHASIS = ESTIMATION_AND_CONFIDENCE_INTERVALS
HYPOTHESIS_TESTING_SECONDARY = YES (permutation test if D12=yes, but emphasis on CI)
INCONCLUSIVE_RESULTS_POSSIBLE = YES (if true effect small relative to variance)
```

## Notes

- N=30 remains a reasonable pragmatic choice
- Human reviewers must explicitly accept inferential limitations
- Study should not be presented as adequately powered without justification
- Primary deliverable: point estimate and 95% confidence interval
- Hypothesis test (if performed) is supplementary, not primary
