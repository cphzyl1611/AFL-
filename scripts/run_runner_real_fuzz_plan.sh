#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"

: "${NV_TOKEN:?NV_TOKEN is required}"
: "${NV_BODY_SCORE_ENDPOINT:?NV_BODY_SCORE_ENDPOINT is required}"
: "${NV_BODY_SCORE_THRESHOLD:?NV_BODY_SCORE_THRESHOLD is required}"
: "${ROOT:?ROOT is required}"
: "${CFG:?CFG is required}"
: "${IN_DIR:?IN_DIR is required and must be the runner manifest seed view}"
: "${SEED_MANIFEST:?SEED_MANIFEST is required}"
: "${OUT_ROOT:?OUT_ROOT is required}"
: "${BODY_VALID_STATS:?BODY_VALID_STATS is required}"
: "${STATUS_PATH:?STATUS_PATH is required}"
: "${RUNNER_RUN_DIR:?RUNNER_RUN_DIR is required}"
: "${RUNNER_DURATION_PLAN:?RUNNER_DURATION_PLAN is required}"

export NV_DEBUG_BODY_VALID="${NV_DEBUG_BODY_VALID:-1}"

unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
export no_proxy="127.0.0.1,localhost"
export NO_PROXY="127.0.0.1,localhost"

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

export ROOT CFG IN_DIR SEED_MANIFEST OUT_ROOT BODY_VALID_STATS STATUS_PATH RUNNER_RUN_DIR
mkdir -p "$RUNNER_RUN_DIR"
cd "$ROOT"

SUMMARY_SRC="$OUT_ROOT/summary.csv"
STATS_SRC="$BODY_VALID_STATS"

for DUR_ITEM in ${RUNNER_DURATION_PLAN}; do
  export DUR="$DUR_ITEM"

  # 清理旧结果，避免复制到上一次遗留文件
  rm -f "$SUMMARY_SRC" "$STATS_SRC"

  "$ROOT/scripts/run_runner_real_fuzz.sh"

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
