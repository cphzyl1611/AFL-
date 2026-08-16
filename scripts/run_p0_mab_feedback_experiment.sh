#!/usr/bin/env bash
#
# P0 deterministic integration experiment.
#
# Exercises one capability chain end to end:
#
#   task.json -> seed -> NC_MAB arm -> nv_json_mutator -> target
#   -> security-state feedback -> MAB reward -> fuzzer_stats / eval_report.json
#
# The target is targets/nv_p0_deterministic_target.py: a local, network-free,
# fully deterministic classifier.  This is NOT a platform experiment and does
# not touch any real O2OA / Alfresco / Flowable service.
#
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PROFILE="${NV_P0_PROFILE:-o2oa_cms_doc_list}"
IN_DIR="${IN_DIR:-$ROOT/in/p0_${PROFILE}}"
OUT_DIR="${OUT_DIR:-$ROOT/out/p0_mab_feedback_${PROFILE}}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MAX_TEST_CASES="${MAX_TEST_CASES:-400}"
TIME_BUDGET="${TIME_BUDGET:-120}"
HARD_TIMEOUT="${HARD_TIMEOUT:-180}"
# Fixed RNG seed: the target is deterministic, so pinning AFL's mutation seed
# makes the whole experiment reproducible run to run.
AFL_RAND_SEED="${AFL_RAND_SEED:-20260816}"

if [[ ! -x "$ROOT/afl-fuzz" ]]; then
  echo "[ERR] $ROOT/afl-fuzz is missing or not executable. Run: make afl-fuzz" >&2
  exit 2
fi
if [[ ! -d "$IN_DIR" ]]; then
  echo "[ERR] seed directory missing: $IN_DIR" >&2
  exit 2
fi
if [[ -e "$OUT_DIR" ]]; then
  echo "[ERR] output directory already exists: $OUT_DIR" >&2
  echo "[ERR] this script never overwrites evidence; set OUT_DIR to a fresh path." >&2
  exit 2
fi

mkdir -p "$OUT_DIR"

TASK_JSON="$OUT_DIR/task.json"
cat > "$TASK_JSON" <<EOF
{
  "target_type": "http_api",
  "target_endpoint": "p0_deterministic_${PROFILE}",
  "seed_source": "seed_file",
  "seed_location": "${IN_DIR}",
  "mutation_scope": ["field_value", "boundary", "structure"],
  "max_test_cases": ${MAX_TEST_CASES},
  "time_budget": ${TIME_BUDGET},
  "enable_validity": 0
}
EOF

export AFL_NO_UI=1
export AFL_SKIP_CPUFREQ=1
export AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1
export AFL_PYTHON_MODULE=nv_json_mutator
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export NV_TASK_PATH="$TASK_JSON"
export NV_STATUS_PATH="$OUT_DIR/nv_http_status.json"
export NV_P0_STATE_LOG="$OUT_DIR/security_states.jsonl"
export NV_P0_PROFILE="$PROFILE"

echo "[*] P0 deterministic integration experiment"
echo "[*] profile=$PROFILE"
echo "[*] input=$IN_DIR"
echo "[*] output=$OUT_DIR"
echo "[*] max_test_cases=$MAX_TEST_CASES time_budget=${TIME_BUDGET}s"
echo "[*] afl_rand_seed=$AFL_RAND_SEED"
echo "[*] mab c=${NV_MAB_C:-<default>} min_explore=${NV_MAB_MIN_EXPLORE:-<default>}"

set +e
timeout "${HARD_TIMEOUT}s" "$ROOT/afl-fuzz" -n -m none -s "$AFL_RAND_SEED" \
  -i "$IN_DIR" -o "$OUT_DIR" \
  -- "$PYTHON_BIN" "$ROOT/targets/nv_p0_deterministic_target.py" @@
status=$?
set -e

if [[ "$status" -ne 0 && "$status" -ne 124 ]]; then
  echo "[ERR] afl-fuzz failed with status=$status" >&2
  exit "$status"
fi

echo "[OK] afl-fuzz finished with status=$status"

OUT_DIR="$OUT_DIR" NV_P0_PROFILE="$PROFILE" \
  "$PYTHON_BIN" "$ROOT/scripts/summarize_p0_mab_feedback.py"

echo "[OK] evidence written under $OUT_DIR"
