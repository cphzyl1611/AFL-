#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ABLATION_OUT_DIR="${ABLATION_OUT_DIR:-$ROOT/out/alfresco_afl_multipart_online_filter_ablation}"
DUR="${DUR:-20}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ -e "$ABLATION_OUT_DIR" ]]; then
  echo "[ERR] multipart ablation output directory already exists: $ABLATION_OUT_DIR" >&2
  echo "[ERR] set ABLATION_OUT_DIR to a fresh path; this script does not delete existing evidence." >&2
  exit 2
fi
if [[ ! -x "$ROOT/afl-fuzz" ]]; then
  echo "[ERR] $ROOT/afl-fuzz is missing or not executable. Run: make -j2 afl-fuzz" >&2
  exit 2
fi

mkdir -p "$ABLATION_OUT_DIR"

run_mode() {
  local mode="$1"
  local fanogan_enabled="$2"
  local afl_exec_timeout_ms="${3:-}"
  local mode_out_dir="$ABLATION_OUT_DIR/$mode"

  echo "[*] Multipart online filter ablation mode=$mode fanogan_enabled=$fanogan_enabled"
  OUT_DIR="$mode_out_dir" \
    ONLINE_FILTER_MODE="$mode" \
    FANOGAN_ENABLED="$fanogan_enabled" \
    AFL_EXEC_TIMEOUT_MS="$afl_exec_timeout_ms" \
    DUR="$DUR" \
    PYTHON_BIN="$PYTHON_BIN" \
    bash "$ROOT/scripts/run_alfresco_afl_multipart_online_filter_smoke.sh"

  OUT_DIR="$mode_out_dir" "$PYTHON_BIN" "$ROOT/scripts/summarize_alfresco_afl_multipart_online_filter_smoke.py"
}

run_mode rule_only 0
run_mode rule_ae 0
run_mode rule_fanogan 1 5000
run_mode rule_ae_fanogan 1 5000

echo "[OK] Multipart online filter ablation runs completed under $ABLATION_OUT_DIR"
