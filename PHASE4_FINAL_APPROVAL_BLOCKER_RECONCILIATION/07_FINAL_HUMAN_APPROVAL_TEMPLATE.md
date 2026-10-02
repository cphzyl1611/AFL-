# Phase 4 — Final Human Approval Template
# AFL++ AE vs SE Paired Comparison Study

**Date:** 2026-09-21

**Protocol Design Package Commitment:**
```
cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19
```

**Phase-3 Evidence Freeze Commitment:**
```
517cd241b85632142a8e74322bb284ce3e5832722cd5afdb2702dbac7c6415a8
```

**Blocker Reconciliation Package:** PHASE4_FINAL_APPROVAL_BLOCKER_RECONCILIATION

---

## Instructions

This template documents the 15 design decisions (D1-D15) requiring human approval before formal experiment execution.

- Each decision shows the **recommended value** (from reconciliation)
- Mark `[X]` to approve the recommended value, or `[ ]` and specify alternative
- All decisions must be explicitly approved (no defaults)
- Sign at the end to authorize experiment execution

---

## DECISION 1: Primary Estimand

**What is being estimated:**

```
θ = E[Δᵢ]

where Δᵢ = security_state_new_total(SE, seed_i) - security_state_new_total(AE, seed_i)
```

**Recommended:** Mean paired difference for `security_state_new_total`

**Approval:**

```
[ ] APPROVED — Primary estimand is mean paired difference θ = E[Δᵢ] for security_state_new_total

Rationale (if alternative chosen):
_____________________________________________________________________
```

---

## DECISION 2: Secondary Exploratory Endpoints

**Recommended endpoints (descriptive analysis only, no multiplicity correction):**

1. `security_state_total` (cumulative security state discoveries)
2. `body_score_pass` (number of valid bodies by score threshold)
3. `body_score_reject` (number of rejected bodies by score threshold)

**Approval:**

```
[ ] APPROVED — Secondary exploratory endpoints as listed above

Alternative endpoints (if any):
_____________________________________________________________________
```

---

## DECISION 3: Validity/Evidence Gates

**Full validity gate set (see 04_FULL_VALIDITY_GATE_CONTRACT.json):**

**Universal gates (all runs):**
- `body_score_rpc_ok > 0`
- `body_score_rpc_fail = 0`
- `trace_invocations > 0`
- `exact_backend_recorded = TRUE`
- `trace_stats_reconciliation = PASS`
- `artifact_contract = PASS`
- `model_comparison_validity = PASS`
- `readback = PASS`

**SE-specific gates:**
- `se_checkpoint_sha256 = 4eace87ac7d7759a729ff98916a5acead4154c803c53884e3ca7f27570dbf20d`
- `se_metadata_sha256 = 2a73ccc3729a3734ab9901b4474feb73d4d42f912ccbc717af48f970ab568226`
- `se_metadata_input_dim = 32`
- `se_threshold = 1.2847454080581664`
- `se_backend = sefanogan_es_reference`

**AE-specific gates:**
- `ae_backend = alfresco_ae_v1`
- `ae_threshold = 1.623614`

**Paired block exclusion:** If either run in a pair fails any gate, the entire paired block is excluded (no replacement).

**Approval:**

```
[ ] APPROVED — Full validity gate set as documented in 04_FULL_VALIDITY_GATE_CONTRACT.json

Alternative gates (if any):
_____________________________________________________________________
```

---

## DECISION 4: Paired Design Confirmation

**Recommended:** Paired comparison design (AE and SE use identical seed within each block)

**Estimand:** Mean paired difference (not independent-samples)

**Approval:**

```
[ ] APPROVED — Paired comparison design with mean paired difference estimand

Rationale (if alternative chosen):
_____________________________________________________________________
```

---

## DECISION 5: Execution Order

**Recommended:** Counterbalanced alternating order

**Exact rule:**
```
Block i: AE-first if (i mod 2) = 1, SE-first if (i mod 2) = 0
```

**For N=30:** 15 AE-first blocks, 15 SE-first blocks

**Rationale:** Phase-3 used fixed AE-first order (did not test order sensitivity). Counterbalancing separates order effects from backend effects.

**Approval:**

```
[ ] APPROVED — Counterbalanced alternating order: odd blocks AE-first, even blocks SE-first

Alternative order strategy (if any):
_____________________________________________________________________
```

---

## DECISION 6: Fuzzing Budget

**Recommended:** Same as Phase-3 (validated in 5+5 pilot)

```
MAX_TEST_CASES = 5
TIME = 60 (seconds)
```

**Evidence:** Phase-3 all 10 runs passed validity gates. Saturation status: INSUFFICIENT_EVIDENCE_TO_DETERMINE.

**Approval:**

```
[ ] APPROVED — MAX_TEST_CASES=5, TIME=60s (Phase-3 validated budget)

Alternative budget (if any):
MAX_TEST_CASES = _____
TIME = _____ seconds
Rationale:
_____________________________________________________________________
```

---

## DECISION 7: Sample Size Method

**Phase-3 constraint:** All 5 paired differences = 0, sample variance = 0

**Available methods:**
- **Method A:** MPID + Power (requires justified MPID and variance — UNAVAILABLE)
- **Method B:** Precision-based (requires justified variance — UNAVAILABLE)
- **Method C:** Blinded variance re-estimation (adaptive two-stage)
- **Method D:** Fixed pragmatic N (resource-constrained)

**Recommended:** Method D (Fixed pragmatic N)

**Fallback (if Method D rejected):** Method C (Blinded variance re-estimation)

**Approval:**

```
[ ] APPROVED — Method D: Fixed pragmatic N

OR

[ ] CHOOSE FALLBACK — Method C: Blinded variance re-estimation

If Method C chosen, specify:
  - Initial stage size N₁: _____
  - Maximum total N_max: _____
  - Re-estimation rule: _____________________________________________________
```

---

## DECISION 8: Fixed N Value (if Method D chosen)

**Recommended:** N = 30

**Justification basis:**
1. Feasibility multiplier: 6× Phase-3 pilot size (5 → 30)
2. Resource constraints: 60 runs total (30 AE + 30 SE)
3. Conventional heuristic reference: N≥30 for CLT applicability

**IMPORTANT — N=30 Inferential Limitations:**

I acknowledge that N=30 is a **pragmatic choice based on feasibility**, not statistical derivation.

I understand:
- The study may be underpowered for small effect sizes
- Confidence intervals may be wide
- Power and precision are NOT guaranteed
- Primary emphasis is on **estimation** (point estimate + 95% CI), not hypothesis testing
- Results should be interpreted as exploratory if inconclusive
- Follow-up studies may be needed if initial results are underpowered

**Status:**
```
N30_ROLE = OPERATIONAL_FEASIBILITY_DRIVEN
N30_POWER_JUSTIFIED = NO
N30_PRECISION_JUSTIFIED = NO
N30_CLT_HEURISTIC_REFERENCE = DESCRIPTIVE_ONLY (not prescriptive power justification)
```

**Approval:**

```
[ ] APPROVED — N = 30 (pragmatic choice, inferential limitations acknowledged)

Alternative N (if any):
N = _____
Justification:
_____________________________________________________________________
```

---

## DECISION 9: Master Seed Selection

**Recommended:** Commitment-derived deterministic seed

**Derivation rule:**
```python
design_commitment = "cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19"
master_seed = int(design_commitment[:8], 16)
# Result: 3485535768
```

**Corrected value:** 3485535768 (32-bit unsigned, Python `random.Random()` compatible)

**Fallback alternative:** Human-interpretable date-based seed (e.g., 20260921)

**Approval:**

```
[ ] APPROVED — Commitment-derived master seed: 3485535768

OR

[ ] CHOOSE FALLBACK — Date-based master seed: 20260921

OR

[ ] SPECIFY ALTERNATIVE — Master seed: _____
Rationale:
_____________________________________________________________________
```

---

## DECISION 10: Source Baseline Identity

**Recommended:** Composite 4-field source identity

**Identity type:** `COMPOSITE_4_FIELD_SOURCE_IDENTITY`

**Four components:**
```json
{
  "git_head_commit": "87bee5c6fa1f0a8f7d6df2a301df3b7f879aa408",
  "runner_sha256": "7acb5192fc7c4c6fbb3f24155d94eb68809cca0306d7600855c6504444bf3650",
  "tracked_diff_sha256": "686a1e65035ac38145b606f4c765f6a1220e6f9f9f2206338354bd2a84112140",
  "canonical_12file_manifest_sha256": "26c2e4f3871d7deffb4ab7fc356f6973b8f01b5985d189ed6afcc79b251a2c5b"
}
```

**Note:** These values match Phase-3 validated baseline exactly.

**Working tree status:** DIRTY (intentionally preserved — contains critical untracked files)

**Approval:**

```
[ ] APPROVED — Composite 4-field source identity as frozen (dirty working tree preserved)

Rationale (if alternative chosen):
_____________________________________________________________________
```

---

## DECISION 11: Stopping Rule

**Recommended:** Fixed-N design (no interim analysis, no early stopping)

**Consequence:** All N paired blocks must complete (excluding validity gate failures)

**Approval:**

```
[ ] APPROVED — Fixed-N design, no interim analysis

Alternative stopping rule (if any):
_____________________________________________________________________
```

---

## DECISION 12: Hypothesis Test

**Recommended:** Permutation test (if requested)

**Primary deliverable:** Point estimate θ̂ and 95% bootstrap confidence interval

**Hypothesis test:** Optional supplementary analysis (two-sided permutation test, α=0.05)

**Approval:**

```
[ ] APPROVED — Perform permutation test as supplementary analysis

OR

[ ] SKIP HYPOTHESIS TEST — Report point estimate and CI only
```

---

## DECISION 13: Confidence Interval Method

**Recommended:** Bootstrap percentile method (95% CI)

**Bootstrap resampling:** 10,000 iterations (paired resampling)

**Rationale:** Robust to discrete counts, ties, small N, non-normality

**Approval:**

```
[ ] APPROVED — 95% bootstrap percentile CI, 10,000 iterations

Alternative CI method (if any):
_____________________________________________________________________
```

---

## DECISION 14: Failure Replacement

**Recommended:** No replacement (intent-to-treat paired blocks)

**Exclusion rule:** If either run in a paired block fails validity gates, exclude the entire block

**Note:** `security_state_new_total=0` is a valid scientific observation, not a failure

**Approval:**

```
[ ] APPROVED — No replacement, paired block exclusion only for validity gate failures

Alternative replacement rule (if any):
_____________________________________________________________________
```

---

## DECISION 15: Multi-Stage Evidence Freeze

**Recommended:** Five-stage evidence freeze protocol

**Stages:**
1. **Protocol Design Freeze** (this approval) — Design decisions, commitments
2. **Reconciliation Freeze** (after execution) — Raw run artifacts, validity gate results
3. **Execution Log Freeze** — Timestamped execution provenance
4. **Run Evidence Freeze** — Per-run manifests, traces, fuzzer_stats
5. **Campaign Freeze** — Aggregate results, statistical analysis

**Each stage:** SHA256 commitment of freeze package

**Approval:**

```
[ ] APPROVED — Five-stage evidence freeze protocol as specified

Alternative freeze protocol (if any):
_____________________________________________________________________
```

---

## Final Authorization

**I have reviewed all 15 decisions and:**

- [X] All recommended values are approved as specified above
- [ ] Some decisions have alternatives specified (see individual sections)

**I authorize formal experiment execution** under the approved design, subject to:

1. All 15 decisions approved with explicit checkmarks
2. No execution until this signed template is archived
3. All validity gates enforced as specified
4. No post-hoc changes to frozen design decisions
5. Multi-stage evidence freeze protocol followed

**Signature:**

```
Name: _____________________________________

Date: _____________________________________

Role: _____________________________________

Signature: ________________________________
```

---

## Reconciliation Metadata

**Prior Reconciliation Package:** PHASE4_HUMAN_DECISION_RECONCILIATION
```
Commitment: f129d6f230b5dec8b47913f06dab6a60b45125be8b68dc2bda458a5a63c94d44
```

**Blocker Reconciliation Package:** PHASE4_FINAL_APPROVAL_BLOCKER_RECONCILIATION

**Blockers Corrected:**
1. Method label verification (Method C = Blinded re-estimation ✓)
2. Master seed arithmetic (3469967646 → 3485535768 ✓)
3. Nomenclature correction ("4-SHA256" → "COMPOSITE_4_FIELD_SOURCE_IDENTITY" ✓)
4. Validity gate completeness (3 gates → full 8+5+2 gate set ✓)
5. N=30 interpretation (operational/feasibility-driven, not CLT-justified ✓)
6. Order rule specification (deterministic alternating pattern ✓)

**All critical blockers resolved. Ready for human review.**

---

## Post-Approval Actions

**After signed approval received:**

1. Archive signed template with SHA256 commitment
2. Generate formal seed list from approved master seed and N
3. Freeze seed list with SHA256 commitment
4. Execute N paired blocks under approved protocol
5. Enforce all validity gates
6. Create multi-stage evidence freeze packages
7. Perform statistical analysis only after run evidence freeze complete

**Formal experiment execution gate:** BLOCKED until signed approval archived.
