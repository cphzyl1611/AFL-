# Deep2Fuzz-ES Changelog

## 1.1.0rc1 - Release Candidate Preparation

This release candidate is prepared from the committed P4 distribution
checkpoint. It is an engineering and distribution milestone; no scientific
metric semantics or live-platform behavior changed.

### Phase 1: Platform Adapter System

- Added the explicit adapter registry and typed platform adapter contract.
- Added the bounded offline `mock_rest` adapter with request, readback, update,
  exact-ID cleanup and absence verification.
- Kept execution identity, state feedback, reporting, MAB and seed accounting
  in the existing core.

### Phase 1.1: Runtime and Distribution Hardening

- Added the `deep2fuzz` install entrypoint, package discovery and dependency
  extras.
- Added the bounded packaged offline sample and source/runtime boundary.

### P1.1: Evidence Validator

- Added read-only evidence verification, path safety, secret scanning and
  structured reconciliation checks.

### P1.2: Config and Schema Validation

- Added versioned fail-closed configuration validation, strict field/type
  checks, path rules and platform-specific schema isolation.

### P1.3: Version and Report Provenance

- Added source, configuration, adapter, scorer and evidence provenance with
  explicit non-Git fail-closed behavior.

### P1.4: CLI and UX

- Standardized CLI exit codes, human diagnostics and JSON output for core,
  configuration and evidence commands.

### P2: Test Speed and Determinism

- Added timing, gate projection, repeatability and failure-diagnostic
  infrastructure.
- Formal gates remain intact. The historical P1.1B 18/20 observation remains
  preserved with an unresolved root cause; P2 is closed with this documented
  limitation.

### P3: Portability and Cross-platform

- Added bounded POSIX process-lifecycle and path portability checks.
- Unsupported Windows process-tree capabilities fail closed.

### P4: Distribution and Clean Install

- Validated fresh wheel and sdist builds, isolated installs, installed CLI
  execution, package-content exclusion and the delivery sample.
- Distribution remains a bounded offline Python/CLI and sample package, not a
  complete native/research standalone bundle.

### Known limitations

The RC preserves the native Windows, cross-host, byte-reproducibility, frozen
32D artifact, SE exact-equivalence, scenario-dependent effectiveness and
project-deliverable verification limits documented in the product README and
RC1 release notes. Cov/Err/Rec/overall remain bounded engineering proxies.
