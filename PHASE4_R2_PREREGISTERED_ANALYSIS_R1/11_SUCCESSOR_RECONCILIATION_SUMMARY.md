# Successor Analysis Reconciliation Summary

## Overview

This successor analysis (PHASE4_R2_PREREGISTERED_ANALYSIS_R1) corrects a primary endpoint extraction defect identified in the predecessor analysis (PHASE4_R2_PREREGISTERED_ANALYSIS).

## Reconciliation Verdict

**Classification:** B) PRIMARY_ENDPOINT_EXTRACTION_DEFECT

**Reconciliation Report:** /tmp/phase4_r2_reconciliation_report.txt

## Defect Summary

**Frozen Primary Endpoint:** security_state_new_total  
**Predecessor Field Used:** body_rule_pass  
**Defect:** Predecessor extracted and analyzed the wrong field from execution evidence

## Value Comparison

| Field | Source File | All 28 AE Values | All 28 SE Values | All 28 Deltas |
|-------|-------------|------------------|------------------|---------------|
| body_rule_pass (DEFECTIVE) | nv_body_valid_stats.json | 5 | 5 | 0 |
| security_state_new_total (CORRECTED) | nv_state_db.json / nv_state_trace.jsonl | 1 | 1 | 0 |

## Statistical Conclusion Impact

**Zero Variance Finding:** UNCHANGED (true for both fields)  
**Mean Paired Difference:** 0.0 (for both fields)  
**Statistical Significance Claim:** Not made (no frozen confirmatory method)

## Scientific Interpretation Impact

**FUNDAMENTALLY DIFFERENT:**

**Predecessor (body_rule_pass = 5):**  
Both backends achieved 5 valid executions per block  
→ Interpretation: Equal execution success rate

**Corrected (security_state_new_total = 1):**  
Both backends discovered 1 unique security state per block  
→ Interpretation: Equal security state coverage exploration

These metrics measure completely different aspects of fuzzer behavior:
- **body_rule_pass** = execution/validity metric (how many test cases passed validation)
- **security_state_new_total** = coverage metric (how many unique security states discovered)

## Reconciliation Process

### Authority Verification (PASS)
- Final evidence commitment: e1330de8d1effbe3daaeb1d7070403b6dacc82a49dfc438a31a8ed9029743486 ✓
- Predecessor commitment: 9b5d90b7033d5a3d76c78599def8b9c31debdf88760f29ae3fb1d28d6c0e794b ✓
- Primary endpoint authority: security_state_new_total (02_ENDPOINTS.json) ✓
- Analysis population authority: 28 pairs (blocks 3-30) ✓

### Corrected Extraction (PASS)
- Extracted security_state_new_total from frozen evidence for 28 pairs ✓
- Source: AE = nv_state_db.json (array length), SE = nv_state_trace.jsonl (count "new":1) ✓
- Row count: 28 ✓
- Missing values: 0 ✓
- Duplicate pairs: 0 ✓

### Independent Verification (PASS)
- Reconciliation claim: All AE=1, SE=1, Delta=0 ✓
- Independent recomputation: CONFIRMED ✓
- AE unique values: [1] ✓
- SE unique values: [1] ✓
- Delta unique values: [0] ✓

### Descriptive Statistics (PASS)
- AE mean: 1.0 (was 5.0 in predecessor) ✓
- SE mean: 1.0 (was 5.0 in predecessor) ✓
- Paired delta mean: 0.0 (unchanged) ✓
- Paired delta SD: 0.0 (unchanged) ✓
- Zero variance: TRUE (unchanged) ✓

### Confirmatory Boundary (VERIFIED)
- Frozen confirmatory method: NOT_FROZEN ✓
- Confirmatory analysis executed: NO ✓
- Significance claim allowed: NO ✓

### Population Accounting (VERIFIED)
- Execution-valid pairs: 30 ✓
- Analysis-eligible pairs: 28 ✓
- Excluded pairs: 2 (blocks 1-2, both authorized) ✓

### Predecessor Preservation (VERIFIED)
- Predecessor package modified: NO ✓
- Predecessor status: PRESERVED_DEFECTIVE_HISTORICAL_PACKAGE ✓

## Corrective Actions Taken

1. Created successor analysis package (PHASE4_R2_PREREGISTERED_ANALYSIS_R1)
2. Extracted correct primary endpoint from frozen evidence
3. Recomputed all descriptive statistics using correct field
4. Verified all values independently
5. Documented defect and correction in detail
6. Preserved predecessor package as defective historical evidence
7. Established clear distinction between execution metrics and coverage metrics

## Corrective Actions NOT Taken (Prohibited)

- Did NOT run new experiments
- Did NOT modify raw evidence
- Did NOT modify final evidence freeze
- Did NOT modify predecessor analysis package
- Did NOT change analysis population rules
- Did NOT change endpoint roles
- Did NOT add new confirmatory endpoints
- Did NOT invent statistical tests
- Did NOT change N, seeds, order, thresholds, or protocol

## Chain of Custody

1. **Evidence Freeze:** PHASE4_FORMAL_EXECUTION_EVIDENCE_R2_FINAL (2026-09-21)
2. **Predecessor Analysis:** PHASE4_R2_PREREGISTERED_ANALYSIS (2026-09-21)
3. **Reconciliation:** Defect identification (2026-09-22, prior session)
4. **Successor Analysis:** PHASE4_R2_PREREGISTERED_ANALYSIS_R1 (2026-09-22, current session)

All artifacts preserved. No evidence modified.

## Next Steps

**Gate Status:** OPEN_FOR_RESULTS_INTERPRETATION_AND_PAPER_WRITEUP

The corrected primary endpoint results provide the foundation for:
- Scientific interpretation of coverage findings
- Publication manuscript preparation
- Decision-making about backend selection
- Planning of follow-up experiments

Users must note:
1. Zero-variance finding limits statistical inference
2. No frozen confirmatory method limits statistical claims
3. Results specific to experimental conditions (5 test cases, 60s runs)
4. Distinction between coverage (security_state_new_total) and execution (body_rule_pass) metrics

