# Execution Order Strategy Reconciliation

## Issue: Order Sensitivity Empirical Basis

**Original Recommendation Statement:**

```
RECOMMENDED_ORDER_STRATEGY = Fixed (AE first)
RATIONALE = "Phase-3 validated, simpler, no order sensitivity observed"
```

**Problem:**

The phrase "no order sensitivity observed" is **unsupported** by Phase-3 evidence.

Phase-3 used **fixed AE-first order for all 10 runs**, therefore:
- Order sensitivity was **not experimentally tested**
- No counterbalanced or randomized comparison was performed
- Cannot empirically rule out order effects from fixed-order data alone

## Phase-3 Evidence: What Was Actually Observed

**Phase-3 Execution Pattern:**

All 5 paired blocks used fixed AE-first order:

```
Block 1: AE(seed_1) → reset → SE(seed_1)
Block 2: AE(seed_2) → reset → SE(seed_2)
Block 3: AE(seed_3) → reset → SE(seed_3)
Block 4: AE(seed_4) → reset → SE(seed_4)
Block 5: AE(seed_5) → reset → SE(seed_5)
```

**What Phase-3 Validated:**

✓ Baseline reset protocol works (both runs start from identical coverage baseline)
✓ Fixed AE-first order is operationally feasible
✓ Both backends produce valid runs under this protocol
✓ Paired design structure is executable

**What Phase-3 Did NOT Test:**

✗ Whether SE-first order would produce different results
✗ Whether order effects exist (temporal drift, carryover, incomplete reset)
✗ Whether counterbalanced order changes paired differences

## Corrected Order Strategy Evaluation

### Option 1: Fixed AE-First (Original Phase-3 Pattern)

**Structure:**

```
For all N paired blocks:
  AE(seed_i) → validate → reset → SE(seed_i) → validate
```

**Advantages:**
- Simpler protocol (no randomization infrastructure)
- Direct continuity with Phase-3 validated procedure
- Operationally straightforward

**Disadvantages:**
- **Confounds order with backend**: AE always runs first, SE always runs second
- If order effects exist (temporal drift, incomplete reset), they are aliased with backend differences
- Cannot separate "AE vs SE" from "first vs second"

**Assumption Required:**
- Baseline reset is complete and effective
- No temporal drift within pairs
- No carryover effects across runs

### Option 2: Fixed SE-First

**Structure:**

```
For all N paired blocks:
  SE(seed_i) → validate → reset → AE(seed_i) → validate
```

**Advantages:**
- Simpler protocol (no randomization)
- Tests whether Phase-3 results replicate under reversed order

**Disadvantages:**
- Breaks continuity with Phase-3 (different order)
- Still confounds order with backend (opposite direction)

### Option 3: Deterministic Counterbalanced Order

**Structure:**

```
Preregistered order schedule:
  Blocks 1-15: AE-first
  Blocks 16-30: SE-first

or alternating:
  Odd blocks: AE-first
  Even blocks: SE-first
```

**Advantages:**
- **Separates order effects from backend effects**
- Balanced design allows analysis of order as blocking factor
- Deterministic (fully reproducible from seed list)
- No randomization infrastructure needed

**Disadvantages:**
- More complex protocol documentation
- Analysis must account for order as covariate/block

### Option 4: Deterministic Randomized Balanced Order

**Structure:**

```
Derive order_i from deterministic PRNG:
  random.Random(ORDER_SEED).choice(['AE_first', 'SE_first']) for each i
  Constrain to ensure N/2 of each order type
```

**Advantages:**
- **Controls for order effects via randomization**
- Balanced (N/2 AE-first, N/2 SE-first)
- Fully reproducible from ORDER_SEED
- Standard practice in crossover/paired designs

**Disadvantages:**
- Requires randomization seed and balance verification
- Order must be preregistered before first run
- Analysis should account for order as stratification factor

## Reconciled Recommendation

**Primary Recommendation: Option 3 (Deterministic Counterbalanced Order)**

**Rationale:**

1. **Scientific rigor:** Separates order effects from backend effects
2. **Reproducibility:** Fully deterministic (no randomization infrastructure)
3. **Simplicity:** Straightforward alternating or block-based pattern
4. **Robustness:** If order effects exist, they are controlled; if not, no harm done
5. **Phase-3 continuity:** Half the blocks use the validated AE-first pattern

**Recommended Implementation:**

```
Alternating pattern:
  - Odd-numbered blocks (1, 3, 5, ..., 29): AE-first
  - Even-numbered blocks (2, 4, 6, ..., 30): SE-first
  
Result: 15 AE-first, 15 SE-first (perfectly balanced)
```

**Fallback Recommendation: Option 1 (Fixed AE-First)**

**Acceptable only if:**
- Human reviewers explicitly judge that order effects are negligible
- Baseline reset protocol is trusted to eliminate all carryover
- Operational simplicity is prioritized over order effect control
- Results will be interpreted with acknowledgment of order confounding

**Not Recommended: Option 2 (Fixed SE-First)**

Breaks Phase-3 continuity without gaining scientific benefit over Option 1.

## Corrected Status

```
ORDER_SENSITIVITY_EMPIRICALLY_ESTABLISHED = NO
PHASE3_ORDER_PATTERN = Fixed AE-first (all 10 runs)
PHASE3_BASELINE_RESET_VALIDATED = YES
ORDER_EFFECT_CONTROL_TESTED_IN_PHASE3 = NO

RECOMMENDED_ORDER_STRATEGY = Deterministic counterbalanced (alternating AE-first / SE-first)
FALLBACK_ORDER_STRATEGY = Fixed AE-first (Phase-3 continuity, assumes no order effects)
```

## Human Decision Required

```
D8_ORDER_STRATEGY = [fixed_ae_first | fixed_se_first | counterbalanced | randomized]

IF D8 = counterbalanced:
  D8_PATTERN = [alternating | first_half_ae_second_half_se]

IF D8 = randomized:
  D8_ORDER_SEED = <integer seed for deterministic randomization>
  D8_BALANCE_RULE = <ensure N/2 of each order type>
```

## Notes

- Phase-3 validated the baseline reset, not order-effect absence
- Counterbalanced order is scientifically more rigorous
- Fixed AE-first is acceptable if order effects are judged negligible by human reviewers
- Any order choice must be frozen before first formal run
