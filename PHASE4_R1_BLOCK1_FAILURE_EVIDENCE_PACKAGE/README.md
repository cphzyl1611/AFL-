# PHASE4 R1 FORMAL EXECUTION - BLOCK 1 FAILURE EVIDENCE PACKAGE

## Status

**EXECUTION STATUS:** BLOCKED_AT_BLOCK_1  
**FAIL_FAST_TRIGGERED:** YES  
**COMPLETED_BLOCKS:** 0 / 30  
**NEXT_GATE:** BLOCKED_PENDING_HUMAN_ADJUDICATION

## What Happened

Phase 4 R1 formal execution began under commitment `5225953ce7fc194a3eebcd02be4609bd89fdf0abddf3bac65442053bb75f0f52`.

Block 1 (seed 1120356083, AE-first schedule) executed:
- **First run (AE):** VALID - 5/5 bodies passed validation, security_state_new_total=1
- **Second run (SE):** INVALID - 0/5 bodies passed validation, artifact contract FAILED

The SE validity backend rejected all mutated inputs that the AE backend accepted, preventing any HTTP execution in the SE run. With zero valid executions, required state tracking artifacts (`nv_probe.json`, `nv_state_db.json`) were never created.

Per the R1 fail-fast contract, the campaign stopped immediately. No rerun, seed replacement, or continuation is permitted without human adjudication.

## Root Cause

The SE scorer (`sefanogan_es_reference`, threshold 1.2847454080581664) is significantly more restrictive than the AE scorer (`alfresco_ae_v1`, threshold 1.623614) for this seed's mutation space.

**Validity gate comparison:**
- AE: 5/5 bodies passed → 5 valid executions
- SE: 0/5 bodies passed → 0 valid executions

This breaks the paired comparison design, which requires both backends to produce primary endpoint observations.

## Evidence Structure

```
00_EXECUTION_FREEZE_STATUS.json         # R1 freeze status
00_R1_COMMITMENT.txt                    # Authoritative commitment hash
04_FORMAL_SEED_LIST.json                # 30 formal seeds
05_FORMAL_PAIRED_ORDER_SCHEDULE.json    # Counterbalanced schedule
06_FORMAL_RUN_BUDGET.json               # 5/60/10 budget
PHASE4_R1_EXECUTION_LEDGER.json         # Execution tracking ledger
BLOCK_01_FAILURE_REPORT.txt             # Detailed failure analysis

block_01_ae_evidence/
  fuzzer_stats                          # AE run statistics
  nv_body_valid_stats.json              # AE body validation (5 pass, 0 reject)
  artifact_report.json                  # AE artifact contract (PASS)

block_01_se_evidence/
  fuzzer_stats                          # SE run statistics
  nv_body_valid_stats.json              # SE body validation (0 pass, 5 reject)
  artifact_report.json                  # SE artifact contract (FAILED)
  executions.jsonl                      # SE execution ledger showing all rejects
```

## Adjudication Options

1. **Adjust SE threshold** to match AE acceptance rate
2. **Disable body score validation** for SE backend
3. **Abandon paired comparison** for this seed
4. **Modify protocol** and create new authorized freeze (R2)

## Full Artifacts

Complete run artifacts preserved at:
- `/tmp/phase4_r1_formal_execution/block_01/ae/`
- `/tmp/phase4_r1_formal_execution/block_01/se/`
- `/tmp/phase4_r1_formal_execution/block_01_failure_evidence/`

## Integrity

Package checksums: `SHA256SUMS.txt`
