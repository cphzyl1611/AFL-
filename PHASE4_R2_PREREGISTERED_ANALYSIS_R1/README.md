# PHASE4_R2_PREREGISTERED_ANALYSIS_R1

## Package Overview

**Type:** SUCCESSOR_CORRECTED_PRIMARY_ENDPOINT  
**Created:** 2026-09-22  
**Predecessor:** PHASE4_R2_PREREGISTERED_ANALYSIS (preserved as defective historical evidence)

This is a corrected successor analysis package that extracts the correct primary endpoint from the frozen execution evidence.

## Predecessor Defect

The predecessor analysis package (PHASE4_R2_PREREGISTERED_ANALYSIS) extracted and analyzed **body_rule_pass** (valid execution count) instead of the frozen primary endpoint **security_state_new_total** (new security state coverage count).

**Reconciliation Verdict:** B) PRIMARY_ENDPOINT_EXTRACTION_DEFECT

## Correction Applied

This successor package extracts the correct primary endpoint (security_state_new_total) from the same frozen execution evidence using:
- AE backend: Array length from `nv_state_db.json`
- SE backend: Count of `"new":1` entries in `nv_state_trace.jsonl`

## Key Results

**Primary Endpoint (CORRECTED):** security_state_new_total  
**Analysis Population:** 28 analysis-eligible pairs (blocks 3-30)  
**Observed Values:** AE=1, SE=1, Δ=0 for all 28 pairs  
**Statistical Conclusion:** Zero variance (SD=0), no confirmatory claims (no frozen method)

## Package Contents

- `00_ANALYSIS_STATUS.json` - Package metadata and status
- `01_ANALYSIS_AUTHORITY_BINDING.json` - Frozen authority bindings
- `02_PREDECESSOR_DEFECT_BINDING.json` - Defect documentation
- `03_CORRECTED_PRIMARY_PAIRED_TABLE.json` - Corrected primary endpoint values for 28 pairs
- `04_CORRECTED_PRIMARY_DESCRIPTIVE_STATISTICS.json` - Descriptive statistics
- `05_CONFIRMATORY_ANALYSIS_BOUNDARY.json` - Confirmatory testing limitations
- `06_EXPLORATORY_SECONDARY_ANALYSIS.json` - Exploratory endpoints status
- `07_ANALYSIS_POPULATION_ACCOUNTING.json` - Population accounting (30→28)
- `08_ANALYSIS_PROVENANCE.json` - Data sources and chain of custody
- `09_RESULTS_FOR_PAPER.md` - Results summary for publication
- `10_LIMITATIONS.md` - Analysis limitations
- `11_SUCCESSOR_RECONCILIATION_SUMMARY.md` - Reconciliation process summary
- `FILE_LIST.txt` - Complete file listing
- `SHA256SUMS.txt` - Package integrity checksums
- `README.md` - This file

## Data Sources

**Final Evidence Package:** PHASE4_FORMAL_EXECUTION_EVIDENCE_R2_FINAL  
**Evidence Commitment:** SHA256 = e1330de8d1effbe3daaeb1d7070403b6dacc82a49dfc438a31a8ed9029743486

**Frozen Design:** PHASE4_FORMAL_EXPERIMENT_PROTOCOL_DESIGN

**Predecessor Analysis:** PHASE4_R2_PREREGISTERED_ANALYSIS  
**Predecessor Commitment:** SHA256 = 9b5d90b7033d5a3d76c78599def8b9c31debdf88760f29ae3fb1d28d6c0e794b

## Integrity Verification

All analysis files are JSON-parseable and checksummed in SHA256SUMS.txt.

To verify package integrity:
```bash
cd PHASE4_R2_PREREGISTERED_ANALYSIS_R1
sha256sum -c SHA256SUMS.txt
```

## No Modifications Made

This successor analysis did NOT:
- Run new experiments
- Modify raw evidence
- Modify final evidence freeze
- Modify predecessor analysis package
- Change analysis population rules
- Change endpoint roles
- Add new confirmatory endpoints
- Invent statistical tests
- Change N, seeds, order, thresholds, or protocol

## Next Steps

**Gate Status:** OPEN_FOR_RESULTS_INTERPRETATION_AND_PAPER_WRITEUP

This corrected analysis provides the foundation for:
- Scientific interpretation of coverage findings
- Publication manuscript preparation
- Backend selection decisions
- Follow-up experiment planning

## Key Distinctions

**body_rule_pass (DEFECTIVE predecessor field):**
- Definition: Count of valid executions passing body validation rules
- Values: AE=5, SE=5 for all 28 pairs
- Interpretation: Execution/validity metric

**security_state_new_total (CORRECTED primary endpoint):**
- Definition: Number of testcases triggering new security state coverage transitions
- Values: AE=1, SE=1 for all 28 pairs
- Interpretation: Coverage effectiveness metric

These measure fundamentally different aspects of fuzzer behavior.

## Contact

For questions about this analysis package, refer to:
- Reconciliation report: /tmp/phase4_r2_reconciliation_report.txt
- Predecessor defect binding: 02_PREDECESSOR_DEFECT_BINDING.json
- Successor reconciliation summary: 11_SUCCESSOR_RECONCILIATION_SUMMARY.md

