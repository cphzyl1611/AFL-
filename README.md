# Deep2Fuzz-ES

Deep2Fuzz-ES is an offline-first platform adapter system built on the AFL++
fuzzing core. It connects seed selection, semantic mutation, validity
filtering, bounded platform execution, readback, cleanup, state feedback and
machine-readable evidence while keeping the existing Cov, Err, Rec, reward,
MAB and seed-accounting contracts in the core.

## Scope and intended use

The package is intended for local development, controlled test fixtures and
authorized disposable platform environments. The default workflows are
offline and do not contact O2OA, Alfresco or the public network. Live platform
credentials are supplied at runtime through existing environment-variable or
0600-file conventions; they are never stored in configuration, evidence or
package artifacts.

This repository contains the Python CLI and adapter boundary together with
the native AFL++ source tree. A wheel or sdist provides the Python interface
and a bounded offline delivery sample. It is not a standalone distribution of
every native, live-platform or research asset in the source tree.

## Capabilities

- explicit platform adapter registry with fail-closed unknown-adapter handling;
- bounded `mock_rest` full-core execution for offline contract checks;
- semantic JSON, URL-query and platform-specific request preparation;
- validity decisions before target execution;
- authenticated readback and exact-ID cleanup contracts;
- existing core ownership of execution identity, status, state feedback,
  Cov/Err/Rec, reward, MAB, seed credit and reports;
- deterministic config and evidence validation with provenance;
- wheel/sdist installation and a packaged offline sample.

## Installation and quick start

From a source checkout, the supported development mode is:

```bash
python -m pip install -e .
deep2fuzz --version
deep2fuzz --help
deep2fuzz doctor
deep2fuzz platform list
deep2fuzz platform run mock_rest
```

For a built distribution, install a freshly built wheel or sdist into an
isolated environment. The core package has no third-party runtime dependency;
optional dependency groups are `dev`, `live`, `model` and `analysis`.

```bash
python -m pip install 'deep2fuzz-es[dev]'
deep2fuzz sample
```

`deep2fuzz sample` uses only packaged local assets and writes a fresh evidence
root. `deep2fuzz config validate CONFIG` validates a configuration without
creating output paths. `deep2fuzz evidence verify EVIDENCE_ROOT` performs the
read-only evidence and provenance checks.

## Platform Adapter System

The core creates the task, run, execution sequence, seed and mutation-arm
identity. An adapter prepares a request, executes its platform-specific
operation, interprets the response, performs readback and exact cleanup, and
may report health. It cannot replace the execution sequence or fabricate core
feedback. The loopback `mock_rest` adapter is the offline contract fixture;
O2OA and Alfresco historical runners remain separate compatibility paths.

## Evidence and configuration

The authoritative configuration format is versioned and rejects unknown
fields, implicit type coercion, unsafe paths, unsupported platforms and invalid
cross-field combinations. Validation is offline, deterministic and
fail-closed. Evidence includes execution identity, state, feedback,
accounting, reports and source/config/scorer provenance where the profile
requires it.

## Scientific claim boundary

The reported metrics are bounded engineering measures:

- `Cov` is a bounded observable security-state coverage proxy;
- `Err` is a bounded anomaly proxy;
- `Rec` is an external platform availability recovery proxy;
- `overall` is a bounded engineering evaluation index.

These metrics are not universal security scores, absolute security-state
coverage, AFL edge coverage, or proof of production security. SE-fAnoGAN-ES
is retained as an optional research backend and project reference realization;
exact external equivalence and universal superiority over AE are not claimed.

## Platform and distribution boundaries

POSIX native execution, offline wheel/sdist builds, fresh isolated installs and
repo-independent installed execution are validated. Windows path semantics
and unsupported-capability fail-closed behavior are covered by the portability
tests, but native Windows execution, native Windows clean install and Windows
process-tree termination are not validated. No production deployment,
cross-host VM reproduction, PyPI publication, signed package, SBOM
certification or byte-identical archive reproducibility is claimed.

## Known limitations

- KL01: the historical P1.1B first sweep was 18/20; its root cause remains
  unresolved and later passes do not erase that observation;
- KL02: native Windows execution is not validated;
- KL03: Windows process-tree termination is unsupported and fails closed;
- KL04: native Windows clean install is unverified;
- KL05: byte-reproducible archives are not claimed;
- KL06: cross-host VM reproduction was not performed;
- KL07: the approved frozen 32D model artifact is missing for fresh exact
  reproduction;
- KL08: exact external SE-fAnoGAN-ES equivalence is not claimed;
- KL09: SE effectiveness is scenario-dependent;
- KL10: Cov, Err, Rec and overall remain bounded engineering proxies;
- KL11: Task 4 papers, patents, research report, component delivery and team
  archives are formal project requirements whose completion is separately
  unverified by current technical acceptance evidence.

## Version and release status

Version `1.1.0rc2` is a Release Candidate. Stable version `1.1.0` has not yet
been released. RC2 corrects the release-status documentation carried by the
RC1 package. Stable release readiness, signing, publication and production
certification require a separate review.

## License

The repository license authority is the root `LICENSE` file, Apache License
2.0. Package metadata points to that file. Third-party components retain any
additional notices present with those components; this README does not grant
or invent terms for them.
