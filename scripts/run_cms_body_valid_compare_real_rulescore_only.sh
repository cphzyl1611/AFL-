#!/usr/bin/env bash
set -euo pipefail

: "${ROOT:?ROOT is required}"
: "${CFG:?CFG is required}"
: "${IN_DIR:?IN_DIR is required and must be the runner manifest seed view}"
: "${SEED_MANIFEST:?SEED_MANIFEST is required}"
: "${OUT_ROOT:?OUT_ROOT is required}"
: "${BODY_VALID_STATS:?BODY_VALID_STATS is required}"
: "${STATUS_PATH:?STATUS_PATH is required}"
: "${RUNNER_RUN_DIR:?RUNNER_RUN_DIR is required}"
: "${DUR:?DUR is required}"

SCRIPT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
ROOT="$(realpath -e -- "$ROOT")"
if [[ "$ROOT" != "$SCRIPT_ROOT" ]]; then
  echo "[ERR] ROOT must be the bounded source root containing this script" >&2
  exit 2
fi

reject_traversal() {
  local name="$1"
  local value="$2"
  if [[ "$value" != /* || "/$value/" == */../* ]]; then
    echo "[ERR] $name must be an absolute path without traversal" >&2
    exit 2
  fi
}

require_under() {
  local name="$1"
  local value="$2"
  local parent="$3"
  reject_traversal "$name" "$value"
  value="$(realpath -m -- "$value")"
  if [[ "$value" != "$parent" && "$value" != "$parent"/* ]]; then
    echo "[ERR] $name escapes its approved root" >&2
    exit 2
  fi
  printf '%s\n' "$value"
}

reject_traversal RUNNER_RUN_DIR "$RUNNER_RUN_DIR"
RUNNER_RUN_DIR="$(realpath -m -- "$RUNNER_RUN_DIR")"
if [[ "$RUNNER_RUN_DIR" == "$ROOT" || "$RUNNER_RUN_DIR" == "$ROOT"/* ]]; then
  echo "[ERR] RUNNER_RUN_DIR must be outside ROOT" >&2
  exit 2
fi

CFG="$(require_under CFG "$CFG" "$ROOT")"
SEED_MANIFEST="$(require_under SEED_MANIFEST "$SEED_MANIFEST" "$ROOT")"
IN_DIR="$(require_under IN_DIR "$IN_DIR" "$RUNNER_RUN_DIR")"
OUT_ROOT="$(require_under OUT_ROOT "$OUT_ROOT" "$RUNNER_RUN_DIR")"
BODY_VALID_STATS="$(require_under BODY_VALID_STATS "$BODY_VALID_STATS" "$RUNNER_RUN_DIR")"
STATUS_PATH="$(require_under STATUS_PATH "$STATUS_PATH" "$RUNNER_RUN_DIR")"
if [[ ! -f "$CFG" || ! -f "$SEED_MANIFEST" || ! -d "$IN_DIR" ]]; then
  echo "[ERR] CFG, SEED_MANIFEST, and manifest-only IN_DIR must exist" >&2
  exit 2
fi
if [[ ! "$DUR" =~ ^[1-9][0-9]*$ ]]; then
  echo "[ERR] DUR must be a positive integer" >&2
  exit 2
fi

declare -A manifest_seeds=()
idx=0
while IFS= read -r manifest_line || [[ -n "$manifest_line" ]]; do
  manifest_line="${manifest_line%$'\r'}"
  [[ -z "${manifest_line//[[:space:]]/}" || "$manifest_line" == \#* ]] && continue
  seed_name="${manifest_line%%,*}"
  seed_name="${seed_name#"${seed_name%%[![:space:]]*}"}"
  seed_name="${seed_name%"${seed_name##*[![:space:]]}"}"
  seed_name="${seed_name##*/}"
  idx=$((idx + 1))
  prefixed=$(printf '%04d__%s' "$idx" "$seed_name")
  if [[ -z "$seed_name" || ! -e "$IN_DIR/$prefixed" || -n "${manifest_seeds[$seed_name]:-}" ]]; then
    echo "[ERR] IN_DIR does not match SEED_MANIFEST" >&2
    exit 2
  fi
  manifest_seeds["$seed_name"]=1
done < "$SEED_MANIFEST"
if (( ${#manifest_seeds[@]} == 0 )); then
  echo "[ERR] SEED_MANIFEST has no seeds" >&2
  exit 2
fi
for seed_path in "$IN_DIR"/*; do
  [[ -e "$seed_path" || -L "$seed_path" ]] || continue
  entry_name="${seed_path##*/}"
  base_name="${entry_name#*__}"
  if [[ -z "${manifest_seeds[$base_name]:-}" ]]; then
    echo "[ERR] IN_DIR contains a seed outside SEED_MANIFEST" >&2
    exit 2
  fi
done

RULES_PATH="${RULES_PATH:-$ROOT/validity/o2oa_query_rules.json}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

: "${NV_TOKEN:?NV_TOKEN is required}"

ENDPOINT="cms_doc_list"
SCORE_ENDPOINT_DEFAULT="unix:///tmp/nv_valid_real.sock"
SCORE_THRESHOLD_DEFAULT="1.5"

mkdir -p "$OUT_ROOT"

SUMMARY_CSV="$OUT_ROOT/summary.csv"
SUMMARY_SOURCE="aflpp_harness"
EXECUTION_SCOPE="o2oa_aflpp_body_harness"
METRIC_SEMANTICS="AFL++ fuzzer_stats plus nv_http_harness body validity counters"
echo "mode,nv_total_valid_exec,nv_err_exec,nv_err_rate,saved_hangs,saved_crashes,last_http_code,last_latency_ms,last_ncov_total,body_rule_pass,body_rule_reject,body_score_pass,body_score_reject,body_score_rpc_ok,body_score_rpc_fail,summary_source,execution_scope,metric_semantics" > "$SUMMARY_CSV"

run_one() {
  local mode="$1"   # baseline | rule_only | rule_score
  local outdir="$OUT_ROOT/$mode"

  echo "[*] Running mode=$mode -> $outdir"

  rm -rf "$outdir"
  rm -f "$STATUS_PATH" "$BODY_VALID_STATS"

  export NV_TARGET_CONFIG="$CFG"
  export NV_ENDPOINT_NAME="$ENDPOINT"
  export NV_STATUS_PATH="$STATUS_PATH"
  export NV_STATUS_LEDGER_PATH="${NV_STATUS_LEDGER_PATH:-$RUNNER_RUN_DIR/evidence/status.jsonl}"
  export AFL_PYTHON_MODULE="nv_json_mutator"
  export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
  export NV_BODY_ONLY_MODE=1
  export NV_KEEP_INITIAL_SEEDS=1
  export NV_TOKEN=${NV_TOKEN}
  export NV_PROBE_PATH="${NV_PROBE_PATH:-$RUNNER_RUN_DIR/nv_probe.json}"
  export NV_STATE_TRACE_PATH="${NV_STATE_TRACE_PATH:-$RUNNER_RUN_DIR/nv_state_trace.jsonl}"
  export NV_CTX_PATH="${NV_CTX_PATH:-$RUNNER_RUN_DIR/nv_ctx.json}"
  export NV_MAB_JOURNAL_PATH="${NV_MAB_JOURNAL_PATH:-$RUNNER_RUN_DIR/evidence/mab_updates.jsonl}"
  export NV_EXECUTION_LEDGER_PATH="${NV_EXECUTION_LEDGER_PATH:-$RUNNER_RUN_DIR/evidence/executions.jsonl}"
  export NV_SEED_SELECTION_AUDIT_PATH="${NV_SEED_SELECTION_AUDIT_PATH:-$RUNNER_RUN_DIR/evidence/seed_selection.jsonl}"
  mkdir -p "${RUNNER_RUN_DIR}/evidence"

  # 关闭旧 C-side validity，避免干扰
  unset ENABLE_VALIDITY || true
  unset NV_VALIDITY_ENDPOINT || true
  unset NV_VALIDITY_THRESHOLD || true

  # 保存外部传入值；如果没传，再用 real 默认值
  local SCORE_ENDPOINT_EFFECTIVE="${NV_BODY_SCORE_ENDPOINT:-$SCORE_ENDPOINT_DEFAULT}"
  local SCORE_THRESHOLD_EFFECTIVE="${NV_BODY_SCORE_THRESHOLD:-$SCORE_THRESHOLD_DEFAULT}"

  unset NV_BODY_RULES || true
  unset NV_BODY_SCORE_ENDPOINT || true
  unset NV_BODY_SCORE_THRESHOLD || true
  export NV_BODY_VALID_STATS="$BODY_VALID_STATS"

  case "$mode" in
    baseline)
      ;;
    rule_only)
      export NV_BODY_RULES="$RULES_PATH"
      ;;
    rule_score)
      export NV_BODY_RULES="$RULES_PATH"
      export NV_BODY_SCORE_ENDPOINT="$SCORE_ENDPOINT_EFFECTIVE"
      export NV_BODY_SCORE_THRESHOLD="$SCORE_THRESHOLD_EFFECTIVE"
      echo "[DBG] rule_score endpoint=$NV_BODY_SCORE_ENDPOINT threshold=$NV_BODY_SCORE_THRESHOLD"
      env | grep '^NV_BODY_' | sort
      echo "[DBG] rule_score endpoint=$NV_BODY_SCORE_ENDPOINT threshold=$NV_BODY_SCORE_THRESHOLD"
      ;;
    *)
      echo "[ERR] unknown mode: $mode"
      exit 1
      ;;
  esac

  set +e
  timeout "${DUR}s" \
    env AFL_NO_UI=1 \
    "$ROOT/afl-fuzz" -n -Z \
      -i "$IN_DIR" \
    -o "$outdir" \
    -- "$PYTHON_BIN" "$ROOT/nv_http_harness.py"
  run_rc=$?
  set -e
  if (( run_rc != 0 && run_rc != 124 )); then
    echo "[ERR] bounded AFL runner failed for mode=$mode rc=$run_rc" >&2
    return "$run_rc"
  fi
  if (( run_rc == 124 )); then
    echo "[WARN] bounded AFL budget expired for mode=$mode; collecting artifacts" >&2
  fi

  local stats="$outdir/fuzzer_stats"
  if [[ ! -f "$stats" ]]; then
    echo "[ERR] missing_fuzzer_stats for mode=$mode" >&2
    return 66
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
  local body_score_rpc_ok=0
  local body_score_rpc_fail=0

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
    print(int(o.get("body_score_rpc_ok",0)))
    print(int(o.get("body_score_rpc_fail",0)))
except Exception:
    print(0); print(0); print(0); print(0); print(0); print(0)
PY
    )
    body_rule_pass="${bparsed[0]}"
    body_rule_reject="${bparsed[1]}"
    body_score_pass="${bparsed[2]}"
    body_score_reject="${bparsed[3]}"
    body_score_rpc_ok="${bparsed[4]}"
    body_score_rpc_fail="${bparsed[5]}"
  fi

  echo "$mode,$nv_total_valid_exec,$nv_err_exec,$nv_err_rate,$saved_hangs,$saved_crashes,$last_http_code,$last_latency_ms,$last_ncov_total,$body_rule_pass,$body_rule_reject,$body_score_pass,$body_score_reject,$body_score_rpc_ok,$body_score_rpc_fail,$SUMMARY_SOURCE,$EXECUTION_SCOPE,$METRIC_SEMANTICS" >> "$SUMMARY_CSV"
}


run_one rule_score

echo
echo "[OK] Wrote $SUMMARY_CSV"
cat "$SUMMARY_CSV"
