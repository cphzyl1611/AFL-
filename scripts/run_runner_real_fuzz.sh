#!/usr/bin/env bash
set -euo pipefail

: "${ROOT:?ROOT is required}"
: "${CFG:?CFG is required}"
: "${IN_DIR:?IN_DIR is required and must be the runner manifest seed view}"
: "${SEED_MANIFEST:?SEED_MANIFEST is required}"
: "${OUT_ROOT:?OUT_ROOT is required}"
: "${BODY_VALID_STATS:?BODY_VALID_STATS is required}"
: "${STATUS_PATH:?STATUS_PATH is required}"
: "${RUNNER_RUN_DIR:?RUNNER_RUN_DIR is required}"
: "${DUR:?DUR is required}"

: "${NV_TOKEN:?NV_TOKEN is required}"
: "${NV_BODY_SCORE_ENDPOINT:?NV_BODY_SCORE_ENDPOINT is required}"
: "${NV_BODY_SCORE_THRESHOLD:?NV_BODY_SCORE_THRESHOLD is required}"

export NV_DEBUG_BODY_VALID="${NV_DEBUG_BODY_VALID:-1}"
export ROOT CFG IN_DIR SEED_MANIFEST OUT_ROOT BODY_VALID_STATS STATUS_PATH RUNNER_RUN_DIR NV_TASK_PATH NV_KEEP_INITIAL_SEEDS NV_STATUS_LEDGER_PATH NV_PROBE_PATH NV_STATE_TRACE_PATH NV_CTX_PATH NV_MAB_JOURNAL_PATH NV_EXECUTION_LEDGER_PATH NV_SEED_SELECTION_AUDIT_PATH DUR

exec "$ROOT/scripts/run_cms_body_valid_compare_real_rulescore_only.sh"
