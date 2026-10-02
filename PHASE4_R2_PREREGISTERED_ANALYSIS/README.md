# Phase 4 R2 Preregistered Analysis Results

This directory contains the complete preregistered analysis of the Phase 4 R2 formal campaign evidence.

## Analysis Protocol Compliance

This analysis follows the frozen preregistered protocol:
- PRIMARY_CONFIRMATORY_ENDPOINT = security_state_new_total (body_rule_pass)
- PAIRING = same formal seed
- PRIMARY_ESTIMAND = mean paired delta, SE_i - AE_i
- N = 30 paired blocks (28 complete, 2 missing primary data)

## Files

1. **01_PAIRED_PRIMARY_ENDPOINT_TABLE.json**
   - Canonical paired primary endpoint table
   - N=28 paired blocks (Blocks 3-30)
   - Missing: Block 1 (no primary data), Block 2 SE (missing primary data)

2. **02_PRIMARY_DESCRIPTIVE_STATISTICS.json**
   - Complete descriptive statistics for primary endpoint
   - Key finding: Zero variance across all 28 pairs (all deltas = 0)

3. **03_CONFIRMATORY_ANALYSIS.json**
   - Confirmatory analysis status: SKIPPED
   - Reason: No frozen confirmatory analysis contract in R2 freeze package
   - Per protocol: "skip confirmatory and proceed to exploratory"

4. **04_EXPLORATORY_SECONDARY_ENDPOINTS.json**
   - Exploratory secondary metrics (HTTP status, trace invocations)
   - Purely descriptive, no hypothesis tests

5. **05_SENSITIVITY_ADJUDICATION_ACCOUNTING.json**
   - R2 semantic gate accounting
   - Block 2 special adjudication details

6. **06_ORDER_BALANCE_DESCRIPTIVE.json**
   - Order balance verification (15 AE-first, 15 SE-first)
   - Primary endpoint cross-tabulation by order
   - Descriptive only, no pre-planned interaction test

## Key Findings

- **Primary endpoint**: All 28 paired blocks show identical values (AE=5, SE=5, delta=0)
- **Zero variance**: Both AE and SE consistently produce exactly 5 valid executions per block
- **Order balance**: Confirmed 15/15 split between AE-first and SE-first blocks
- **Effective N**: 28 complete pairs (missing Block 1 and Block 2 SE primary data)

## Evidence Authority

This analysis is based on the frozen evidence package:
- Evidence commitment: e1330de8d1effbe3daaeb1d7070403b6dacc82a49dfc438a31a8ed9029743486
- Evidence directory: PHASE4_FORMAL_EXECUTION_EVIDENCE_R2_FINAL/

## Analysis Integrity

See SHA256SUMS.txt for file integrity verification.
Analysis package commitment computed in STEP 11.
