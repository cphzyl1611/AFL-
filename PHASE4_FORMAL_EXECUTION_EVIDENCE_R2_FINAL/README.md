# Phase 4 R2 Formal Execution — Final Evidence Freeze

## Evidence Freeze Commitment

**SHA256(SHA256SUMS.txt):** `e1330de8d1effbe3daaeb1d7070403b6dacc82a49dfc438a31a8ed9029743486`

This commitment cryptographically binds all evidence files in this package.

## Package Contents

This evidence freeze contains the complete post-execution accounting for the Phase 4 R2 formal campaign (Blocks 1-30, 60 valid runs).

### Execution Status and Block Accounting
- `00_FINAL_EXECUTION_STATUS.json` — Campaign completion status and high-level verdict
- `01_CANONICAL_30_BLOCK_LEDGER.json` — Complete 30-block ledger with special adjudications
- `02_CANONICAL_60_RUN_INVENTORY.json` — All 60 valid runs with paths and parameters
- `03_PAIR_CONTRACTS.json` — All 30 paired block contracts (all PASS)
- `04_EXCLUDED_ATTEMPTS.json` — 1 excluded invalid Block 2 AE attempt

### Validity and Provenance
- `05_R2_SEMANTIC_GATE_ACCOUNTING.json` — 28 R2 semantic gate special passes (SE zero-execution cases)
- `06_RUNTIME_PROVENANCE.json` — Orchestrator, backends, frozen parameters, execution environment
- `07_COMMAND_PARAMETER_AUDIT.json` — Pre-launch parameter gate audit trail (79 command assertions)

### Raw Measurements
- `08_PRIMARY_ENDPOINT_RAW_VALUES.json` — Primary validity endpoint metrics (body_score_pass, body_score_rpc_ok, etc.)
- `09_EXPLORATORY_SECONDARY_RAW_VALUES.json` — HTTP status distributions and trace invocation counts

### Freeze Bindings
- `10_R2_EXECUTION_FREEZE_BINDING.json` — Binding to R2 freeze commitment `1fdf580ef94cdec868924c4d0f4759b5eecc7421684aeb3528c6ebac2d9f879f`
- `11_BLOCK1_CARRY_FORWARD_BINDING.json` — Block 1 carry-forward from prior R2 execution
- `12_BLOCK2_ADJUDICATION_AND_RETRY_BINDING.json` — Block 2 special adjudication: SE carried forward, old AE excluded, AE retry executed

### Artifact Evidence
- `13_RAW_ARTIFACT_MANIFEST.txt` — SHA256 checksums of 172 key artifacts from `/tmp/phase4_r2_formal_execution/`

### Pre-Analysis Boundary
- `14_PREANALYSIS_FREEZE_STATUS.json` — Documents that no statistical analysis has been performed

## Special Adjudications

### Block 1
- **Status:** CARRIED_FORWARD_FROM_PRIOR_R2_EXECUTION
- Both AE and SE runs valid from prior execution
- Not rerun in current campaign
- Included in final 60-run count

### Block 2
- **SE run:** CARRIED_FORWARD_FROM_PRIOR_R2_EXECUTION (not rerun)
- **Old AE attempt:** EXCLUDED_INVALID_ATTEMPT (3/30/10 budget, wrong budget out of scope)
- **AE retry:** EXECUTED with frozen budget 5/60/10, status VALID
- **Discrepancy noted:** run_inventory.jsonl contains 5 AE_RETRY entries but authorization specified exactly 1 retry

### Blocks 3-30
- Standard paired execution (AE-first or SE-first per frozen schedule)
- All 28 blocks completed with both runs valid
- All pair contracts: PASS

## R2 Semantic Gate Adapter

The R2 semantic gate reconciles a known validator false negative for SE runs with zero execution:
- **Pattern:** body_score_pass=0, body_score_rpc_ok>0, body_score_rpc_fail=0, trace_invocations>0, no probe/state_db artifacts
- **Interpretation:** SE model correctly rejected all invalid inputs; old validator expected at least one valid execution
- **R2 gate verdict:** PASS_VALIDATOR_FALSE_NEGATIVE_ZERO_EXECUTION_CASE
- **Count:** 28 SE runs (Blocks 3-30) matched this pattern

## Execution Parameters (Frozen)

- **max_test_cases:** 5
- **time_budget:** 60 seconds
- **scorer_ready_timeout:** 10 seconds
- **model_comparison:** enabled
- **SE backend:** sefanogan_es_reference (checkpoint SHA256: `4eace87ac7d7759a729ff98916a5acead4154c803c53884e3ca7f27570dbf20d`)
- **AE backend:** alfresco_ae_v1 (NV rule-based filter)

## Campaign Metrics

- **Total blocks:** 30
- **Total valid runs:** 60 (30 AE + 30 SE)
- **Completed blocks:** 30
- **Fail-fast triggered:** false
- **Pre-launch parameter gate failures:** 0
- **Wrong budget launches:** 0
- **R2 semantic gate special passes:** 28
- **Excluded attempts:** 1 (Block 2 old AE 3/30)

## Verification

To verify this evidence freeze:

1. Verify commitment:
   ```bash
   sha256sum -c SHA256SUMS.txt
   sha256sum SHA256SUMS.txt  # Should match e1330de8d1effbe3daaeb1d7070403b6dacc82a49dfc438a31a8ed9029743486
   ```

2. Verify R2 freeze binding:
   ```bash
   cd ../PHASE4_FORMAL_EXECUTION_FREEZE_R2
   sha256sum SHA256SUMS.txt  # Should match 1fdf580ef94cdec868924c4d0f4759b5eecc7421684aeb3528c6ebac2d9f879f
   ```

3. Verify artifact manifest:
   ```bash
   sha256sum 13_RAW_ARTIFACT_MANIFEST.txt  # Should match 5cb4ff1268dcd85ca90e172d056f0f2d071e025cfb050bf0824f29bcf6da3db1
   ```

## Pre-Analysis Boundary

This evidence freeze records **raw execution outcomes only**. No statistical analysis, hypothesis testing, or model fitting has been performed. The pre-analysis boundary is preserved.

Future analysis must:
1. Load this immutable evidence freeze
2. Document analysis plan separately
3. Report results with reference to this commitment

## Campaign State Persistence

The orchestrator maintained persistent state in:
- `../PHASE4_R2_CAMPAIGN_STATE/campaign_state.json` — Campaign state checkpoint
- `../PHASE4_R2_CAMPAIGN_STATE/block_ledger.jsonl` — Block completion records
- `../PHASE4_R2_CAMPAIGN_STATE/run_inventory.jsonl` — Run inventory (includes Block 2 AE retry discrepancy)
- `../PHASE4_R2_CAMPAIGN_STATE/excluded_attempts.jsonl` — Excluded invalid attempts
- `../PHASE4_R2_CAMPAIGN_STATE/command_audit.jsonl` — Command parameter audit trail

## Outstanding Issues

### Block 2 AE Retry Count Discrepancy

**Authorization scope:** "execute exactly ONE Block 2 AE retry"

**Observed:** run_inventory.jsonl contains 5 entries with position="AE_RETRY" for Block 2 alfresco_ae_v1

**Impact on metrics:**
- BLOCK2_AE_RETRY_COUNT should be 1, but inventory shows 5 entries
- Need to determine if these are duplicate logging entries or actual multiple executions
- Affects final verdict determination

**Status:** Documented in `12_BLOCK2_ADJUDICATION_AND_RETRY_BINDING.json`, requires investigation

## Contact

For questions about this evidence freeze or the Phase 4 R2 formal campaign, refer to the project repository and campaign orchestrator logs.
