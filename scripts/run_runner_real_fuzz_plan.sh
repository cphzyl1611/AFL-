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

SUMMARY_SRC="$PWD/out/cms_body_valid_compare_real/summary.csv"
STATS_SRC="/tmp/nv_body_valid_stats.json"

for DUR_ITEM in ${RUNNER_DURATION_PLAN}; do
  export DUR="$DUR_ITEM"

  # 清理旧结果，避免复制到上一次遗留文件
  rm -f "$SUMMARY_SRC" "$STATS_SRC"

  ./scripts/run_runner_real_fuzz.sh

  # 等 summary.csv 真正写完
  for _ in $(seq 1 20); do
    if [ -s "$SUMMARY_SRC" ]; then
      break
    fi
    sleep 0.5
  done

  if [ -s "$SUMMARY_SRC" ]; then
    cp "$SUMMARY_SRC" "$RUNNER_RUN_DIR/summary_dur${DUR}.csv"
  else
    echo "[WARN] summary.csv missing for DUR=${DUR}" >&2
  fi

  # 等 stats json 真正写完
  for _ in $(seq 1 20); do
    if [ -s "$STATS_SRC" ]; then
      break
    fi
    sleep 0.5
  done

  if [ -s "$STATS_SRC" ]; then
    cp "$STATS_SRC" "$RUNNER_RUN_DIR/body_valid_stats_dur${DUR}.json"
  else
    echo "[WARN] nv_body_valid_stats.json missing for DUR=${DUR}" >&2
  fi
done