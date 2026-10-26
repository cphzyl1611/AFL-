#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="${OUT_DIR:-$ROOT/reproduce-results/delivery-smoke-$STAMP}"
if [[ -e "$OUT_DIR" ]]; then
  echo "ERROR: refusing to overwrite existing sample directory: $OUT_DIR" >&2
  exit 2
fi

mkdir -p "$(dirname "$OUT_DIR")"
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    -u ALL_PROXY -u all_proxy \
    ROOT="$ROOT" OUT_DIR="$OUT_DIR" PYTHON_BIN="$PYTHON_BIN" \
    MAX_TEST_CASES="${MAX_TEST_CASES:-8}" \
    TIME_BUDGET="${TIME_BUDGET:-5}" HARD_TIMEOUT="${HARD_TIMEOUT:-20}" \
    AFL_RAND_SEED="${AFL_RAND_SEED:-20261026}" \
    "$PYTHON_BIN" "$ROOT/scripts/run_task4_sample.py"

echo "TASK4_SAMPLE=PASS"
echo "SAMPLE_DIR=$OUT_DIR"
