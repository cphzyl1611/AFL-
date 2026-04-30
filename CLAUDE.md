# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

This is a **research fork of AFL++** extended with two custom systems:

1. **SS probabilistic scheduler** (`feat/ss-prob-scheduler` branch): Replaces AFL++'s alias-table seed selection with a coverage-weighted roulette. Each queue entry carries `ss_cov_cnt`, `ss_selected_cnt`, and `ss_prob`. Selection weight is `(ss_cov_cnt + 1) / (ss_selected_cnt + 1)^0.7`, floored at 0.01.

2. **NV framework** (HTTP JSON API fuzzing): Extends AFL++ to fuzz live HTTP JSON APIs instead of binaries. Key additions embedded into `afl_state_t`:
   - `nv_task_cfg_t nv_task` — runtime config loaded from `task.json` or `$NV_TASK_CONFIG`
   - `nv_mab_t` — UCB multi-armed bandit with 3 mutation arms (field value, boundary, structure)
   - Validity filtering pipeline: rule-based (`nv_body_valid.py`) + optional score-based (`nv_valid_server_mock.py` over Unix socket)

## Build

```bash
make                # build afl-fuzz and all tools
make distclean      # clean everything
```

Optional flags: `ASAN_BUILD=1`, `UBSAN_BUILD=1`, `NO_UTF=1`.

The built binary is `./afl-fuzz` in the repo root.

## Running Experiments

The primary experiment entry point is:

```bash
NV_TOKEN=<token> \
CFG=targets/o2oa_query.json \
IN_DIR=in/o2oa_body \
DUR=120 \
bash scripts/run_main_baseline_rule_generic.sh
```

This runs each endpoint in both `baseline` and `rule_only` modes and writes results to `out/main_baseline_rule_generic/summary.csv`.

**Key environment variables for `afl-fuzz` + NV harness:**

| Variable | Purpose |
|---|---|
| `NV_TOKEN` | Auth token injected into HTTP headers (required) |
| `NV_TARGET_CONFIG` | Path to JSON target config (default: `task.json`) |
| `NV_ENDPOINT_NAME` | Which endpoint to fuzz (matches `name` in config) |
| `NV_BODY_RULES` | Path to validity rules JSON; unset = baseline mode |
| `NV_BODY_SCORE_ENDPOINT` | Unix socket for score-based validity server |
| `NV_BODY_SCORE_THRESHOLD` | Score threshold for second-level filter |
| `NV_STATUS_PATH` | Where harness writes HTTP response stats (default: `/tmp/nv_http_status.json`) |

## Code Architecture

### Modified AFL++ Core (C)

All modifications are additive to upstream AFL++ internals:

- **`src/afl-fuzz-queue.c`**: `select_next_queue_entry()` — the SS probabilistic scheduler. Called instead of the alias table when `old_seed_selection` is off.

- **`src/afl-fuzz-one.c`**: NV-MAB arm selection (`nv_get_current_arm()`), mutation dispatch, reward updates to `nv_mab_t`. Also contains `nv_covset_*` helpers for tracking unique coverage hashes per seed.

- **`src/afl-fuzz-run.c`**: HTTP harness integration — after each execution, reads `NV_STATUS_PATH` to get HTTP status, updates NV validity counters (`nv_valid_cnt`, `nv_err_exec`, etc.), and sends inputs to the validity Unix socket.

- **`src/afl-fuzz-init.c`**: Loads `nv_task_cfg_t` from JSON task file at startup.

- **`src/afl-fuzz-stats.c`**: Writes NV-specific fields (`nv_total_valid_exec`, `nv_err_exec`, `nv_err_rate`, etc.) to `fuzzer_stats`.

- **`include/afl-fuzz.h`**: The central `afl_state_t` struct. NV fields are grouped at the top. `queue_entry` has the three SS fields (`ss_cov_cnt`, `ss_selected_cnt`, `ss_prob`). `nv_mab_t` and `nv_task_cfg_t` typedefs are here.

### Python NV Framework

- **`nv_http_harness.py`**: AFL++ persistent-mode harness. Reads mutated input from stdin, parses as JSON body, sends HTTP request to target, writes response metadata to `$NV_STATUS_PATH`. Loaded as the `-- <target>` argument to `afl-fuzz`.

- **`nv_body_valid.py`**: Stateless validity module. Called inline from the harness. Applies rule-based filtering (field presence, type checks, depth/size limits) configured by `$NV_BODY_RULES`. Returns `(pass: bool, reason: str)`.

- **`nv_valid_server_mock.py`**: Score-based validity Unix socket server. Receives JSON payloads and returns a float score. Used as the second validity gate when `NV_BODY_SCORE_ENDPOINT` is set.

- **`nv_state_probe.py`**: Tracks fuzzer-side state (coverage count, HTTP response distribution) and writes to `$NV_STATUS_PATH`.

### Target Configurations

- **`task.json`** / **`targets/`**: JSON config files specifying `target_type`, `target_endpoint`, `endpoints[]`, `enable_validity`, `validity_endpoint`, etc.
- **`validity/`**: Rule JSON files referenced by `$NV_BODY_RULES`.
- **`in/`** / **`in_http/`**: Seed input directories.

### Third-party Additions

- **`src/third_party/cjson/`**: cJSON library used in `afl-fuzz-one.c` and `afl-fuzz-run.c` for JSON parsing inside the fuzzer core (NV reward computation, validity socket protocol).

## Branch Context

Current branch `feat/ss-prob-scheduler` contains the SS scheduler work. The global counters `ss_new_bits_any` and `ss_new_bits_kept` (declared `extern u64` across several `.c` files) track how many times seeds on this scheduler produced new coverage.
