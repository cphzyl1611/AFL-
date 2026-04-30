#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${RUNNER_RUN_DIR:?RUNNER_RUN_DIR is required}"
: "${RUNNER_DURATION_PLAN:?RUNNER_DURATION_PLAN is required}"

mkdir -p "$RUNNER_RUN_DIR"

SUMMARY_SRC="$PWD/out/flowable_process_start_compare/summary.csv"
STATS_SRC="/tmp/nv_body_valid_stats.json"

for DUR_ITEM in ${RUNNER_DURATION_PLAN}; do
  export DUR="$DUR_ITEM"

  rm -f "$SUMMARY_SRC" "$STATS_SRC"

  ./scripts/run_flowable_process_start_compare.sh

  if [ -s "$SUMMARY_SRC" ]; then
    cp "$SUMMARY_SRC" "$RUNNER_RUN_DIR/summary_dur${DUR}.csv"
  fi

  if [ -s "$STATS_SRC" ]; then
    cp "$STATS_SRC" "$RUNNER_RUN_DIR/body_valid_stats_dur${DUR}.json"
  fi
done
