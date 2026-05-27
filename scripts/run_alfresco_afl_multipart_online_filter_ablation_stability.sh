#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
STABILITY_OUT_DIR="${STABILITY_OUT_DIR:-$ROOT/out/alfresco_afl_multipart_online_filter_ablation_stability}"
RUNS="${RUNS:-3}"
DUR="${DUR:-20}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ "$RUNS" -lt 1 ]]; then
  echo "[ERR] RUNS must be >= 1" >&2
  exit 2
fi
if [[ -e "$STABILITY_OUT_DIR" ]]; then
  echo "[ERR] multipart stability output directory already exists: $STABILITY_OUT_DIR" >&2
  echo "[ERR] set STABILITY_OUT_DIR to a fresh path; this script does not delete existing evidence." >&2
  exit 2
fi
if [[ ! -x "$ROOT/afl-fuzz" ]]; then
  echo "[ERR] $ROOT/afl-fuzz is missing or not executable. Run: make -j2 afl-fuzz" >&2
  exit 2
fi

mkdir -p "$STABILITY_OUT_DIR"

run_mode_once() {
  local mode="$1"
  local fanogan_enabled="$2"
  local afl_exec_timeout_ms="$3"
  local run_id="$4"
  local run_dir="$STABILITY_OUT_DIR/$mode/$run_id"

  echo "[*] Multipart online filter ablation stability mode=$mode run=$run_id fanogan_enabled=$fanogan_enabled"
  OUT_DIR="$run_dir" \
    ONLINE_FILTER_MODE="$mode" \
    FANOGAN_ENABLED="$fanogan_enabled" \
    AFL_EXEC_TIMEOUT_MS="$afl_exec_timeout_ms" \
    DUR="$DUR" \
    PYTHON_BIN="$PYTHON_BIN" \
    bash "$ROOT/scripts/run_alfresco_afl_multipart_online_filter_smoke.sh"

  OUT_DIR="$run_dir" "$PYTHON_BIN" "$ROOT/scripts/summarize_alfresco_afl_multipart_online_filter_smoke.py"
}

for run in $(seq 1 "$RUNS"); do
  run_id="$(printf "run_%02d" "$run")"
  run_mode_once rule_only 0 "" "$run_id"
  run_mode_once rule_ae 0 "" "$run_id"
  run_mode_once rule_fanogan 1 5000 "$run_id"
  run_mode_once rule_ae_fanogan 1 5000 "$run_id"
done

echo "[OK] Multipart online filter ablation stability runs completed under $STABILITY_OUT_DIR"
