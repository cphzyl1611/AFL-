# Alfresco Multipart Bounded Reproduction Manual

## Preconditions

Run from:

```bash
cd /home/dministrator/AFLplusplus-alfresco-real-feedback
```

Required runtime variables are process-only:

```bash
export ALFRESCO_USER='<ALFRESCO_USER>'
export ALFRESCO_PASS='<ALFRESCO_PASS>'
```

Do not place credentials in source files, seed files, task JSON, reports, or shell history intended for delivery.

The service must be reachable at the configured local Alfresco endpoint and the dedicated upload parent must already exist. The runner does not create a missing dedicated parent.

## Canonical inputs

```text
in/alfresco_multipart_upload_bounded/manifest.txt
in/alfresco_multipart_upload_bounded/seed_0.http
in/alfresco_multipart_upload_bounded/seed_1.http
in/alfresco_multipart_upload_bounded/seed_2.http
```

The positive manifest is the only AFL seed authority. The following are negative fixtures and must not be added to the positive manifest:

```text
negative_boundary_mismatch.http
negative_missing_filedata.http
```

All positive seeds are regular files and full HTTP multipart requests. They include `autoRename=true` so repeated bounded executions do not fail merely because of duplicate names.

## Dry-run

Dry-run validates the manifest and parser without contacting Alfresco or launching AFL:

```bash
python3 scripts/reproduce_alfresco_multipart_bounded.py \
  --output-root /tmp/alfresco-multipart-repro-dry-<run-id>
```

Expected result:

```text
status = dry_run_pass
```

## One-shot real reproduction

The one-shot driver runs four stages serially and stops at the first failure:

```text
1. negative validation
2. field_value
3. boundary
4. structure
```

Execute only when real writes are intended:

```bash
python3 scripts/reproduce_alfresco_multipart_bounded.py \
  --output-root /tmp/alfresco-multipart-repro-<run-id> \
  --allow-real-write \
  --max-test-cases 12 \
  --time-budget 45
```

Each arm receives a fresh run-root under the output directory. Do not reuse an old output directory. The command creates Alfresco documents; the final report contains redacted counts and paths only.

## Direct bounded invocation

For one arm only:

```bash
python3 scripts/run_alfresco_bounded_feedback.py \
  --scenario multipart_upload \
  --mutation-scope field_value \
  --seed-manifest "$PWD/in/alfresco_multipart_upload_bounded/manifest.txt" \
  --seed-source-dir "$PWD/in/alfresco_multipart_upload_bounded" \
  --run-root /tmp/alfresco-multipart-single-<run-id> \
  --max-test-cases 12 \
  --time-budget 45
```

Replace `field_value` with exactly one of `boundary` or `structure` for the other arms. Direct invocation is useful for diagnosis; the one-shot driver is the canonical ordered reproduction entry.

## Evidence acceptance

A bounded arm is PASS only if all of the following are present and reconciled:

```text
AFL++ task contract and stdin launch
manifest-controlled regular-file seeds
at least two selected queue IDs
at least one real HTTP 201
response node identity for every 201
exec_seq/status for every target invocation
validation rejects explicitly non-target
execution ledger reconciled
MAB journal reconciled
seed-selection audit reconciled
metadata and content read-back for every successful upload
artifact report = pass
runner exit code = 0
```

For negative validation:

```text
boundary mismatch and missing filedata rejected before upload
HTTP requests sent = 0
created nodes = 0
validation_reject = true
target_invoked = false
```

## Artifact layout

Each arm contains:

```text
runs/<arm>/task.json
runs/<arm>/seed_input/
runs/<arm>/afl-out/fuzzer_stats
runs/<arm>/evidence/multipart_uploads.jsonl
runs/<arm>/evidence/executions.jsonl
runs/<arm>/evidence/mab_updates.jsonl
runs/<arm>/evidence/seed_selection.jsonl
runs/<arm>/evidence/multipart_readback.json
runs/<arm>/evidence/artifact_report.json
```

Raw run-roots are external evidence and are not committed to Git. Preserve the final redacted summary before removing temporary run inputs.

## Scope boundary

```text
static-loop = separate interface replay evidence
bounded = AFL++/MAB/ledger/read-back evidence
long-term stability = not run
scale validation = not run
```
