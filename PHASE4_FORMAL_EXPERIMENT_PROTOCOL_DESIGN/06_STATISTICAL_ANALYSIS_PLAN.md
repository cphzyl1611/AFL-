# Statistical Analysis Plan

## Primary Endpoint Analysis

**Primary Endpoint:** `security_state_new_total` (paired differences)

**Data Structure:**

- N paired observations: (AE_i, SE_i) for i = 1, ..., N
- Paired differences: Δᵢ = SE_i - AE_i
- Primary estimand: θ = E[Δᵢ]

## Analysis Challenges

**Data Characteristics:**

- Primary endpoint is a non-negative count (≥ 0)
- Phase-3 pilot showed many ties (all five pairs had Δᵢ = 0)
- Distribution of Δᵢ is likely discrete, bounded below at some negative value and above at some positive value
- May have substantial probability mass at zero

**Why Standard Paired t-Test May Be Inappropriate:**

- Assumes continuous, approximately normal distribution of differences
- With many ties at zero, normality assumption is violated
- Small sample size makes asymptotic approximations unreliable
- Ties reduce power of rank-based methods (sign test, Wilcoxon signed-rank)

## Recommended Analysis Strategy

### 1. Descriptive Statistics (Always Report)

For all N valid paired blocks, report:

**Paired Differences:**

- Full list of observed Δᵢ values
- Sample mean: Δ̄ = (1/N) Σ Δᵢ
- Sample median
- Sample standard deviation: s_Δ
- Minimum, maximum
- Proportion of ties (Δᵢ = 0)
- Proportion positive (Δᵢ > 0)
- Proportion negative (Δᵢ < 0)

**Raw Values:**

- AE values: mean, median, range
- SE values: mean, median, range

**Visual Summary:**

- Histogram or density plot of Δᵢ
- Scatter plot: AE_i vs SE_i with diagonal reference line

### 2. Point Estimate

**Primary Point Estimate:**

```
Δ̄ = (1/N) Σ Δᵢ
```

This is the sample mean paired difference, an unbiased estimate of θ under random sampling.

**Alternative Point Estimates (Exploratory):**

- Median paired difference (robust to outliers)
- Trimmed mean (if outliers are present)

Report the sample mean as primary; others as sensitivity checks.

### 3. Uncertainty Quantification

**Bootstrap Confidence Interval (Recommended):**

Given the discrete, potentially non-normal distribution and presence of ties, a **percentile bootstrap CI** is more appropriate than t-based or normal approximations.

**Procedure:**

```
For b = 1 to B (e.g., B = 10,000):
  1. Resample N paired differences with replacement: Δ*_b = {Δ*_i}
  2. Compute Δ̄*_b = mean(Δ*_b)

95% CI = [percentile_2.5(Δ̄*), percentile_97.5(Δ̄*)]
```

**Advantages:**

- Makes no distributional assumptions beyond exchangeability
- Handles ties naturally
- Widely accepted for small-sample estimation

**Assumptions:**

- Paired blocks are exchangeable (reasonable if seeds are randomly generated)
- Bootstrap resampling preserves the dependence structure (valid for paired data)

### 4. Hypothesis Testing (If Preregistered)

**Null Hypothesis:**

```
H₀: θ = 0  (no mean difference in security_state_new_total between SE and AE)
```

**Test Options:**

#### Option T1: Paired t-Test (Classical, But Potentially Invalid)

- Assumes normality of Δᵢ
- With ties and small N, this assumption is questionable
- **Use only if N is large enough for CLT to apply (e.g., N ≥ 30) and visual inspection supports approximate normality**

#### Option T2: Wilcoxon Signed-Rank Test

- Nonparametric, robust to non-normality
- **Problem:** Many ties at zero reduce power substantially
- The test discards all zero differences, so effective N may be much smaller than nominal N

#### Option T3: Sign Test

- Nonparametric, simple
- Tests whether median(Δᵢ) = 0
- **Problem:** Also loses power with many ties
- Only counts sign of non-zero differences

#### Option T4: Permutation Test (Recommended)

- Nonparametric, exact (for small N)
- Tests H₀: distribution of Δᵢ is symmetric around zero

**Procedure:**

```
Observed test statistic: T_obs = Δ̄

For each of 2^N possible sign flips of Δᵢ:
  1. Flip signs: Δ_perm = ±Δᵢ
  2. Compute T_perm = mean(Δ_perm)

Two-sided p-value = P(|T_perm| ≥ |T_obs| | H₀)
```

**Advantages:**

- Exact p-value for small N
- Handles ties naturally (a tie contributes zero to both original and permuted statistics)
- Does not assume normality

**Disadvantages:**

- Computationally intensive for large N (use Monte Carlo approximation if N > 20)
- Assumes exchangeability under the null

#### Option T5: Bootstrap Hypothesis Test

- Construct bootstrap CI for θ
- Reject H₀: θ = 0 if 0 is not in the CI
- This is equivalent to a two-sided test at the corresponding α level

**Recommendation:**

**For small N (e.g., N ≤ 30):**

→ Use **permutation test (T4)** or **bootstrap CI (T5)** as the primary inferential method.

**For larger N (e.g., N > 30) and if Δᵢ appears approximately normal:**

→ Paired t-test (T1) may be acceptable; report it alongside bootstrap CI for robustness.

**Report sign test (T3) and Wilcoxon (T2) as sensitivity checks**, but acknowledge their limitations with ties.

### 5. Equivalence and Non-Inferiority Testing

**Important:**

- Failure to reject H₀: θ = 0 does NOT imply equivalence
- To claim equivalence, a separate equivalence testing framework is required

**If Equivalence is a Study Objective:**

Must preregister:

- **Equivalence margin:** ±δ_eq (e.g., ±0.5 security_state_new_total events)
- **Equivalence hypotheses:**
  ```
  H₀: |θ| ≥ δ_eq
  H₁: |θ| < δ_eq
  ```
- **Two one-sided tests (TOST)** procedure or equivalence CI

Without a preregistered equivalence margin, no equivalence claim can be made.

### 6. Secondary Endpoint Analysis

**Secondary endpoints** (e.g., `security_state_total`, `body_score_pass`, `body_score_reject`) are reported **descriptively** unless explicitly promoted to confirmatory status before execution.

**Descriptive Reporting:**

- Same paired-difference structure as primary endpoint
- Point estimates and CIs
- No hypothesis tests unless preregistered

**Exploratory Objectives:**

- Understand AE vs SE accept/reject behavior patterns
- Assess whether observed differences in primary endpoint are consistent with secondary metrics

### 7. Handling Ties and Zero Inflation

**If many Δᵢ = 0:**

- Report the proportion of ties explicitly
- Discuss whether ties reflect:
  - True equivalence for those seeds
  - Insensitivity of the endpoint (e.g., both models rarely trigger new coverage)
  - Statistical censoring or floor effects

**Zero-Inflated Models (Advanced, Optional):**

If a substantial proportion of Δᵢ = 0 and this is scientifically meaningful, consider:

- Zero-inflated count regression models
- Hurdle models

These are exploratory and require more complex assumptions.

### 8. Sensitivity Analyses

Report the following sensitivity checks:

**S1: Exclude Outliers (if any)**

- Re-analyze after removing extreme paired differences (if scientifically justified)

**S2: Stratified Analysis (if applicable)**

- Stratify by execution order (if randomized)
- Stratify by other covariates (e.g., initial corpus size) if recorded

**S3: Alternative Estimators**

- Report median paired difference alongside mean
- Compare bootstrap CI with t-based CI (if N is large enough)

**S4: Include Failed Runs (Worst-Case Imputation)**

- As a sensitivity check, impute failed runs with worst-case values and re-analyze
- This is exploratory and should not replace the primary analysis on valid runs only

## Analysis Software and Reproducibility

**Preregistered Analysis Script:**

The protocol must include a reference analysis script (e.g., Python or R) that:

- Reads the frozen run manifest
- Computes all descriptive statistics
- Generates bootstrap CIs
- Performs the preregistered hypothesis test (if any)
- Produces tables and figures

**Script Freeze:**

The analysis script must be frozen before the first real run (or before any unblinding if a blinded re-estimation stage is used).

**Reproducibility:**

- All analysis code committed to git with SHA
- All random seeds for bootstrap/permutation recorded
- All intermediate results saved

## Multiple Comparisons

**Single Primary Comparison:**

The protocol specifies exactly one primary confirmatory comparison:

```
SE vs AE on security_state_new_total
```

**No Multiplicity Adjustment Required for Primary Analysis:**

A single preregistered hypothesis test does not require multiplicity adjustment.

**Secondary/Exploratory Comparisons:**

- Reported descriptively without p-values, OR
- If p-values are reported, they are labeled exploratory and not used for confirmatory claims

**If Multiple Confirmatory Comparisons Are Desired:**

Must preregister:

- Which comparisons are confirmatory
- Multiplicity adjustment method (e.g., Bonferroni, Holm, Benjamini-Hochberg)

## Reporting Standards

The final statistical report must include:

- All N planned paired blocks (valid and excluded)
- Exclusion reasons for failed blocks
- Descriptive statistics for Δᵢ, AE_i, SE_i
- Primary point estimate with CI
- Hypothesis test results (if preregistered)
- All sensitivity analyses
- Visual summaries (plots)
- Reproducible analysis code and seed

## Human Decisions Required

```
H1_TEST: Should a hypothesis test be performed, or is estimation-only sufficient?
H2_TEST_METHOD: If testing, which test (permutation, bootstrap CI, t-test, other)?
H3_EQUIV: Is equivalence testing an objective? If yes, what is the equivalence margin?
H4_SECONDARY: Are any secondary endpoints confirmatory, or all exploratory?
H5_MULTIPLICITY: If multiple confirmatory tests, what adjustment method?
```

## Recommendation Summary

**Recommended Primary Analysis:**

1. **Point estimate:** Sample mean paired difference Δ̄
2. **Uncertainty:** 95% percentile bootstrap CI (B = 10,000)
3. **Hypothesis test (if desired):** Permutation test or declare 0 not in CI
4. **Secondary endpoints:** Descriptive only, no confirmatory tests
5. **Sensitivity:** Report median, exclude outliers, stratify by order if randomized

**Analysis Tier:**

- Treat as **estimation-focused** rather than pure hypothesis testing
- Report CIs prominently
- Avoid over-interpreting non-significant p-values as equivalence

This approach is robust to the data characteristics (ties, small N, discrete counts) and aligns with modern statistical best practices.

## Notes

- The analysis plan must be frozen before execution
- No post-hoc switching of analysis methods based on observed data
- All deviations from the preregistered plan must be justified and reported transparently
- Exploratory analyses are permitted but clearly labeled as such
