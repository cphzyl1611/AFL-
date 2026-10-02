# Protocol Master Seed Selection Rule

## Issue: Discretionary vs Deterministic Derivation

**Original Recommendation:**

```
D11_PROTOCOL_MASTER_SEED = 20260921
RATIONALE = Protocol design date (2026-09-21)
```

**Problem:**

The date-based seed is **reproducible** but introduces **post-hoc discretion**:
- Why this date? (design date vs approval date vs execution date)
- Could be influenced by intermediate results or timing
- Arbitrary choice among many valid integers

## Comparison of Selection Methods

### Method A: Human-Chosen Fixed Integer

**Examples:**
- Lucky number (e.g., 42, 1337)
- Memorable date (20260921)
- Arbitrary large integer

**Advantages:**
- Simple, human-interpretable
- Can encode meaningful metadata (date, version)

**Disadvantages:**
- Introduces post-hoc discretion
- No algorithmic justification
- Could be gamed if intermediate results are visible

### Method B: Protocol Design Date

**Example:**
```
20260921  (protocol design completion: 2026-09-21)
```

**Advantages:**
- Reproducible from documented event
- Documents temporal context
- Conventional practice

**Disadvantages:**
- **Discretionary**: Why design date, not approval date or execution date?
- Vulnerable to "try again tomorrow" if results are unfavorable
- Not algorithmically derived from frozen content

### Method C: Deterministic Derivation from Design Package Commitment

**Algorithm:**

```python
# Derive master seed from frozen protocol design commitment SHA256
design_commitment = "cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19"

# Extract first 8 hex characters and convert to integer
master_seed = int(design_commitment[:8], 16)

# Result: master_seed = 3469967646
```

**Advantages:**
- **Zero post-hoc discretion**: Seed is uniquely determined by frozen protocol content
- Cannot be gamed: commitment is frozen before seed is derived
- Algorithmically justified: one-to-one mapping from protocol → seed
- Reproducible: anyone with the commitment can derive the same seed
- Self-documenting: seed proves protocol was frozen before seed list generation

**Disadvantages:**
- Less human-interpretable than a date
- Slightly more complex to explain

### Method D: Hybrid (Commitment-Derived with Human Override Option)

**Algorithm:**

```python
# Default: derive from commitment
master_seed = int(design_commitment[:8], 16)  # 3469967646

# Human override: if reviewers have strong preference, allow explicit choice
# Requires documented justification in approval template
```

**Advantages:**
- Deterministic by default
- Allows human override if scientifically justified
- Balances algorithmic rigor with human governance

## Reconciled Recommendation

**Primary Recommendation: Method C (Deterministic Derivation from Design Package Commitment)**

**Algorithm:**

```python
import hashlib

# Phase-4 design package commitment (frozen)
design_commitment = "cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19"

# Derive master seed: first 8 hex digits → 32-bit unsigned integer
master_seed = int(design_commitment[:8], 16)

# Result: 3469967646
```

**Verification:**

```python
>>> design_commitment = "cfc10e1861161522f8187ae7c9aa8a98d834578252bc15e33957a97e2fc44b19"
>>> int(design_commitment[:8], 16)
3469967646
```

**Rationale:**

1. **Minimizes post-hoc discretion**: Seed is uniquely determined by frozen protocol
2. **Cannot be gamed**: Design commitment exists before seed derivation
3. **Algorithmically justified**: Deterministic one-to-one mapping
4. **Self-documenting**: Anyone can verify seed derivation from commitment
5. **Cryptographic binding**: Links seed list generation to specific protocol version

**Fallback Recommendation: Method B (Protocol Design Date)**

**Acceptable only if:**
- Human reviewers prefer human-interpretable seed
- Date is clearly documented as protocol design completion date
- No intermediate results are visible before seed selection

**Not Recommended: Method A (Arbitrary Human Choice)**

Introduces unnecessary discretion without algorithmic justification.

## Deterministic Seed Generation Procedure (After Approval)

**Once D1/D7 determine N, and master seed is selected:**

```python
import random

# Inputs (from approved decisions)
N = 30  # Example: D7 fixed N
PROTOCOL_MASTER_SEED = 3469967646  # Derived from design commitment

# Generate N distinct seeds deterministically
prng = random.Random(PROTOCOL_MASTER_SEED)
seed_list = [prng.randint(1, 2**31 - 1) for _ in range(N)]

# Freeze seed list with SHA256 commitment
import hashlib
import json
seed_list_json = json.dumps(seed_list, sort_keys=True, indent=2)
seed_list_commitment = hashlib.sha256(seed_list_json.encode('utf-8')).hexdigest()

# Record in execution freeze package
```

**Note:** Do not generate seed list until human approval authorizes N and master seed.

## Reconciled Status

```
RECOMMENDED_MASTER_SEED_SELECTION_RULE = Deterministic derivation from design commitment
DETERMINISTIC_ALGORITHM = int(design_commitment[:8], 16)
DERIVED_MASTER_SEED = 3469967646
FALLBACK_RULE = Protocol design date (20260921)
POST_HOC_DISCRETION_MINIMIZED = YES
```

## Human Decision Required

```
D11_MASTER_SEED_SELECTION_RULE = [commitment_derived | design_date | human_chosen]

IF D11 = commitment_derived:
  MASTER_SEED = 3469967646  (automatically derived, no further input required)

IF D11 = design_date:
  MASTER_SEED = 20260921  (protocol design date)

IF D11 = human_chosen:
  MASTER_SEED = <positive integer specified by human reviewer with justification>
```

## Notes

- Commitment-derived seed is scientifically most rigorous
- Seed list generation occurs only after human approval of D11 and N
- All three methods are reproducible; commitment-derived minimizes discretion
