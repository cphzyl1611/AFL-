# Alfresco Multi-Interface Expansion

This directory contains evidence and results from AFL++ NV framework capability expansion to multiple Alfresco REST API interfaces beyond the original `metadata_update` scenario.

## Structure

```
alfresco_multiinterface_expansion/
├── README.md                                    # This file
├── alfresco_multiinterface_round1_completion_report.md  # Round 1 executive summary
└── round1_content_update_evidence/              # Complete evidence package
    ├── EVIDENCE_MANIFEST.txt                    # Detailed manifest
    ├── PACKAGE_ROOT_HASH.txt                    # Cryptographic commitment
    ├── SHA256SUMS.txt                           # File checksums
    ├── artifact_report.json                     # Runner contract validation
    ├── readback.json                            # Byte-exact content verification
    ├── task.json                                # Task configuration
    ├── target.json                              # Runtime target config
    ├── nv_state_trace.jsonl                     # HTTP state transitions
    ├── nv_http_status.json                      # Final HTTP snapshot
    ├── fuzzer_stats                             # AFL++ statistics
    ├── mab_updates.jsonl                        # Multi-armed bandit journal
    ├── executions.jsonl                         # Execution lifecycle ledger
    └── seed_selection.jsonl                     # Seed selection audit
```

## Round 1: content_update (COMPLETE ✅)

**Interface**: `PUT /nodes/{nodeId}/content`  
**Status**: SUCCESS  
**Backend**: AE (alfresco_ae_v1) - READY  
**Date**: 2026-09-22  

### Key Results

- ✅ Pilot execution: 3 valid executions, all HTTP 2xx responses
- ✅ Readback verification: byte-exact content hash (SHA-256)
- ✅ Artifact contract: All gates PASS, runner exit_code=0
- ✅ MAB feedback: 2 committed updates, journal reconciled
- ✅ Seed selection audit: Valid and reconciled

### Backend Determination

**AE Backend (alfresco_ae_v1)**: READY ✅
- 32-dim text content features (`extract_text_content_features`)
- Pilot execution successful
- All validity gates passed

**SE Backend (sefanogan_es_reference)**: NOT_APPLICABLE ⚠️
- Requires 38-dim metadata features (JSON field structure)
- content_update uses text/plain content
- Design-level incompatibility: 32-dim ≠ 38-dim

### Code Modifications

Three fixes applied to `scripts/run_alfresco_bounded_feedback.py`:

1. **Line 510-516**: Dynamic endpoint lookup in `seed_request_metadata()`
2. **Line 1516-1522**: Exclude `body_valid_stats` for content_update
3. **Line 1268-1293**: Align content readback with canonical schema

All modifications preserve existing metadata_update/multipart_upload functionality.

---

## Interface Coverage Matrix

| Interface | Method | Content-Type | AE Backend | SE Backend | Status |
|-----------|--------|--------------|------------|------------|--------|
| `metadata_update` | POST | application/json | ✅ READY | ✅ READY | Production |
| `multipart_upload` | POST | multipart/form-data | ❓ TBD | ❓ TBD | Pending |
| `content_update` | PUT | text/plain | ✅ READY | ⚠️ NOT_APPLICABLE | Round 1 COMPLETE |

---

## Evidence Integrity

All evidence artifacts include SHA-256 checksums in `SHA256SUMS.txt`. Package root hash computed from:
- SHA256SUMS.txt
- EVIDENCE_MANIFEST.txt

See `PACKAGE_ROOT_HASH.txt` for cryptographic commitment.

---

## Security Constraints

All work in this directory observes these constraints:
- ❌ No Phase-4 metadata_update evidence modified
- ❌ No metadata_update experiments rerun
- ❌ No model thresholds changed
- ❌ No AFL++ C code modified
- ❌ No git commits without explicit approval
- ❌ No large campaigns
- ❌ No AE/SE superiority claims

---

## References

- Primary orchestrator: `../scripts/run_alfresco_bounded_feedback.py`
- AE model metadata: `../model_stage/models/alfresco_ae_v1_meta.json`
- SE model metadata: `../model_stage/models/sefanogan_es_reference_meta.json`
- Feature extraction: `../model_stage/alfresco_feature_extraction.py`
