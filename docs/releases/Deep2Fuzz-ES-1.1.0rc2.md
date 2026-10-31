# Deep2Fuzz-ES 1.1.0rc2

## Version and release class

- Version: `1.1.0rc2`
- Release class: Release Candidate
- Reason for RC2: correct a material false release-status statement in the
  RC1 product README and the package long description derived from it.
- RC1 remains immutable: the existing `deep2fuzz-es-v1.1.0-rc.1` tag,
  prerelease, wheel, sdist and release evidence are not edited or replaced.

## Correction and package impact

The RC1 README said that the RC1 candidate tag had not been created, although
the tag and prerelease had already been published. RC2 replaces that
time-sensitive claim with lifecycle-safe wording: `1.1.0rc2` is a Release
Candidate and stable `1.1.0` has not yet been released. The README is the
package long description, so fresh RC2 wheel and sdist metadata carry the
corrected status.

This is a documentation and version correction only. Runtime behavior,
scientific behavior, configuration and provenance schemas, CLI command
contracts, adapter semantics, validity, scheduling, Cov/Err/Rec/overall,
reward, MAB, seed accounting, scoring and termination are unchanged.

## Included capabilities

- installable `deep2fuzz` CLI with core and optional dependency boundaries;
- explicit adapter registry and typed adapter contract;
- bounded offline `mock_rest` full-core execution;
- strict config validation and read-only evidence verification;
- source/config/adapter/scorer provenance;
- existing core Cov/Err/Rec, reward, MAB, seed-credit and report accounting;
- fresh wheel/sdist build and isolated-install validation.

## Platform and distribution boundaries

POSIX native execution, offline wheel/sdist builds, fresh isolated installs
and repo-independent installed execution are validated. Windows path
semantics and unsupported-capability fail-closed behavior are covered by the
portability tests, but native Windows execution, native Windows clean install
and Windows process-tree termination are not validated. No production
deployment, cross-host VM reproduction, PyPI publication, signed package,
SBOM certification or byte-identical archive reproducibility is claimed.
No live O2OA or Alfresco run is part of this RC2 closure.

## Known limitations

- KL01: the historical P1.1B first sweep was `18/20`; its root cause remains
  unresolved and later passes do not erase that observation;
- KL02: native Windows execution is not validated;
- KL03: Windows process-tree termination is `UNSUPPORTED_FAIL_CLOSED`;
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

## Scientific claim boundaries

`Cov` is a bounded observable security-state coverage proxy, `Err` is a
bounded anomaly proxy, `Rec` is an external platform availability recovery
proxy, and `overall` is a bounded engineering evaluation index. RC2 does not
claim a universal security score, absolute security-state coverage, production
certification, or universal SE superiority. SE-fAnoGAN-ES remains an optional
research backend and project reference realization; exact external
equivalence is not claimed.

## Future stable readiness

Stable readiness must be reviewed again after RC2 tagged-source verification,
fresh artifact verification, publication decision and observation. At stable
`1.1.0`, the candidate wording must transition to stable wording and remove
the statement that stable `1.1.0` has not yet been released.
