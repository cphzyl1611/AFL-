#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
STABILITY_OUT_DIR="${STABILITY_OUT_DIR:-$ROOT/out/alfresco_afl_content_update_stability}"
RUNS="${RUNS:-3}"
DUR="${DUR:-60}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ "$RUNS" -lt 1 ]]; then
  echo "[ERR] RUNS must be >= 1" >&2
  exit 2
fi
if [[ -e "$STABILITY_OUT_DIR" ]]; then
  echo "[ERR] stability output directory already exists: $STABILITY_OUT_DIR" >&2
  echo "[ERR] set STABILITY_OUT_DIR to a fresh path; this script does not delete existing evidence." >&2
  exit 2
fi
if [[ ! -x "$ROOT/afl-fuzz" ]]; then
  echo "[ERR] $ROOT/afl-fuzz is missing or not executable. Run: make -j2 afl-fuzz" >&2
  exit 2
fi

mkdir -p "$STABILITY_OUT_DIR"

for run in $(seq 1 "$RUNS"); do
  run_id="$(printf "run_%02d" "$run")"
  run_dir="$STABILITY_OUT_DIR/$run_id"
  echo "[*] Stability run $run/$RUNS -> $run_dir"
  OUT_DIR="$run_dir" DUR="$DUR" PYTHON_BIN="$PYTHON_BIN" bash "$ROOT/scripts/run_alfresco_afl_content_update_smoke.sh"
  OUT_DIR="$run_dir" "$PYTHON_BIN" "$ROOT/scripts/summarize_alfresco_afl_content_update_smoke.py"
done

echo "[OK] Stability runs completed under $STABILITY_OUT_DIR"
