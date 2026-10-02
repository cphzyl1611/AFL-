# Sample Size Method Reconciliation

## Issue 1: Method Label Verification

**Original Phase-4 Protocol Design (05_SAMPLE_SIZE_PLAN.md):**

The frozen protocol document defines exactly four methods:

- **Option A:** MPID + Power (conventional power analysis)
- **Option B:** Precision-based (target CI width)
- **Option C:** Blinded variance re-estimation (two-stage adaptive)
- **Option D:** Fixed pragmatic N (resource-constrained)

**Human Decision Matrix Summary Statement:**

The prior human decision summary reported:

```
recommended = D (Fixed pragmatic N)
fallback = C (Blinded variance re-estimation)
```

**Reconciliation Verdict:**

**NO MISMATCH DETECTED.** The labels A/B/C/D are consistent across:
- Protocol design document
- Decision matrix
- Human approval template

The prior summary correctly mapped:
- Method D = Fixed pragmatic N ✓
- Method C = Blinded variance re-estimation ✓

## Issue 2: N=30 Statistical Derivation Status

**Original Recommendation:**

```
D7_FIXED_N = 30 (recommended: 30)
```

**Justification Provided:**

1. Represents 6× increase over Phase-3 pilot (N=5)
2. Conventional threshold for approximate CLT applicability
3. Balances precision with feasibility
4. Provides reasonable initial estimate for future studies

**Question:** Is N=30 statistically derived or pragmatically chosen?

**Analysis:**

N=30 is **NOT** statistically derived in the formal sense. It does not result from:
- Power calculation with justified MPID and variance
- Precision-based calculation with target CI width
- Blinded re-estimation from pilot data

N=30 **IS** pragmatically chosen based on:
- **Conventional rule of thumb:** N≥30 often cited as threshold for CLT applicability
- **Feasibility multiplier:** 6× Phase-3 pilot size
- **Resource constraints:** Balances information gain vs execution cost
- **Uncertainty acknowledgment:** Study may be underpowered for small effects

**Reconciliation Verdict:**

```
N30_STATISTICALLY_DERIVED = NO
N30_JUSTIFICATION_TYPE = PRAGMATIC_FEASIBILITY_WITH_CONVENTIONAL_HEURISTIC
```

N=30 remains a reasonable recommendation but must be framed as:
- **Human pragmatic choice**, not statistical calculation
- Subject to conventional heuristic reasoning
- Acknowledging potential low power for small effect sizes

## Issue 3: Recommended Method Re-evaluation

**Phase-3 Constraint:**

- Paired differences: Δᵢ = [0, 0, 0, 0, 0]
- Sample variance: 0
- No external variance data available
- No established MPID in domain

**Method Evaluation:**

| Method | Requires | Phase-3 Supports? | Feasibility |
|--------|----------|-------------------|-------------|
| **A (MPID + Power)** | Justified MPID + variance assumption | NO | Requires unjustified assumptions |
| **B (Precision-based)** | Justified variance assumption | NO | Requires unjustified variance |
| **C (Blinded re-estimation)** | Two-stage infrastructure, N₁, N_max | YES (protocol-wise) | Complex, adds operational overhead |
| **D (Fixed pragmatic N)** | Feasibility justification only | YES | Simple, transparent about uncertainty |

**Re-evaluation Given Constraints:**

**Primary Recommendation: Method D (Fixed pragmatic N)**

**Rationale:**
1. Phase-3 variance = 0 provides no empirical basis for Methods A or B
2. No external data exists to justify variance assumption independently
3. MPID is subjective; no domain consensus on meaningful difference threshold
4. Method D is transparent: acknowledges uncertainty, emphasizes estimation over hypothesis testing
5. Aligns with exploratory nature of initial formal comparison
6. Simpler operational execution than Method C

**Fallback Recommendation: Method C (Blinded re-estimation)**

**Rationale:**
1. If variance uncertainty is the dominant concern and resources allow two stages
2. Uses real data to calibrate N₂ from observed variance in Stage 1
3. Maintains Type I error control if blinding is strict
4. More operationally complex but data-adaptive

**Not Recommended: Methods A or B**

Both require variance assumptions that cannot be justified from Phase-3 pilot or external data.

## Reconciled Recommendation

```
RECOMMENDED_SAMPLE_SIZE_METHOD = D (Fixed pragmatic N)
FALLBACK_SAMPLE_SIZE_METHOD = C (Blinded variance re-estimation)
NOT_RECOMMENDED = [A (MPID + Power), B (Precision-based)]

IF_METHOD_D_CHOSEN:
  RECOMMENDED_N = 30
  N_JUSTIFICATION = Pragmatic feasibility (6× Phase-3, conventional CLT heuristic)
  N_STATISTICALLY_DERIVED = NO
  POWER_GUARANTEE = NONE (study may be underpowered for small effects)
  ANALYSIS_EMPHASIS = Estimation and confidence intervals

IF_METHOD_C_CHOSEN:
  RECOMMENDED_N1 = 15
  RECOMMENDED_NMAX = 50
  RE_ESTIMATION_RULE = Preregistered MPID/power formula applied to observed Stage 1 variance
  BLINDING_REQUIREMENT = No model label analysis until Stage 2 complete
```

## Human Decision Required

```
D1_SAMPLE_SIZE_METHOD = [A | B | C | D]

IF D1 = D:
  D7_FIXED_N = <integer>  (recommended: 30, pragmatic not statistical)

IF D1 = C:
  D6_BLINDED_N1 = <integer>  (recommended: 15)
  D6_BLINDED_NMAX = <integer>  (recommended: 50)
  D6_RE_ESTIMATION_RULE = <formula using observed s_Δ²>
```

## Notes

- N=30 recommendation stands but is correctly framed as pragmatic choice
- Method D remains preferred given Phase-3 constraint of zero observed variance
- Any formal power claim would require unjustified assumptions
- Study emphasis: estimation and confidence intervals, not hypothesis testing alone
