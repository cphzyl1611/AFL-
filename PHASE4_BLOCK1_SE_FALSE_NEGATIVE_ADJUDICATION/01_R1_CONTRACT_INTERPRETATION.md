# R1 Contract Interpretation

**Created:** 2026-09-21  
**Subject:** Phase 4 R1 artifact_contract gate semantic scope

---

## Frozen R1 Contract Language

### Source: 08_FULL_VALIDITY_GATE_CONTRACT.json

```json
{
  "gate_name": "artifact_contract",
  "applies_to": "universal",
  "condition": "= PASS",
  "description": "All required run artifacts (fuzzer_stats, manifest JSON, trace files) are present and parseable"
}
```

**Key observation:** The description explicitly enumerates three artifact categories:
1. fuzzer_stats
2. manifest JSON
3. trace files

**Not mentioned:** nv_probe.json, nv_state_db.json

---

## Validator Implementation

### Source: scripts/run_alfresco_bounded_feedback.py

```python
execution_required = {
    'status': True,
    'status_seq': True,
    'probe': True,          # nv_probe.json
    'state_db': True,       # nv_state_db.json
    'state_trace': True,
    'afl_stats': True,
    'mab_journal': True,
    'seed_selection_audit': True,
    'body_valid_stats': True
}
```

**Validator behavior:** Requires probe and state_db files in addition to the three categories listed in the R1 frozen contract description.

---

## Semantic Reconciliation

### R1 Contract Semantically Requires nv_probe.json?

**NO**

- The frozen description does not explicitly list probe as required
- "trace files" could be interpreted to include probe, but probe is not a trace file — it is a state snapshot file written by nv_state_probe.update_state()
- The contract uses precise enumeration ("fuzzer_stats, manifest JSON, trace files") rather than open-ended language

### R1 Contract Semantically Requires nv_state_db.json?

**NO**

- Same reasoning as probe
- state_db is a persistent state database, not a trace file or manifest
- Not explicitly enumerated in the frozen contract description

### R1 Contract Semantically Requires body_score_pass > 0?

**NO**

- No validity gate in 08_FULL_VALIDITY_GATE_CONTRACT.json specifies body_score_pass > 0
- Gate 09_FAILURE_EXCLUSION_INTERRUPTION_RULES.md explicitly states: "If security_state_new_total = 0: This is a valid scientific observation, NOT a failure"
- The body_score_pass=0 outcome is a valid endpoint measurement, not a failure condition

---

## Validator vs Contract Alignment

**Conclusion:** The validator implementation is **stricter** than the frozen R1 semantic contract.

The validator requires artifacts (probe, state_db) that are not explicitly listed in the frozen contract description. This creates a false negative when architecturally correct runs (body_score_pass=0, zero HTTP requests sent) produce the scientifically expected artifact set without these files.

---

## Interpretation Confidence

**HIGH**

The frozen contract language uses explicit enumeration rather than catch-all language. The absence of probe and state_db from the enumeration is semantically meaningful under standard contract interpretation principles.
