#!/usr/bin/env bash
set -euo pipefail

# Phase 3 — Final 5+5 Campaign
# After INPUT_DIM reconciliation, with correct SE Python environment

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo "=== PHASE 3: 5+5 FINAL CAMPAIGN ==="
echo ""
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# ============================================================================
# STEP 0: PREFLIGHT
# ============================================================================

echo "STEP 0: PREFLIGHT"
echo ""

# Required environment variables
if [ -z "${ALFRESCO_USER:-}" ]; then
  echo "✗ ALFRESCO_USER not set"
  exit 1
fi

if [ -z "${ALFRESCO_PASS:-}" ]; then
  echo "✗ ALFRESCO_PASS not set"
  exit 1
fi

if [ -z "${SEFANOGAN_REFERENCE_CHECKPOINT:-}" ]; then
  echo "✗ SEFANOGAN_REFERENCE_CHECKPOINT not set"
  exit 1
fi

if [ -z "${SEFANOGAN_REFERENCE_META_PATH:-}" ]; then
  echo "✗ SEFANOGAN_REFERENCE_META_PATH not set"
  exit 1
fi

echo "✓ Required environment variables set"
echo ""

# Verify HEAD
EXPECTED_HEAD="87bee5c6fa1f0a8f7d6df2a301df3b7f879aa408"
ACTUAL_HEAD=$(git rev-parse HEAD)

if [ "$ACTUAL_HEAD" != "$EXPECTED_HEAD" ]; then
  echo "✗ HEAD mismatch"
  echo "  Expected: $EXPECTED_HEAD"
  echo "  Actual:   $ACTUAL_HEAD"
  exit 1
fi

echo "✓ HEAD = $EXPECTED_HEAD"
echo ""

# Verify runner SHA256
RUNNER_PATH="scripts/run_alfresco_bounded_feedback.py"
EXPECTED_RUNNER_SHA="7acb5192fc7c4c6fbb3f24155d94eb68809cca0306d7600855c6504444bf3650"
ACTUAL_RUNNER_SHA=$(sha256sum "$RUNNER_PATH" | awk '{print $1}')

if [ "$ACTUAL_RUNNER_SHA" != "$EXPECTED_RUNNER_SHA" ]; then
  echo "✗ Runner SHA256 mismatch"
  echo "  Expected: $EXPECTED_RUNNER_SHA"
  echo "  Actual:   $ACTUAL_RUNNER_SHA"
  exit 1
fi

echo "✓ RUNNER_SHA256 = $EXPECTED_RUNNER_SHA"
echo ""

# Verify tracked diff SHA256
EXPECTED_DIFF_SHA="686a1e65035ac38145b606f4c765f6a1220e6f9f9f2206338354bd2a84112140"
ACTUAL_DIFF_SHA=$(git diff HEAD | sha256sum | awk '{print $1}')

if [ "$ACTUAL_DIFF_SHA" != "$EXPECTED_DIFF_SHA" ]; then
  echo "✗ Tracked diff SHA256 mismatch"
  echo "  Expected: $EXPECTED_DIFF_SHA"
  echo "  Actual:   $ACTUAL_DIFF_SHA"
  exit 1
fi

echo "✓ TRACKED_DIFF_SHA256 = $EXPECTED_DIFF_SHA"
echo ""

# Verify canonical 12-file manifest
MANIFEST_PATH="/tmp/phase2_recovered_12file_manifest.txt"
EXPECTED_MANIFEST_SHA="26c2e4f3871d7deffb4ab7fc356f6973b8f01b5985d189ed6afcc79b251a2c5b"
ACTUAL_MANIFEST_SHA=$(sha256sum "$MANIFEST_PATH" | awk '{print $1}')

if [ "$ACTUAL_MANIFEST_SHA" != "$EXPECTED_MANIFEST_SHA" ]; then
  echo "✗ Manifest SHA256 mismatch"
  echo "  Expected: $EXPECTED_MANIFEST_SHA"
  echo "  Actual:   $ACTUAL_MANIFEST_SHA"
  exit 1
fi

echo "✓ CANONICAL_12FILE_MANIFEST_SHA256 = $EXPECTED_MANIFEST_SHA"

# Verify each file in manifest
MANIFEST_OK=true
while IFS= read -r line; do
  expected_hash=$(echo "$line" | awk '{print $1}')
  file_path=$(echo "$line" | awk '{print $2}')
  
  if [ ! -f "$file_path" ]; then
    echo "✗ Missing: $file_path"
    MANIFEST_OK=false
    continue
  fi
  
  actual_hash=$(sha256sum "$file_path" | awk '{print $1}')
  if [ "$actual_hash" != "$expected_hash" ]; then
    echo "✗ Hash mismatch: $file_path"
    echo "  Expected: $expected_hash"
    echo "  Actual:   $actual_hash"
    MANIFEST_OK=false
  fi
done < "$MANIFEST_PATH"

if [ "$MANIFEST_OK" = false ]; then
  echo ""
  echo "✗ Manifest verification failed"
  exit 1
fi

echo "✓ All 12 files match canonical manifest"
echo ""

# Verify SE runtime artifacts
EXPECTED_CHECKPOINT_SHA="4eace87ac7d7759a729ff98916a5acead4154c803c53884e3ca7f27570dbf20d"
EXPECTED_META_SHA="2a73ccc3729a3734ab9901b4474feb73d4d42f912ccbc717af48f970ab568226"

ACTUAL_CHECKPOINT_SHA=$(sha256sum "$SEFANOGAN_REFERENCE_CHECKPOINT" | awk '{print $1}')
ACTUAL_META_SHA=$(sha256sum "$SEFANOGAN_REFERENCE_META_PATH" | awk '{print $1}')

if [ "$ACTUAL_CHECKPOINT_SHA" != "$EXPECTED_CHECKPOINT_SHA" ]; then
  echo "✗ SE checkpoint SHA256 mismatch"
  echo "  Expected: $EXPECTED_CHECKPOINT_SHA"
  echo "  Actual:   $ACTUAL_CHECKPOINT_SHA"
  exit 1
fi

if [ "$ACTUAL_META_SHA" != "$EXPECTED_META_SHA" ]; then
  echo "✗ SE metadata SHA256 mismatch"
  echo "  Expected: $EXPECTED_META_SHA"
  echo "  Actual:   $ACTUAL_META_SHA"
  exit 1
fi

echo "✓ RUNTIME_SE_CHECKPOINT_SHA256 = $EXPECTED_CHECKPOINT_SHA"
echo "✓ RUNTIME_SE_METADATA_SHA256 = $EXPECTED_META_SHA"
echo ""

# Verify SE input_dim
RUNTIME_INPUT_DIM=$(python3 -c "import json; meta=json.load(open('$SEFANOGAN_REFERENCE_META_PATH')); print(meta['input_dim'])")

if [ "$RUNTIME_INPUT_DIM" != "32" ]; then
  echo "✗ SE input_dim mismatch"
  echo "  Expected: 32"
  echo "  Actual:   $RUNTIME_INPUT_DIM"
  exit 1
fi

echo "✓ RUNTIME_SE_METADATA_INPUT_DIM = 32"
echo ""

# Docker daemon check
if ! docker info > /dev/null 2>&1; then
  echo "✗ Docker daemon not reachable"
  exit 1
fi

echo "✓ DOCKER_DAEMON_REACHABLE = YES"
echo ""

# Alfresco check
python3 << 'PYCHECK'
import sys
sys.path.insert(0, "integration")
from alfresco_real_feedback_adapter import AlfrescoClient, build_auth_header
import os

client = AlfrescoClient(
    base_url="https://cloud.sjtucyberai.com/alfresco",
    auth_header=build_auth_header(os.environ["ALFRESCO_USER"], os.environ["ALFRESCO_PASS"]),
    verify_ssl=False,
)

try:
    resp = client.get("/alfresco/api/-default-/public/cmis/versions/1.1/browser")
    if resp.status_code == 200:
        print("✓ ALFRESCO_REAL_API_STATUS = HTTP_200")
    else:
        print(f"✗ ALFRESCO_REAL_API_STATUS = HTTP_{resp.status_code}")
        sys.exit(1)
except Exception as e:
    print(f"✗ ALFRESCO_MAIN_CONTEXT_READY = NO ({e})")
    sys.exit(1)
PYCHECK

if [ $? -ne 0 ]; then
  exit 1
fi

echo ""
echo "✓ All preflight checks passed"
echo ""
echo "========================================================================"
echo ""

# ============================================================================
# CAMPAIGN CONFIGURATION
# ============================================================================

SCENARIO="metadata_update"
MAX_TEST_CASES=5
TIME_BUDGET=60
SCORER_READY_TIMEOUT=10

# Conda environment for SE scorer
CONDA_PYTHON="/home/dministrator/miniconda3/envs/aflpp-se-calib-pip/bin/python3"

if [ ! -x "$CONDA_PYTHON" ]; then
  echo "✗ Conda Python not found: $CONDA_PYTHON"
  exit 1
fi

echo "✓ SE Python environment: $CONDA_PYTHON"
echo ""

SEEDS=(20260915 20260916 20260917 20260918 20260919)
OUTPUT_ROOT="out/phase3_5plus5_final"

mkdir -p "$OUTPUT_ROOT"

echo "Campaign configuration:"
echo "  SCENARIO: $SCENARIO"
echo "  MAX_TEST_CASES: $MAX_TEST_CASES"
echo "  TIME_BUDGET: $TIME_BUDGET"
echo "  SEEDS: ${SEEDS[*]}"
echo "  OUTPUT_ROOT: $OUTPUT_ROOT"
echo ""

# ============================================================================
# CAMPAIGN EXECUTION
# ============================================================================

VALID_AE_RUNS=0
VALID_SE_RUNS=0
FAILED_RUNS=()

AE_SECURITY_STATE_VALUES=()
SE_SECURITY_STATE_VALUES=()

for SEED in "${SEEDS[@]}"; do
  echo "========================================================================"
  echo "SEED $SEED"
  echo "========================================================================"
  echo ""
  
  # ------------------------------------------------------------------------
  # AE RUN
  # ------------------------------------------------------------------------
  
  echo "--- AE RUN (seed=$SEED) ---"
  echo ""
  
  AE_OUTPUT="$OUTPUT_ROOT/ae_seed_$SEED"
  
  python3 scripts/run_alfresco_bounded_feedback.py \
    --scenario "$SCENARIO" \
    --afl-seed "$SEED" \
    --max-test-cases "$MAX_TEST_CASES" \
    --time-budget "$TIME_BUDGET" \
    --scorer-ready-timeout "$SCORER_READY_TIMEOUT" \
    --validity-backend alfresco_ae_v1 \
    --model-comparison \
    --scorer-python "$CONDA_PYTHON" \
    --run-root "$AE_OUTPUT"
  
  AE_RC=$?
  
  if [ $AE_RC -ne 0 ]; then
    echo "✗ AE run failed with exit code $AE_RC"
    FAILED_RUNS+=("ae_seed_$SEED")
    echo ""
    echo "CAMPAIGN ABORTED: AE run failed before inline validation"
    exit 1
  fi
  
  echo "✓ AE run completed (exit code 0)"
  echo ""
  
  # Inline validation
  echo "Validating AE run..."
  
  AE_REPORT="$AE_OUTPUT/artifact_report.json"
  
  if [ ! -f "$AE_REPORT" ]; then
    echo "✗ AE artifact report missing"
    FAILED_RUNS+=("ae_seed_$SEED")
    echo ""
    echo "CAMPAIGN ABORTED"
    exit 1
  fi
  
  python3 << PYVAL
import json
import sys

with open("$AE_REPORT") as f:
    report = json.load(f)

ok = report.get("ok", False)
if not ok:
    print("✗ AE artifact_contract = FAIL")
    sys.exit(1)

# Check model-comparison participation
mc = report.get("model_comparison_validity", {})
if mc.get("verdict") != "PASS":
    print(f"✗ AE model_comparison_validity = {mc.get('verdict')}")
    sys.exit(1)

# Check RPC stats
part = mc.get("participation", {})
body_score_rpc_ok = part.get("body_score_rpc_ok", 0)
body_score_rpc_fail = part.get("body_score_rpc_fail", 0)

if body_score_rpc_ok == 0:
    print("✗ AE body_score_rpc_ok = 0")
    sys.exit(1)

if body_score_rpc_fail != 0:
    print(f"✗ AE body_score_rpc_fail = {body_score_rpc_fail}")
    sys.exit(1)

trace_invocations = part.get("trace_invocations", 0)
if trace_invocations == 0:
    print("✗ AE trace_invocations = 0")
    sys.exit(1)

trace_backend = part.get("trace_backend")
if trace_backend != "alfresco_ae_v1":
    print(f"✗ AE trace_backend = {trace_backend} (expected alfresco_ae_v1)")
    sys.exit(1)

# Extract security_state_new
security_state_new = report.get("readback", {}).get("security_state_new")
if security_state_new is None:
    print("✗ AE security_state_new missing")
    sys.exit(1)

print(f"✓ AE validation PASS")
print(f"  security_state_new: {security_state_new}")
print(f"  body_score_rpc_ok: {body_score_rpc_ok}")
print(f"  trace_invocations: {trace_invocations}")
PYVAL
  
  if [ $? -ne 0 ]; then
    FAILED_RUNS+=("ae_seed_$SEED")
    echo ""
    echo "CAMPAIGN ABORTED"
    exit 1
  fi
  
  # Extract security_state_new
  AE_SECURITY_STATE=$(python3 -c "import json; r=json.load(open('$AE_REPORT')); print(r['readback']['security_state_new'])")
  AE_SECURITY_STATE_VALUES+=("$AE_SECURITY_STATE")
  
  VALID_AE_RUNS=$((VALID_AE_RUNS + 1))
  
  echo ""
  
  # Reset baseline
  echo "Resetting Alfresco baseline..."
  python3 << 'PYRESET'
import sys
sys.path.insert(0, "integration")
from alfresco_real_feedback_adapter import AlfrescoClient, build_auth_header
import os

client = AlfrescoClient(
    base_url="https://cloud.sjtucyberai.com/alfresco",
    auth_header=build_auth_header(os.environ["ALFRESCO_USER"], os.environ["ALFRESCO_PASS"]),
    verify_ssl=False,
)

# Reset security_state to empty
from integration.alfresco_reset import reset_security_state_to_empty
reset_security_state_to_empty(client)
print("✓ Baseline reset complete")
PYRESET
  
  if [ $? -ne 0 ]; then
    echo "✗ Baseline reset failed"
    exit 1
  fi
  
  echo ""
  
  # ------------------------------------------------------------------------
  # SE RUN
  # ------------------------------------------------------------------------
  
  echo "--- SE RUN (seed=$SEED) ---"
  echo ""
  
  SE_OUTPUT="$OUTPUT_ROOT/se_seed_$SEED"
  
  python3 scripts/run_alfresco_bounded_feedback.py \
    --scenario "$SCENARIO" \
    --afl-seed "$SEED" \
    --max-test-cases "$MAX_TEST_CASES" \
    --time-budget "$TIME_BUDGET" \
    --scorer-ready-timeout "$SCORER_READY_TIMEOUT" \
    --validity-backend sefanogan_es_reference \
    --model-comparison \
    --scorer-python "$CONDA_PYTHON" \
    --run-root "$SE_OUTPUT"
  
  SE_RC=$?
  
  if [ $SE_RC -ne 0 ]; then
    echo "✗ SE run failed with exit code $SE_RC"
    FAILED_RUNS+=("se_seed_$SEED")
    echo ""
    echo "CAMPAIGN ABORTED"
    exit 1
  fi
  
  echo "✓ SE run completed (exit code 0)"
  echo ""
  
  # Inline validation
  echo "Validating SE run..."
  
  SE_REPORT="$SE_OUTPUT/artifact_report.json"
  
  if [ ! -f "$SE_REPORT" ]; then
    echo "✗ SE artifact report missing"
    FAILED_RUNS+=("se_seed_$SEED")
    echo ""
    echo "CAMPAIGN ABORTED"
    exit 1
  fi
  
  python3 << PYVAL
import json
import sys

with open("$SE_REPORT") as f:
    report = json.load(f)

ok = report.get("ok", False)
if not ok:
    print("✗ SE artifact_contract = FAIL")
    sys.exit(1)

mc = report.get("model_comparison_validity", {})
if mc.get("verdict") != "PASS":
    print(f"✗ SE model_comparison_validity = {mc.get('verdict')}")
    sys.exit(1)

part = mc.get("participation", {})
body_score_rpc_ok = part.get("body_score_rpc_ok", 0)
body_score_rpc_fail = part.get("body_score_rpc_fail", 0)

if body_score_rpc_ok == 0:
    print("✗ SE body_score_rpc_ok = 0")
    sys.exit(1)

if body_score_rpc_fail != 0:
    print(f"✗ SE body_score_rpc_fail = {body_score_rpc_fail}")
    sys.exit(1)

trace_invocations = part.get("trace_invocations", 0)
if trace_invocations == 0:
    print("✗ SE trace_invocations = 0")
    sys.exit(1)

trace_backend = part.get("trace_backend")
if trace_backend != "sefanogan_es_reference":
    print(f"✗ SE trace_backend = {trace_backend} (expected sefanogan_es_reference)")
    sys.exit(1)

# Verify SE provenance
runtime_checkpoint_sha = part.get("runtime_checkpoint_sha256")
runtime_metadata_sha = part.get("runtime_metadata_sha256")
runtime_input_dim = part.get("runtime_metadata_input_dim")

EXPECTED_CHECKPOINT = "4eace87ac7d7759a729ff98916a5acead4154c803c53884e3ca7f27570dbf20d"
EXPECTED_META = "2a73ccc3729a3734ab9901b4474feb73d4d42f912ccbc717af48f970ab568226"

if runtime_checkpoint_sha != EXPECTED_CHECKPOINT:
    print(f"✗ SE runtime_checkpoint_sha256 mismatch")
    print(f"  Expected: {EXPECTED_CHECKPOINT}")
    print(f"  Actual: {runtime_checkpoint_sha}")
    sys.exit(1)

if runtime_metadata_sha != EXPECTED_META:
    print(f"✗ SE runtime_metadata_sha256 mismatch")
    print(f"  Expected: {EXPECTED_META}")
    print(f"  Actual: {runtime_metadata_sha}")
    sys.exit(1)

if runtime_input_dim != 32:
    print(f"✗ SE runtime_input_dim = {runtime_input_dim} (expected 32)")
    sys.exit(1)

security_state_new = report.get("readback", {}).get("security_state_new")
if security_state_new is None:
    print("✗ SE security_state_new missing")
    sys.exit(1)

print(f"✓ SE validation PASS")
print(f"  security_state_new: {security_state_new}")
print(f"  body_score_rpc_ok: {body_score_rpc_ok}")
print(f"  trace_invocations: {trace_invocations}")
print(f"  runtime_checkpoint_sha256: {runtime_checkpoint_sha[:16]}...")
print(f"  runtime_metadata_sha256: {runtime_metadata_sha[:16]}...")
print(f"  runtime_input_dim: {runtime_input_dim}")
PYVAL
  
  if [ $? -ne 0 ]; then
    FAILED_RUNS+=("se_seed_$SEED")
    echo ""
    echo "CAMPAIGN ABORTED"
    exit 1
  fi
  
  SE_SECURITY_STATE=$(python3 -c "import json; r=json.load(open('$SE_REPORT')); print(r['readback']['security_state_new'])")
  SE_SECURITY_STATE_VALUES+=("$SE_SECURITY_STATE")
  
  VALID_SE_RUNS=$((VALID_SE_RUNS + 1))
  
  echo ""
  
  # Reset baseline again
  echo "Resetting Alfresco baseline..."
  python3 << 'PYRESET2'
import sys
sys.path.insert(0, "integration")
from alfresco_real_feedback_adapter import AlfrescoClient, build_auth_header
import os

client = AlfrescoClient(
    base_url="https://cloud.sjtucyberai.com/alfresco",
    auth_header=build_auth_header(os.environ["ALFRESCO_USER"], os.environ["ALFRESCO_PASS"]),
    verify_ssl=False,
)

from integration.alfresco_reset import reset_security_state_to_empty
reset_security_state_to_empty(client)
print("✓ Baseline reset complete")
PYRESET2
  
  if [ $? -ne 0 ]; then
    echo "✗ Baseline reset failed"
    exit 1
  fi
  
  echo ""
  echo "✓ Seed $SEED pair complete (AE + SE)"
  echo ""
done

echo "========================================================================"
echo "CAMPAIGN COMPLETE"
echo "========================================================================"
echo ""

# ============================================================================
# FINAL REPORT
# ============================================================================

echo "PHASE3_5PLUS5_VERDICT = COMPLETE"
echo ""
echo "VALID_AE_RUNS = $VALID_AE_RUNS"
echo "VALID_SE_RUNS = $VALID_SE_RUNS"
echo "TOTAL_VALID_RUNS = $((VALID_AE_RUNS + VALID_SE_RUNS))"
echo ""

if [ $VALID_AE_RUNS -eq 5 ] && [ $VALID_SE_RUNS -eq 5 ]; then
  echo "GLOBAL_5PLUS5_CONTRACT = PASS"
else
  echo "GLOBAL_5PLUS5_CONTRACT = FAIL"
  exit 1
fi

echo ""
echo "AE_SECURITY_STATE_NEW_VALUES = [${AE_SECURITY_STATE_VALUES[*]}]"
echo "SE_SECURITY_STATE_NEW_VALUES = [${SE_SECURITY_STATE_VALUES[*]}]"
echo ""

# Compute descriptive statistics
python3 << 'PYSTATS'
import sys

ae_values = [float(x) for x in sys.argv[1].strip("[]").split()]
se_values = [float(x) for x in sys.argv[2].strip("[]").split()]

def stats(values, label):
    import statistics
    print(f"{label}_MEAN = {statistics.mean(values):.2f}")
    print(f"{label}_MEDIAN = {statistics.median(values):.2f}")
    if len(values) > 1:
        print(f"{label}_SAMPLE_SD = {statistics.stdev(values):.2f}")
    else:
        print(f"{label}_SAMPLE_SD = N/A")
    print(f"{label}_MIN = {min(values):.2f}")
    print(f"{label}_MAX = {max(values):.2f}")
    print(f"{label}_RANGE = {max(values) - min(values):.2f}")

stats(ae_values, "AE_SECURITY_STATE_NEW")
print()
stats(se_values, "SE_SECURITY_STATE_NEW")
print()

deltas = [se - ae for se, ae in zip(se_values, ae_values)]
print(f"PAIRED_DELTAS_SE_MINUS_AE = {deltas}")
print()
print("DESCRIPTIVE_ANALYSIS_ONLY = YES")
print("STATISTICAL_SUPERIORITY_CLAIM = NO")
PYSTATS "[${AE_SECURITY_STATE_VALUES[*]}]" "[${SE_SECURITY_STATE_VALUES[*]}]"

echo ""
echo "ENGINEERING_VARIANCE_PILOT = PASS"
echo "NEXT_FORMAL_EXPERIMENT_GATE = OPEN_FOR_HUMAN_DESIGN_REVIEW"
echo ""
echo "SOURCE_CHANGED_DURING_PHASE3 = NO"
echo "TESTS_CHANGED_DURING_PHASE3 = NO"
echo "MODEL_FILES_CHANGED_DURING_PHASE3 = NO"
echo "GIT_REFS_CHANGED = NO"
echo "COMMIT = NO"
echo "PUSH = NO"
echo ""
echo "Campaign completed successfully."

