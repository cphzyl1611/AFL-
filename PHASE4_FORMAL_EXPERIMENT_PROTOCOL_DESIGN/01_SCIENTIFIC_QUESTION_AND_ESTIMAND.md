# Scientific Question and Estimand

## Scientific Question

**Primary Question:**

Under a fixed and reproducible experiment contract, what is the difference in observed `security_state_new_total` counts between SE-backend and AE-backend scoring when applied to paired fuzzing runs with identical seeds, corpus, target, and execution budget?

**Formulation:**

This is a neutral, testable question about model-conditioned testing behavior. The question does not assume model superiority, coverage equivalence, or threshold comparability.

## Estimand

**Primary Estimand:**

The mean paired difference in `security_state_new_total` across N experimental units:

```
θ = E[Δᵢ]
where Δᵢ = SE_security_state_new_total_i - AE_security_state_new_total_i
```

**Experimental Unit:**

One experimental unit is a **paired seed block** consisting of:

- AE run: AE(seed_i) → AE_security_state_new_total_i
- SE run: SE(seed_i) → SE_security_state_new_total_i
- Paired difference: Δᵢ = SE_i - AE_i

**Pairing Rationale:**

Within each pair, AE and SE share:

- Identical integer seed
- Identical source snapshot
- Identical initial corpus
- Identical mutation scope
- Identical target identity
- Identical target baseline
- Identical testcase budget
- Identical time budget
- Identical scorer lifecycle contract

Pairing removes between-seed variance and isolates the model-conditioned behavior difference.

## Interpretation of Paired Differences

**Positive Δᵢ > 0:**

For seed i, the SE backend observed more `security_state_new_total` events than the AE backend.

**Zero Δᵢ = 0:**

For seed i, both backends observed the same `security_state_new_total` count.

**Negative Δᵢ < 0:**

For seed i, the AE backend observed more `security_state_new_total` events than the SE backend.

## What This Estimand Does Not Claim

- This estimand does not define "model superiority" as a protocol assumption.
- This estimand does not claim AE and SE are "equivalent" if Δᵢ = 0.
- This estimand does not compare raw threshold magnitudes as if score scales were directly comparable.
- This estimand does not extrapolate beyond the input distribution, target, and execution budget defined in the protocol.

## Phase-3 Pilot Observation (Descriptive Only)

Across the five paired seeds in the Phase-3 engineering pilot, AE and SE each observed `security_state_new_total = 1`, so all five observed paired deltas were 0.

This pilot observation is descriptive and does not constitute a scientific conclusion about the formal estimand.

## Binding to Phase-3 Freeze

This formal protocol binds to the Phase-3 evidence freeze package with commitment:

```
517cd241b85632142a8e74322bb284ce3e5832722cd5afdb2702dbac7c6415a8
```

The formal study does not reinterpret or rewrite Phase-3 evidence.
