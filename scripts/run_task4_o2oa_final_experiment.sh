#!/usr/bin/env bash
# Task 4 final O2OA reproducibility entrypoint.
#
# The default is the read-only URL-query scenario. Writes require an explicit
# opt-in and the dedicated fixture gates in run_task4_o2oa_write_experiment.py.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MAX_TEST_CASES=3
TIME_BUDGET=30
OUT_DIR=""
DRY_RUN=0
RUN_ID=""
WRITE_SCENARIO=0

usage() {
  printf '%s\n' \
    "Usage: $(basename "$0") [options]" \
    "" \
    "Run the bounded, read-only O2OA Task-4 URL-query experiment." \
    "" \
    "Options:" \
    "  --help                  Show this help." \
    "  --dry-run               Validate the local plan; do not contact O2OA." \
    "  --out-dir DIR           Fresh evidence directory." \
    "  --max-test-cases N      Counted valid fuzz cases (default: 3)." \
    "  --time-budget SEC       AFL task safety budget (default: 30)." \
    "  --with-write-scenario    Explicit bounded disposable create/update mode." \
    "" \
    "Required environment:" \
    "  NV_TOKEN                Nonblank O2OA raw token (never printed)." \
    "" \
    "Default: GET /x_file_assemble_control/jaxrs/share/list/my." \
    "Write mode additionally requires the dedicated category and identity."
}

die() {
  printf 'O2OA_EXPERIMENT_VERDICT=FAIL\nERROR=%s\n' "$1" >&2
  exit 2
}

while (($#)); do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --out-dir)
      (($# >= 2)) || die "--out-dir requires a value"
      OUT_DIR="$2"
      shift 2
      ;;
    --max-test-cases)
      (($# >= 2)) || die "--max-test-cases requires a value"
      MAX_TEST_CASES="$2"
      shift 2
      ;;
    --time-budget)
      (($# >= 2)) || die "--time-budget requires a value"
      TIME_BUDGET="$2"
      shift 2
      ;;
    --with-write-scenario)
      WRITE_SCENARIO=1
      shift
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

[[ "$MAX_TEST_CASES" =~ ^[1-9][0-9]*$ ]] || die "max-test-cases must be a positive integer"
[[ "$TIME_BUDGET" =~ ^[1-9][0-9]*$ ]] || die "time-budget must be a positive integer"
[[ -n "${NV_TOKEN:-}" ]] || die "NV_TOKEN must be set and nonblank"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "Python interpreter not found: $PYTHON_BIN"
if ((WRITE_SCENARIO)); then
  write_args=(--max-test-cases "$MAX_TEST_CASES" --time-budget "$TIME_BUDGET")
  if ((DRY_RUN)); then write_args+=(--dry-run); fi
  if [[ -n "$OUT_DIR" ]]; then write_args+=(--out-dir "$OUT_DIR"); fi
  exec "$PYTHON_BIN" "$ROOT/scripts/run_task4_o2oa_write_experiment.py" "${write_args[@]}"
fi
command -v timeout >/dev/null 2>&1 || die "timeout command not found"
[[ -x "$ROOT/afl-fuzz" ]] || die "$ROOT/afl-fuzz is missing or not executable; run: make afl-fuzz"

TARGET_CONFIG="$ROOT/targets/o2oa_query.json"
BODY_RULES="$ROOT/validity/o2oa_query_rules.json"
CANONICAL_SEED="$ROOT/in/o2oa_url_query/seed_file_share_list_my_query_0.json"
HARNESS="$ROOT/nv_http_harness.py"
MUTATOR="$ROOT/nv_json_mutator.py"

for required in "$TARGET_CONFIG" "$BODY_RULES" "$CANONICAL_SEED" "$HARNESS" "$MUTATOR"; do
  [[ -f "$required" ]] || die "required file missing: $required"
done

"$PYTHON_BIN" - "$TARGET_CONFIG" "$BODY_RULES" "$CANONICAL_SEED" <<'PY'
import json
import pathlib
import sys

config_path, rules_path, seed_path = map(pathlib.Path, sys.argv[1:])
config = json.loads(config_path.read_text(encoding="utf-8"))
rules = json.loads(rules_path.read_text(encoding="utf-8"))
seed = json.loads(seed_path.read_text(encoding="utf-8"))
endpoint = next(
    (item for item in config.get("endpoints", [])
     if item.get("name") == "file_share_list_my_query"),
    None,
)
if endpoint != {
    "name": "file_share_list_my_query",
    "method": "GET",
    "path": "/x_file_assemble_control/jaxrs/share/list/my",
    "transport": "url_query",
    "request_body": "none",
}:
    raise SystemExit("O2OA_READ_ONLY_ENDPOINT_CONTRACT_MISMATCH")
query_rule = rules.get("endpoints", {}).get("file_share_list_my_query", {}).get("query", {})
enum = query_rule.get("properties", {}).get("fileType", {}).get("enum")
if enum != ["attachment", "folder"]:
    raise SystemExit("O2OA_QUERY_RULE_CONTRACT_MISMATCH")
if seed != {"query": {"fileType": "attachment"}}:
    raise SystemExit("O2OA_CANONICAL_SEED_CONTRACT_MISMATCH")
if seed.get("body") is not None:
    raise SystemExit("O2OA_BODYLESS_SEED_CONTRACT_MISMATCH")
PY

if [[ -z "$OUT_DIR" ]]; then
  RUN_ID="$(date '+%Y%m%dT%H%M%S%z')"
  OUT_DIR="/home/cphzy/task4-evidence/final-repro-${RUN_ID}/o2oa"
else
  RUN_ID="$(basename "$(dirname "$OUT_DIR")")-$(basename "$OUT_DIR")"
fi
OUT_DIR="$(realpath -m "$OUT_DIR")"

case "$OUT_DIR" in
  "$ROOT"|"$ROOT"/*)
    die "out-dir must be outside the repository worktree"
    ;;
esac

if [[ -e "$OUT_DIR" ]] && [[ -n "$(find "$OUT_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  die "out-dir must be fresh: $OUT_DIR"
fi

if ((DRY_RUN)); then
  printf '%s\n' \
    "O2OA_DRY_RUN=PASS" \
    "NETWORK_CONTACTED=NO" \
    "CREDENTIAL_PRESENT=YES" \
    "CREDENTIAL_PRINTED=NO" \
    "METHOD=GET" \
    "ENDPOINT=/x_file_assemble_control/jaxrs/share/list/my" \
    "REQUEST_BODY=NONE" \
    "MUTATION_SCOPE=field_value,boundary,structure" \
    "MAX_TEST_CASES=$MAX_TEST_CASES" \
    "TIME_BUDGET=$TIME_BUDGET" \
    "PLANNED_RUN_ROOT=$OUT_DIR" \
    "BUSINESS_STATE_MUTATION=NO"
  exit 0
fi

# Direct, proxy-free health check. This endpoint does not receive NV_TOKEN.
"$PYTHON_BIN" - "$TARGET_CONFIG" <<'PY'
import json
import pathlib
import sys
import urllib.request

cfg = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
health = cfg.get("health_url")
base = cfg.get("base")
if health != "http://127.0.0.1:80/" or base != "http://127.0.0.1:20020":
    raise SystemExit("O2OA_PINNED_RUNTIME_TOPOLOGY_MISMATCH")
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(health, timeout=5) as response:
    code = int(response.getcode())
if not 200 <= code < 500:
    raise SystemExit("O2OA_HEALTH_CHECK_FAILED")
print(f"O2OA_DIRECT_HEALTH_HTTP={code}")
PY

mkdir -p "$OUT_DIR/evidence" "$OUT_DIR/seed_input" "$OUT_DIR/err_cases"
cp "$CANONICAL_SEED" "$OUT_DIR/seed_input/seed_file_share_list_my_query_0.json"

TASK_JSON="$OUT_DIR/task.json"
"$PYTHON_BIN" - "$TASK_JSON" "$OUT_DIR/seed_input" "$MAX_TEST_CASES" "$TIME_BUDGET" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
payload = {
    "target_type": "http_api",
    "target_endpoint": "file_share_list_my_query",
    "seed_source": "seed_file",
    "seed_location": str(pathlib.Path(sys.argv[2]).resolve()),
    "mutation_scope": ["field_value", "boundary", "structure"],
    "max_test_cases": int(sys.argv[3]),
    "time_budget": int(sys.argv[4]),
    "enable_validity": 0,
}
path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY

: > "$OUT_DIR/evidence/mab_updates.jsonl"
: > "$OUT_DIR/evidence/executions.jsonl"
: > "$OUT_DIR/evidence/seed_selection.jsonl"
: > "$OUT_DIR/evidence/status.jsonl"

export AFL_NO_UI=1
export AFL_SKIP_CPUFREQ=1
export AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1
export AFL_FAST_CAL=1
export AFL_PYTHON_MODULE=nv_json_mutator
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="127.0.0.1,localhost"
export NV_TARGET_CONFIG="$TARGET_CONFIG"
export NV_ENDPOINT_NAME="file_share_list_my_query"
export NV_BODY_ONLY_MODE=1
export NV_BODY_RULES="$BODY_RULES"
export NV_TASK_PATH="$TASK_JSON"
export NV_STATUS_PATH="$OUT_DIR/nv_http_status.json"
export NV_STATUS_LEDGER_PATH="$OUT_DIR/evidence/status.jsonl"
export NV_PROBE_PATH="$OUT_DIR/nv_probe.json"
export NV_STATE_DB="$OUT_DIR/nv_state_db.json"
export NV_STATE_TRACE_PATH="$OUT_DIR/nv_state_trace.jsonl"
export NV_BODY_VALID_STATS="$OUT_DIR/nv_body_valid_stats.json"
export NV_MAB_JOURNAL_PATH="$OUT_DIR/evidence/mab_updates.jsonl"
export NV_EXECUTION_LEDGER_PATH="$OUT_DIR/evidence/executions.jsonl"
export NV_SEED_SELECTION_AUDIT_PATH="$OUT_DIR/evidence/seed_selection.jsonl"
export NV_ERR_DIR="$OUT_DIR/err_cases"
export NV_KEEP_INITIAL_SEEDS=1

PY_LIBDIR="$("$PYTHON_BIN" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR") or "")')"
if [[ -n "$PY_LIBDIR" ]]; then
  export LD_LIBRARY_PATH="$PY_LIBDIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

printf '%s\n' \
  "O2OA_EXPERIMENT_START=YES" \
  "RUN_ROOT=$OUT_DIR" \
  "METHOD=GET" \
  "REQUEST_BODY=NONE" \
  "DIRECT_NO_PROXY=YES" \
  "CREDENTIAL_PRINTED=NO"

set +e
timeout "$((TIME_BUDGET + 60))s" \
  "$ROOT/afl-fuzz" -n -Z -m none -t 10000+ \
  -i "$OUT_DIR/seed_input" -o "$OUT_DIR/afl-out" \
  -- "$PYTHON_BIN" "$HARNESS"
AFL_RC=$?
set -e

"$PYTHON_BIN" - "$OUT_DIR" "$RUN_ID" "$MAX_TEST_CASES" "$TIME_BUDGET" "$AFL_RC" <<'PY'
import json
import math
import os
import pathlib
import sys
from datetime import datetime, timezone

root = pathlib.Path(sys.argv[1]).resolve()
run_id = sys.argv[2]
max_cases = int(sys.argv[3])
time_budget = int(sys.argv[4])
afl_rc = int(sys.argv[5])

def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {}

def load_jsonl(path):
    records = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    except (OSError, UnicodeError, ValueError):
        return []
    return records

report = load_json(root / "afl-out" / "eval_report.json")
states = report.get("security_state_cov", {})
mab = report.get("mab", {})
err = report.get("err", {})
rec = report.get("rec", {})
execution = report.get("exec", {})
statuses = load_jsonl(root / "evidence" / "status.jsonl")
mab_events = load_jsonl(root / "evidence" / "mab_updates.jsonl")

security_total = int(states.get("security_state_total", 0) or 0)
security_new = int(states.get("security_state_new_total", 0) or 0)
security_capacity = int(states.get("security_state_capacity", 0) or 0)
valid_exec = int(execution.get("valid_exec", 0) or 0)
mab_pulls = int(mab.get("total_pulls", 0) or 0)
coverage_rate = min(1.0, security_new / security_capacity) if security_capacity else None
anomaly_rate = float(err.get("err_rate", 0.0)) if err else None
recovery_rate = float(rec.get("rec_rate", 0.0)) if rec else None

# The formal implementation has configurable weights and no implicit project
# default. This reproducibility wrapper declares equal weights explicitly.
score_weights = {"beta1": 1.0 / 3.0, "beta2": 1.0 / 3.0, "beta3": 1.0 / 3.0}
overall_score = None
if coverage_rate is not None and anomaly_rate is not None and recovery_rate is not None:
    overall_score = (
        score_weights["beta1"] * coverage_rate
        + score_weights["beta2"] * (1.0 / (1.0 + anomaly_rate))
        + score_weights["beta3"] * recovery_rate
    )

base_path = "/x_file_assemble_control/jaxrs/share/list/my"
network_records = [item for item in statuses if int(item.get("http_code", 0) or 0) != 0]
safe_transport = bool(network_records)
for item in network_records:
    path = str(item.get("path", ""))
    safe_transport = safe_transport and item.get("method") == "GET"
    safe_transport = safe_transport and path in {
        base_path + "?fileType=attachment",
        base_path + "?fileType=folder",
    }
    safe_transport = safe_transport and int(item.get("body_hash16", -1)) == 0

token = os.environ.get("NV_TOKEN", "").encode("utf-8")
token_occurrences = 0
if token:
    for path in root.rglob("*"):
        if path.is_file() and path.name not in {"summary.json", "SUMMARY.md", "secret_scan.json"}:
            try:
                token_occurrences += path.read_bytes().count(token)
            except OSError:
                pass

secret_scan = {
    "schema_version": 1,
    "exact_runtime_token_occurrences": token_occurrences,
    "verdict": "PASS" if token_occurrences == 0 else "FAIL",
    "note": "The secret value is neither stored nor printed.",
}
(root / "secret_scan.json").write_text(
    json.dumps(secret_scan, sort_keys=True, indent=2) + "\n", encoding="utf-8"
)

required_artifacts = [
    root / "task.json",
    root / "afl-out" / "fuzzer_stats",
    root / "afl-out" / "eval_report.json",
    root / "nv_http_status.json",
    root / "evidence" / "status.jsonl",
    root / "evidence" / "executions.jsonl",
    root / "evidence" / "mab_updates.jsonl",
    root / "evidence" / "seed_selection.jsonl",
    root / "nv_state_trace.jsonl",
]
missing = [str(path.relative_to(root)) for path in required_artifacts if not path.is_file()]
committed_updates = sum(1 for item in mab_events if item.get("event") == "mab_update")

checks = {
    "afl_exit_zero": afl_rc == 0,
    "valid_exec_budget_reached": valid_exec >= max_cases,
    "security_state_observed": security_total > 0 and int(states.get("security_state_observations", 0) or 0) > 0,
    "mab_feedback_committed": mab_pulls > 0 and committed_updates > 0,
    "read_only_bodyless_get_only": safe_transport,
    "no_exact_runtime_token_in_artifacts": token_occurrences == 0,
    "required_artifacts_present": not missing,
}
verdict = "PASS" if all(checks.values()) else "FAIL"

summary = {
    "schema_version": 1,
    "platform": "o2oa",
    "platform_version": "9.5.2",
    "scenario": "formal_live_url_query_read_only",
    "run_id": run_id,
    "captured_at": datetime.now(timezone.utc).isoformat(),
    "endpoint": "GET " + base_path + "?fileType=attachment|folder",
    "seed_source": "seed_file",
    "max_test_cases": max_cases,
    "time_budget": time_budget,
    "valid_exec": valid_exec,
    "coverage_rate": coverage_rate,
    "anomaly_rate": anomaly_rate,
    "recovery_rate": recovery_rate,
    "overall_score": overall_score,
    "security_state_total": security_total,
    "security_state_new_total": security_new,
    "mab_total_pulls": mab_pulls,
    "verdict": verdict,
    "run_root": str(root),
    "raw_artifacts": {
        "eval_report": str(root / "afl-out" / "eval_report.json"),
        "fuzzer_stats": str(root / "afl-out" / "fuzzer_stats"),
        "status_journal": str(root / "evidence" / "status.jsonl"),
        "execution_ledger": str(root / "evidence" / "executions.jsonl"),
        "mab_journal": str(root / "evidence" / "mab_updates.jsonl"),
    },
    "transport": {
        "direct_no_proxy": True,
        "request_body": "none",
        "actual_http_requests": len(network_records),
        "http_2xx": sum(1 for item in network_records if 200 <= int(item.get("http_code", 0)) < 300),
        "local_validation_rejects": sum(1 for item in statuses if item.get("validation_reject") == 1),
    },
    "formal_score": {
        "formula": "P_sec = beta1*Cov + beta2*(1/(1+Err)) + beta3*R_rec",
        "weights": score_weights,
        "coverage_denominator": security_capacity,
        "zero_denominator_policy": "Cov=0 when capacity=0; R_rec=0 when recovery_total=0",
    },
    "checks": checks,
    "missing_artifacts": missing,
    "afl_exit_code": afl_rc,
}
(root / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)

def metric(value):
    return "null" if value is None else format(value, ".12g")

lines = [
    "# Task 4 O2OA final reproducibility summary",
    "",
    f"- Verdict: `{verdict}`",
    f"- Run root: `{root}`",
    f"- Scenario: read-only bodyless GET URL-query fuzzing",
    f"- Valid executions: `{valid_exec}` / requested `{max_cases}`",
    f"- Security-state coverage rate: `{metric(coverage_rate)}`",
    f"- Anomaly rate: `{metric(anomaly_rate)}`",
    f"- Recovery rate: `{metric(recovery_rate)}`",
    f"- Overall score (declared equal weights): `{metric(overall_score)}`",
    f"- Security states total/new: `{security_total}` / `{security_new}`",
    f"- MAB pulls: `{mab_pulls}`",
    f"- Actual HTTP requests: `{len(network_records)}`",
    f"- Exact runtime-token occurrences in raw artifacts: `{token_occurrences}`",
    "",
    "The raw AFL++, harness, execution-ledger, state-trace, MAB, and seed-selection artifacts are retained under this run root.",
    "The experiment issues no business-object create, update, or delete request.",
]
(root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

print(f"O2OA_EXPERIMENT_VERDICT={verdict}")
print(f"COVERAGE_RATE={metric(coverage_rate)}")
print(f"ANOMALY_RATE={metric(anomaly_rate)}")
print(f"RECOVERY_RATE={metric(recovery_rate)}")
print(f"OVERALL_SCORE={metric(overall_score)}")
print(f"RUN_ROOT={root}")
raise SystemExit(0 if verdict == "PASS" else 1)
PY
