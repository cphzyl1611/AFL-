#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/AFLplusplus}"
CFG="${CFG:-$ROOT/nv_target_o2oa_query.json}"
IN_DIR="${IN_DIR:-$ROOT/in_o2oa_body}"
OUT_ROOT="${OUT_ROOT:-$ROOT/out_o2oa_body_baseline}"
STATUS_PATH="${STATUS_PATH:-/tmp/nv_http_status.json}"
DUR="${DUR:-180}"   # 每个接口跑多少秒，先默认 180 秒
PYTHON_BIN="${PYTHON_BIN:-python3}"

# 需要你事先 export NV_TOKEN=...
: "${NV_TOKEN:?NV_TOKEN is required}"

ENDPOINTS=(
  "cms_doc_list"
  "person_detail"
  "review_count"
  "hotpic_list"
  "calendar_filter"
)

mkdir -p "$OUT_ROOT"

SUMMARY_CSV="$OUT_ROOT/summary.csv"
echo "endpoint,nv_total_valid_exec,nv_err_exec,nv_err_rate,saved_hangs,saved_crashes,last_http_code,last_latency_ms,last_ncov_total" > "$SUMMARY_CSV"

run_one() {
  local ep="$1"
  local outdir="$OUT_ROOT/$ep"

  echo "[*] Running endpoint=$ep -> $outdir"

  rm -rf "$outdir"
  rm -f "$STATUS_PATH"

  export NV_TARGET_CONFIG="$CFG"
  export NV_ENDPOINT_NAME="$ep"
  export NV_STATUS_PATH="$STATUS_PATH"

  # timeout 到点后返回非 0，这里不能因为 set -e 直接退出
  timeout "${DUR}s" \
    env AFL_NO_UI=1 \
    "$ROOT/afl-fuzz" -n \
      -i "$IN_DIR" \
      -o "$outdir" \
      -- "$PYTHON_BIN" "$ROOT/nv_http_harness.py" \
    || true

  local stats="$outdir/fuzzer_stats"

  if [[ ! -f "$stats" ]]; then
    echo "[WARN] missing fuzzer_stats for $ep"
    echo "$ep,0,0,0,0,0,-1,-1,-1" >> "$SUMMARY_CSV"
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

  echo "$ep,$nv_total_valid_exec,$nv_err_exec,$nv_err_rate,$saved_hangs,$saved_crashes,$last_http_code,$last_latency_ms,$last_ncov_total" >> "$SUMMARY_CSV"
}

for ep in "${ENDPOINTS[@]}"; do
  run_one "$ep"
done

echo
echo "[OK] Wrote $SUMMARY_CSV"
cat "$SUMMARY_CSV"