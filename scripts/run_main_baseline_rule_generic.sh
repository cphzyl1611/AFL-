#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/AFLplusplus}"
CFG="${CFG:-$ROOT/targets/o2oa_query.json}"
IN_DIR="${IN_DIR:-$ROOT/in/o2oa_body}"
OUT_ROOT="${OUT_ROOT:-$ROOT/out/main_baseline_rule_generic}"
STATUS_PATH="${STATUS_PATH:-/tmp/nv_http_status.json}"
BODY_VALID_STATS="${BODY_VALID_STATS:-/tmp/nv_body_valid_stats.json}"
RULES_PATH="${RULES_PATH:-$ROOT/validity/o2oa_query_rules.json}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DUR="${DUR:-120}"

: "${NV_TOKEN:?NV_TOKEN is required}"

mkdir -p "$OUT_ROOT"

SUMMARY_CSV="$OUT_ROOT/summary.csv"
echo "endpoint,mode,nv_total_valid_exec,nv_err_exec,nv_err_rate,saved_hangs,saved_crashes,last_http_code,last_latency_ms,last_ncov_total,body_rule_pass,body_rule_reject" > "$SUMMARY_CSV"

get_endpoints_from_cfg() {
  "$PYTHON_BIN" - "$CFG" <<'PY'
import json, sys
cfg_path = sys.argv[1]
with open(cfg_path, "r", encoding="utf-8") as f:
    cfg = json.load(f)
eps = cfg.get("endpoints", [])
for ep in eps:
    if isinstance(ep, dict):
        name = str(ep.get("name", "")).strip()
        if name:
            print(name)
PY
}

if [[ -n "${ENDPOINTS:-}" ]]; then
  mapfile -t ENDPOINT_LIST < <(printf '%s\n' $ENDPOINTS)
else
  mapfile -t ENDPOINT_LIST < <(get_endpoints_from_cfg)
fi

if [[ "${#ENDPOINT_LIST[@]}" -eq 0 ]]; then
  echo "[ERR] no endpoints found. Set ENDPOINTS or check $CFG"
  exit 1
fi

run_one() {
  local endpoint="$1"
  local mode="$2"   # baseline | rule_only
  local outdir="$OUT_ROOT/${endpoint}_${mode}"

  echo "[*] Running endpoint=$endpoint mode=$mode -> $outdir"

  rm -rf "$outdir"
  rm -f "$STATUS_PATH" "$BODY_VALID_STATS"

  export NV_TARGET_CONFIG="$CFG"
  export NV_TOKEN=${NV_TOKEN}
  export NV_ENDPOINT_NAME="$endpoint"
  export NV_STATUS_PATH="$STATUS_PATH"
  export NV_BODY_VALID_STATS="$BODY_VALID_STATS"

  unset NV_BODY_SCORE_ENDPOINT || true
  unset NV_BODY_SCORE_THRESHOLD || true

  if [[ "$mode" == "baseline" ]]; then
    unset NV_BODY_RULES || true
  elif [[ "$mode" == "rule_only" ]]; then
    export NV_BODY_RULES="$RULES_PATH"
  else
    echo "[ERR] unknown mode: $mode"
    exit 1
  fi

  timeout "${DUR}s" \
    env AFL_NO_UI=1 \
    "$ROOT/afl-fuzz" -n \
      -i "$IN_DIR" \
      -o "$outdir" \
      -- "$PYTHON_BIN" "$ROOT/nv_http_harness.py" \
    || true

  local stats="$outdir/fuzzer_stats"

  if [[ ! -f "$stats" ]]; then
    echo "[WARN] missing fuzzer_stats for endpoint=$endpoint mode=$mode"
    echo "$endpoint,$mode,0,0,0,0,0,-1,-1,-1,0,0" >> "$SUMMARY_CSV"
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
except Exception:
    print(0); print(0)
PY
    )
    body_rule_pass="${bparsed[0]}"
    body_rule_reject="${bparsed[1]}"
  fi

  echo "$endpoint,$mode,$nv_total_valid_exec,$nv_err_exec,$nv_err_rate,$saved_hangs,$saved_crashes,$last_http_code,$last_latency_ms,$last_ncov_total,$body_rule_pass,$body_rule_reject" >> "$SUMMARY_CSV"
}

for ep in "${ENDPOINT_LIST[@]}"; do
  run_one "$ep" baseline
  run_one "$ep" rule_only
done

echo
echo "[OK] Wrote $SUMMARY_CSV"
cat "$SUMMARY_CSV"