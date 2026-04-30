#!/usr/bin/env bash
set -euo pipefail

ROOT="$HOME/AFLplusplus"
cd "$ROOT"

if [[ $# -ne 2 ]]; then
  echo "Usage: bash scripts/run_stage2_validation.sh <baseline_156|enhanced_182> <20|60>"
  exit 1
fi

EXP_NAME="$1"
DUR="$2"

if [[ "$DUR" != "20" && "$DUR" != "60" ]]; then
  echo "Duration must be 20 or 60"
  exit 1
fi

LATEST_DIR=$(ls -td docs/final_results/experiments/${EXP_NAME}_* 2>/dev/null | head -n 1 || true)
if [[ -z "${LATEST_DIR:-}" ]]; then
  echo "No experiment directory found for $EXP_NAME"
  exit 1
fi

MODEL_PATH="$ROOT/$LATEST_DIR/sefanogan_ae_model.pt"
META_PATH="$ROOT/$LATEST_DIR/sefanogan_ae_meta.json"

if [[ ! -f "$MODEL_PATH" || ! -f "$META_PATH" ]]; then
  echo "Model or meta file missing in $LATEST_DIR"
  exit 1
fi

echo "[INFO] experiment = $EXP_NAME"
echo "[INFO] duration   = $DUR"
echo "[INFO] exp dir    = $LATEST_DIR"
echo "[INFO] model      = $MODEL_PATH"
echo "[INFO] meta       = $META_PATH"

echo
echo "[INFO] Before running this script, make sure AE score server is already started with:"
echo "export SEFANOGAN_MODE=ae"
echo "export SEFANOGAN_MODEL_PATH=\"$MODEL_PATH\""
echo "export SEFANOGAN_AE_META_PATH=\"$META_PATH\""
echo "python3 nv_valid_server_real.py"
echo

export NV_BODY_SCORE_ENDPOINT='unix:///tmp/nv_valid_real.sock'
export NV_BODY_SCORE_THRESHOLD='1.0'
export NV_DEBUG_BODY_VALID=1

if [[ -z "${NV_TOKEN:-}" ]]; then
  echo "NV_TOKEN is not set. Please export NV_TOKEN before running."
  exit 1
fi

IN_DIR="$ROOT/in/o2oa_body_model_compare" DUR="$DUR" ./scripts/run_cms_body_valid_compare_real_rulescore_only.sh

cp out/cms_body_valid_compare_real/summary.csv "$LATEST_DIR/summary_dur${DUR}.csv"
cat /tmp/nv_body_valid_stats.json > "$LATEST_DIR/body_valid_stats_dur${DUR}.json"

echo "[OK] validation finished"
echo "[OK] saved:"
echo "  $LATEST_DIR/summary_dur${DUR}.csv"
echo "  $LATEST_DIR/body_valid_stats_dur${DUR}.json"
