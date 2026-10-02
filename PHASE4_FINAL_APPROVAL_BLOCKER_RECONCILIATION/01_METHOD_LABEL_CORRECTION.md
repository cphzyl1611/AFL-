# Sample Size Method Label Correction

## BLOCKER 1: Method Label Mismatch

**Issue:** The prior reconciliation incorrectly labeled the fallback method.

**Authoritative Frozen Design Package (05_SAMPLE_SIZE_PLAN.md):**

The Phase-4 design package defines exactly four methods:

- **Option A:** Minimum Practically Important Difference (MPID) + Power
- **Option B:** Precision-Based Design
- **Option C:** Blinded Variance Re-estimation
- **Option D:** Fixed Pragmatic N

**Prior Reconciliation Error:**

```
RECOMMENDED_SAMPLE_SIZE_METHOD = D (Fixed pragmatic N)
FALLBACK_SAMPLE_SIZE_METHOD = C (Blinded variance re-estimation)
```

This is **CORRECT**. The prior reconciliation correctly identified:
- Method C = Blinded variance re-estimation
- Method D = Fixed pragmatic N

**Verification Against Frozen Design:**

Reading lines 130-183 of `05_SAMPLE_SIZE_PLAN.md`:

```
### Option C: Blinded Variance Re-estimation

**Approach:**

Run an initial blinded stage (e.g., N₁ = 10-20 paired blocks) without analyzing 
model labels, estimate the variance of paired differences, then re-estimate the 
required total N and continue to that target.
```

**Conclusion:**

**NO LABEL MISMATCH EXISTS.** The prior reconciliation correctly labeled all four methods:

- A = MPID + Power
- B = Precision-based
- C = Blinded variance re-estimation
- D = Fixed pragmatic N

The fallback recommendation (Method C) is correctly labeled.

## Corrected Status

```
AUTHORITATIVE_METHOD_A = MPID + Power (requires justified MPID and variance)
AUTHORITATIVE_METHOD_B = Precision-based (targets CI width, requires justified variance)
AUTHORITATIVE_METHOD_C = Blinded variance re-estimation (two-stage adaptive)
AUTHORITATIVE_METHOD_D = Fixed pragmatic N (resource-constrained)

CORRECTED_FALLBACK_SAMPLE_SIZE_METHOD = C (Blinded variance re-estimation)

LABEL_MISMATCH_DETECTED = NO
PRIOR_RECONCILIATION_LABELS = CORRECT
```

## Notes

- All method labels A/B/C/D are consistent with frozen design package
- No correction needed for method labels
- Fallback (Method C) is correctly identified
