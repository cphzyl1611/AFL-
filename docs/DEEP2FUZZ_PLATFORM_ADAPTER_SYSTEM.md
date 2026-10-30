# Deep2Fuzz Platform Adapter System

This document describes the post-freeze Phase 1 engineering extension. It adds
a small explicit adapter boundary without changing the frozen fuzzing,
validity, Cov, Err, Rec, seed-credit, or MAB semantics.

## Architecture

The existing runner remains the source of execution orchestration. It creates
the run layout and execution identity, loads seeds, invokes validity, writes
status and state, attributes feedback, and generates reports. The extension
registry in `integration/platforms/registry.py` is an explicit map from a
stable name to a local adapter factory. It does not load arbitrary modules,
install packages, contact a marketplace, or hot-reload code.

The Phase 1 `mock_rest` adapter is a loopback-only contract fixture. Its
in-memory service binds `127.0.0.1` on an ephemeral port and is disposed when
the smoke finishes. The adapter disables inherited HTTP proxies for that
loopback request path.

## Core and adapter responsibilities

Core responsibilities remain task/run/execution identity, seed and mutation
dispatch, validity decisions, status and state traces, MAB and seed
accounting, Cov/Err/Rec reporting, budgets, evidence paths, and secret-safe
logging. The adapter owns platform request construction, response
interpretation, business success versus expected rejection, object IDs,
readback, exact-ID cleanup, an optional health check, and a small runtime
business context.

The adapter receives the core-created `ExecutionIdentity`:
`task_id`, `run_id`, `exec_seq`, `seed_id`, and `mutation_arm`. It cannot
replace or mint those fields. Each structured result carries the same identity.
The Phase 1 smoke records the same `exec_seq` through adapter, status, and
execution-ledger references; MAB and report references are explicitly marked
core-owned and are not fabricated as commits by the mock.

## Contract

`PlatformAdapter` requires `build_request`, `interpret_response`,
`business_verdict`, `extract_object_id`, `create`, `update`, `readback`,
`cleanup`, and `update_runtime_context`. `health_check`
and `runtime_context` are optional capabilities in the sense that a platform
may report them as unsupported; the mock provides both. `update_runtime_context`
accepts only non-secret business context and returns the adapter-owned context.

Results are typed dataclasses rather than arbitrary dictionaries:

* `AdapterExecutionResult` records HTTP code, response class, business success,
  expected rejection, semantic failure, object ID, error kind, latency, and a
  safe message.
* `ReadbackResult` records payload matching, absence, and semantic failure.
* `CleanupResult` records exact-ID deletion and a subsequent absence check.
* `HealthResult` is health-only and never counts as business recovery.

Secret-bearing field names are rejected from request headers and structured
metadata. Platform configurations may hold environment-variable names for
credentials in future adapters, but never credential values.

## Registry and CLI

The user-facing executable is `deep2fuzz`:

```text
deep2fuzz doctor
deep2fuzz test
deep2fuzz sample
deep2fuzz platform list
deep2fuzz platform validate mock_rest
deep2fuzz platform smoke mock_rest
deep2fuzz platform run mock_rest
deep2fuzz platform init example_platform
```

`doctor` performs local Python, package, venv, pytest, compiler, zlib, AFL,
import, and configuration checks only; it never probes a live service. It
reports `OFFLINE_READY`, `PLUGIN_READY`, `NATIVE_RUNTIME_READY`,
`LIVE_PLATFORM_READY`, and `MODEL_BACKEND_READY`. `test` runs the extension
contract suite with pytest when available, or the standard-library unittest
fallback. `sample` delegates to the committed `scripts/run_task4_sample.py`
delivery runner; `platform smoke` produces loopback adapter evidence. The
Phase 1 baseline deferred `platform run`; Phase 1.1 adds only the bounded
`mock_rest` full-core offline contract, leaving platform-specific live runners
outside this command.

`platform init` creates a placeholder with `platform.json`, `target.json`,
`rules.json`, `adapter.py`, `seeds/seed_0.json`, and a README. Generated
configuration uses loopback/example values and contains no secrets.

## Mock and contract tests

The mock exposes `GET /health`, `POST /api/items`, `GET /api/items/{id}`,
`PUT /api/items/{id}`, and `DELETE /api/items/{id}`. Contract tests cover
creation, ID extraction, readback, update, second readback, exact-ID cleanup
and absence, expected 4xx rejection, malformed JSON, missing IDs, connection
failure, health semantics, validity rejection, identity preservation, registry
fail-closed behavior, and secret-field rejection. The smoke is bounded and
disposable; it is not a performance or scientific experiment.

## New-platform workflow

1. Define a local profile and validity rules using the existing project
   configuration conventions.
2. Implement the contract with core-created identities and structured results.
3. Register the adapter explicitly and add offline contract tests first.
4. Validate request and response semantics, readback, ownership/absence, and
   cleanup on a disposable local fixture.
5. Integrate the adapter at the runner boundary only after the generic
   identity, status, feedback, and report contracts are stable.

Level 1 is an offline contract adapter and mock. Level 2 is a local,
disposable real-service adapter with an explicit bounded runner integration.
Level 3 is a separately approved experiment with platform-specific evidence;
this extension does not claim Level 2 or Level 3 for O2OA or Alfresco.

## Backward compatibility and limitations

O2OA and Alfresco paths are not migrated or wrapped by this extension. Their
existing runners and evidence contracts remain the compatibility authority.
The frozen offline delivery set remains a separate 235/235 baseline claim.

## Phase 1.1 runtime and distribution hardening

The package version is defined once in `deep2fuzz_version.py` (`1.1.0.dev0`).
Install the Python interface with:

```text
python -m pip install -e .
deep2fuzz --help
deep2fuzz --version
deep2fuzz platform list
deep2fuzz doctor
```

`pyproject.toml` is the authoritative dependency contract. Core remains
standard-library-only. `deep2fuzz-es[dev]` adds pytest, `[live]` adds requests,
`[model]` adds numpy/pandas/torch, and `[analysis]` adds pandas/matplotlib.
From a source checkout, install extras with `python -m pip install -e '.[dev]'`
and the corresponding extra name. The historical `requirements*.txt` files
are compatibility installer exports.

The supported install mode is
`SUPPORTED_INSTALL_MODE = EDITABLE_SOURCE_TREE`: the Python package exposes
the CLI and adapters, while AFL++ native binaries and repository assets remain
in the source tree. `doctor` reports Python, package, native tools, core
imports, registry status, and optional backend availability without contacting
O2OA, Alfresco, or any network service. Missing optional dependencies and
native tools produce an install/next-action message.

`deep2fuzz platform run mock_rest` is the bounded offline full-core contract.
It feeds one identified HTTP seed through AFL++ validity, the existing
custom-mutator arm, the loopback `mock_rest` adapter, and the existing
status/state, Err/Rec, reward, NC_MAB, seed-credit, and eval-report paths.
Adapter lifecycle events carry the task, run, seed, arm, and core-assigned
execution sequence. The companion `identity_reconciliation.json` joins those
events to frozen core ledgers by `exec_seq`; it does not alter core artifact
schemas. Overall score reporting reuses
`scripts/compute_formal_security_score.py`. The adapter does not implement a
second MAB, Cov, Err, Rec, seed, or report calculation. The runner supports
explicit `success`, `validity_rejection`, `expected_rejection`, and
`semantic_failure` offline scenarios; all evidence roots are new and refuse
overwrite.

The correlation headers used by this mock bridge are enabled only by the
explicit `DEEP2FUZZ_CORE_ADAPTER_BRIDGE=1` runner setting. Ordinary historical
mutator output is unchanged, and the bridge strips the headers before any
loopback service request.

### Cleanup fail-closed contract

When a platform adapter cannot verify exact-ID cleanup, the target writes a
run-scoped `control/abort.json` marker with an atomic temporary-file plus
`os.replace()` publish. The marker contains only terminal reason and execution
identity; object identifiers are hashed and response bodies/credentials are
never stored. Every target invocation checks the marker before constructing an
adapter or making a request, so a scheduler/supervisor race cannot create a
new object or contact the platform after cleanup failure.

The offline runner watches the marker, waits for the failing execution's
status record, requests graceful AFL++ termination, and escalates only after a
bounded wait. The mock runner supplies an explicit bounded 2-second AFL++
target timeout so Python target startup does not inherit the platform's
implicit 1-second dry-run limit on a busy host. It preserves the partial run
root and writes terminal status (`run_complete=false`,
`terminal_reason=CLEANUP_FAILED`) plus supervisor timing metadata. A terminal
marker makes `deep2fuzz platform run mock_rest` return a nonzero exit code; it
is not represented as a fake crash and does not alter Cov, Err, Rec, reward,
MAB, seed-credit, or report semantics. The explicit `cleanup_failure`
scenario is loopback-only and exists solely to exercise this fail-closed
contract.

The frozen mainline entrypoints are `select_next_queue_entry` in
`src/afl-fuzz-queue.c` (called from `src/afl-fuzz.c`), `nv_mab_pick` in
`src/afl-fuzz-one.c`, `nv_validity_check` and `fuzz_run_target` in
`src/afl-fuzz-run.c`, and `nv_observe_security_state_once` for status/state,
security-state Cov, and seed credit. `fuzz_run_target` owns Err/Rec counters;
`nv_reward_from_obs` computes the existing reward;
`nv_mab_journal_commit_update` commits MAB; and
`nv_write_eval_report_json` writes the existing report. The generic runner
reconciles these artifacts by core `exec_seq`; overall scoring uses the
existing `scripts/compute_formal_security_score.py` utility.

Known boundary: this runner is a mock/loopback contract only. It does not
contact or claim reproducibility against a live O2OA or Alfresco service, and
the SE-fAnoGAN-ES model remains an optional existing model route rather than a
new Phase 1.1 model implementation.

### Post-Phase 1.1 engineering backlog

These items are recorded for later work and are not part of this hardening
scope:

* P1.1 evidence validator: implemented as `deep2fuzz evidence verify`.
* P1.2 config schema validation: implemented as `deep2fuzz config validate`.
  P1.3 version/report provenance and P1.4 CLI consistency are implemented
  below.
* P2: logging UX, config discoverability, mock/dev tooling, test
  speed/determinism.
* P3: portable setup, cross-platform paths, Windows/WSL ergonomics.

## Phase 2 P1.1 evidence verification
Run the offline, read-only validator against an existing evidence directory:

```text
deep2fuzz evidence verify <run-root>
deep2fuzz evidence verify <run-root> --json
```

Supported profiles are `platform-run` (the Phase 1.1 generic mock runner),
`delivery-sample`, and `audit-evidence` roots containing
`FINAL_STATUS.json` plus `EVIDENCE_PATHS.json`. Unknown profiles fail closed.
The validator parses JSON/JSONL, verifies an optional `SHA256SUMS.txt`, checks
profile-specific identities and accounting, recomputes overall score only by
calling the existing `scripts/compute_formal_security_score.py` module, checks
cleanup/abort evidence, and scans supported text artifacts for credential-like
values. Audit roots are checked against their path manifest rather than being
treated as campaign runs.

Exit codes are stable: 0 means all applicable required checks pass, 1 means
evidence validation failed, and 2 means the invocation/root input is invalid.
`--json` writes one JSON result to stdout. Both modes are offline and do not
write to the selected root, repair evidence, rerun a campaign, or follow a
symlink outside the root. It reports file count, byte count, and elapsed time.
The secret scan is heuristic and limited to common text evidence formats; it
does not inspect arbitrary binary payloads, prove the absence of every secret,
or authenticate evidence provenance. Findings contain only an artifact path,
category, and short digest fingerprint, never the matched value. The validator
does not inspect paths outside the selected root and stops profile-specific
reads if a discovered symlink escapes that root.

The common checks cover filesystem/path safety, JSON/JSONL parseability, an
optional SHA-256 manifest, and the bounded text secret scan. `platform-run`
also validates contract JSON shape, execution/status/state identity, validity
candidate accounting, MAB journal/pull attribution, seed credit, Cov/Err/Rec,
the existing formal scorer, report/stat consistency, cleanup, and terminal
cleanup-abort evidence. `delivery-sample` checks its sample report, counters,
summary CSV, recovery-null policy, and score against the existing scorer;
platform cleanup and abort checks are not applicable to that profile.
`audit-evidence` checks final status, SHA-256, and evidence path integrity; it
does not apply campaign accounting rules. Historical manifests that include
`EVIDENCE_PATHS.json` in their file list and pre-manifest count are interpreted
using that recorded convention without changing those roots.

The verifier checks recorded classifications and arithmetic relationships. It
does not reclassify HTTP/business responses, reproduce the MAB or seed-scheduler
algorithms, or infer missing execution facts. Unsupported or ambiguous roots
fail closed. P1.1 through P1.4 and the P2 test speed/determinism infrastructure
are implemented. P2 records speed as neutral rather than claiming a significant
speedup. An early P1.1B sweep recorded 18/20 with two failures; later
independent first-attempt studies passed, but the historical attempt-level
details were not retained, so the root cause remains unresolved and is a
documented limitation. Later passes do not erase that observation.

## Phase 2 P1.3 version and report provenance

New platform-run and delivery-sample roots embed a machine-readable
`provenance` object in the report and write the same object to
`provenance.json`. The object uses `provenance_schema_version: "1"` and
records the single-source product version, full local Git commit and tree,
relevant source dirty state, the P1.2 canonical semantic configuration
fingerprint, adapter name/contract version, formal scorer contract ID and
fingerprint, run/task identity, evidence profile/schema, and a UTC timezone-aware
`generated_at` timestamp. `provenance_config.json` is the exact semantic input
used for the config fingerprint; whitespace and object key order do not affect
the fingerprint.

The relevant dirty-source policy excludes editable-install metadata
(`deep2fuzz_es.egg-info`), caches, virtual environments, build/dist output,
logs, runtime output roots, and evidence roots. Git status is read locally
with untracked files expanded and rename detection disabled. Tracked changes,
deletions, symlink target changes, and relevant untracked source files set
`dirty: true` and receive a deterministic fingerprint. Collection is bounded
to 100,000 relevant paths and 64 MiB per changed file. A source tree without
`.git` metadata fails clearly rather than fabricating a commit or tree.

The formal scorer contract ID is `formal-security-score-v1`; its fingerprint
covers only `scripts/compute_formal_security_score.py`, which contains the
formal score and null-recovery policy. Adapter name and contract version are
declared against the supported adapter registry and verified at the
`DECLARED_ONLY` level; the verifier does not claim to hash or independently
reconstruct adapter semantics. Provenance checks label their level in JSON:
`STRUCTURAL` checks validate shape/format, `RECOMPUTABLE` checks independently
recalculate a value from local evidence/source, and `DECLARED_ONLY` checks
validate a recorded value against the declared contract registry.

`deep2fuzz evidence verify` recomputes source, config, and scorer identities
when their local inputs are available. It distinguishes structural,
recomputable, and declared identity checks and fails closed for missing new
provenance, unsupported schema, source/config/scorer/adapter mismatches,
invalid timestamps, and report/provenance disagreement. New audit evidence
bundles carry the object in `FINAL_STATUS.json` and repeat it in
`provenance.json`; the verifier requires these copies to agree. Historical
P1.1/P1.2 and frozen roots without `provenance_required` retain the legacy
validation contract and report provenance as not applicable. Provenance
collection and verification are offline and read-only; they do not prove
platform availability or security, and they do not duplicate the formal
scorer or scientific metric semantics.

## Phase 2 P1.2 configuration validation

Run configuration is one versioned JSON document. The authoritative schema is
`schema_version: "1"` with `platform`, `run`, `inputs`, `output`, `validity`,
and `platform_config` blocks. `run` requires positive integer
`max_test_cases` plus positive numeric `time_budget_seconds` and
`timeout_seconds`; case/budget values remain in the exact integer range of the
existing cJSON runtime. AFL consumes the validated budget in whole seconds;
sub-second budgets fail because the native integer conversion would disable
the time bound. `inputs` requires exactly one existing `seed_file` or
`seed_dir`; and `output` requires a new evidence root outside the source
repository. The bounded mock runner's `seed_dir` form must contain exactly one
regular seed file because the existing reconciliation contract assigns one
seed identity. Relative paths resolve from the configuration file directory
and cannot escape it, including through symlinks. Validation does not create
paths or modify the configuration.

The selected platform block is strict and platform-aware. `mock_rest` accepts
an optional positive `timeout_sec` and requires `cleanup.required: true` for
its object-producing contract. O2OA accepts `o2oa_default` plus a credential
environment-variable name, and Alfresco accepts the existing profile names
plus username/password environment-variable names. These references are
validated for syntax only; values are never read or printed. O2OA and Alfresco
validation is structural and does not contact either service.

Use `deep2fuzz config validate <config>` for human output or add `--json` for
machine-readable output. Exit code 0 means valid, 1 means a deterministic
schema/path failure, and 2 means the input could not be read. Unknown fields,
unknown schema versions, invalid types, non-finite numbers, path escapes, and
cross-field violations fail closed. `deep2fuzz platform run mock_rest
--config <config>` validates before importing or running the core; a valid
configuration supplies the existing run limits, validity flag, seed, mock
timeout, and evidence root to the existing offline core path. This is not a
live O2OA or Alfresco execution interface.

## Phase 2 P1.4 CLI consistency

The supported command tree is `doctor`, `test`, `sample`, `platform` (`list`,
`validate`, `smoke`, `init`, `run`), `config validate`, and `evidence verify`.
Existing invocations and the single version source in `deep2fuzz_version.py`
remain unchanged. Command names are lowercase and options use hyphenated
names. Help and version requests only parse and render CLI metadata.

Exit codes are stable: 0 means success, 1 means a configuration/evidence
validation failure or platform runtime failure, 2 means invalid invocation or
unreadable input, and 3 means an unexpected internal error. Expected errors do
not show tracebacks. Unexpected error output is concise and omits exception
details that could contain secret values. Domain error codes and the P1.1/P1.2
machine result structures are preserved.

Human results go to stdout. Parser/input diagnostics go to stderr. A failed
schema check against a readable configuration and a failed evidence check
against a readable root are domain results, so they remain on stdout with exit
code 1. An unreadable or missing input is an invocation error on stderr with
exit code 2. `config validate --json` and `evidence verify --json` each emit one
JSON value to stdout and no human banner; their existing machine result shapes
are retained. `doctor`, `platform smoke`, and `platform run` continue to emit
their established machine-readable output; `platform list` and
`platform validate` use human text output.

`doctor` performs local/offline capability checks only. It does not probe
O2OA, Alfresco, or public services. The CLI layer only parses and dispatches,
validates invocation details, renders existing results, and selects an exit
code. Config schema validation, evidence verification, adapter execution,
provenance, and scientific/accounting logic remain in their existing modules.
The CLI adds no runtime dependencies. It does not provide a `--json` mode for
commands that have no existing machine-result contract.

## Phase 2 P2 test speed and determinism

P2 adds test infrastructure only. `tests/test_groups.json` is the explicit
selection manifest for the Phase 1, P1.1-P1.4, required-74, combined-227,
frozen-offline, delivery-sample, and P2 groups. Formal pytest groups contain
sorted, exact node IDs; the runner validates syntax, uniqueness, collection,
and collection drift before execution. Counts are descriptive metadata and do
not authorize gate membership. The frozen offline group retains its existing
file selection and `-k` expression.

`scripts/run_deep2fuzz_tests.py --group <name> [--repeat N] --json` is a
small wrapper around pytest. It fixes hash seed, locale, timezone, offline
mode, and proxy handling for the subprocess, records wall time and the pytest
slowest list, and emits sanitized timeout diagnostics. `--repeat` performs
independent executions; the first run is the acceptance verdict and any
failing repeated run makes the repeat command nonzero. It is not a retry or
failure masker, and diagnostic reruns are disabled. Results and mutable run output are never cached. The
developer `p2` group is not an acceptance authority and cannot replace the
required-74, combined-227, frozen-offline, or delivery-sample gates.

Tests use isolated temporary roots, sorted filesystem enumeration, explicit
random seeds where randomness is needed, UTC formatting, monotonic deadlines,
bounded polling, OS-assigned ephemeral ports, and deterministic subprocess
cleanup. New parallel execution is not enabled: shared repository state,
evidence roots, global environment, and process lifecycle make the formal
groups serial by default. Timeout diagnostics include test/group identity,
elapsed and deadline values, process state, and a bounded sanitized stderr
excerpt; they never include credential values or authorization material.

This infrastructure does not alter validity, Cov/Err/Rec/overall, MAB,
reward, seed accounting, execution identity, configuration/provenance schemas,
or the public CLI contract. It measures and diagnoses timing and
repeatability; it is not a platform availability check and does not contact
O2OA, Alfresco, or external services.
