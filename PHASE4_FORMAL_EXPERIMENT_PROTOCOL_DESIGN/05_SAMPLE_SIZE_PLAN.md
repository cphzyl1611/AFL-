# Sample Size Plan

## Constraint: Phase-3 Pilot Observations

**Phase-3 Primary Endpoint Results:**

- N = 5 paired blocks
- Observed paired differences: Δᵢ = [0, 0, 0, 0, 0]
- Sample mean: 0
- Sample variance: 0
- Sample standard deviation: 0

**Implication:**

The Phase-3 pilot cannot provide a reliable variance estimate for conventional power analysis. Using variance = 0 would imply infinite power, which is not scientifically justified.

**What Phase-3 Does NOT Support:**

- Conventional power calculation using observed pilot variance
- Effect-size estimation from pilot data
- Claims that "no effect exists" based on five zeros

**What Phase-3 Does Support:**

- Engineering validation of the paired experimental protocol
- Confirmation that both backends can produce valid runs
- Evidence that the primary endpoint is measurable and well-defined
- Baseline for qualitative protocol refinement

## Sample Size Determination Options

### Option A: Minimum Practically Important Difference (MPID)

**Approach:**

Define a minimum paired difference that would be scientifically or practically meaningful, then choose N to detect that difference with specified power and significance level.

**Requirements:**

- Human-specified MPID: e.g., "detecting a mean paired difference of δ = 1.0 security_state_new_total event per run is meaningful"
- Variance assumption: must come from external knowledge, simulation, or conservative worst-case reasoning (not from Phase-3 pilot alone)
- Conventional parameters: α = 0.05, power = 0.80 (or other preregistered values)

**Example (Illustrative Only):**

If:
- MPID = δ = 1.0
- Assumed σ_Δ = 2.0 (standard deviation of paired differences, from external reasoning)
- α = 0.05 (two-sided)
- Power = 0.80

Then a paired t-test sample size formula gives approximately:

```
N ≈ (z_α/2 + z_β)² × (σ_Δ / δ)²
N ≈ (1.96 + 0.84)² × (2.0 / 1.0)²
N ≈ 7.84 × 4.0
N ≈ 31.4 → N = 32 paired blocks
```

**Human Decisions Required:**

```
H1_MPID: What is the minimum practically important paired difference δ?
H2_VAR: What variance assumption σ_Δ² is justified?
H3_POWER: What significance level α and power are appropriate?
```

**Advantages:**

- Standard approach for confirmatory studies
- Clear interpretation of Type I and Type II error rates
- Widely accepted in scientific literature

**Disadvantages:**

- MPID is subjective and domain-specific
- Variance assumption may be poorly calibrated
- Requires human judgment calls that affect N substantially

---

### Option B: Precision-Based Design

**Approach:**

Choose N to achieve a target confidence interval width for the paired mean difference, regardless of hypothesis testing.

**Requirements:**

- Target maximum CI width: e.g., "95% CI width no wider than W"
- Variance assumption: must come from external knowledge or conservative reasoning

**Example (Illustrative Only):**

If:
- Target 95% CI width: W = 1.0
- Assumed σ_Δ = 2.0
- 95% CI: mean ± t_{N-1, 0.025} × (σ_Δ / √N)
- CI width = 2 × t × (σ_Δ / √N)

Solving for N when t ≈ 2 (approximation for moderate N):

```
1.0 = 2 × 2 × (2.0 / √N)
√N = 8
N = 64 paired blocks
```

**Human Decisions Required:**

```
H1_PREC: What is the target maximum 95% CI width?
H2_VAR: What variance assumption σ_Δ² is justified?
```

**Advantages:**

- Focuses on estimation precision rather than hypothesis testing
- Interpretable: "we want to estimate the paired difference within ± X units"
- Avoids the need to specify MPID

**Disadvantages:**

- Still requires variance assumption
- May produce larger N than power-based designs if high precision is desired
- Does not directly address Type I/II error rates

---

### Option C: Blinded Variance Re-estimation

**Approach:**

Run an initial blinded stage (e.g., N₁ = 10-20 paired blocks) without analyzing model labels, estimate the variance of paired differences, then re-estimate the required total N and continue to that target.

**Requirements:**

- Preregistered N₁ (initial stage size)
- Preregistered re-estimation rule (how to compute N₂ from observed variance)
- Blinding: the variance estimation stage analyzes |Δᵢ| or Δᵢ² without looking at which model has higher/lower values
- Preregistered maximum N_max (cap on total sample size)

**Example Procedure:**

```
Stage 1 (Blinded):
  - Run N₁ = 15 paired blocks
  - Compute s_Δ² (sample variance of paired differences)
  - Do NOT analyze which model is ahead
  - Re-estimate N₂ using s_Δ² and preregistered MPID/power

Stage 2 (Completion):
  - Run additional (N₂ - N₁) paired blocks if N₂ > N₁
  - If N₂ > N_max, stop at N_max
  - Analyze all data together

Final Analysis:
  - All N₂ (or N_max) paired blocks included
  - No peeking at model labels during re-estimation
```

**Human Decisions Required:**

```
H1_STAGE1: What is N₁ (initial blinded stage size)?
H2_MPID: What MPID/power parameters guide re-estimation?
H3_MAX: What is N_max (maximum allowed total N)?
```

**Advantages:**

- Uses real data to calibrate variance
- Maintains Type I error control if blinding is strict
- Adaptive without being opportunistic

**Disadvantages:**

- More complex protocol
- Requires strict blinding discipline
- May still hit N_max without sufficient power if variance is large

---

### Option D: Fixed Pragmatic N

**Approach:**

Choose a fixed N based on resource constraints, logistical feasibility, and qualitative judgment rather than formal power calculation.

**Requirements:**

- Transparent justification for the chosen N
- Acknowledgment that the study may be underpowered for small effects
- Emphasis on estimation and confidence intervals rather than hypothesis testing

**Example Rationale:**

"We choose N = 30 paired blocks because:
- It represents a 6× increase over the Phase-3 pilot (N = 5)
- It is feasible within project resource constraints
- It provides a reasonable basis for initial estimation
- We will report confidence intervals and treat results as exploratory if power is insufficient"

**Human Decisions Required:**

```
H1_FIXED_N: What fixed N is feasible and reasonable?
```

**Advantages:**

- Simple, transparent
- Avoids unjustified variance/MPID assumptions
- Focuses on feasibility

**Disadvantages:**

- No formal power guarantees
- May produce inconclusive results if N is too small
- Requires careful interpretation to avoid over-claiming

---

## Comparison and Recommendation

| Option | Pros | Cons | Suitability |
|--------|------|------|-------------|
| A: MPID + Power | Standard, interpretable | Needs MPID + variance assumption | Best if MPID and variance can be justified |
| B: Precision-based | Focuses on estimation | Needs variance assumption | Good if estimation precision is the priority |
| C: Blinded re-estimation | Data-adaptive, Type I control | Complex, needs strict blinding | Good if pilot variance is truly unknown |
| D: Fixed pragmatic N | Simple, honest | No power guarantees | Acceptable if resources are constrained |

**Recommendation:**

**If a defensible MPID and variance assumption can be obtained through human expert judgment or external data:**

→ Use **Option A (MPID + Power)** for a confirmatory study.

**If variance is truly unknown and resources allow a two-stage design:**

→ Use **Option C (Blinded re-estimation)** to let real data calibrate N.

**If neither MPID nor variance can be justified, but some larger N is feasible:**

→ Use **Option D (Fixed pragmatic N)** and treat the study as exploratory/estimation-focused.

**Current Status:**

```
FORMAL_SAMPLE_SIZE_STATUS = REQUIRES_HUMAN_CHOICE_OF_MPID_OR_PRECISION_TARGET
```

Without human decisions on MPID, variance assumption, or precision target, N cannot be formally computed.

## Human Decisions Summary

To finalize the sample size plan, the following decisions are required:

```
H1 = What sample-size method (A, B, C, or D)?
H2 = If A or B: What is the MPID or precision target?
H3 = If A, B, or C: What variance assumption is justified?
H4 = If A: What α and power?
H5 = If B: What target CI width?
H6 = If C: What N₁, N_max, and re-estimation rule?
H7 = If D: What fixed N is feasible and reasonable?
```

## Notes

- The Phase-3 pilot variance of zero does not support extrapolation to a formal power calculation.
- All variance assumptions must be justified independently of Phase-3 observed variance.
- The chosen method must be preregistered before execution.
- No interim analysis of model labels is permitted outside a preregistered blinded re-estimation stage.
