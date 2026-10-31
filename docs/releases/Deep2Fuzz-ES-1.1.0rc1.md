# Deep2Fuzz-ES 1.1.0rc1

## Product

Deep2Fuzz-ES is an offline-first platform adapter system built on the AFL++
fuzzing core. This document describes the release candidate preparation from
the P4 distribution checkpoint.

## Version and release class

- Version: `1.1.0rc1`
- Release class: Release Candidate
- Candidate tag for a later decision: `deep2fuzz-es-v1.1.0-rc.1`
- Tag, publication and GitHub release: not performed in this preparation
- Source authority: `c9b0f3558cbea6cddb46a435f6de452849a17790`

## Included capabilities

- installable `deep2fuzz` CLI with core and optional dependency boundaries;
- explicit adapter registry and typed adapter contract;
- bounded offline `mock_rest` full-core execution;
- strict config validation and read-only evidence verification;
- source/config/adapter/scorer provenance;
- existing core Cov/Err/Rec, reward, MAB, seed-credit and report accounting;
- fresh wheel/sdist build and isolated-install validation.

## Validated workflows

The acceptance evidence covers offline CLI commands, config and evidence
validation, the mock adapter contract, packaged delivery sample execution,
fresh wheel and sdist installation, source-tree leakage checks, package-content
exclusion, and the maintained regression gates. No live O2OA or Alfresco run
is part of this RC preparation.

## Distribution format

The release artifact policy is a freshly built wheel and sdist from the
eventual tagged commit. The package includes the Python interface and bounded
offline sample runtime. Native AFL++ and research/live-platform assets remain
source-tree capabilities and are not represented as a standalone wheel.

## Platform support

POSIX native execution is validated. The O2OA formal bounded chain and Alfresco
bounded engineering evidence remain preserved. Windows path semantics and
fail-closed unsupported capabilities are tested, while native Windows
execution, native Windows clean install and Windows process-tree termination
are not validated.

## Known limitations

- KL01: P1.1B historical first sweep `18/20`; root cause unresolved;
- KL02: native Windows execution not validated;
- KL03: Windows process-tree termination is `UNSUPPORTED_FAIL_CLOSED`;
- KL04: native Windows clean install unverified;
- KL05: byte-reproducible archives not claimed;
- KL06: cross-host VM reproduction not performed;
- KL07: frozen approved 32D model artifact missing for fresh exact reproduction;
- KL08: exact external SE-fAnoGAN-ES equivalence not claimed;
- KL09: SE effectiveness is scenario-dependent;
- KL10: Cov/Err/Rec/overall are bounded engineering proxies/index;
- KL11: Task 4 papers, patents and team deliverable archives remain separately
  unverified by current technical acceptance evidence.

## Scientific claim boundaries

`Cov` is a bounded observable security-state coverage proxy, `Err` is a bounded
anomaly proxy, `Rec` is an external platform availability recovery proxy, and
`overall` is a bounded engineering evaluation index. The RC does not claim a
universal security score, absolute security-state coverage, production
certification, or universal SE superiority. SE-fAnoGAN-ES remains an optional
research backend and project reference realization; exact external equivalence
is not claimed.

## Evidence summary

P1.1, P1.2, P1.3, P1.4, P2, P3 and P4 checkpoints are preserved in the evidence
chain. P2 remains `CLOSED_WITH_DOCUMENTED_LIMITATION`; the historical 18/20
observation is immutable. Task 4 technical implementation is
`YES_WITH_DOCUMENTED_PROVENANCE_AND_REPRODUCIBILITY_LIMITATIONS`; team-level
papers, patents, report and archive completion are not inferred from this
software evidence.

## Artifact build policy

Build wheel and sdist freshly from the final tagged commit in isolated local
build roots. Do not reuse dirty-worktree or historical test artifacts. Verify
metadata, package contents, hashes and secret scans before publication.

## Upgrade and compatibility

The RC changes the package version and release metadata only. Existing CLI
commands, config schema, provenance schema, scientific output semantics,
runtime accounting and protected platform paths remain unchanged. The previous
`1.1.0.dev0` development package is superseded by this candidate version when
installed from the RC source.

## License

The package points to the repository root `LICENSE` file, Apache License 2.0.
Additional third-party notices remain authoritative for their respective
components.
