#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
IN_DIR="${IN_DIR:-$ROOT/in/alfresco_afl_content_update_smoke}"
OUT_DIR="${OUT_DIR:-$ROOT/out/alfresco_afl_content_update_smoke_latest}"
TARGET="${TARGET:-$ROOT/targets/alfresco_content_update_mock.py}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DUR="${DUR:-20}"

if [[ ! -x "$ROOT/afl-fuzz" ]]; then
  echo "[ERR] $ROOT/afl-fuzz is missing or not executable. Run: make -j2 afl-fuzz" >&2
  exit 2
fi
if [[ ! -d "$IN_DIR" ]]; then
  echo "[ERR] input seed directory missing: $IN_DIR" >&2
  exit 2
fi
if [[ ! -f "$TARGET" ]]; then
  echo "[ERR] mock target missing: $TARGET" >&2
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
export ALFRESCO_AFL_MOCK_STATS_PATH="$OUT_DIR/mock_stats.jsonl"

echo "[*] Running representative AFL++ mutation-chain smoke"
echo "[*] input=$IN_DIR"
echo "[*] output=$OUT_DIR"
echo "[*] duration=${DUR}s"

set +e
timeout "${DUR}s" "$ROOT/afl-fuzz" -n -m none -i "$IN_DIR" -o "$OUT_DIR" -- "$PYTHON_BIN" "$TARGET" @@
status=$?
set -e

if [[ "$status" -ne 0 && "$status" -ne 124 ]]; then
  echo "[ERR] afl-fuzz failed with status=$status" >&2
  exit "$status"
fi

echo "[OK] AFL++ smoke finished with status=$status"
find "$OUT_DIR" -name fuzzer_stats -print
