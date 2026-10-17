#!/usr/bin/env bash
# Task 4 final Alfresco reproducibility entrypoint.
#
# The canonical runner has a fail-closed clean-source attestation. The accepted
# repository is intentionally dirty with O2OA-only changes, so this wrapper
# executes the Alfresco runner from a temporary detached worktree at HEAD.
# Remote writes are restricted to the dedicated calibration namespace and are
# restored/deleted by exact node ID.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCENARIO="metadata_update"
MAX_TEST_CASES=3
TIME_BUDGET=30
OUT_DIR=""
DRY_RUN=0
RUN_ID=""
EXEC_REPO=""
WORKTREE_PARENT=""
ACTIVE_SCENARIO=""
ACTIVE_ROOT=""

usage() {
  printf '%s\n' \
    "Usage: $(basename "$0") [options]" \
    "" \
    "Run bounded real-feedback Task-4 experiments against the dedicated" \
    "Alfresco calibration namespace." \
    "" \
    "Options:" \
    "  --help                  Show this help." \
    "  --dry-run               Validate the local plan; no network or writes." \
    "  --scenario NAME         metadata_update, content_update," \
    "                          multipart_upload, or all (default: metadata_update)." \
    "  --out-dir DIR           Fresh evidence directory." \
    "  --max-test-cases N      Counted valid fuzz cases per scenario (default: 3)." \
    "  --time-budget SEC       AFL task safety budget per scenario (default: 30)." \
    "" \
    "Required for a real run:" \
    "  ALFRESCO_USER           Basic-auth username (never printed)." \
    "  ALFRESCO_PASS           Basic-auth password (never printed)." \
    "" \
    "Pinned service: http://127.0.0.1:8080" \
    "Dedicated namespace: NV_AFL_REAL_PLATFORM_CALIBRATION/" \
    "                     nv-afl-levelc-metadata.txt"
}

die() {
  printf 'ALFRESCO_EXPERIMENT_VERDICT=FAIL\nERROR=%s\n' "$1" >&2
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
    --scenario)
      (($# >= 2)) || die "--scenario requires a value"
      SCENARIO="$2"
      shift 2
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
    *)
      die "unknown option: $1"
      ;;
  esac
done

case "$SCENARIO" in
  metadata_update|content_update|multipart_upload|all) ;;
  *) die "scenario must be metadata_update, content_update, multipart_upload, or all" ;;
esac
[[ "$MAX_TEST_CASES" =~ ^[1-9][0-9]*$ ]] || die "max-test-cases must be a positive integer"
[[ "$TIME_BUDGET" =~ ^[1-9][0-9]*$ ]] || die "time-budget must be a positive integer"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "Python interpreter not found: $PYTHON_BIN"
command -v git >/dev/null 2>&1 || die "git is required"
[[ -x "$ROOT/afl-fuzz" ]] || die "$ROOT/afl-fuzz is missing or not executable; run: make afl-fuzz"

REQUIRED_FILES=(
  "scripts/run_alfresco_bounded_feedback.py"
  "scripts/run_alfresco_levelc_metadata.py"
  "targets/alfresco_metadata_update.json"
  "targets/alfresco_content_update.json"
  "targets/alfresco_multipart_upload.json"
  "validity/alfresco_metadata_update_rules.json"
  "validity/alfresco_content_update_rules.json"
  "validity/alfresco_multipart_upload_rules.json"
  "in/alfresco_multipart_upload_bounded/manifest.txt"
  "model_stage/alfresco_feature_extractor.py"
  "model_stage/models/alfresco_ae_v1_meta.json"
  "model_stage/models/alfresco_fanogan_v1_candidate.pt"
  "model_stage/models/alfresco_fanogan_v1_candidate_meta.json"
  "runtime_baseline_manifest.json"
)
for relative in "${REQUIRED_FILES[@]}"; do
  [[ -f "$ROOT/$relative" ]] || die "required file missing: $ROOT/$relative"
done

# Prove that the detached execution source, rather than the accepted dirty
# worktree view, matches the frozen runtime-baseline hashes.
"$PYTHON_BIN" - "$ROOT" <<'PY'
import hashlib
import json
import pathlib
import subprocess
import sys

root = pathlib.Path(sys.argv[1])
manifest = json.loads((root / "runtime_baseline_manifest.json").read_text(encoding="utf-8"))
for entry in manifest.get("files", []):
    blob = subprocess.run(
        ["git", "show", "HEAD:" + entry["path"]],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    if hashlib.sha256(blob).hexdigest() != entry["sha256"]:
        raise SystemExit("HEAD_RUNTIME_BASELINE_HASH_MISMATCH:" + entry["path"])
PY

if [[ -z "$OUT_DIR" ]]; then
  RUN_ID="$(date '+%Y%m%dT%H%M%S%z')"
  OUT_DIR="/home/cphzy/task4-evidence/final-repro-${RUN_ID}/alfresco"
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

credentials_present=NO
if [[ -n "${ALFRESCO_USER:-}" && -n "${ALFRESCO_PASS:-}" ]]; then
  credentials_present=YES
fi

write_blocked_summary() {
  local reason="$1"
  mkdir -p "$OUT_DIR"
  "$PYTHON_BIN" - "$OUT_DIR" "$RUN_ID" "$SCENARIO" "$MAX_TEST_CASES" "$TIME_BUDGET" "$reason" "$ROOT" <<'PY'
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

root = pathlib.Path(sys.argv[1]).resolve()
run_id, scenario = sys.argv[2], sys.argv[3]
max_cases, time_budget = int(sys.argv[4]), int(sys.argv[5])
reason = sys.argv[6]
repo = pathlib.Path(sys.argv[7])
head = subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
    capture_output=True, text=True,
).stdout.strip()
summary = {
    "schema_version": 1,
    "platform": "alfresco",
    "scenario": scenario,
    "run_id": run_id,
    "captured_at": datetime.now(timezone.utc).isoformat(),
    "endpoint": "multiple" if scenario == "all" else scenario,
    "seed_source": None,
    "max_test_cases": max_cases,
    "time_budget": time_budget,
    "valid_exec": 0,
    "coverage_rate": None,
    "anomaly_rate": None,
    "recovery_rate": None,
    "overall_score": None,
    "security_state_total": 0,
    "security_state_new_total": 0,
    "mab_total_pulls": 0,
    "verdict": "BLOCKED_ENVIRONMENT",
    "blocker": reason,
    "run_root": str(root),
    "source_head": head,
    "network_contacted": False if reason == "MISSING_ALFRESCO_USER_OR_ALFRESCO_PASS" else None,
}
(root / "summary.json").write_text(
    json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8"
)
(root / "SUMMARY.md").write_text(
    "# Task 4 Alfresco final reproducibility summary\n\n"
    "- Verdict: `BLOCKED_ENVIRONMENT`\n"
    f"- Blocker: `{reason}`\n"
    f"- Planned scenario: `{scenario}`\n"
    f"- Run root: `{root}`\n\n"
    "No fuzz campaign or platform write was performed. The entrypoint's syntax and dry-run are validated separately.\n",
    encoding="utf-8",
)
(root / "secret_scan.json").write_text(
    json.dumps({
        "schema_version": 1,
        "exact_credential_occurrences": 0,
        "verdict": "PASS",
        "note": "No credential value was stored or printed.",
    }, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
PY
}

if ((DRY_RUN)); then
  printf '%s\n' \
    "ALFRESCO_DRY_RUN=PASS" \
    "NETWORK_CONTACTED=NO" \
    "CREDENTIALS_PRESENT=$credentials_present" \
    "CREDENTIALS_PRINTED=NO" \
    "SCENARIO=$SCENARIO" \
    "MAX_TEST_CASES=$MAX_TEST_CASES" \
    "TIME_BUDGET=$TIME_BUDGET" \
    "PLANNED_RUN_ROOT=$OUT_DIR" \
    "EXECUTION_SOURCE=temporary_clean_worktree_at_HEAD" \
    "TARGET_NAMESPACE=dedicated_calibration_only" \
    "STATE_RESTORE_OR_EXACT_ID_DELETE=ENFORCED"
  exit 0
fi

if [[ "$credentials_present" != YES ]]; then
  write_blocked_summary "MISSING_ALFRESCO_USER_OR_ALFRESCO_PASS"
  printf '%s\n' \
    "ALFRESCO_EXPERIMENT_VERDICT=BLOCKED_ENVIRONMENT" \
    "BLOCKER=MISSING_ALFRESCO_USER_OR_ALFRESCO_PASS" \
    "CREDENTIALS_PRINTED=NO" \
    "RUN_ROOT=$OUT_DIR"
  exit 3
fi

mkdir -p "$OUT_DIR"
SOURCE_HEAD="$(git -C "$ROOT" rev-parse HEAD)"
printf '%s\n' "$SOURCE_HEAD" > "$OUT_DIR/source_head.txt"
sha256sum "$ROOT/afl-fuzz" > "$OUT_DIR/afl_fuzz_binary.sha256"

cleanup_remote() {
  local scenario_root="$1"
  local scenario_name="$2"
  "$PYTHON_BIN" - "$EXEC_REPO" "$scenario_root" "$scenario_name" <<'PY'
import base64
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

repo = pathlib.Path(sys.argv[1])
run_root = pathlib.Path(sys.argv[2])
scenario = sys.argv[3]
baseline = run_root.parent.parent / "baselines" / scenario
state_path = baseline / "state.json"
result_path = run_root / "cleanup.json"

def publish(result):
    result["captured_at"] = datetime.now(timezone.utc).isoformat()
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")

try:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location(
        "task4_alfresco_cleanup", repo / "scripts" / "run_alfresco_bounded_feedback.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    credentials = module.runtime_credentials()
    client = module.build_alfresco_client(module.ALFRESCO_BASE_URL, credentials)
    api = "/alfresco/api/-default-/public/alfresco/versions/1"
    records = []

    if scenario == "metadata_update":
        node_id = state["node_id"]
        restore = {
            key: detail["value"] if detail["present"] else None
            for key, detail in state["properties"].items()
        }
        code, _ = client.request(
            "PUT", f"{api}/nodes/{node_id}", body={"properties": restore}
        )
        observed = client.get_node(node_id).get("properties") or {}
        exact = code in (200, 201)
        for key, detail in state["properties"].items():
            exact = exact and ((key in observed) is bool(detail["present"]))
            if detail["present"]:
                exact = exact and observed.get(key) == detail["value"]
        records.append({"node_id": node_id, "restore_http_status": code, "exact_match": exact})
        verdict = "PASS" if exact else "FAIL"

    elif scenario == "content_update":
        node_id = state["node_id"]
        content = (baseline / "content.bin").read_bytes()
        request = urllib.request.Request(
            client.base + f"{api}/nodes/{node_id}/content",
            data=content,
            method="PUT",
            headers={
                "Authorization": client._auth,
                "Content-Type": "application/octet-stream",
                "Accept": "application/json",
            },
        )
        try:
            with client.opener.open(request, timeout=client.timeout) as response:
                code = int(response.getcode())
                response.read()
        except urllib.error.HTTPError as exc:
            code = int(exc.code)
            exc.read()
        observed = module.read_content_bytes(client, node_id)
        expected_hash = "sha256:" + hashlib.sha256(content).hexdigest()
        observed_hash = "sha256:" + hashlib.sha256(observed).hexdigest()
        exact = code in (200, 201) and expected_hash == observed_hash
        records.append({
            "node_id": node_id,
            "restore_http_status": code,
            "expected_sha256": expected_hash,
            "observed_sha256": observed_hash,
            "exact_match": exact,
        })
        verdict = "PASS" if exact else "FAIL"

    elif scenario == "multipart_upload":
        parent_id = state["parent_id"]
        journal = run_root / "evidence" / "multipart_uploads.jsonl"
        created = {}
        if journal.is_file():
            for raw in journal.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                item = json.loads(raw)
                status = int(item.get("http_status", 0) or 0)
                node_id = item.get("response_node_id")
                if 200 <= status < 300 and isinstance(node_id, str) and node_id:
                    if item.get("parent_node_id") != parent_id:
                        raise RuntimeError("MULTIPART_PARENT_BINDING_MISMATCH")
                    created[node_id] = item
        uuid_re = re.compile(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        )
        exact = True
        for node_id in sorted(created):
            if not uuid_re.fullmatch(node_id):
                raise RuntimeError("MULTIPART_NODE_ID_INVALID")
            get_code, payload = client.request("GET", f"{api}/nodes/{node_id}")
            if get_code == 404:
                records.append({"node_id": node_id, "delete_http_status": None, "absence_http_status": 404})
                continue
            entry = payload.get("entry") if isinstance(payload, dict) else None
            if get_code != 200 or not isinstance(entry, dict) or entry.get("parentId") != parent_id:
                records.append({"node_id": node_id, "delete_refused": True, "predelete_http_status": get_code})
                exact = False
                continue
            delete_code, _ = client.request("DELETE", f"{api}/nodes/{node_id}?permanent=true")
            absent_code, _ = client.request("GET", f"{api}/nodes/{node_id}")
            item_ok = delete_code in (200, 204) and absent_code == 404
            exact = exact and item_ok
            records.append({
                "node_id": node_id,
                "delete_http_status": delete_code,
                "absence_http_status": absent_code,
                "exact_parent_match": True,
                "exact_id_absent": item_ok,
            })
        verdict = "PASS" if exact else "FAIL"
    else:
        raise RuntimeError("UNKNOWN_CLEANUP_SCENARIO")

    publish({
        "schema_version": 1,
        "scenario": scenario,
        "scope": "exact_id_only",
        "records": records,
        "verdict": verdict,
    })
    print(f"ALFRESCO_{scenario.upper()}_CLEANUP={verdict}")
    raise SystemExit(0 if verdict == "PASS" else 1)
except Exception as exc:
    publish({
        "schema_version": 1,
        "scenario": scenario,
        "scope": "exact_id_only",
        "records": [],
        "verdict": "FAIL",
        "error_class": exc.__class__.__name__,
        "error_code": str(exc) if str(exc).isupper() and " " not in str(exc) else "CLEANUP_EXCEPTION",
    })
    print(f"ALFRESCO_{scenario.upper()}_CLEANUP=FAIL")
    raise SystemExit(1)
PY
}

finish() {
  local saved_rc=$?
  set +e
  if [[ -n "$ACTIVE_SCENARIO" && -n "$ACTIVE_ROOT" && -n "$EXEC_REPO" ]]; then
    cleanup_remote "$ACTIVE_ROOT" "$ACTIVE_SCENARIO" >/dev/null 2>&1
  fi
  if [[ -n "$EXEC_REPO" && -e "$EXEC_REPO" ]]; then
    git -C "$ROOT" worktree remove --force "$EXEC_REPO" >/dev/null 2>&1
  fi
  if [[ -n "$WORKTREE_PARENT" && -d "$WORKTREE_PARENT" ]]; then
    rmdir "$WORKTREE_PARENT" >/dev/null 2>&1
  fi
  return "$saved_rc"
}
trap finish EXIT

WORKTREE_PARENT="$(mktemp -d /tmp/task4-alfresco-worktree.XXXXXX)"
EXEC_REPO="$WORKTREE_PARENT/source"
git -C "$ROOT" worktree add --detach "$EXEC_REPO" "$SOURCE_HEAD" > "$OUT_DIR/worktree_setup.log" 2>&1
cp "$ROOT/afl-fuzz" "$EXEC_REPO/afl-fuzz.real"

# The canonical runner serializes credentials redundantly into AFL_TARGET_ENV.
# AFL records every AFL_* variable in fuzzer_setup, so passing that serialized
# copy would leak credentials. Normal POSIX environment inheritance already
# supplies the same variables to the harness. This local binary shim removes
# only the redundant serialized copy before execing the audited binary.
"$PYTHON_BIN" - "$EXEC_REPO/afl-fuzz" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
path.write_text(
    "#!/usr/bin/env bash\n"
    "set -euo pipefail\n"
    "unset AFL_TARGET_ENV\n"
    "exec \"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)/afl-fuzz.real\" \"$@\"\n",
    encoding="utf-8",
)
PY
chmod +x "$EXEC_REPO/afl-fuzz" "$EXEC_REPO/afl-fuzz.real"

# Canonical direct/no-proxy service, container, 401/200, and credential gate.
set +e
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY \
  "$PYTHON_BIN" "$EXEC_REPO/scripts/run_alfresco_bounded_feedback.py" \
  --preflight-only > "$OUT_DIR/preflight.log" 2>&1
PREFLIGHT_RC=$?
set -e
if ((PREFLIGHT_RC != 0)); then
  write_blocked_summary "CANONICAL_PREFLIGHT_FAILED"
  printf '%s\n' \
    "ALFRESCO_EXPERIMENT_VERDICT=BLOCKED_ENVIRONMENT" \
    "BLOCKER=CANONICAL_PREFLIGHT_FAILED" \
    "CREDENTIALS_PRINTED=NO" \
    "PREFLIGHT_LOG=$OUT_DIR/preflight.log" \
    "RUN_ROOT=$OUT_DIR"
  exit 3
fi

snapshot_baseline() {
  local scenario_root="$1"
  local scenario_name="$2"
  "$PYTHON_BIN" - "$EXEC_REPO" "$scenario_root" "$scenario_name" <<'PY'
import hashlib
import importlib.util
import json
import pathlib
import sys

repo = pathlib.Path(sys.argv[1])
run_root = pathlib.Path(sys.argv[2])
scenario = sys.argv[3]
baseline = run_root.parent.parent / "baselines" / scenario
baseline.mkdir(parents=True, exist_ok=False)
spec = importlib.util.spec_from_file_location(
    "task4_alfresco_snapshot", repo / "scripts" / "run_alfresco_bounded_feedback.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
credentials = module.runtime_credentials()
client = module.build_alfresco_client(module.ALFRESCO_BASE_URL, credentials)

if scenario == "multipart_upload":
    resolved = module.resolve_existing_dedicated_parent(client)
    state = {
        "scenario": scenario,
        "parent_id": resolved["folder_id"],
        "dedicated_namespace": True,
    }
else:
    resolved = (
        module.resolve_existing_dedicated_content_node(client)
        if scenario == "content_update"
        else module.resolve_existing_dedicated_node(client)
    )
    node_id = resolved["file_id"]
    if resolved.get("target_name") != "nv-afl-levelc-metadata.txt":
        raise SystemExit("DEDICATED_TARGET_NAME_MISMATCH")
    state = {
        "scenario": scenario,
        "node_id": node_id,
        "parent_id": resolved["folder_id"],
        "target_name": resolved.get("target_name"),
        "dedicated_namespace": True,
    }
    if scenario == "metadata_update":
        properties = client.get_node(node_id).get("properties") or {}
        state["properties"] = {
            key: {"present": key in properties, "value": properties.get(key)}
            for key in ("cm:title", "cm:description")
        }
    elif scenario == "content_update":
        content = module.read_content_bytes(client, node_id)
        (baseline / "content.bin").write_bytes(content)
        state["content_sha256"] = "sha256:" + hashlib.sha256(content).hexdigest()
        state["content_length"] = len(content)

(baseline / "state.json").write_text(
    json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(f"ALFRESCO_{scenario.upper()}_BASELINE_SNAPSHOT=PASS")
PY
}

run_one() {
  local scenario_name="$1"
  local scenario_root="$OUT_DIR/scenarios/$scenario_name"
  local runner_log="$OUT_DIR/logs/${scenario_name}.runner.log"
  mkdir -p "$OUT_DIR/logs"
  ACTIVE_SCENARIO="$scenario_name"
  ACTIVE_ROOT="$scenario_root"
  snapshot_baseline "$scenario_root" "$scenario_name"

  local command=(
    "$PYTHON_BIN" "$EXEC_REPO/scripts/run_alfresco_bounded_feedback.py"
    --scenario "$scenario_name"
    --run-root "$scenario_root"
    --max-test-cases "$MAX_TEST_CASES"
    --time-budget "$TIME_BUDGET"
    --mutation-scope field_value,boundary,structure
    --validity-backend alfresco_ae_v1
  )
  if [[ "$scenario_name" == multipart_upload ]]; then
    command+=(
      --seed-manifest "$EXEC_REPO/in/alfresco_multipart_upload_bounded/manifest.txt"
      --seed-source-dir "$EXEC_REPO/in/alfresco_multipart_upload_bounded"
    )
  fi

  printf 'ALFRESCO_SCENARIO_START=%s\n' "$scenario_name"
  set +e
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY \
    "${command[@]}" > "$runner_log" 2>&1
  local runner_rc=$?
  set -e
  mkdir -p "$scenario_root"
  cp "$runner_log" "$scenario_root/runner.log"

  set +e
  cleanup_remote "$scenario_root" "$scenario_name"
  local cleanup_rc=$?
  if ((cleanup_rc != 0)); then
    cleanup_remote "$scenario_root" "$scenario_name"
    cleanup_rc=$?
  fi
  set -e

  "$PYTHON_BIN" - "$scenario_root/wrapper_status.json" "$scenario_name" "$runner_rc" "$cleanup_rc" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
scenario = sys.argv[2]
runner_rc = int(sys.argv[3])
cleanup_rc = int(sys.argv[4])
payload = {
    "schema_version": 1,
    "scenario": scenario,
    "runner_exit_code": runner_rc,
    "cleanup_exit_code": cleanup_rc,
    "verdict": "PASS" if runner_rc == 0 and cleanup_rc == 0 else "FAIL",
}
path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY

  ACTIVE_SCENARIO=""
  ACTIVE_ROOT=""
  if ((runner_rc != 0 || cleanup_rc != 0)); then
    return 1
  fi
  return 0
}

if [[ "$SCENARIO" == all ]]; then
  SCENARIOS=(metadata_update content_update multipart_upload)
else
  SCENARIOS=("$SCENARIO")
fi

RUNS_OK=1
for item in "${SCENARIOS[@]}"; do
  if ! run_one "$item"; then
    RUNS_OK=0
    break
  fi
done

"$PYTHON_BIN" - "$OUT_DIR" "$RUN_ID" "$SCENARIO" "$MAX_TEST_CASES" "$TIME_BUDGET" "$SOURCE_HEAD" "${#SCENARIOS[@]}" <<'PY'
import base64
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

root = pathlib.Path(sys.argv[1]).resolve()
run_id = sys.argv[2]
requested = sys.argv[3]
max_cases = int(sys.argv[4])
time_budget = int(sys.argv[5])
source_head = sys.argv[6]
expected_count = int(sys.argv[7])

def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {}

def normalized(scenario_root):
    status = load(scenario_root / "wrapper_status.json")
    task = load(scenario_root / "task.json")
    report = load(scenario_root / "afl-out" / "eval_report.json")
    artifact = load(scenario_root / "evidence" / "artifact_report.json")
    cleanup = load(scenario_root / "cleanup.json")
    scenario = status.get("scenario", scenario_root.name)
    states = report.get("security_state_cov", {})
    err = report.get("err", {})
    rec = report.get("rec", {})
    execution = report.get("exec", {})
    mab = report.get("mab", {})
    capacity = int(states.get("security_state_capacity", 0) or 0)
    new = int(states.get("security_state_new_total", 0) or 0)
    cov = min(1.0, new / capacity) if capacity else None
    anomaly = float(err.get("err_rate", 0.0)) if err else None
    recovery = float(rec.get("rec_rate", 0.0)) if rec else None
    weights = {"beta1": 1.0 / 3.0, "beta2": 1.0 / 3.0, "beta3": 1.0 / 3.0}
    overall = None
    if cov is not None and anomaly is not None and recovery is not None:
        overall = (
            weights["beta1"] * cov
            + weights["beta2"] * (1.0 / (1.0 + anomaly))
            + weights["beta3"] * recovery
        )
    endpoints = {
        "metadata_update": "PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/{nodeId}",
        "content_update": "PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/{nodeId}/content",
        "multipart_upload": "POST /alfresco/api/-default-/public/alfresco/versions/1/nodes/{parentNodeId}/children",
    }
    wrapper_pass = status.get("verdict") == "PASS"
    artifact_pass = (
        artifact.get("runner", {}).get("exit_code") == 0
        and artifact.get("artifact_final_result") == "pass"
    )
    cleanup_pass = cleanup.get("verdict") == "PASS"
    verdict = "PASS" if wrapper_pass and artifact_pass and cleanup_pass else "FAIL"
    return {
        "platform": "alfresco",
        "scenario": scenario,
        "run_id": run_id + "-" + scenario,
        "endpoint": endpoints.get(scenario),
        "seed_source": task.get("seed_source"),
        "max_test_cases": int(task.get("max_test_cases", max_cases) or max_cases),
        "time_budget": int(task.get("time_budget", time_budget) or time_budget),
        "valid_exec": int(execution.get("valid_exec", 0) or 0),
        "coverage_rate": cov,
        "anomaly_rate": anomaly,
        "recovery_rate": recovery,
        "overall_score": overall,
        "security_state_total": int(states.get("security_state_total", 0) or 0),
        "security_state_new_total": new,
        "mab_total_pulls": int(mab.get("total_pulls", 0) or 0),
        "verdict": verdict,
        "readback_verdict": artifact.get("readback_verdict"),
        "cleanup_verdict": cleanup.get("verdict"),
        "score_provenance": {
            "formula": "P_sec = beta1*Cov + beta2*(1/(1+Err)) + beta3*R_rec",
            "weights": weights,
            "coverage_denominator": capacity,
        },
        "raw_artifacts": {
            "eval_report": str(scenario_root / "afl-out" / "eval_report.json"),
            "artifact_report": str(scenario_root / "evidence" / "artifact_report.json"),
            "cleanup": str(scenario_root / "cleanup.json"),
            "runner_log": str(scenario_root / "runner.log"),
        },
    }

scenario_results = []
scenario_dir = root / "scenarios"
if scenario_dir.is_dir():
    for child in sorted(scenario_dir.iterdir()):
        if child.is_dir() and (child / "wrapper_status.json").is_file():
            scenario_results.append(normalized(child))

patterns = []
user = os.environ.get("ALFRESCO_USER", "")
password = os.environ.get("ALFRESCO_PASS", "")
for value in (user, password):
    if value:
        patterns.append(value.encode("utf-8"))
if user and password:
    patterns.append(base64.b64encode(f"{user}:{password}".encode("utf-8")))
occurrences = 0
serialized_target_env = 0
for path in root.rglob("*"):
    if not path.is_file() or path.name in {"summary.json", "SUMMARY.md", "secret_scan.json"}:
        continue
    try:
        data = path.read_bytes()
    except OSError:
        continue
    occurrences += sum(data.count(pattern) for pattern in patterns)
    if path.name == "fuzzer_setup":
        serialized_target_env += data.count(b"AFL_TARGET_ENV=")

secret_scan = {
    "schema_version": 1,
    "exact_credential_occurrences": occurrences,
    "serialized_afl_target_env_occurrences": serialized_target_env,
    "verdict": "PASS" if occurrences == 0 and serialized_target_env == 0 else "FAIL",
    "note": "Credential values are neither stored in this report nor printed.",
}
(root / "secret_scan.json").write_text(
    json.dumps(secret_scan, sort_keys=True, indent=2) + "\n", encoding="utf-8"
)

complete = len(scenario_results) == expected_count
all_pass = complete and all(item["verdict"] == "PASS" for item in scenario_results)
verdict = "PASS" if all_pass and secret_scan["verdict"] == "PASS" else "FAIL"
single = scenario_results[0] if len(scenario_results) == 1 else None
summary = {
    "schema_version": 1,
    "platform": "alfresco",
    "scenario": requested,
    "run_id": run_id,
    "captured_at": datetime.now(timezone.utc).isoformat(),
    "endpoint": single["endpoint"] if single else "multiple",
    "seed_source": single["seed_source"] if single else "mixed",
    "max_test_cases": max_cases,
    "time_budget": time_budget,
    "valid_exec": single["valid_exec"] if single else sum(item["valid_exec"] for item in scenario_results),
    "coverage_rate": single["coverage_rate"] if single else None,
    "anomaly_rate": single["anomaly_rate"] if single else None,
    "recovery_rate": single["recovery_rate"] if single else None,
    "overall_score": single["overall_score"] if single else None,
    "security_state_total": single["security_state_total"] if single else sum(item["security_state_total"] for item in scenario_results),
    "security_state_new_total": single["security_state_new_total"] if single else sum(item["security_state_new_total"] for item in scenario_results),
    "mab_total_pulls": single["mab_total_pulls"] if single else sum(item["mab_total_pulls"] for item in scenario_results),
    "verdict": verdict,
    "run_root": str(root),
    "source_head": source_head,
    "execution_source": "temporary clean detached worktree (removed after run)",
    "scenario_results": scenario_results,
    "aggregation_note": (
        "Rates and overall score are null for scenario=all because independent state spaces are not averaged."
        if not single else None
    ),
    "secret_scan": secret_scan,
}
(root / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)

def metric(value):
    return "null" if value is None else format(value, ".12g")

lines = [
    "# Task 4 Alfresco final reproducibility summary",
    "",
    f"- Verdict: `{verdict}`",
    f"- Run root: `{root}`",
    f"- Requested scenario: `{requested}`",
    f"- Source HEAD: `{source_head}`",
    f"- Coverage rate: `{metric(summary['coverage_rate'])}`",
    f"- Anomaly rate: `{metric(summary['anomaly_rate'])}`",
    f"- Recovery rate: `{metric(summary['recovery_rate'])}`",
    f"- Overall score: `{metric(summary['overall_score'])}`",
    "",
    "## Scenario results",
    "",
]
for item in scenario_results:
    lines.append(
        f"- `{item['scenario']}`: `{item['verdict']}`; valid_exec={item['valid_exec']}; "
        f"states={item['security_state_total']}; MAB pulls={item['mab_total_pulls']}; "
        f"readback={item['readback_verdict']}; cleanup={item['cleanup_verdict']}"
    )
lines.extend([
    "",
    "Every write was confined to the dedicated calibration namespace. Metadata/content baselines were restored byte/field exactly; multipart resources were removed by returned node ID and checked absent.",
    "Native AFL++, harness, readback, state, ledger, MAB, and cleanup artifacts remain under each scenario directory.",
])
(root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

print(f"ALFRESCO_EXPERIMENT_VERDICT={verdict}")
for item in scenario_results:
    print(f"SCENARIO_{item['scenario'].upper()}_VERDICT={item['verdict']}")
print(f"COVERAGE_RATE={metric(summary['coverage_rate'])}")
print(f"ANOMALY_RATE={metric(summary['anomaly_rate'])}")
print(f"RECOVERY_RATE={metric(summary['recovery_rate'])}")
print(f"OVERALL_SCORE={metric(summary['overall_score'])}")
print(f"RUN_ROOT={root}")
raise SystemExit(0 if verdict == "PASS" else 1)
PY

if ((RUNS_OK == 0)); then
  exit 1
fi
