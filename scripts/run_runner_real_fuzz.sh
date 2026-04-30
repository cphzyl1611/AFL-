#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${NV_TOKEN:?NV_TOKEN is required}"
: "${NV_BODY_SCORE_ENDPOINT:?NV_BODY_SCORE_ENDPOINT is required}"
: "${NV_BODY_SCORE_THRESHOLD:?NV_BODY_SCORE_THRESHOLD is required}"

export NV_DEBUG_BODY_VALID="${NV_DEBUG_BODY_VALID:-1}"
export IN_DIR="${IN_DIR:-$PWD/in/o2oa_body_model_compare}"
export DUR="${DUR:-20}"

rm -rf "$PWD/out/cms_body_valid_compare_real"
rm -f /tmp/nv_body_valid_stats.json

./scripts/run_cms_body_valid_compare_real_rulescore_only.sh