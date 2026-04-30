#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${NV_TOKEN:?NV_TOKEN is required}"
: "${NV_BODY_SCORE_ENDPOINT:?NV_BODY_SCORE_ENDPOINT is required}"
: "${NV_BODY_SCORE_THRESHOLD:?NV_BODY_SCORE_THRESHOLD is required}"
: "${RUNNER_RUN_DIR:?RUNNER_RUN_DIR is required}"
: "${RUNNER_DURATION_PLAN:?RUNNER_DURATION_PLAN is required}"

export NV_DEBUG_BODY_VALID="${NV_DEBUG_BODY_VALID:-1}"
export IN_DIR="${IN_DIR:-$PWD/in/o2oa_body_model_compare}"

mkdir -p "$RUNNER_RUN_DIR"

for DUR_ITEM in ${RUNNER_DURATION_PLAN}; do
  export DUR="$DUR_ITEM"

  ./scripts/run_runner_real_fuzz.sh

  if [ -f "$PWD/out/cms_body_valid_compare_real/summary.csv" ]; then
    cp "$PWD/out/cms_body_valid_compare_real/summary.csv" \
      "$RUNNER_RUN_DIR/summary_dur${DUR}.csv"
  fi

  if [ -f "/tmp/nv_body_valid_stats.json" ]; then
    cp "/tmp/nv_body_valid_stats.json" \
      "$RUNNER_RUN_DIR/body_valid_stats_dur${DUR}.json"
  fi
done