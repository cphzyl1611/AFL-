#!/usr/bin/env bash
set -euo pipefail

# ======================
# Config (override via env)
# ======================
DUR="${DUR:-120}"
OUTROOT="${OUTROOT:-out_http_ablation_v2}"
IN_DIR="${IN_DIR:-$PWD/in_http}"
HARNESS="${HARNESS:-$PWD/nv_http_harness.py}"
PYMOD="${PYMOD:-nv_json_mutator}"
AFLBIN="${AFLBIN:-$PWD/afl-fuzz}"
REPORT_GEN="${REPORT_GEN:-$PWD/make_report.py}"

# Auto nall inputs
NV_ENDPOINTS="${NV_ENDPOINTS:-5}"

# If you want to FIX NALL (disable auto), run:
#   USE_NV_NALL=1 NV_NALL=1080 ...
USE_NV_NALL="${USE_NV_NALL:-0}"
NALL=""
if [[ "$USE_NV_NALL" == "1" ]]; then
  NALL="${NV_NALL:-}"
fi

# Probe/status temp files (shared, but cleaned each run)
export NV_STATUS_PATH="${NV_STATUS_PATH:-/tmp/nv_http_status.json}"
export NV_PROBE_PATH="${NV_PROBE_PATH:-/tmp/nv_probe.json}"
export NV_STATE_DB="${NV_STATE_DB:-/tmp/nv_state_db.json}"

clean_probe() {
  rm -f "$NV_STATE_DB" "$NV_PROBE_PATH" "$NV_STATUS_PATH"
}

write_task() {
  local enable_mab="$1"
  local scope_json="$2"
  local task_path="$3"

  local vep="${NV_VALIDITY_ENDPOINT:-}"
  local vth="${NV_VALIDITY_THRESHOLD:-0.8}"
  local ev="${ENABLE_VALIDITY:-0}"

  # 注意：只有 vep 非空才写 validity_endpoint；否则走纯规则模式
  if [[ -n "$vep" ]]; then
cat > "$task_path" <<TASK
{
  "target_type": "binary",
  "max_test_cases": 0,
  "time_budget": ${DUR},
  "mutation_scope": ${scope_json},
  "enable_mab": ${enable_mab},
  "enable_validity": ${ev},
  "validity_endpoint": "${vep}",
  "validity_threshold": ${vth}
}
TASK
  else
cat > "$task_path" <<TASK
{
  "target_type": "binary",
  "max_test_cases": 0,
  "time_budget": ${DUR},
  "mutation_scope": ${scope_json},
  "enable_mab": ${enable_mab},
  "enable_validity": ${ev}
}
TASK
  fi
}

run_one() {
  local name="$1"
  local enable_mab="$2"
  local scope_json="$3"

  local run_dir="${OUTROOT}/${name}"
  local task_path="${run_dir}/task.json"
  local out_dir="${run_dir}/out"
  local err_dir="${run_dir}/err_cases"

  mkdir -p "$run_dir"
  rm -rf "$out_dir" "$err_dir"
  mkdir -p "$out_dir" "$err_dir"

  clean_probe
  write_task "$enable_mab" "$scope_json" "$task_path"

  echo "[*] Run ${name} (enable_mab=${enable_mab}, scope=${scope_json}) -> ${out_dir}"

  envs=(
  "AFL_NO_UI=1"
  "PYTHONPATH=$PWD"
  "AFL_PYTHON_MODULE=$PYMOD"
  "NV_TASK_PATH=$task_path"
  "NV_STATUS_PATH=$NV_STATUS_PATH"
  "NV_PROBE_PATH=$NV_PROBE_PATH"
  "NV_STATE_DB=$NV_STATE_DB"
  "NV_ENDPOINTS=$NV_ENDPOINTS"
  "NV_ERR_DIR=$err_dir"
  # 关键：默认清掉父环境的 NV_NALL，确保自动 nall 生效
  "NV_NALL="
)
  envs+=("NV_TARGET_CONFIG=${NV_TARGET_CONFIG:-$PWD/nv_target.json}")

# 只有显式固定口径时才注入
if [[ -n "${NALL:-}" ]]; then
  envs+=("NV_NALL=$NALL")
fi

  # Run afl-fuzz (log output for debugging)
  env "${envs[@]}" \
    "$AFLBIN" -n -i "$IN_DIR" -o "$out_dir" -- /usr/bin/python3 "$HARNESS" \
    >"$run_dir/afl_stdout.log" 2>"$run_dir/afl_stderr.log" || true

  # Freeze probe/db/status snapshots into out_dir (avoid /tmp mixing)
  [[ -f "$NV_PROBE_PATH"  ]] && cp "$NV_PROBE_PATH"  "$out_dir/nv_probe.json" || true
  [[ -f "$NV_STATE_DB"    ]] && cp "$NV_STATE_DB"    "$out_dir/nv_state_db.json" || true
  [[ -f "$NV_STATUS_PATH" ]] && cp "$NV_STATUS_PATH" "$out_dir/nv_http_status.json" || true

  # Generate report.json using this run's frozen probe
  if [[ -f "$out_dir/nv_probe.json" ]]; then
    NV_PROBE_PATH="$out_dir/nv_probe.json" python3 "$REPORT_GEN" "$out_dir" \
      >"$run_dir/report_stdout.log" 2>"$run_dir/report_stderr.log" || true
  fi
}

summarize_report() {
  local out_dir="$1"
  local report="${out_dir}/report.json"

  # If missing, try to generate once (best-effort)
  if [[ ! -f "$report" && -f "$out_dir/nv_probe.json" ]]; then
    NV_PROBE_PATH="$out_dir/nv_probe.json" python3 "$REPORT_GEN" "$out_dir" >/dev/null 2>&1 || true
  fi
  if [[ ! -f "$report" ]]; then
    echo "0,0,0,0,0,0,0,0"
    return
  fi

  python3 - <<PY
import json
r=json.load(open("${report}"))
cov=r.get("Cov",{})
er=r.get("ErrRec",{})
sc=r.get("Score",{})
print("{},{},{:.6f},{},{},{:.6f},{:.6f},{:.6f}".format(
  int(cov.get("ncov_total",0)),
  int(cov.get("nall",0)),
  float(cov.get("C_final",0.0)),
  int(er.get("err_cnt",0)),
  int(er.get("rec_cnt",0)),
  float(er.get("err_rate",0.0)),
  float(er.get("rec_rate",0.0)),
  float(sc.get("total",0.0)),
))
PY
}

summarize_plot() {
  local out_dir="$1"
  local plot="${out_dir}/plot_data"
  if [[ ! -f "$plot" ]]; then
    echo "0,0,0,0,0,0,0,0,0,0,0"
    return
  fi
  python3 - <<PY
lines=open("${plot}","r",encoding="utf-8",errors="ignore").read().splitlines()
hdr=None
last=None
for ln in lines:
  if ln.startswith("#"):
    hdr=[x.strip() for x in ln.lstrip("#").split(",")]
  elif ln.strip():
    last=[x.strip() for x in ln.split(",")]
idx={n:i for i,n in enumerate(hdr or [])}
def get(name, default="0"):
  i=idx.get(name,None)
  return last[i] if (i is not None and i < len(last)) else default

print(",".join([
  get("nv_status_cnt","0"),
  get("nv_ncov_hit","0"),
  get("nv_err_cnt","0"),
  get("nv_rec_cnt","0"),
  get("nv_rec_ms_sum","0"),
  get("nv_mab_a0_pulls","0"),
  get("nv_mab_a1_pulls","0"),
  get("nv_mab_a2_pulls","0"),
  get("nv_mab_a0_mean","0"),
  get("nv_mab_a1_mean","0"),
  get("nv_mab_a2_mean","0"),
]))
PY
}

main() {
  mkdir -p "$OUTROOT"

  run_one "mab_all" 1 '["field_value","boundary","structure"]'
  run_one "only_field" 0 '["field_value"]'
  run_one "only_boundary" 0 '["boundary"]'
  run_one "only_structure" 0 '["structure"]'

  # Summary CSV (report.json)
  local sumcsv="${OUTROOT}/summary.csv"
  echo "run,ncov_total,nall,C_final,err_cnt,rec_cnt,err_rate,rec_rate,score" > "$sumcsv"
  for r in mab_all only_field only_boundary only_structure; do
    echo "${r},$(summarize_report "${OUTROOT}/${r}/out")" >> "$sumcsv"
  done

  # Plot CSV (plot_data last line)
  local plotcsv="${OUTROOT}/ablation_plot.csv"
  echo "run,nv_status_cnt,nv_ncov_hit,nv_err_cnt,nv_rec_cnt,nv_rec_ms_sum,a0_pulls,a1_pulls,a2_pulls,a0_mean,a1_mean,a2_mean" > "$plotcsv"
  for r in mab_all only_field only_boundary only_structure; do
    echo "${r},$(summarize_plot "${OUTROOT}/${r}/out")" >> "$plotcsv"
  done

  echo "[OK] Wrote ${sumcsv}"
  cat "$sumcsv"
  echo
  echo "[OK] Wrote ${plotcsv}"
  cat "$plotcsv"
}

main "$@"
