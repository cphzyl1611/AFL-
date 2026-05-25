#!/usr/bin/env python3
"""Summarize four-mode AFL++ online filter ablation evidence."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = Path(os.environ.get("ABLATION_OUT_DIR", ROOT / "out" / "alfresco_afl_online_filter_ablation"))
SUMMARY_CSV = BASE_DIR / "ablation_summary.csv"
DETAILS_CSV = BASE_DIR / "ablation_details.csv"
REPORT_JSON = BASE_DIR / "ablation_report.json"
MODES = ["rule_only", "rule_ae", "rule_fanogan", "rule_ae_fanogan"]
SUMMARY_SOURCE = "afl_fuzz_online_filter_ablation"
EXECUTION_SCOPE = "alfresco_content_update_mock_afl_online_filter_four_mode_ablation"
METRIC_SEMANTICS = (
    "Four-mode ablation over representative AFL++ online filter smoke; mock target only, "
    "not full SE-fAnoGAN-ES and not real Alfresco service."
)

DETAIL_HEADER = [
    "mode",
    "run_time",
    "execs_done",
    "execs_per_sec",
    "saved_crashes",
    "saved_hangs",
    "nv_total_valid_exec",
    "nv_err_exec",
    "nv_err_rate",
    "body_rule_pass",
    "body_rule_reject",
    "body_score_pass",
    "body_score_reject",
    "body_score_rpc_ok",
    "body_score_rpc_fail",
    "sent_to_target",
    "filtered_by_rule",
    "filtered_by_ae",
    "filtered_by_fanogan",
    "summary_source",
    "execution_scope",
]

SUMMARY_HEADER = [
    "modes",
    "total_execs_done",
    "total_valid_exec",
    "total_err_exec",
    "max_nv_err_rate",
    "saved_crashes_total",
    "saved_hangs_total",
    "rule_only_sent_to_target",
    "rule_ae_sent_to_target",
    "rule_fanogan_sent_to_target",
    "rule_ae_fanogan_sent_to_target",
    "rule_only_filtered_by_rule",
    "rule_ae_filtered_by_ae",
    "rule_fanogan_filtered_by_fanogan",
    "rule_ae_fanogan_filtered_by_fanogan",
    "ae_primary_recommendation",
    "fanogan_online_observation",
    "summary_source",
    "execution_scope",
    "metric_semantics",
]


def parse_key_value_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def read_summary(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        row = next(reader, None)
    if row is None:
        raise ValueError(f"empty summary: {path}")
    return dict(row)


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def collect_mode(mode: str) -> dict[str, Any]:
    mode_dir = BASE_DIR / mode
    summary = read_summary(mode_dir / "summary.csv")
    stats = parse_key_value_file(mode_dir / "fuzzer_stats")
    report_path = mode_dir / "eval_report.json"
    report: dict[str, Any] = {}
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "mode": mode,
        "run_time": int_value(stats.get("run_time")),
        "execs_done": int_value(stats.get("execs_done")),
        "execs_per_sec": stats.get("execs_per_sec", "0"),
        "saved_crashes": int_value(summary.get("saved_crashes")),
        "saved_hangs": int_value(summary.get("saved_hangs")),
        "nv_total_valid_exec": int_value(summary.get("nv_total_valid_exec")),
        "nv_err_exec": int_value(summary.get("nv_err_exec")),
        "nv_err_rate": float_value(summary.get("nv_err_rate")),
        "body_rule_pass": int_value(summary.get("body_rule_pass")),
        "body_rule_reject": int_value(summary.get("body_rule_reject")),
        "body_score_pass": int_value(summary.get("body_score_pass")),
        "body_score_reject": int_value(summary.get("body_score_reject")),
        "body_score_rpc_ok": int_value(summary.get("body_score_rpc_ok")),
        "body_score_rpc_fail": int_value(summary.get("body_score_rpc_fail")),
        "sent_to_target": int_value(summary.get("sent_to_target")),
        "filtered_by_rule": int_value(summary.get("filtered_by_rule")),
        "filtered_by_ae": int_value(summary.get("filtered_by_ae")),
        "filtered_by_fanogan": int_value(summary.get("filtered_by_fanogan")),
        "summary_source": summary.get("summary_source", ""),
        "execution_scope": summary.get("execution_scope", ""),
        "summary_path": str(mode_dir / "summary.csv"),
        "fuzzer_stats_path": str(mode_dir / "fuzzer_stats"),
        "eval_report_path": str(report_path),
        "report": report,
    }


def main() -> int:
    rows = [collect_mode(mode) for mode in MODES]
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    with DETAILS_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=DETAIL_HEADER, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            output_row = dict(row)
            output_row["nv_err_rate"] = f"{float(row['nv_err_rate']):.6f}"
            writer.writerow({key: output_row[key] for key in DETAIL_HEADER})

    by_mode = {str(row["mode"]): row for row in rows}
    total_err_exec = sum(int(row["nv_err_exec"]) for row in rows)
    saved_crashes_total = sum(int(row["saved_crashes"]) for row in rows)
    saved_hangs_total = sum(int(row["saved_hangs"]) for row in rows)
    all_stable = total_err_exec == 0 and saved_crashes_total == 0 and saved_hangs_total == 0

    rule_ae_sent = int(by_mode["rule_ae"]["sent_to_target"])
    rule_fanogan_sent = int(by_mode["rule_fanogan"]["sent_to_target"])
    rule_ae_fanogan_sent = int(by_mode["rule_ae_fanogan"]["sent_to_target"])
    fanogan_errors = int(by_mode["rule_fanogan"]["body_score_rpc_fail"]) + int(by_mode["rule_ae_fanogan"]["body_score_rpc_fail"])
    fanogan_execs = int(by_mode["rule_fanogan"]["execs_done"]) + int(by_mode["rule_ae_fanogan"]["execs_done"])
    ae_execs = int(by_mode["rule_ae"]["execs_done"])
    if fanogan_errors:
        fanogan_observation = "fanogan_online_path_has_scoring_errors_keep_ae_v1_primary"
    elif fanogan_execs < ae_execs:
        fanogan_observation = "fanogan_online_path_runs_without_scoring_error_but_short_sample_count_keep_ae_v1_primary"
    elif rule_fanogan_sent == rule_ae_sent and rule_ae_fanogan_sent == rule_ae_sent:
        fanogan_observation = "fanogan_online_path_runs_close_to_rule_ae_continue_evaluation"
    else:
        fanogan_observation = "fanogan_online_path_runs_with_different_distribution_continue_evaluation"

    summary_row = {
        "modes": len(rows),
        "total_execs_done": sum(int(row["execs_done"]) for row in rows),
        "total_valid_exec": sum(int(row["nv_total_valid_exec"]) for row in rows),
        "total_err_exec": total_err_exec,
        "max_nv_err_rate": f"{max(float(row['nv_err_rate']) for row in rows):.6f}",
        "saved_crashes_total": saved_crashes_total,
        "saved_hangs_total": saved_hangs_total,
        "rule_only_sent_to_target": int(by_mode["rule_only"]["sent_to_target"]),
        "rule_ae_sent_to_target": rule_ae_sent,
        "rule_fanogan_sent_to_target": rule_fanogan_sent,
        "rule_ae_fanogan_sent_to_target": rule_ae_fanogan_sent,
        "rule_only_filtered_by_rule": int(by_mode["rule_only"]["filtered_by_rule"]),
        "rule_ae_filtered_by_ae": int(by_mode["rule_ae"]["filtered_by_ae"]),
        "rule_fanogan_filtered_by_fanogan": int(by_mode["rule_fanogan"]["filtered_by_fanogan"]),
        "rule_ae_fanogan_filtered_by_fanogan": int(by_mode["rule_ae_fanogan"]["filtered_by_fanogan"]),
        "ae_primary_recommendation": "keep_ae_v1_as_primary" if all_stable else "investigate_online_filter_errors",
        "fanogan_online_observation": fanogan_observation,
        "summary_source": SUMMARY_SOURCE,
        "execution_scope": EXECUTION_SCOPE,
        "metric_semantics": METRIC_SEMANTICS,
    }

    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerow(summary_row)

    report = {
        "summary_source": SUMMARY_SOURCE,
        "execution_scope": EXECUTION_SCOPE,
        "metric_semantics": METRIC_SEMANTICS,
        "base_dir": str(BASE_DIR),
        "modes": rows,
        "summary": summary_row,
        "boundary": [
            "SE-fAnoGAN-ES-style online filter four-mode ablation only",
            "not full SE-fAnoGAN-ES",
            "not full GAN/fAnoGAN",
            "mock target is not real Alfresco service",
            "not all scenarios are AFL++ mutation-chain covered",
            "AE v1 remains primary",
            "fAnoGAN candidate does not replace AE v1",
        ],
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[OK] Wrote {SUMMARY_CSV}")
    print(f"[OK] Wrote {DETAILS_CSV}")
    print(f"[OK] Wrote {REPORT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
