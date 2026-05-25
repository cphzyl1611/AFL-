#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
IN_DIR="${IN_DIR:-$ROOT/in/alfresco_afl_metadata_update_smoke}"
OUT_DIR="${OUT_DIR:-$ROOT/out/alfresco_afl_metadata_online_filter_smoke_latest}"
TARGET="${TARGET:-$ROOT/targets/alfresco_metadata_update_online_filter_wrapper.py}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DUR="${DUR:-20}"
ONLINE_FILTER_MODE="${ONLINE_FILTER_MODE:-rule_ae}"
FANOGAN_ENABLED="${FANOGAN_ENABLED:-0}"
AFL_EXEC_TIMEOUT_MS="${AFL_EXEC_TIMEOUT_MS:-}"

if [[ ! -x "$ROOT/afl-fuzz" ]]; then
  echo "[ERR] $ROOT/afl-fuzz is missing or not executable. Run: make -j2 afl-fuzz" >&2
  exit 2
fi
if [[ ! -d "$IN_DIR" ]]; then
  echo "[ERR] input seed directory missing: $IN_DIR" >&2
  exit 2
fi
if [[ ! -f "$TARGET" ]]; then
  echo "[ERR] metadata online filter wrapper missing: $TARGET" >&2
  exit 2
fi
if [[ -e "$OUT_DIR" ]]; then
  echo "[ERR] output directory already exists: $OUT_DIR" >&2
  echo "[ERR] move it aside or set OUT_DIR to a fresh path; this script does not delete existing evidence." >&2
  exit 2
fi

mkdir -p "$OUT_DIR"

export AFL_NO_UI=1
export AFL_SKIP_CPUFREQ=1
export AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1
export ONLINE_FILTER_MODE
export FANOGAN_ENABLED
export ONLINE_FILTER_STATS_PATH="$OUT_DIR/filter_stats.jsonl"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "[*] Running Alfresco metadata_update AFL++ online filter smoke"
echo "[*] input=$IN_DIR"
echo "[*] output=$OUT_DIR"
echo "[*] duration=${DUR}s"
echo "[*] online_filter_mode=$ONLINE_FILTER_MODE"
echo "[*] fanogan_enabled=$FANOGAN_ENABLED"
if [[ -n "$AFL_EXEC_TIMEOUT_MS" ]]; then
  echo "[*] afl_exec_timeout_ms=$AFL_EXEC_TIMEOUT_MS"
fi

afl_timeout_args=()
if [[ -n "$AFL_EXEC_TIMEOUT_MS" ]]; then
  afl_timeout_args=(-t "$AFL_EXEC_TIMEOUT_MS")
fi
unset AFL_EXEC_TIMEOUT_MS

set +e
timeout "${DUR}s" "$ROOT/afl-fuzz" -n -m none "${afl_timeout_args[@]}" -i "$IN_DIR" -o "$OUT_DIR" -- "$PYTHON_BIN" "$TARGET" @@
status=$?
set -e

if [[ "$status" -ne 0 && "$status" -ne 124 ]]; then
  echo "[ERR] afl-fuzz failed with status=$status" >&2
  exit "$status"
fi

echo "[OK] AFL++ metadata_update online filter smoke finished with status=$status"
find "$OUT_DIR" -name fuzzer_stats -print
