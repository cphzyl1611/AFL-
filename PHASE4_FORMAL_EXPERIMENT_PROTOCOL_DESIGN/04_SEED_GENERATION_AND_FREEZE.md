# Seed Generation and Freeze

## Seed Generation Requirements

All seeds must be:

- Generated deterministically from a preregistered procedure
- Frozen before the first real run
- Recorded in the protocol manifest
- Not chosen after seeing any outcomes
- Not replaced if a run fails

## Proposed Seed Generation Method

**Deterministic PRNG Derivation:**

```
Input:
  - PROTOCOL_MASTER_SEED: a fixed integer (human-chosen, preregistered)
  - N: number of paired seed blocks (human-chosen, preregistered)

Procedure:
  1. Initialize Python random.Random(PROTOCOL_MASTER_SEED)
  2. Generate N distinct positive integers in range [1, 2^31 - 1]
  3. Store as SEED_LIST = [seed_1, seed_2, ..., seed_N]
  4. Freeze SEED_LIST in protocol manifest before first real run

Output:
  - Exact seed list used for all N paired blocks
```

**Deterministic Seed Script (Reference Implementation):**

```python
import random
import json

def generate_protocol_seeds(master_seed: int, n: int) -> list[int]:
    """Generate N deterministic AFL++ seeds from a protocol master seed."""
    rng = random.Random(master_seed)
    seeds = []
    for _ in range(n):
        seed = rng.randint(1, 2**31 - 1)
        seeds.append(seed)
    return seeds

def freeze_seed_manifest(master_seed: int, n: int, output_path: str):
    """Generate and freeze seed list to JSON manifest."""
    seeds = generate_protocol_seeds(master_seed, n)
    manifest = {
        "protocol_master_seed": master_seed,
        "n_pairs": n,
        "seed_list": seeds,
        "generation_method": "Python random.Random(master_seed).randint(1, 2**31 - 1)",
        "frozen": True
    }
    with open(output_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    return seeds
```

## Seed Freeze Timing

**Before First Real Run:**

The exact seed list must be frozen and committed to the protocol manifest before the first paired block is executed.

**After Freeze:**

- No seeds may be added
- No seeds may be removed
- No seeds may be replaced due to run failures
- The planned denominator remains N

## Seed List Recording

**Protocol Manifest Must Include:**

```json
{
  "protocol_master_seed": <integer>,
  "n_pairs": <integer>,
  "seed_list": [seed_1, seed_2, ..., seed_N],
  "generation_method": "<exact procedure>",
  "frozen_timestamp": "<ISO 8601>",
  "frozen_by": "<human reviewer>",
  "sha256_seed_list": "<hash of seed_list JSON array>"
}
```

## Run Manifest Recording

Every run manifest must record:

- Which seed from the frozen seed list was used
- Position in the seed list (pair index)
- Whether the run completed or failed

## Failure and Exclusion Policy

**If a paired block fails validity gates:**

- The failed block is excluded from analysis
- The seed is **not** replaced
- The next seed in the frozen list is used
- The planned denominator remains N
- The failure is recorded in the evidence package

**Denominator Integrity:**

The denominator for the primary analysis is always the number of preregistered seeds N, not the number of successful paired blocks.

If k paired blocks fail, the analysis reports:

- N total preregistered blocks
- (N - k) valid blocks contributing to the estimate
- k exclusions with reasons

## No Post-Hoc Seed Selection

The protocol forbids:

- Choosing seeds after observing outcomes
- Replacing seeds that produced undesirable results
- Reordering the seed list based on intermediate results
- Generating additional seeds after seeing preliminary estimates

## Human Decision Required

```
H1_SEED: What is the protocol master seed?
H2_SEED: What is N (number of paired blocks)?
```

These decisions must be made and frozen before formal execution begins.

## Phase-3 Pilot Seeds (Reference Only)

The Phase-3 pilot used seeds [100, 200, 300, 400, 500] as an ad-hoc choice for engineering validation.

The formal study must use a new, preregistered seed generation procedure independent of the Phase-3 pilot.

## Recommendation

Use the deterministic PRNG method above with:

- A human-chosen PROTOCOL_MASTER_SEED (e.g., 20260921 or another meaningful integer)
- N determined by the sample-size plan (see 05_SAMPLE_SIZE_PLAN.md)

This method is simple, deterministic, reproducible, and widely accepted in computational experiments.

## Notes

- The seed list is frozen before execution, not generated iteratively
- Seed generation is independent of all run outcomes
- The exact seed list becomes part of the protocol's reproducibility contract
- Any replication or extension study can verify the seed list by re-running the generation script with the same master seed
