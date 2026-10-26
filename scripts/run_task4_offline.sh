#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

for cmd in "$PYTHON_BIN" make timeout; do
  if [[ "$cmd" == */* ]]; then
    [[ -x "$cmd" ]] || { echo "ERROR: required executable not found: $cmd" >&2; exit 2; }
  elif ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $cmd" >&2
    exit 2
  fi
done

"$PYTHON_BIN" -c 'import pytest' >/dev/null 2>&1 || {
  echo "ERROR: pytest is unavailable; install requirements-dev.txt" >&2
  exit 2
}

PYTHON_CONFIG="$(dirname "$PYTHON_BIN")/python3-config"
if [[ ! -e "$PYTHON_CONFIG" ]]; then
  SYSTEM_PYTHON_CONFIG="$(command -v python3-config || true)"
  if [[ -z "$SYSTEM_PYTHON_CONFIG" ]]; then
    echo "ERROR: python3-config is required for C feedback probes" >&2
    exit 2
  fi
  TASK4_SYSTEM_PYTHON_CONFIG="$SYSTEM_PYTHON_CONFIG" \
    cp "$ROOT/scripts/python3-config-wrapper.sh" "$PYTHON_CONFIG"
  chmod 0755 "$PYTHON_CONFIG"
fi

cd "$ROOT"
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    -u ALL_PROXY -u all_proxy \
    "$PYTHON_BIN" scripts/validate_project_configs.py
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    -u ALL_PROXY -u all_proxy \
    "$PYTHON_BIN" scripts/delivery_preflight_check.py

if [[ ! -x "$ROOT/afl-fuzz" ]]; then
  make -j"${JOBS:-2}" afl-fuzz
fi

TEST_FILES=(
  tests/test_delivery_hardening.py
  tests/test_formal_security_score.py
  tests/test_api_formal_schema_compliance.py
  tests/test_delivery_platform_interfaces.py
  tests/test_fuzz_api.py
  tests/test_url_query.py
  tests/test_query_integration.py
  tests/test_project_configs.py
  tests/test_summary_evidence.py
  tests/test_nv_mab_unit.py
  tests/test_nv_mab_journal.py
  tests/test_nv_covset_unit.py
  tests/test_o2oa_create_update_e2e.py
  tests/test_o2oa_url_query_e2e.py
  tests/test_o2oa_share_list_query_e2e.py
  tests/test_p0_mab_feedback_evidence.py
)

env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    -u ALL_PROXY -u all_proxy \
    PYTHONHASHSEED=0 timeout "${OFFLINE_TEST_TIMEOUT:-300}s" "$PYTHON_BIN" -m pytest "${TEST_FILES[@]}" \
    -k "not test_filter_by_task_name" --maxfail=1 -q

# The full attribution probe compiles multiple C harnesses once per test and
# is intentionally kept outside the default gate. Run representative
# fail-closed and confirmed-arm contracts under a separate short bound.
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    -u ALL_PROXY -u all_proxy \
    PYTHONHASHSEED=0 timeout "${FEEDBACK_TEST_TIMEOUT:-90}s" "$PYTHON_BIN" -m pytest \
    tests/test_nv_feedback_attribution.py \
    -k "c_validation_rejection_clears_pending_without_execution or confirmed_actual_arm_receives_the_only_mab_update or new_state_is_credited_once_and_existing_state_is_not" \
    --maxfail=1 -q

echo "TASK4_OFFLINE=PASS"
