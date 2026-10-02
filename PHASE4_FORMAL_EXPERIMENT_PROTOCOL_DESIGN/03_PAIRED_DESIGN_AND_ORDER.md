# Paired Design and Order

## Paired Design Structure

**Experimental Unit:**

One paired seed block consists of two runs sharing an identical integer seed:

```
Block_i:
  - AE run: seed_i → AE_security_state_new_total_i
  - SE run: seed_i → SE_security_state_new_total_i
  - Paired difference: Δᵢ = SE_i - AE_i
```

**Within-Pair Invariants:**

Both runs within a pair share:

- **Seed:** Identical integer seed for AFL++ PRNG
- **Source snapshot:** Identical git commit SHA
- **Initial corpus:** Identical input directory contents
- **Mutation scope:** Identical AFL++ mutation operators
- **Target identity:** Identical endpoint, host, configuration
- **Target baseline:** Identical security_state baseline reset between runs
- **Testcase budget:** Identical MAX_TEST_CASES parameter
- **Time budget:** Identical TIME_BUDGET parameter
- **Scorer lifecycle contract:** Identical RPC/trace/validity protocol

**Between-Pair Variation:**

Different seed blocks use different integer seeds drawn from the preregistered seed list.

## Within-Pair Execution Order

**Baseline Order (Recommended):**

```
For each seed_i:
  1. AE(seed_i)
  2. Validate AE run
  3. Reset target baseline (security_state)
  4. SE(seed_i)
  5. Validate SE run
```

**Rationale for Fixed Order:**

- Simpler protocol, no randomization infrastructure required
- Phase-3 pilot used this order successfully
- Both runs reset the target baseline, so persistent target state does not accumulate across the pair
- If target baseline reset is effective, order effects should be minimal

**Alternative: Counterbalanced/Randomized Order**

If order effects are a scientific concern (e.g., if target baseline reset might be incomplete, or if there are suspected carryover effects), the protocol can specify:

```
For each seed_i:
  - Draw order_i from a deterministic preregistered randomization
  - If order_i = "AE_first": run AE, validate, reset, run SE, validate
  - If order_i = "SE_first": run SE, validate, reset, run AE, validate
```

**Requirements for Randomized Order:**

- Deterministic randomization seed (frozen before execution)
- Exact order sequence preregistered in protocol manifest
- Balance rule: ensure approximately equal AE-first and SE-first blocks
- Order recorded in every run manifest
- Analysis accounts for order as a blocking/stratification factor if appropriate

**Human Decision Required:**

```
H5 = Fixed order (AE always first) vs randomized/counterbalanced order?
```

**Recommendation:**

Use fixed order (AE first) unless there is specific evidence or scientific concern that order effects would materially affect the estimand. The Phase-3 pilot did not observe any indication of order sensitivity, and the baseline reset protocol was validated.

## Baseline Reset Protocol

**Between-Run Reset:**

After each run within a pair, the target baseline must be reset to ensure the next run starts from an identical coverage baseline.

**Phase-3 Validated Reset Procedure:**

The Phase-3 pilot validated a baseline reset that includes:

- Clearing the fuzzer's security_state bitmap
- Resetting the security_state_total and security_state_new_total counters
- Ensuring the target application returns to a consistent initial state

**Evidence Requirement:**

Every run manifest must record:

- Baseline identity before the run
- Baseline identity after the reset (before the next run)
- Confirmation that security_state_new_total started at 0 for both runs in the pair

## Pairing Validity Gates

A paired block is valid for analysis only if **both** runs within the pair pass all validity gates:

- AE run: passes all AE validity gates
- SE run: passes all SE validity gates (including SE provenance)
- Both runs: baseline reset confirmed

If either run in a pair fails, the entire paired block is excluded from analysis (denominator preserved, failure recorded).

## No Replacement Policy

Failed paired blocks are not replaced. The planned denominator (number of preregistered seeds) remains fixed.

## Notes

- Pairing removes between-seed variance and isolates model-conditioned behavior differences.
- Within-pair order is recorded in every run manifest.
- The protocol does not choose order after observing outcomes.
- All order decisions are frozen before the first real run.
