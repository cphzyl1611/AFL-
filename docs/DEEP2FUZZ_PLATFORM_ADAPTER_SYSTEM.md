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
deep2fuzz platform init example_platform
```

`doctor` performs local Python, venv, pytest, compiler, zlib, AFL, import, and
configuration checks only; it never probes a live service. It reports the
required `OFFLINE_READY`, `MOCK_PLATFORM_READY`, `LIVE_PLATFORM_READY`, and
`MODEL_BACKEND_READY` fields. `test` runs the extension contract suite with pytest when available,
or the standard-library unittest fallback. `sample` delegates to the committed
`scripts/run_task4_sample.py` delivery runner; `platform smoke` produces the
loopback adapter evidence. `platform run` is intentionally
`NOT_IN_PHASE1` until a generic full-run contract can be specified without
duplicating the established runner.

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

Phase 1 intentionally has no generic live-platform runner, no automatic
discovery, no remote plugin loading, no packaging/install entry point, and no
scientific result claim. The engineering backlog records those follow-ups;
they are not silently expanded into this phase.
