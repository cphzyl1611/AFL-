# Phase 4 — Approved Design Summary

**Approval Date:** 2026-09-21

**Human Approval Statement:**
```
批准按最终 approval template 的推荐值执行 D1–D15
```

**Interpretation:** All recommended values in the final bound D1-D15 approval template are approved.

---

## Primary Estimand (D1)

**Approved:** Mean paired difference for `security_state_new_total`

```
θ = E[Δᵢ]
where Δᵢ = security_state_new_total(SE, seed_i) - security_state_new_total(AE, seed_i)
```

---

## Secondary Endpoints (D2)

**Exploratory endpoints (descriptive analysis only):**

1. `security_state_total` (cumulative security state discoveries)
2. `body_score_pass` (number of valid bodies by score threshold)
3. `body_score_reject` (number of rejected bodies by score threshold)

**No multiplicity correction.** Not confirmatory endpoints.

---

## Paired Design (D4)

**Approved:** Paired comparison design

- AE and SE use identical seed within each block
- Estimand is mean paired difference (not independent-samples)

---

## Sample Size (D7, D8)

**Method:** D (Fixed pragmatic N)

**N:** 30 paired blocks

**N=30 Role:** OPERATIONAL_FEASIBILITY_DRIVEN
- NOT power-justified
- NOT precision-justified
- CLT heuristic reference is DESCRIPTIVE_ONLY (not prescriptive)
- Human acceptance of inferential limitations: YES

**Justification:**
- Feasibility multiplier: 6× Phase-3 pilot size (5 → 30)
- Resource constraints: 60 runs total (30 AE + 30 SE)
- Conventional heuristic reference: N≥30 for CLT applicability

**Limitations acknowledged:**
- Study may be underpowered for small effect sizes
- Confidence intervals may be wide
- Primary emphasis on estimation (point estimate + 95% CI), not hypothesis testing

---

## Execution Order (D5)

**Approved:** Counterbalanced alternating order

**Rule:** Block i → AE-first if (i mod 2) = 1, SE-first if (i mod 2) = 0

**For N=30:**
- 15 AE-first blocks
- 15 SE-first blocks

**Rationale:** Separates order effects from backend effects (Phase-3 did not test order sensitivity)

---

## Master Seed (D9)

**Approved:** Commitment-derived deterministic seed

**Derivation:**
```
design_commitment = "cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19"
master_seed = int(design_commitment[:8], 16)
Result: 3485535768
```

**Domain:** 32-bit unsigned integer

---

## Source Baseline Identity (D10)

**Approved:** Composite 4-field source identity

**Type:** COMPOSITE_4_FIELD_SOURCE_IDENTITY

**Four components:**
1. `git_head_commit`: 87bee5c6fa1f0a8f7d6df2a301df3b7f879aa408
2. `runner_sha256`: 7acb5192fc7c4c6fbb3f24155d94eb68809cca0306d7600855c6504444bf3650
3. `tracked_diff_sha256`: 686a1e65035ac38145b606f4c765f6a1220e6f9f9f2206338354bd2a84112140
4. `canonical_12file_manifest_sha256`: 26c2e4f3871d7deffb4ab7fc356f6973b8f01b5985d189ed6afcc79b251a2c5b

**Working tree status:** DIRTY (intentionally preserved — contains critical untracked files)

---

## Fuzzing Budget (D6)

**Approved:** Same as Phase-3 (validated in 5+5 pilot)

```
MAX_TEST_CASES = 5
TIME = 60 seconds
```

---

## Validity Gates (D3)

**Approved:** Full validity gate set (8 universal + 5 SE-specific + 2 AE-specific)

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
- `checkpoint_sha256 = 4eace87ac7d7759a729ff98916a5acead4154c803c53884e3ca7f27570dbf20d`
- `metadata_sha256 = 2a73ccc3729a3734ab9901b4474feb73d4d42f912ccbc717af48f970ab568226`
- `metadata_input_dim = 32`
- `threshold = 1.2847454080581664`
- `backend = sefanogan_es_reference`

**AE-specific gates:**
- `backend = alfresco_ae_v1`
- `threshold = 1.623614`

**Paired block exclusion:** If either run in a pair fails any gate, exclude entire paired block (no replacement).

---

## Failure Replacement (D14)

**Approved:** No replacement (intent-to-treat paired blocks)

**Exclusion rule:** If either run in paired block fails validity gates, exclude entire block

**Note:** `security_state_new_total=0` is a valid scientific observation, not a failure

---

## Stopping Rule (D11)

**Approved:** Fixed-N design (no interim analysis, no early stopping)

All N paired blocks must complete (excluding validity gate failures)

---

## Statistical Analysis (D12, D13)

**Primary deliverable:** Point estimate θ̂ and 95% bootstrap confidence interval

**CI method:** Bootstrap percentile method
- 10,000 iterations
- Paired resampling

**Hypothesis test:** Optional supplementary analysis (two-sided permutation test, α=0.05)

---

## Multi-Stage Evidence Freeze (D15)

**Approved:** Five-stage evidence freeze protocol

**Stages:**
1. Protocol Design Freeze (this approval)
2. Reconciliation Freeze (after execution)
3. Execution Log Freeze
4. Run Evidence Freeze
5. Campaign Freeze

**Each stage:** SHA256 commitment of freeze package

---

## Authoritative Commitments

**Phase-4 design package:**
```
cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19
```

**Phase-3 evidence freeze:**
```
517cd241b85632142a8e74322bb284ce3e5832722cd5afdb2702dbac7c6415a8
```

**Approval-blocker reconciliation:**
```
7aede8f3266322c70835d8c82fd88015533a4968f95bf7739fc85f38c0cfa6c3
```

**Final approval template:**
```
e825bfc9385b7ce7498824574c7012809afa3fb9e17d1776170d2c8f1644568e
```

---

## Execution Constraints

- No execution until formal execution freeze approved
- All 15 decisions approved with explicit human authorization
- All validity gates enforced as specified
- No post-hoc changes to frozen design decisions
- Multi-stage evidence freeze protocol followed
