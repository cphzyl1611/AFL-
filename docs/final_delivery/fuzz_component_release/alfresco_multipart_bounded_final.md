# Alfresco Multipart Bounded Fuzzing Final Report

**Scope:** Alfresco multipart upload fuzzing only. Long-term stability and scale validation are intentionally not run.

## Final status

```text
ALFRESCO_MULTIPART_STATIC_LOOP             = PASS
ALFRESCO_MULTIPART_BOUNDED_FUZZ            = PASS
ALFRESCO_MULTIPART_REAL_VALIDATION_REJECT = PASS
ALFRESCO_MULTIPART_FIELD_VALUE_REAL        = PASS
ALFRESCO_MULTIPART_BOUNDARY_REAL           = PASS
ALFRESCO_MULTIPART_STRUCTURE_REAL          = PASS
ALFRESCO_MULTIPART_MULTI_ARM_REAL         = PASS
```

## Canonical inputs

```text
seed directory = in/alfresco_multipart_upload_bounded/
positive manifest = manifest.txt
positive seeds = seed_0.http, seed_1.http, seed_2.http
negative fixtures = negative_boundary_mismatch.http, negative_missing_filedata.http
```

The positive manifest contains exactly three regular files. Negative fixtures are separate and are not included in the positive AFL corpus. Positive seeds are full HTTP multipart requests containing `name`, `nodeType=cm:content`, `autoRename=true`, and `filedata`.

## One-shot reproduction

The bounded repository contains:

```text
scripts/reproduce_alfresco_multipart_bounded.py
```

Default mode performs canonical-seed validation and does not perform real writes:

```bash
cd /home/dministrator/AFLplusplus-alfresco-real-feedback
python3 scripts/reproduce_alfresco_multipart_bounded.py \
  --output-root /tmp/alfresco-multipart-reproduction-dry
```

Real mode requires explicit authorization and process-only credentials:

```bash
export ALFRESCO_USER='<ALFRESCO_USER>'
export ALFRESCO_PASS='<ALFRESCO_PASS>'
python3 scripts/reproduce_alfresco_multipart_bounded.py \
  --output-root /tmp/alfresco-multipart-reproduction-<run-id> \
  --allow-real-write \
  --max-test-cases 12 \
  --time-budget 45
```

The script runs, in order:

```text
negative validation
field_value
boundary
structure
```

It stops at the first failed stage and writes only a redacted summary outside the repository. It is a one-shot bounded experiment driver, not a long-running service, scheduler, CI campaign manager, or scale orchestrator.

## Real negative validation evidence

Final closure run:

```text
run root = /tmp/alfresco-multipart-closure-final-20260831
```

The two negative inputs were rejected before the upload client:

```text
boundary mismatch       = validation_reject, target_invoked=false
missing filedata        = validation_reject, target_invoked=false
HTTP requests sent      = 0
nodes created           = 0
parent children         = 88 before / 88 after
status records          = 2
```

No negative input committed an upload or MAB reward.

## Real three-arm evidence

Each arm used the canonical positive manifest, an independent run-root, one mutation scope, AFL++ stdin transport, and a dedicated Alfresco parent. Runs were serial and used the same current local service instance.

| Arm | Scope | HTTP 201 uploads | Read-back | Selected queues | Ledger/MAB | Runner |
|---|---|---:|---:|---:|---|---:|
| M0 | `field_value` | 21 | 21/21 | 0,1 | reconciled | 0 |
| M1 | `boundary` | 21 | 21/21 | 0,1 | reconciled | 0 |
| M2 | `structure` | 21 | 21/21 | 0,1 | reconciled | 0 |

For every arm:

```text
response node identity for every HTTP 201 = present
metadata read-back HTTP = 200
content read-back HTTP = 200
content size/hash comparison = pass for every successful upload
target/status identity mismatch = 0
unobserved execution = 0
seed-audit invalid = 0
artifact final result = pass
```

The final run produced 11 committed MAB updates and one pending cleanup per arm; execution ledger and MAB journal reconciled. Service-side automatic naming was recorded from the response envelope and used for read-back identity checks.

## Boundary and structure semantics

```text
field_value = changes filedata while preserving multipart envelope
boundary    = changes Content-Type boundary and all body delimiters consistently
structure   = adds a valid optional description part while retaining name/nodeType/filedata
```

The arm handshake is recorded through `NV_JSON_ARM_USED`. Existing metadata JSON mutation behavior remains covered separately.

## Existing static-loop boundary

The historical static-loop remains available and is reported separately:

```text
ALFRESCO_MULTIPART_STATIC_LOOP = PASS
```

It is not used as evidence for the bounded AFL++ result.

## Validation and release checks

```text
multipart focused tests = PASS
Alfresco bounded tests = PASS
Python syntax = PASS
git diff --check = PASS
C/AFL build = required before final integration report
secret scan = required before final integration report
```

## Explicit non-goals

```text
LONG_TERM_STABILITY = NOT_RUN_BY_SCOPE
SCALE_VALIDATION = NOT_RUN_BY_SCOPE
commit/push/merge = not performed by this closure plan
```
