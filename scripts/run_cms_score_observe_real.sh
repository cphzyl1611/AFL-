#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/AFLplusplus}"
CFG="${CFG:-$ROOT/targets/o2oa_query.json}"
IN_DIR="${IN_DIR:-$ROOT/in/o2oa_body_cms_score}"
OUT_ROOT="${OUT_ROOT:-$ROOT/out/cms_score_observe_real}"
RULES_PATH="${RULES_PATH:-$ROOT/validity/o2oa_query_rules.json}"
STATUS_PATH="${STATUS_PATH:-/tmp/nv_http_status.json}"
BODY_VALID_STATS="${BODY_VALID_STATS:-/tmp/nv_body_valid_stats.json}"
DUR="${DUR:-120}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

: "${NV_TOKEN:?NV_TOKEN is required}"

mkdir -p "$OUT_ROOT"
rm -rf "$OUT_ROOT"/*
rm -f "$STATUS_PATH" "$BODY_VALID_STATS"

export NV_TARGET_CONFIG="$CFG"
export NV_ENDPOINT_NAME="cms_doc_list"
export NV_STATUS_PATH="$STATUS_PATH"
export NV_TOKEN="$NV_TOKEN"
export NV_BODY_RULES="$RULES_PATH"
export NV_BODY_VALID_STATS="$BODY_VALID_STATS"

# 关键：这里故意给一个极大阈值，只观察 score，不做 reject
export NV_BODY_SCORE_ENDPOINT="${NV_BODY_SCORE_ENDPOINT:-unix:///tmp/nv_valid_real.sock}"
export NV_BODY_SCORE_THRESHOLD="${NV_BODY_SCORE_THRESHOLD:-999999}"
export NV_DEBUG_BODY_VALID="${NV_DEBUG_BODY_VALID:-1}"

unset NV_TASK_PATH || true
unset ENABLE_VALIDITY || true
unset NV_VALIDITY_ENDPOINT || true
unset NV_VALIDITY_THRESHOLD || true

echo "[*] Observing model score distribution..."
echo "[*] endpoint=$NV_ENDPOINT_NAME"
echo "[*] score_endpoint=$NV_BODY_SCORE_ENDPOINT"
echo "[*] score_threshold=$NV_BODY_SCORE_THRESHOLD"
echo "[*] in_dir=$IN_DIR"
echo "[*] out_root=$OUT_ROOT"

timeout "${DUR}s" \
  env AFL_NO_UI=1 \
  "$ROOT/afl-fuzz" -n \
    -i "$IN_DIR" \
    -o "$OUT_ROOT" \
    -- "$PYTHON_BIN" "$ROOT/nv_http_harness.py" \
  || true

echo
echo "[*] BODY_VALID_STATS:"
cat "$BODY_VALID_STATS" 2>/dev/null || true

echo
echo "[*] STATUS_PATH:"
cat "$STATUS_PATH" 2>/dev/null || true

echo
echo "[*] fuzzer_stats:"
tail -n 80 "$OUT_ROOT/fuzzer_stats" 2>/dev/null || true

echo
echo "[OK] observation finished: $OUT_ROOT"