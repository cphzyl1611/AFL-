# Evidence Freeze Contract

## Purpose

This contract defines what evidence must be frozen at each stage of the formal experiment and how that evidence is committed for reproducibility.

## Freeze Stages

### Stage 1: Protocol Design Freeze (Current Stage)

**What is Frozen:**

- This protocol design package
- Scientific question and estimand definition
- Endpoint specifications
- Paired design and order policy
- Seed generation procedure (method, not yet the actual seed list)
- Sample size determination method
- Statistical analysis plan
- Failure/exclusion/stopping rules
- Runtime provenance contract
- Evidence freeze contract itself

**Commitment:**

```
Protocol Design Package SHA256 = <computed after all design files are written>
```

**Status:**

This freeze occurs **before any real experimental runs**.

**Human Approval Gate:**

The protocol design must be reviewed and approved by a human before advancing to Stage 2.

---

### Stage 2: Execution Freeze (Pre-Experiment)

**What is Frozen:**

- Exact seed list (generated from preregistered procedure)
- Exact N (number of paired blocks)
- Source baseline git commit SHA
- Execution order list (if randomized/counterbalanced)
- Exact MAX_TEST_CASES and TIME_BUDGET values
- Target endpoint and configuration
- Analysis script (code + git SHA)
- Any human decisions from Stage 1 (MPID, variance assumptions, etc.)

**Commitment:**

```json
{
  "execution_freeze_sha256": "<commitment>",
  "protocol_design_sha256": "<Stage 1 commitment>",
  "seed_list_sha256": "<hash of frozen seed list JSON>",
  "source_baseline_sha": "<git commit SHA>",
  "n_pairs": <integer>,
  "max_test_cases": <integer>,
  "time_budget_seconds": <integer>,
  "analysis_script_sha": "<git SHA or file hash>",
  "frozen_timestamp": "<ISO 8601>",
  "frozen_by": "<human reviewer>"
}
```

**Status:**

This freeze occurs **after human approval of protocol design** and **before the first real run**.

**No Changes Allowed After This Point:**

- Cannot add/remove/replace seeds
- Cannot change analysis method
- Cannot modify stopping rules
- Cannot adjust thresholds or model artifacts

---

### Stage 3: Run-Level Freeze (Per-Run)

**What is Frozen:**

After each individual run (AE or SE) completes:

- Run manifest JSON with all provenance fields
- fuzzer_stats file
- Trace files
- Any other run-specific artifacts

**Commitment:**

```json
{
  "run_id": "<unique run identifier>",
  "run_manifest_sha256": "<hash of run_manifest.json>",
  "fuzzer_stats_sha256": "<hash of fuzzer_stats>",
  "trace_files_sha256": ["<hash1>", "<hash2>", ...],
  "frozen_timestamp": "<ISO 8601>"
}
```

**Status:**

Each run is frozen immediately after completion and validation.

**Immutability:**

Run artifacts are never modified after freeze. Any re-analysis reads the frozen artifacts.

---

### Stage 4: Paired-Block Freeze (Per-Pair)

**What is Frozen:**

After both runs in a paired block complete (or fail):

- AE run artifacts + commitment
- SE run artifacts + commitment
- Paired block validity status
- Paired difference Δᵢ (if valid)
- Exclusion reason (if failed)

**Commitment:**

```json
{
  "pair_index": <integer>,
  "seed": <integer>,
  "ae_run_freeze": {
    "run_manifest_sha256": "<AE manifest hash>",
    "status": "valid" | "failed"
  },
  "se_run_freeze": {
    "run_manifest_sha256": "<SE manifest hash>",
    "status": "valid" | "failed"
  },
  "paired_block_status": "valid" | "excluded",
  "exclusion_reason": "<reason if excluded>",
  "paired_difference_delta_i": <integer or null>,
  "frozen_timestamp": "<ISO 8601>"
}
```

**Status:**

Each paired block is frozen immediately after both runs complete.

---

### Stage 5: Campaign Completion Freeze (Post-Experiment)

**What is Frozen:**

After all N preregistered paired blocks are attempted:

- All run-level freezes
- All paired-block freezes
- Exclusion summary
- Raw data (all Δᵢ values)
- No analysis results yet (analysis comes in Stage 6)

**Commitment:**

```json
{
  "campaign_freeze_sha256": "<commitment>",
  "execution_freeze_sha256": "<Stage 2 commitment>",
  "total_preregistered_blocks": <N>,
  "valid_blocks": <k>,
  "excluded_blocks": <N - k>,
  "all_paired_blocks": [
    {"pair_index": 1, "freeze_sha256": "<hash>", "status": "valid"},
    {"pair_index": 2, "freeze_sha256": "<hash>", "status": "excluded"},
    ...
  ],
  "frozen_timestamp": "<ISO 8601>"
}
```

**Status:**

This freeze occurs **after the last run completes** and **before statistical analysis begins**.

**Unblinding:**

At this stage, all data is collected but not yet analyzed. The campaign completion freeze can occur before unblinding (if a blinded design was used).

---

### Stage 6: Analysis Freeze (Final)

**What is Frozen:**

After statistical analysis is complete:

- Descriptive statistics
- Point estimates
- Confidence intervals
- Hypothesis test results (if any)
- Secondary endpoint summaries
- Sensitivity analyses
- All tables and figures
- Final statistical report

**Commitment:**

```json
{
  "analysis_freeze_sha256": "<commitment>",
  "campaign_freeze_sha256": "<Stage 5 commitment>",
  "analysis_script_sha256": "<hash of executed analysis code>",
  "primary_point_estimate": <float>,
  "primary_ci_95_lower": <float>,
  "primary_ci_95_upper": <float>,
  "hypothesis_test_p_value": <float or null>,
  "secondary_results": {...},
  "frozen_timestamp": "<ISO 8601>"
}
```

**Status:**

This is the final freeze. All results are committed.

**Supersession Policy:**

If errors are discovered in the analysis after this freeze:

- The original analysis freeze remains in the evidence package (never deleted)
- A corrected analysis freeze is created with:
  - New SHA256 commitment
  - Supersedes field pointing to original freeze
  - Detailed explanation of the correction
  - Re-run of analysis script with corrections

---

## Evidence Package Structure

The complete formal experiment evidence package must contain:

```
PHASE4_FORMAL_EXPERIMENT_EVIDENCE/
├── 00_PROTOCOL_DESIGN/
│   ├── (all files from PHASE4_FORMAL_EXPERIMENT_PROTOCOL_DESIGN/)
│   └── PROTOCOL_DESIGN_SHA256.txt
├── 01_EXECUTION_FREEZE/
│   ├── execution_freeze.json
│   ├── seed_list.json
│   ├── source_baseline.txt (git SHA)
│   ├── analysis_script.py (frozen before execution)
│   └── EXECUTION_FREEZE_SHA256.txt
├── 02_RUN_ARTIFACTS/
│   ├── pair_001/
│   │   ├── ae/
│   │   │   ├── run_manifest.json
│   │   │   ├── fuzzer_stats
│   │   │   ├── trace_*.json
│   │   │   └── RUN_SHA256.txt
│   │   └── se/
│   │       ├── run_manifest.json
│   │       ├── fuzzer_stats
│   │       ├── trace_*.json
│   │       └── RUN_SHA256.txt
│   ├── pair_002/
│   │   └── ...
│   └── ...
├── 03_PAIRED_BLOCKS/
│   ├── pair_001_freeze.json
│   ├── pair_002_freeze.json
│   └── ...
├── 04_CAMPAIGN_COMPLETION/
│   ├── campaign_freeze.json
│   ├── all_paired_differences.json
│   ├── exclusion_summary.json
│   └── CAMPAIGN_FREEZE_SHA256.txt
├── 05_ANALYSIS_RESULTS/
│   ├── analysis_freeze.json
│   ├── descriptive_statistics.json
│   ├── bootstrap_ci_results.json
│   ├── hypothesis_test_results.json (if applicable)
│   ├── figures/
│   │   ├── paired_differences_histogram.png
│   │   ├── ae_vs_se_scatter.png
│   │   └── ...
│   ├── analysis_log.txt
│   └── ANALYSIS_FREEZE_SHA256.txt
├── 06_PHASE3_BINDING/
│   ├── phase3_freeze_commitment.txt
│   └── phase3_freeze_package_reference.json
├── FILE_LIST.txt
├── SHA256SUMS.txt
└── README.md
```

## SHA256 Commitment Procedure

**For Each Freeze Stage:**

1. Complete all artifacts for that stage
2. Compute SHA256 for each individual file
3. Aggregate individual hashes into a stage-level manifest
4. Compute SHA256 of the stage-level manifest
5. Write the stage commitment hash to a top-level commitment file

**Verification:**

Any party can verify the evidence package by:

1. Re-computing SHA256 for each file
2. Comparing against the committed hashes
3. Verifying the chain of commitments from protocol design → execution → runs → campaign → analysis

## Immutability Policy

**After a freeze:**

- Frozen artifacts are **never modified**
- Frozen artifacts are **never deleted**
- Corrections or amendments create **new versioned artifacts** with supersession links

**If an error is discovered:**

- Document the error in an errata file
- Create a corrected version with new SHA256
- Preserve the original frozen version
- Link the correction to the original with a supersedes field

## Reproducibility Contract

**Minimal Reproducibility Requirement:**

Given:

- The execution freeze package (Stage 2)
- The same source baseline (git SHA)
- The same frozen model artifacts (SE checkpoint, AE config)

An independent party should be able to:

- Re-run the experiment with the same seed list
- Produce run manifests with identical structure (but possibly different actual outcomes due to target/network non-determinism)
- Apply the frozen analysis script to their collected data
- Compare their results to the original frozen analysis results

**Full Reproducibility (If Target is Deterministic):**

If the target application is fully deterministic and the environment is controlled:

- An independent party should be able to reproduce **exactly** the same paired differences Δᵢ
- This level of reproducibility may not be achievable for live HTTP API targets with non-deterministic behavior

## Chain of Trust

The evidence package forms a chain of trust:

```
Phase-3 Freeze (validated pilot)
    ↓
Protocol Design Freeze (this design)
    ↓
Execution Freeze (preregistered experiment parameters)
    ↓
Run-Level Freezes (individual run artifacts)
    ↓
Paired-Block Freezes (paired observations)
    ↓
Campaign Completion Freeze (all data collected)
    ↓
Analysis Freeze (final results)
```

Each stage references the SHA256 commitment of the previous stage, ensuring the chain is unbroken.

## Notes

- All timestamps are ISO 8601 format with timezone
- All SHA256 hashes are lowercase hexadecimal
- All JSON manifests use deterministic key ordering for consistent hashing
- The evidence package is self-contained: all references are internal or to Phase-3 frozen package
- No evidence is stored outside the package structure
- The package can be archived, transferred, and verified independently
