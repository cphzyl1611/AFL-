# Task 4 Delivery Guide

This guide reproduces the component's bounded offline delivery smoke from a
clean checkout. It does not start Docker, O2OA, Alfresco, Flowable, or a real
authentication session. It does not run a performance benchmark.

## Tested environment

- Ubuntu 24.04 LTS on WSL2, x86_64
- Python 3.12.x
- GCC and Make from Ubuntu 24.04
- 16 GB host memory; commands are sequential

Install the system prerequisites listed in [`DEPENDENCIES.md`](DEPENDENCIES.md),
then export or check out the accepted source tree. The release baseline used
for this verification is commit `2b15006df14fa6a3fcfba109ca3573f4fbd8190b`.

```bash
git clone <repository-url> AFL-
cd AFL-
git checkout 2b15006df14fa6a3fcfba109ca3573f4fbd8190b
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
cp scripts/python3-config-wrapper.sh .venv/bin/python3-config
chmod 0755 .venv/bin/python3-config
make -j2 afl-fuzz
```

The dependency install is the only step that may contact a package index. The
repository itself has no third-party offline runtime dependency. If
The symlink makes the matching system `python3-config` visible beside the
virtualenv interpreter; the C feedback tests use the matching CPython headers
and libpython. The offline runner creates the symlink automatically when it is
missing and fails closed if the system tool is unavailable.

## Bounded offline acceptance

Run the explicit, network-free acceptance command:

```bash
PYTHON_BIN="$PWD/.venv/bin/python" ./scripts/run_task4_offline.sh
```

It validates project configs, runs the bounded preflight, builds `afl-fuzz` if
needed, and invokes only the declared offline test files. Expected exit code is
`0`, ending with `TASK4_OFFLINE=PASS`. The command unsets proxy variables,
does not traverse `$HOME` or `task4-evidence`, excludes `.git`/virtualenvs,
and does not discover tests recursively.

## Deterministic sample output

After the acceptance command, run:

```bash
PYTHON_BIN="$PWD/.venv/bin/python" ./scripts/run_task4_sample.sh
```

This creates a new directory under `reproduce-results/delivery-smoke-*` and
fails rather than overwriting an existing directory. It uses four committed
local seeds, a fixed AFL seed, validity enabled, and a five-second hard bound.
It writes `sample_eval_report.json`, `sample_fuzzer_stats.txt`,
`sample_summary.md`, and `sample_metadata.json`. The report must contain
`coverage_rate`, `anomaly_rate`, `recovery_rate`, `overall_score`, `task_id`,
`endpoint`, and `seed_source`; the wrapper checks JSON structure, null
denominator semantics, no secrets, and no old absolute worktree paths.

The sample is explicitly `DELIVERY_SMOKE_ONLY` and `NOT_FOR_PERFORMANCE_CLAIM`.
Cov is the bounded security-state proxy (new states divided by fixed hash-set
capacity), not total theoretical system coverage. `Err` is the error rate and
`Rec` is the recovery rate. A missing Err or recovery denominator makes the
corresponding rate and overall score `null`; a displayed zero counter is not an
observation. The sample does not change scientific claims.

## Live platform boundary

Live O2OA and Alfresco commands are separate and are never selected by the
offline runner. They require an authorized local service and credentials kept
outside the repository (for example, a mode-0600 environment file sourced only
in the invoking shell). O2OA write runs use `NV_TOKEN`,
`NV_O2OA_CATEGORY_ID`, and `NV_O2OA_CURRENT_USER_IDENTITY` together with the
target configuration; Alfresco runs use `ALFRESCO_BASE_URL`, `ALFRESCO_USER`,
and `ALFRESCO_PASS`. Existing historical real-service evidence remains
historical; this delivery command does not refresh it. The approved Alfresco
32D frozen artifact is unavailable in this checkout, so the SE comparison is
not part of the fresh offline result.

For troubleshooting, check `command -v gcc make python3-config timeout`,
`python3-config --includes`, and `python3-config --embed --ldflags`. Missing
`Python.h` means the `python3.12-dev` package is absent; missing zlib headers
means `zlib1g-dev` is absent. Do not substitute live credentials or disable a
validation assertion to make the offline command pass.
