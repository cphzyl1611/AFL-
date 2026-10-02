# Analysis Limitations

## 1. Zero Variance Limitation

**Finding:** All 28 paired differences equal zero (SD = 0)

**Impact:** Standard statistical inference methods (parametric and nonparametric) are not applicable because there is no variance to test against. This includes:
- Paired t-test (requires variance for t-statistic)
- Wilcoxon signed-rank test (requires tied ranks, all ranks are tied at 0)
- Permutation tests (all permutations yield identical test statistics)
- Bootstrap confidence intervals (resampling produces identical values)

**Interpretation:** This is a factual observation, not a statistical limitation per se. The zero variance indicates complete consistency across all 28 paired observations.

## 2. No Frozen Confirmatory Method

**Finding:** Multiple test options listed in frozen design authority but no specific method frozen; multiple human decisions remain UNDECIDED

**Impact:** Confirmatory statistical claims (significance, equivalence, noninferiority, superiority) are not supported. Only factual descriptive observations can be reported.

**Context:** The frozen design (PHASE4_FORMAL_EXPERIMENT_PROTOCOL_DESIGN/10_HUMAN_DECISIONS_REQUIRED.md) explicitly marks decisions as UNDECIDED including:
- D1: Sample size method
- D2: Minimum practically important difference (MPID)
- D3: Variance assumption
- D10: Inference method selection
- D14: Secondary endpoint confirmatory status
- D15: Multiplicity adjustment

## 3. Experimental Conditions Scope

**Conditions:** Results limited to specific experimental parameters:
- max_test_cases = 5 (5 valid test cases per run)
- time_budget = 60s (60-second fuzzing runs)
- scorer_ready_timeout = 10s (validity scorer timeout)

**Impact:** Generalization beyond these conditions requires additional experiments. Different resource budgets, timeout values, or target configurations may yield different results.

**Note:** These parameters were frozen in the protocol design and applied uniformly across all runs.

## 4. Single Endpoint Observation (No Distribution Estimation)

**Finding:** Each backend discovered exactly 1 unique security state per block; all observations at the same value

**Impact:**
- Cannot characterize endpoint distribution shape (normal, skewed, discrete, etc.)
- Cannot estimate effect size precision (no variance for confidence intervals)
- Cannot assess outliers or influential observations (all observations identical)
- Cannot validate parametric test assumptions (normality, equal variance)

**Context:** This reflects actual experimental outcomes under the specified conditions, not a methodological limitation.

## 5. Carry-Forward Exclusions (Blocks 1-2)

**Finding:** 2 of 30 execution-valid pairs excluded from primary analysis population

**Exclusion Reasons:**
- Block 1: Evidence carried forward from prior R2 execution; no primary endpoint data in current R2 execution freeze
- Block 2: SE primary endpoint data missing; SE run carried forward from prior execution

**Impact:**
- Analysis population reduced from 30 to 28 pairs
- Primary analysis does not include Block 1 or Block 2 observations
- Cannot assess whether excluded blocks would have shown different patterns

**Authorization:** Both exclusions documented and authorized by explicit special adjudication (Block 1) and frozen PAIR_EXCLUSION_RULE (Block 2)

**Clarification:** This does not indicate experimental failure. All 30 pairs executed successfully and passed validity gates. The exclusions are due to documented special handling (carry-forward).

## 6. Predecessor Defect Impact

**Finding:** Original analysis extracted wrong primary endpoint field (body_rule_pass instead of security_state_new_total)

**Impact:**
- Analysis timeline disrupted requiring successor analysis
- Predecessor results (AE=5, SE=5) not usable for primary endpoint reporting
- Additional reconciliation and verification steps required
- Increased documentation burden to track defect and correction

**Mitigation:** Predecessor package preserved as defective historical evidence; corrected extraction independently verified; all reconciliation steps documented

## 7. Single-Study Design (No Replication)

**Finding:** Results based on one formal experiment (R2) with 28 analysis-eligible pairs

**Impact:**
- No assessment of cross-study consistency or reproducibility
- Cannot estimate between-study variability
- Single realization of experimental conditions

**Context:** This is inherent to the single-study design; replication would require additional formal experiments with independent execution

## 8. Field Confusion Risk in Interpretation

**Finding:** Multiple fields with similar names in evidence files:
- security_state_new_total (primary confirmatory endpoint)
- security_state_total (exploratory secondary endpoint)
- body_rule_pass (exploratory secondary endpoint)

**Impact:** Readers must carefully distinguish:
- **security_state_new_total** = count of new security state transitions (COVERAGE metric, primary endpoint)
- **security_state_total** = absolute coverage level including initial corpus (EXPLORATORY)
- **body_rule_pass** = count of valid executions passing validation (EXECUTION/VALIDITY metric, exploratory)

The predecessor defect demonstrates the consequence of field confusion.

## 9. Exploratory Endpoint Role Boundaries

**Finding:** Multiple exploratory secondary endpoints available but not promoted to confirmatory

**Impact:**
- Exploratory findings (http_status_distribution, trace_invocation_count, body_rule_pass, body_rule_reject) remain descriptive only
- Cannot make confirmatory claims about secondary endpoints
- Multiplicity adjustment not applied (not needed for exploratory descriptives)

**Authorization:** Consistent with frozen design recommendation (D14: keep all secondary endpoints exploratory)

## 10. Discrete Count Endpoint Nature

**Finding:** Primary endpoint is a discrete count (integer values: 0, 1, 2, ...)

**Impact:**
- Cannot be fractional or negative
- Small-count distributions may not approximate normal distribution
- Ties are common in discrete data (observed here: all values = 1)

**Context:** This is inherent to the endpoint definition (count of coverage transitions), not a limitation

---

## Summary

The primary limitations affecting interpretation are:

1. **Zero variance** precluding standard statistical inference
2. **No frozen confirmatory method** limiting statistical claims to factual observations
3. **Single-value observation** preventing distribution characterization

The other limitations provide context about scope, exclusions, and interpretation boundaries but do not invalidate the corrected primary endpoint findings.

