# Phase 4 Formal Experiment Protocol Design

**Protocol Version:** 1.0.0  
**Design Date:** 2026-09-21  
**Status:** AWAITING_HUMAN_APPROVAL

## Purpose

This directory contains the preregistration-style protocol design for a formal paired AE-vs-SE comparison experiment.

**This is a DESIGN package, not execution results.** No formal experiment runs have been performed. All experimental units, seeds, and outcomes remain undefined until human approval and formal execution begin.

## Background

This protocol design binds to the **Phase-3 evidence freeze package** with commitment:

```
517cd241b85632142a8e74322bb284ce3e5832722cd5afdb2702dbac7c6415a8
```

Phase-3 was an engineering-variance pilot (N=5 paired blocks) that validated the paired experimental protocol and observed:

- AE and SE each produced `security_state_new_total = 1`
- All five paired differences: Δᵢ = [0, 0, 0, 0, 0]
- Validity gates, fail-fast policy, and evidence contracts all passed

Phase-3 demonstrated protocol feasibility but cannot provide reliable variance estimates for formal power analysis.

## Scientific Question

**Under a fixed and reproducible experiment contract, what is the difference in observed `security_state_new_total` counts between SE-backend and AE-backend scoring when applied to paired fuzzing runs with identical seeds, corpus, target, and execution budget?**

This is a neutral, testable question about model-conditioned testing behavior. The protocol does not assume model superiority or coverage equivalence.

## Protocol Structure

| File | Description |
|------|-------------|
| `00_DESIGN_STATUS.json` | Protocol metadata and design status |
| `01_SCIENTIFIC_QUESTION_AND_ESTIMAND.md` | Scientific question, estimand definition, and interpretation |
| `02_ENDPOINTS.json` | Primary and secondary endpoints, validity gates, diagnostic metrics |
| `03_PAIRED_DESIGN_AND_ORDER.md` | Paired experimental unit structure, order policy, baseline reset |
| `04_SEED_GENERATION_AND_FREEZE.md` | Deterministic seed generation procedure and freeze policy |
| `05_SAMPLE_SIZE_PLAN.md` | Sample size determination methods and variance considerations |
| `06_STATISTICAL_ANALYSIS_PLAN.md` | Point estimates, uncertainty quantification, hypothesis testing |
| `07_FAILURE_EXCLUSION_AND_STOPPING_RULES.md` | Fail-fast gates, exclusion criteria, stopping rules |
| `08_RUNTIME_PROVENANCE_CONTRACT.json` | Frozen model artifacts, thresholds, budget parameters |
| `09_EVIDENCE_FREEZE_CONTRACT.md` | Multi-stage evidence freeze and SHA256 commitment procedure |
| `10_HUMAN_DECISIONS_REQUIRED.md` | All unresolved human decisions blocking execution |
| `README.md` | This file |
| `FILE_LIST.txt` | Complete file listing |
| `SHA256SUMS.txt` | SHA256 hashes for all protocol files |

## Key Design Features

### Primary Estimand

Mean paired difference in `security_state_new_total`:

```
θ = E[Δᵢ]  where  Δᵢ = SE_i - AE_i
```

### Experimental Unit

One paired seed block: AE(seed_i) and SE(seed_i) sharing identical experimental conditions.

### Pairing Benefits

- Removes between-seed variance
- Isolates model-conditioned behavior differences
- Validated in Phase-3 pilot

### Sample Size

**Current Status:** REQUIRES_HUMAN_CHOICE

Four methods are evaluated:

- **A:** MPID + Power (conventional, requires justified MPID and variance)
- **B:** Precision-based (targets CI width, requires justified variance)
- **C:** Blinded re-estimation (data-adaptive, two-stage)
- **D:** Fixed pragmatic N (resource-constrained)

Human decision required before N can be determined.

### Statistical Analysis

**Recommended Primary Analysis:**

- Point estimate: Sample mean paired difference
- Uncertainty: 95% percentile bootstrap CI (B=10,000)
- Hypothesis test (if desired): Permutation test
- Rationale: Robust to discrete counts, ties, and small N

### Fail-Fast and Stopping Rules

All Phase-3 validated gates are preserved:

- Per-run validity gates (RPC, trace, provenance)
- Paired-block exclusion (no replacement)
- Consecutive-failure stopping rules (infrastructure, target, scorer)
- Evidence contract enforcement

### Frozen Artifacts

**SE Backend:**

- Model: `sefanogan_es_reference`
- Checkpoint SHA256: `4eace87ac7d7759a729ff98916a5acead4154c803c53884e3ca7f27570dbf20d`
- Metadata SHA256: `2a73ccc3729a3734ab9901b4474feb73d4d42f912ccbc717af48f970ab568226`
- Threshold: `1.2847454080581664`

**AE Backend:**

- Model: `alfresco_ae_v1`
- Threshold: `1.623614`

## Human Decisions Required

**Critical (Block Execution):**

- **D1:** Sample size method (A, B, C, or D)
- **D2-D7:** Method-specific parameters (MPID, variance, N, etc.)
- **D8:** Execution order (fixed AE-first vs randomized)
- **D9:** Execution budget (MAX_TEST_CASES, TIME_BUDGET)
- **D10:** Source baseline (git commit SHA)
- **D11:** Protocol master seed (for deterministic seed generation)

**Secondary (Clarify Analysis):**

- **D12:** Hypothesis testing (estimation-only vs test + p-value)
- **D13:** Equivalence testing (objective or not)
- **D14:** Secondary endpoints (all exploratory vs some confirmatory)
- **D15:** Multiplicity adjustment (if needed)

See `10_HUMAN_DECISIONS_REQUIRED.md` for complete details.

## Execution Gate

```
FORMAL_EXPERIMENT_EXECUTION_GATE = BLOCKED_PENDING_HUMAN_DESIGN_APPROVAL
```

No formal experiment runs are permitted until:

1. All critical human decisions (D1-D11) are resolved
2. Human reviewers approve this protocol design
3. Execution freeze package (Stage 2) is created with:
   - Frozen seed list
   - Frozen source baseline
   - Frozen analysis script
   - All parameters committed with SHA256

## Phase-3 Corrections Applied

This protocol does **not** carry forward these phrases as scientific conclusions:

- ❌ "coverage equivalence"
- ❌ "SE threshold is more conservative because 1.285 < 1.624"
- ❌ "AE and SE are equivalent"
- ❌ "AE better than SE" or "SE better than AE"

**Permitted Phase-3 descriptive statements:**

✅ "Across the five paired seeds in the Phase-3 engineering pilot, AE and SE each observed security_state_new_total = 1, so all five observed paired deltas for that metric were 0."

✅ "On the Phase-3 input distribution, AE and SE exhibited different empirical accept/reject behavior."

## What This Protocol Does NOT Do

- Execute any formal experiment runs
- Generate the final seed list (requires N from D1-D7 first)
- Modify source code, tests, or model files
- Make git commits or pushes
- Change thresholds or model artifacts
- Reinterpret or rewrite Phase-3 evidence

## Next Steps

1. **Human Review:** Convene reviewers to discuss protocol design
2. **Resolve Decisions:** Make all critical decisions (D1-D11)
3. **Execution Freeze:** Create Stage 2 freeze package with:
   - Frozen seed list from chosen N
   - Frozen analysis script
   - All parameters committed
4. **Human Approval:** Final approval to begin formal runs
5. **Execution:** Run formal experiment according to frozen protocol
6. **Analysis:** Apply frozen analysis script to collected data
7. **Reporting:** Generate final evidence package with SHA256 commitments

## Contact and Questions

For questions about this protocol design, refer to:

- Scientific question: `01_SCIENTIFIC_QUESTION_AND_ESTIMAND.md`
- Sample size: `05_SAMPLE_SIZE_PLAN.md`
- Statistical analysis: `06_STATISTICAL_ANALYSIS_PLAN.md`
- Human decisions: `10_HUMAN_DECISIONS_REQUIRED.md`

## Evidence Chain

```
Phase-3 Freeze (validated pilot)
    ↓
Protocol Design Freeze (this package) ← YOU ARE HERE
    ↓
Execution Freeze (preregistered parameters) ← NEXT GATE
    ↓
Formal Experiment Runs
    ↓
Analysis Freeze
    ↓
Final Evidence Package
```

## Reproducibility

This protocol design is committed with SHA256 for reproducibility. Any modifications create a new protocol version.

**Design Package Commitment:** (computed after all files written — see `SHA256SUMS.txt`)

## Version History

- **1.0.0** (2026-09-21): Initial protocol design, awaiting human approval
