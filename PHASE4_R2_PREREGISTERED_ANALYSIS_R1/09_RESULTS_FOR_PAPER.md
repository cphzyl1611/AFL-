# Phase 4 R2 Primary Endpoint Results

## Executive Summary

**Formal Experiment:** 30 valid paired blocks (AE vs SE backends)  
**Primary Analysis Population:** 28 analysis-eligible pairs (blocks 3-30)  
**Primary Endpoint (CORRECTED):** security_state_new_total  
**Observed Result:** Identical values across all 28 pairs (AE=1, SE=1, Δ=0)

---

## Background: Predecessor Analysis Defect

This is a **successor analysis** correcting a primary endpoint extraction defect in the predecessor package.

**Predecessor Package:** PHASE4_R2_PREREGISTERED_ANALYSIS  
**Defect:** Extracted `body_rule_pass` (valid execution count) instead of frozen primary endpoint `security_state_new_total` (new security state coverage count)  
**Predecessor Values:** AE=5, SE=5, Δ=0 (for body_rule_pass)  
**Corrected Values:** AE=1, SE=1, Δ=0 (for security_state_new_total)

The predecessor analysis package is preserved as defective historical evidence and was not modified.

---

## Primary Endpoint: security_state_new_total

**Definition:** Number of testcases that triggered new security_state coverage transitions during the fuzzing run

**Source Authority:** PHASE4_FORMAL_EXPERIMENT_PROTOCOL_DESIGN/02_ENDPOINTS.json

**Extraction Method:**
- AE backend: Array length from `nv_state_db.json`
- SE backend: Count of `"new":1` entries in `nv_state_trace.jsonl`

**Primary Estimand:** θ = E[Δᵢ] where Δᵢ = SE_security_state_new_total_i - AE_security_state_new_total_i

---

## Analysis Population

**Execution-Valid Paired Blocks:** 30 (blocks 1-30)  
**Analysis-Eligible Pairs:** 28 (blocks 3-30)  
**Excluded Pairs:** 2 (blocks 1-2)

**Block 1 Exclusion:** Evidence carried forward from prior R2 execution; no primary endpoint data in current R2 execution freeze (authorized by explicit special adjudication)

**Block 2 Exclusion:** SE primary endpoint data missing; SE run carried forward from prior execution, not rerun in R2 (authorized by frozen PAIR_EXCLUSION_RULE requiring complete paired data)

**Important:** All 30 pairs executed successfully and passed validity gates. The 2-pair exclusion is due to documented special handling (carry-forward), not experimental failure.

---

## Primary Endpoint Results

### Corrected Primary Paired Data (security_state_new_total)

| Statistic | AE Backend | SE Backend | Paired Difference (SE - AE) |
|-----------|------------|------------|------------------------------|
| N | 28 | 28 | 28 |
| Mean | 1.0 | 1.0 | 0.0 |
| Median | 1.0 | 1.0 | 0.0 |
| SD | 0.0 | 0.0 | 0.0 |
| Min | 1 | 1 | 0 |
| Max | 1 | 1 | 0 |

### Paired Difference Distribution

- Δ > 0: 0 pairs (0%)
- Δ = 0: 28 pairs (100%)
- Δ < 0: 0 pairs (0%)

### Zero Variance Case

All 28 paired differences equal zero. Standard deviation is zero because there is no variance in the paired differences.

---

## Factual Observation

**Across the 28 analysis-eligible paired blocks, the observed primary endpoint security_state_new_total was identical for AE and SE in every pair.**

Both backends discovered exactly **1 unique security state** per block across all 28 complete paired blocks.

---

## Confirmatory Analysis Boundary

**Frozen Confirmatory Method:** NOT_FROZEN

The frozen design authority (PHASE4_FORMAL_EXPERIMENT_PROTOCOL_DESIGN/06_STATISTICAL_ANALYSIS_PLAN.md and 10_HUMAN_DECISIONS_REQUIRED.md) lists multiple test options (paired t-test, Wilcoxon, permutation, bootstrap) but does not freeze a specific confirmatory method. Multiple human decisions remain UNDECIDED including sample size method, MPID, variance assumption, and inference method.

**Confirmatory Analysis Executed:** NO

**Statistical Claims:**
- p-value: NOT COMPUTED
- Confidence interval: NOT COMPUTABLE (zero variance)
- Statistical significance: NO CLAIM (no frozen method and zero variance case)
- Equivalence: NO CLAIM (no frozen equivalence bounds)
- Noninferiority: NO CLAIM (no frozen noninferiority margin)
- Superiority: NO CLAIM (no frozen test and all deltas = 0)

**Note:** The zero-variance observation (all deltas = 0, SD = 0) is a factual finding, not a statistical inference. Standard hypothesis testing methods are not applicable because there is no variance to test against.

---

## Scientific Interpretation

### Primary Endpoint (security_state_new_total = 1)

**Finding:** Both AE and SE backends discovered exactly 1 unique security state per block across all 28 pairs.

**Interpretation:** The two backends achieved identical security state coverage exploration in every analyzed paired block. Under the experimental conditions (5 valid test cases per run, 60-second time budget, 10-second scorer timeout), neither backend discovered additional unique security states beyond the single state observed in each block.

**Context:** This is a coverage-related metric measuring new security state transitions discovered during fuzzing.

### Distinction from Predecessor Defect (body_rule_pass = 5)

**Predecessor Finding (DEFECTIVE):** Both backends achieved 5 valid executions per block.

**Distinction:** The predecessor defect reported execution success (body_rule_pass = count of valid executions passing body validation rules), not coverage effectiveness (security_state_new_total = count of new security states discovered).

- `body_rule_pass = 5`: Both backends successfully executed 5 valid test cases per run (execution/validity metric)
- `security_state_new_total = 1`: Both backends discovered 1 unique security state per run (coverage metric)

These are fundamentally different aspects of fuzzer behavior from different source files (nv_body_valid_stats.json vs nv_state_db.json/nv_state_trace.jsonl).

---

## Exploratory Secondary Endpoints

Exploratory secondary analyses are preserved from the frozen evidence package (PHASE4_FORMAL_EXECUTION_EVIDENCE_R2_FINAL/09_EXPLORATORY_SECONDARY_RAW_VALUES.json).

Frozen exploratory endpoints include:
- security_state_total (absolute coverage levels)
- body_rule_pass (valid execution count - correctly classified as exploratory)
- body_rule_reject (rejected execution count)
- http_status_distribution
- trace_invocation_count

**Note:** `body_rule_pass` is correctly classified as an EXPLORATORY secondary endpoint in the frozen design. The predecessor defect was incorrectly using it as the PRIMARY endpoint. It remains valid for exploratory/descriptive purposes.

No exploratory endpoints were promoted to confirmatory status. No new exploratory endpoints were added.

---

## Data Integrity

**Final Evidence Package:** PHASE4_FORMAL_EXECUTION_EVIDENCE_R2_FINAL  
**Evidence Commitment:** SHA256 = e1330de8d1effbe3daaeb1d7070403b6dacc82a49dfc438a31a8ed9029743486

**Predecessor Analysis Package:** PHASE4_R2_PREREGISTERED_ANALYSIS  
**Predecessor Commitment:** SHA256 = 9b5d90b7033d5a3d76c78599def8b9c31debdf88760f29ae3fb1d28d6c0e794b

**Modifications:**
- New experiments run: NO
- Raw evidence modified: NO
- Final evidence freeze modified: NO
- Predecessor analysis modified: NO
- Analysis population changed: NO
- Primary endpoint changed: NO (corrected extraction only)

---

## Limitations

1. **Zero Variance:** All paired differences equal zero, preventing variance-based statistical inference

2. **No Frozen Confirmatory Method:** Multiple test options listed in frozen design but no specific method frozen; confirmatory claims not supported

3. **Experimental Conditions:** Results limited to: max_test_cases=5, time_budget=60s, scorer_ready_timeout=10s

4. **Single Endpoint Observation:** Each backend discovered exactly 1 unique security state per block; no variance to characterize endpoint distribution or estimate effect size precision

5. **Carry-Forward Exclusions:** Blocks 1-2 excluded due to carry-forward preventing complete primary endpoint data collection (documented and authorized)

6. **Predecessor Defect Impact:** Original analysis timeline disrupted by extraction defect requiring successor analysis

---

## Successor Package Status

**Package:** PHASE4_R2_PREREGISTERED_ANALYSIS_R1  
**Type:** SUCCESSOR_CORRECTED_PRIMARY_ENDPOINT  
**Predecessor:** PHASE4_R2_PREREGISTERED_ANALYSIS (preserved as defective historical evidence)  
**Correction:** Primary endpoint extraction corrected from body_rule_pass to security_state_new_total  
**Reconciliation Report:** /tmp/phase4_r2_reconciliation_report.txt

---

## Next Steps

Results interpretation and scientific conclusions should be developed with awareness of:

1. The zero-variance finding limiting statistical inference methods
2. The distinction between coverage effectiveness (security_state_new_total) and execution success (body_rule_pass)
3. The absence of frozen confirmatory testing procedures
4. The experimental context (5 test cases, 60-second runs, specific target configuration)

This successor analysis provides the corrected primary endpoint results as the foundation for further interpretation and publication decisions.

