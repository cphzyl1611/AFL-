#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/AFLplusplus}"
CFG="${CFG:-$ROOT/targets/o2oa_query.json}"
IN_DIR="${IN_DIR:-$ROOT/in/o2oa_body}"
OUT_ROOT="${OUT_ROOT:-$ROOT/out/cms_score_sweep}"
RULES_PATH="${RULES_PATH:-$ROOT/validity/o2oa_query_rules.json}"
STATUS_PATH="${STATUS_PATH:-/tmp/nv_http_status.json}"
BODY_VALID_STATS="${BODY_VALID_STATS:-/tmp/nv_body_valid_stats.json}"
DUR="${DUR:-120}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

: "${NV_TOKEN:?NV_TOKEN is required}"

ENDPOINT="cms_doc_list"
RULES_PATH="${RULES_PATH:-$ROOT/validity/o2oa_query_rules.json}"
SCORE_ENDPOINT="${NV_BODY_SCORE_ENDPOINT:-unix:///tmp/nv_valid.sock}"

THRESHOLDS=(
  "5.82"
  "2.0"
  "1.0"
  "0.5"
  "0.2"
)

mkdir -p "$OUT_ROOT"

SUMMARY_CSV="$OUT_ROOT/summary.csv"
echo "threshold,nv_total_valid_exec,nv_err_exec,nv_err_rate,saved_hangs,saved_crashes,last_http_code,last_latency_ms,last_ncov_total,body_rule_pass,body_rule_reject,body_score_pass,body_score_reject" > "$SUMMARY_CSV"

run_one() {
  local th="$1"
  local tag
  tag=$(echo "$th" | tr '.' '_')
  local outdir="$OUT_ROOT/th_${tag}"

  echo "[*] Running threshold=$th -> $outdir"

  rm -rf "$outdir"
  rm -f "$STATUS_PATH" "$BODY_VALID_STATS"

  export NV_TARGET_CONFIG="$CFG"
  export NV_TOKEN="$NV_TOKEN"
  export NV_ENDPOINT_NAME="$ENDPOINT"
  export NV_STATUS_PATH="$STATUS_PATH"

  export NV_BODY_RULES="$RULES_PATH"
  export NV_BODY_SCORE_ENDPOINT="$SCORE_ENDPOINT"
  export NV_BODY_SCORE_THRESHOLD="$th"
  export NV_BODY_VALID_STATS="$BODY_VALID_STATS"

  timeout "${DUR}s" \
    env AFL_NO_UI=1 \
    "$ROOT/afl-fuzz" -n \
      -i "$IN_DIR" \
      -o "$outdir" \
      -- "$PYTHON_BIN" "$ROOT/nv_http_harness.py" \
    || true

  local stats="$outdir/fuzzer_stats"

  if [[ ! -f "$stats" ]]; then
    echo "[WARN] missing fuzzer_stats for threshold=$th"
    echo "$th,0,0,0,0,0,-1,-1,-1,0,0,0,0" >> "$SUMMARY_CSV"
    return
  fi

  local nv_total_valid_exec nv_err_exec nv_err_rate saved_hangs saved_crashes
  nv_total_valid_exec=$(awk -F: '/^nv_total_valid_exec/ {gsub(/ /,"",$2); print $2}' "$stats")
  nv_err_exec=$(awk -F: '/^nv_err_exec/ {gsub(/ /,"",$2); print $2}' "$stats")
  nv_err_rate=$(awk -F: '/^nv_err_rate/ {gsub(/ /,"",$2); print $2}' "$stats")
  saved_hangs=$(awk -F: '/^saved_hangs/ {gsub(/ /,"",$2); print $2}' "$stats")
  saved_crashes=$(awk -F: '/^saved_crashes/ {gsub(/ /,"",$2); print $2}' "$stats")

  local last_http_code="-1"
  local last_latency_ms="-1"
  local last_ncov_total="-1"

  if [[ -f "$STATUS_PATH" ]]; then
    readarray -t parsed < <(
      "$PYTHON_BIN" - <<PY
import json
p="$STATUS_PATH"
try:
    with open(p,"r",encoding="utf-8") as f:
        o=json.load(f)
    print(o.get("http_code",-1))
    print(o.get("latency_ms",-1))
    print(o.get("ncov_total",-1))
except Exception:
    print(-1); print(-1); print(-1)
PY
    )
    last_http_code="${parsed[0]}"
    last_latency_ms="${parsed[1]}"
    last_ncov_total="${parsed[2]}"
  fi

  local body_rule_pass=0
  local body_rule_reject=0
  local body_score_pass=0
  local body_score_reject=0

  if [[ -f "$BODY_VALID_STATS" ]]; then
    readarray -t bparsed < <(
      "$PYTHON_BIN" - <<PY
import json
p="$BODY_VALID_STATS"
try:
    with open(p,"r",encoding="utf-8") as f:
        o=json.load(f)
    print(int(o.get("body_rule_pass",0)))
    print(int(o.get("body_rule_reject",0)))
    print(int(o.get("body_score_pass",0)))
    print(int(o.get("body_score_reject",0)))
except Exception:
    print(0); print(0); print(0); print(0)
PY
    )
    body_rule_pass="${bparsed[0]}"
    body_rule_reject="${bparsed[1]}"
    body_score_pass="${bparsed[2]}"
    body_score_reject="${bparsed[3]}"
  fi

  echo "$th,$nv_total_valid_exec,$nv_err_exec,$nv_err_rate,$saved_hangs,$saved_crashes,$last_http_code,$last_latency_ms,$last_ncov_total,$body_rule_pass,$body_rule_reject,$body_score_pass,$body_score_reject" >> "$SUMMARY_CSV"
}

for th in "${THRESHOLDS[@]}"; do
  run_one "$th"
done

echo
echo "[OK] Wrote $SUMMARY_CSV"
cat "$SUMMARY_CSV"