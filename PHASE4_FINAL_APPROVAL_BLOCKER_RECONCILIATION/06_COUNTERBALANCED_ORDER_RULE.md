# Counterbalanced Order Rule

## BLOCKER 6: Execution Order Specification

**Issue:** Prior reconciliation recommended "counterbalanced alternating" but did not freeze the exact deterministic rule.

**Prior Reconciliation (INCOMPLETE):**

```
EXECUTION_ORDER_RECOMMENDATION = Counterbalanced alternating
```

This is correct in spirit but lacks operational precision.

## Exact Deterministic Rule

**For each paired block i (i = 1, 2, ..., N):**

```
if i is odd:
    run AE first, then SE
else:
    run SE first, then AE
```

**Formal specification:**

```
ORDER(i) = AE-first  if (i mod 2) = 1
ORDER(i) = SE-first  if (i mod 2) = 0
```

**Concrete example for N=30:**

```
Block 1: AE-first
Block 2: SE-first
Block 3: AE-first
Block 4: SE-first
...
Block 29: AE-first
Block 30: SE-first
```

**Balance:**
- AE-first blocks: {1, 3, 5, ..., 29} → 15 blocks
- SE-first blocks: {2, 4, 6, ..., 30} → 15 blocks

**Exact 50/50 balance for any even N.**

## Why Counterbalanced Order

**Scientific motivation:**

1. **Separates order effects from backend effects:** If execution order systematically affects outcomes (e.g., first run warms caches, depletes server resources, or triggers rate limiting), counterbalancing ensures both models experience first-run and second-run conditions equally.

2. **Phase-3 did not test order sensitivity:** Phase-3 used fixed AE-first order for all 5 paired blocks. This was pragmatic but means order effects are confounded with backend effects.

3. **Conservative design:** Counterbalancing is standard practice when order effects are plausible but unmeasured.

## What Counterbalancing Does NOT Do

**Important limitations:**

- Does NOT eliminate order effects
- Does NOT guarantee order effects are small
- Does NOT justify ignoring order as a factor

**What it DOES do:**

- Ensures order effects contribute equally to both AE and SE aggregate outcomes
- Prevents systematic bias favoring whichever backend typically runs first
- Allows post-hoc order effect estimation if warranted

## Implementation Requirements

**Execution contract:**

```
EXECUTION_ORDER_RULE = DETERMINISTIC_ALTERNATING
BLOCK_i_ORDER = AE-first if (i mod 2) = 1, SE-first if (i mod 2) = 0
ORDER_DECISION_TIMING = BEFORE_OUTCOMES_OBSERVED
ORDER_BALANCE_FOR_N30 = 15 AE-first, 15 SE-first
```

**Prohibition:**

```
ADAPTIVE_ORDER_SELECTION = FORBIDDEN
POST_HOC_ORDER_CHOICE = FORBIDDEN
```

Order must be determined by block index alone, never by observed outcomes.

## Seed Assignment Interaction

**Seed list:** `[seed_1, seed_2, ..., seed_30]` (generated deterministically from master seed)

**Block i execution:**

```python
seed_i = seed_list[i - 1]  # 1-indexed block → 0-indexed list

if i % 2 == 1:
    # AE-first block
    run_ae(seed=seed_i, block_id=i, order="AE-first")
    run_se(seed=seed_i, block_id=i, order="AE-first")
else:
    # SE-first block
    run_se(seed=seed_i, block_id=i, order="SE-first")
    run_ae(seed=seed_i, block_id=i, order="SE-first")
```

**Critical:** The same seed is used for both AE and SE within each block, preserving the paired design.

## Run Manifest Provenance

**Each run manifest JSON must record:**

```json
{
  "block_id": 1,
  "seed": 1234567890,
  "backend": "alfresco_ae_v1",
  "execution_order": "AE-first",
  "order_position": "first"
}
```

```json
{
  "block_id": 1,
  "seed": 1234567890,
  "backend": "sefanogan_es_reference",
  "execution_order": "AE-first",
  "order_position": "second"
}
```

This allows post-hoc order effect analysis if Δᵢ shows systematic pattern by order.

## Corrected Status

```
EXECUTION_ORDER_RULE = DETERMINISTIC_ALTERNATING
COUNTERBALANCED_RULE = BLOCK_i_AE_FIRST_IF_ODD_SE_FIRST_IF_EVEN
ORDER_BALANCE_FOR_N30 = 15_AE_FIRST_15_SE_FIRST
ORDER_DECISION_TIMING = PRE_SPECIFIED_BY_BLOCK_INDEX
ADAPTIVE_ORDER_FORBIDDEN = YES

PHASE3_ORDER_SENSITIVITY_TESTED = NO
PHASE3_USED_FIXED_AE_FIRST = YES (all 5 blocks)
COUNTERBALANCING_RATIONALE = CONSERVATIVE_DECONFOUNDING (not empirical evidence)
```

## Notes

- Exact 50/50 balance for N=30
- Order must not depend on observed outcomes
- Run manifests record order provenance for post-hoc analysis
- Counterbalancing is a precaution, not a guarantee order effects are negligible
