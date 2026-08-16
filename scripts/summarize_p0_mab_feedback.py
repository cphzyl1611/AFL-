#!/usr/bin/env python3
"""Summarise a P0 deterministic MAB / security-state feedback experiment.

Reads fuzzer_stats + eval_report.json + security_states.jsonl from OUT_DIR and
writes summary.csv next to them.  Nothing here computes metrics of its own --
every number is copied from the fuzzer's own runtime output so the summary can
be cross-checked against fuzzer_stats by hand.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Any


FIELDS = [
    "profile",
    "summary_source",
    "execution_scope",
    "metric_semantics",
    "execs_done",
    "run_time",
    "nv_total_valid_exec",
    "nv_err_exec",
    "saved_crashes",
    "saved_hangs",
    "edges_found",
    # mab
    "nv_mab_c",
    "nv_mab_min_explore",
    "nv_mab_total_pulls",
    "nv_mab_cold_start_picks",
    "nv_mab_ucb_picks",
    "arm0_pulls",
    "arm1_pulls",
    "arm2_pulls",
    "arm0_mean",
    "arm1_mean",
    "arm2_mean",
    "arm0_sum",
    "arm1_sum",
    "arm2_sum",
    # security state coverage
    "security_state_total",
    "security_state_new_total",
    "security_state_delta_last",
    "security_state_observations",
    "security_state_seed_credit",
    "state_log_records",
    "state_log_distinct_states",
    "state_log_minus_observations",
    "state_log_distinct_minus_covset",
    "state_accounting_note",
    # seed scheduling
    "ss_cov_sum",
    "ss_cov_max",
    "ss_selected_sum",
    "ss_prob_max",
    "boundary",
]

BOUNDARY = (
    "P0 deterministic integration test; local network-free target; "
    "not a platform experiment; not a real O2OA/Alfresco/Flowable service; "
    "AFL native edge coverage is not used as the security-state metric"
)


def parse_key_value(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip()] = value.strip()
    return out


def num(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def main() -> int:
    out_dir = Path(os.environ.get("OUT_DIR", "")).resolve()
    if not out_dir.is_dir():
        raise SystemExit("OUT_DIR must point at an existing experiment directory")

    stats_path = out_dir / "fuzzer_stats"
    if not stats_path.is_file():
        raise SystemExit(f"missing fuzzer_stats: {stats_path}")
    stats = parse_key_value(stats_path)

    report_path = out_dir / "eval_report.json"
    report: dict[str, Any] = {}
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))

    state_log = out_dir / "security_states.jsonl"
    records = 0
    distinct: set[str] = set()
    if state_log.is_file():
        for line in state_log.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            records += 1
            try:
                distinct.add(json.loads(line).get("security_state_id", ""))
            except Exception:
                pass

    row = {
        "profile": os.environ.get("NV_P0_PROFILE", ""),
        "summary_source": "p0_mab_security_state_feedback",
        "execution_scope": "p0_deterministic_integration_test",
        "metric_semantics": (
            "AFL++ run over a deterministic local target; Cov is the project "
            "security-state coverage (method+path+response class), not AFL "
            "native edge coverage"
        ),
        "execs_done": stats.get("execs_done", ""),
        "run_time": stats.get("run_time", ""),
        "nv_total_valid_exec": stats.get("nv_total_valid_exec", ""),
        "nv_err_exec": stats.get("nv_err_exec", ""),
        "saved_crashes": stats.get("saved_crashes", ""),
        "saved_hangs": stats.get("saved_hangs", ""),
        "edges_found": stats.get("edges_found", ""),
        "nv_mab_c": stats.get("nv_mab_c", ""),
        "nv_mab_min_explore": stats.get("nv_mab_min_explore", ""),
        "nv_mab_total_pulls": stats.get("nv_mab_total_pulls", ""),
        "nv_mab_cold_start_picks": stats.get("nv_mab_cold_start_picks", ""),
        "nv_mab_ucb_picks": stats.get("nv_mab_ucb_picks", ""),
        "arm0_pulls": stats.get("nv_mab_arm0_pulls", ""),
        "arm1_pulls": stats.get("nv_mab_arm1_pulls", ""),
        "arm2_pulls": stats.get("nv_mab_arm2_pulls", ""),
        "arm0_mean": stats.get("nv_mab_arm0_mean", ""),
        "arm1_mean": stats.get("nv_mab_arm1_mean", ""),
        "arm2_mean": stats.get("nv_mab_arm2_mean", ""),
        "arm0_sum": stats.get("nv_mab_arm0_sum", ""),
        "arm1_sum": stats.get("nv_mab_arm1_sum", ""),
        "arm2_sum": stats.get("nv_mab_arm2_sum", ""),
        "security_state_total": stats.get("security_state_total", ""),
        "security_state_new_total": stats.get("security_state_new_total", ""),
        "security_state_delta_last": stats.get("security_state_delta_last", ""),
        "security_state_observations": stats.get("security_state_observations", ""),
        "security_state_seed_credit": stats.get("security_state_seed_credit", ""),
        "state_log_records": str(records),
        "state_log_distinct_states": str(len(distinct)),
        "state_log_minus_observations": str(
            records - int(num(stats.get("security_state_observations"), 0))),
        "state_log_distinct_minus_covset": str(
            len(distinct) - int(num(stats.get("security_state_total"), 0))),
        "state_accounting_note": (
            "state_log_records counts every target execution, including the "
            "dry-run/calibration/trim executions that never reach "
            "common_fuzz_stuff; security_state_observations counts only the "
            "fuzzing-loop executions whose status document was read and was "
            "not a replay. state_log_distinct_minus_covset is therefore the "
            "number of states only ever reached outside the fuzzing loop."
        ),
        "ss_cov_sum": stats.get("ss_cov_sum", ""),
        "ss_cov_max": stats.get("ss_cov_max", ""),
        "ss_selected_sum": stats.get("ss_selected_sum", ""),
        "ss_prob_max": stats.get("ss_prob_max", ""),
        "boundary": BOUNDARY,
    }

    summary_path = out_dir / "summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(row)

    print(f"[OK] wrote {summary_path}")
    print(
        "[*] mab: c={c} min_explore={me} pulls={p} cold={cs} ucb={ucb} "
        "arms={a0}/{a1}/{a2}".format(
            c=row["nv_mab_c"], me=row["nv_mab_min_explore"],
            p=row["nv_mab_total_pulls"], cs=row["nv_mab_cold_start_picks"],
            ucb=row["nv_mab_ucb_picks"], a0=row["arm0_pulls"],
            a1=row["arm1_pulls"], a2=row["arm2_pulls"]))
    print(
        "[*] security states: total={t} new={n} obs={o} seed_credit={sc} "
        "log_records={lr} log_distinct={ld}".format(
            t=row["security_state_total"], n=row["security_state_new_total"],
            o=row["security_state_observations"],
            sc=row["security_state_seed_credit"],
            lr=row["state_log_records"], ld=row["state_log_distinct_states"]))
    print("[*] seed scheduling: ss_cov_sum={s} ss_cov_max={m}".format(
        s=row["ss_cov_sum"], m=row["ss_cov_max"]))
    if report:
        print("[*] eval_report.json mab block present:",
              "mab" in report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
