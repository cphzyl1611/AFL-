#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/AFLplusplus}"
CFG="${CFG:-$ROOT/nv_target_o2oa_query.json}"
IN_DIR="${IN_DIR:-$ROOT/in_o2oa_body}"
OUT_ROOT="${OUT_ROOT:-$ROOT/out_o2oa_body_compare}"
STATUS_PATH="${STATUS_PATH:-/tmp/nv_http_status.json}"
DUR="${DUR:-180}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# validity 参数
VALIDITY_ENDPOINT_DEFAULT="unix:///tmp/nv_valid.sock"
VALIDITY_THRESHOLD_DEFAULT="5.82"

: "${NV_TOKEN:?NV_TOKEN is required}"

ENDPOINTS=(
  "cms_doc_list"
  "review_count"
  "hotpic_list"
)

mkdir -p "$OUT_ROOT"

SUMMARY_CSV="$OUT_ROOT/summary_compare.csv"
echo "mode,endpoint,nv_total_valid_exec,nv_err_exec,nv_err_rate,saved_hangs,saved_crashes,last_http_code,last_latency_ms,last_ncov_total,nv_valid_cnt,nv_invalid_cnt,nv_invalid_score_cnt,nv_invalid_allow_cnt,nv_invalid_parse_cnt" > "$SUMMARY_CSV"

run_one() {
  local mode="$1"   # baseline | validity
  local ep="$2"
  local outdir="$OUT_ROOT/${mode}_${ep}"
  local task_json="$outdir/task.json"

  echo "[*] Running mode=$mode endpoint=$ep -> $outdir"

  rm -rf "$outdir"
  mkdir -p "$outdir"
  rm -f "$STATUS_PATH"

  export NV_TARGET_CONFIG="$CFG"
  export NV_ENDPOINT_NAME="$ep"
  export NV_STATUS_PATH="$STATUS_PATH"

  if [[ "$mode" == "baseline" ]]; then
    cat > "$task_json" <<TASK
{
  "target_type": "binary",
  "max_test_cases": 0,
  "time_budget": ${DUR},
  "enable_validity": 0
}
TASK
  else
    local vep="${NV_VALIDITY_ENDPOINT:-$VALIDITY_ENDPOINT_DEFAULT}"
    local vth="${NV_VALIDITY_THRESHOLD:-$VALIDITY_THRESHOLD_DEFAULT}"

    cat > "$task_json" <<TASK
{
  "target_type": "binary",
  "max_test_cases": 0,
  "time_budget": ${DUR},
  "enable_validity": 1,
  "validity_endpoint": "${vep}",
  "validity_threshold": ${vth}
}
TASK
  fi

  export NV_TASK_PATH="$task_json"

  timeout "${DUR}s" \
    env AFL_NO_UI=1 \
    "$ROOT/afl-fuzz" -n \
      -i "$IN_DIR" \
      -o "$outdir" \
      -- "$PYTHON_BIN" "$ROOT/nv_http_harness.py" \
    || true

  local stats="$outdir/fuzzer_stats"

  if [[ ! -f "$stats" ]]; then
    echo "[WARN] missing fuzzer_stats for mode=$mode endpoint=$ep"
    echo "$mode,$ep,0,0,0,0,0,-1,-1,-1,0,0,0,0,0" >> "$SUMMARY_CSV"
    return
  fi

  local nv_total_valid_exec nv_err_exec nv_err_rate saved_hangs saved_crashes
  local nv_valid_cnt nv_invalid_cnt nv_invalid_score_cnt nv_invalid_allow_cnt nv_invalid_parse_cnt

  nv_total_valid_exec=$(awk -F: '/^nv_total_valid_exec/ {gsub(/ /,"",$2); print $2}' "$stats")
  nv_err_exec=$(awk -F: '/^nv_err_exec/ {gsub(/ /,"",$2); print $2}' "$stats")
  nv_err_rate=$(awk -F: '/^nv_err_rate/ {gsub(/ /,"",$2); print $2}' "$stats")
  saved_hangs=$(awk -F: '/^saved_hangs/ {gsub(/ /,"",$2); print $2}' "$stats")
  saved_crashes=$(awk -F: '/^saved_crashes/ {gsub(/ /,"",$2); print $2}' "$stats")

  nv_valid_cnt=$(awk -F: '/^nv_valid_cnt/ {gsub(/ /,"",$2); print $2}' "$stats")
  nv_invalid_cnt=$(awk -F: '/^nv_invalid_cnt/ {gsub(/ /,"",$2); print $2}' "$stats")
  nv_invalid_score_cnt=$(awk -F: '/^nv_invalid_score_cnt/ {gsub(/ /,"",$2); print $2}' "$stats")
  nv_invalid_allow_cnt=$(awk -F: '/^nv_invalid_allow_cnt/ {gsub(/ /,"",$2); print $2}' "$stats")
  nv_invalid_parse_cnt=$(awk -F: '/^nv_invalid_parse_cnt/ {gsub(/ /,"",$2); print $2}' "$stats")

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

  echo "$mode,$ep,$nv_total_valid_exec,$nv_err_exec,$nv_err_rate,$saved_hangs,$saved_crashes,$last_http_code,$last_latency_ms,$last_ncov_total,$nv_valid_cnt,$nv_invalid_cnt,$nv_invalid_score_cnt,$nv_invalid_allow_cnt,$nv_invalid_parse_cnt" >> "$SUMMARY_CSV"
}

for ep in "${ENDPOINTS[@]}"; do
  run_one baseline "$ep"
done

for ep in "${ENDPOINTS[@]}"; do
  run_one validity "$ep"
done

echo
echo "[OK] Wrote $SUMMARY_CSV"
cat "$SUMMARY_CSV"