#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export IN_DIR="${IN_DIR:-$PWD/in/flowable_process_start}"
export OUT_DIR="${OUT_DIR:-$PWD/out/flowable_process_start_compare}"
export DUR="${DUR:-20}"

rm -rf "$OUT_DIR"
rm -f /tmp/nv_body_valid_stats.json

python3 scripts/run_flowable_process_start_compare.py
