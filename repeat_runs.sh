#!/usr/bin/env bash
set -euo pipefail

R="${R:-3}"                 # 重复次数
NV_ENDPOINTS="${NV_ENDPOINTS:-5}"

# 120s & 300s 两组预算
BUDGETS=("120" "300")

for b in "${BUDGETS[@]}"; do
  for i in $(seq 1 "$R"); do
    out="out_http_ablation_${b}_r${i}"
    echo "[*] budget=${b}s repeat=${i}/${R} OUTROOT=${out}"
    OUTROOT="$out" NV_ENDPOINTS="$NV_ENDPOINTS" DUR="$b" ./run_ablation_v2.sh >/dev/null
  done
done

echo "[OK] Finished. Now summarize:"
echo "  python3 summarize_repeats.py --r $R --out repeat_summary.csv"
