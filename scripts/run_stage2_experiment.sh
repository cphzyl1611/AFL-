#!/usr/bin/env bash
set -euo pipefail

ROOT="$HOME/AFLplusplus"
cd "$ROOT"

if [[ $# -ne 1 ]]; then
  echo "Usage: bash scripts/run_stage2_experiment.sh <baseline_156|enhanced_182>"
  exit 1
fi

EXP_NAME="$1"

case "$EXP_NAME" in
  baseline_156)
    MANIFEST="model_stage/manifests/dataset_manifest_156.txt"
    ;;
  enhanced_182)
    MANIFEST="model_stage/manifests/dataset_manifest_182.txt"
    ;;
  *)
    echo "Unknown experiment name: $EXP_NAME"
    echo "Allowed: baseline_156 | enhanced_182"
    exit 1
    ;;
esac

STAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="docs/final_results/experiments/${EXP_NAME}_${STAMP}"
mkdir -p "$OUTDIR"

echo "[INFO] experiment = $EXP_NAME"
echo "[INFO] manifest   = $MANIFEST"
echo "[INFO] outdir     = $OUTDIR"

python3 model_stage/build_dataset.py --manifest "$MANIFEST"
cp model_stage/data/sefanogan_dataset.jsonl "$OUTDIR/"

python3 model_stage/export_features.py
cp model_stage/data/sefanogan_features.csv "$OUTDIR/"
cp model_stage/data/sefanogan_features_summary.json "$OUTDIR/"

python3 model_stage/split_dataset.py
cp model_stage/data/sefanogan_train.jsonl "$OUTDIR/"
cp model_stage/data/sefanogan_val.jsonl "$OUTDIR/"

python3 model_stage/sefanogan_train_ae.py
cp model_stage/models/sefanogan_ae_model.pt "$OUTDIR/"
cp model_stage/models/sefanogan_ae_meta.json "$OUTDIR/"

cat > "$OUTDIR/experiment_info.txt" <<INFO
experiment=$EXP_NAME
manifest=$MANIFEST
timestamp=$STAMP
INFO

cat > "$OUTDIR/README.md" <<INFO
# Experiment: $EXP_NAME

## Basic Info
- experiment: $EXP_NAME
- manifest: $MANIFEST
- timestamp: $STAMP

## Files
- sefanogan_dataset.jsonl
- sefanogan_features.csv
- sefanogan_features_summary.json
- sefanogan_train.jsonl
- sefanogan_val.jsonl
- sefanogan_ae_model.pt
- sefanogan_ae_meta.json
- experiment_info.txt

## Validation Outputs
After running validation, the following files may appear:
- summary_dur20.csv
- body_valid_stats_dur20.json
- summary_dur60.csv
- body_valid_stats_dur60.json

## Validation Command Examples
bash scripts/run_stage2_validation.sh $EXP_NAME 20
bash scripts/run_stage2_validation.sh $EXP_NAME 60
INFO

echo "[OK] experiment finished"
echo "[OK] results saved to $OUTDIR"
