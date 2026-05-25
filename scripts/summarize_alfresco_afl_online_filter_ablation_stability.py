#!/usr/bin/env python3
"""Summarize short stability runs for four AFL++ online filter modes."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = Path(os.environ.get("STABILITY_OUT_DIR", ROOT / "out" / "alfresco_afl_online_filter_ablation_stability"))
SUMMARY_CSV = BASE_DIR / "stability_summary.csv"
DETAILS_CSV = BASE_DIR / "stability_details.csv"
REPORT_JSON = BASE_DIR / "stability_report.json"
MODES = ["rule_only", "rule_ae", "rule_fanogan", "rule_ae_fanogan"]
SUMMARY_SOURCE = "afl_fuzz_online_filter_ablation_stability"
EXECUTION_SCOPE = "alfresco_content_update_mock_afl_online_filter_four_mode_short_stability"
METRIC_SEMANTICS = (
    "Short stability experiment over four SE-fAnoGAN-ES-style online filter modes in "
    "representative AFL++ mutation-chain; mock target only, not full SE-fAnoGAN-ES "
    "and not real Alfresco service."
)

DETAIL_HEADER = [
    "mode",
    "run_id",
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
    "runs_per_mode",
    "total_runs",
    "total_execs_done",
    "total_valid_exec",
    "total_err_exec",
    "max_nv_err_rate",
    "saved_crashes_total",
    "saved_hangs_total",
    "scoring_error_total",
    "rule_only_stability_score",
    "rule_ae_stability_score",
    "rule_fanogan_stability_score",
    "rule_ae_fanogan_stability_score",
    "overall_stability_score",
    "ae_primary_recommendation",
    "fanogan_online_stability_observation",
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


def collect_run(mode: str, run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.csv"
    stats_path = run_dir / "fuzzer_stats"
    report_path = run_dir / "eval_report.json"
    summary = read_summary(summary_path)
    stats = parse_key_value_file(stats_path)
    report: dict[str, Any] = {}
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "mode": mode,
        "run_id": run_dir.name,
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
        "summary_path": str(summary_path),
        "fuzzer_stats_path": str(stats_path),
        "eval_report_path": str(report_path),
        "report": report,
    }


def collect_runs() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mode in MODES:
        mode_dir = BASE_DIR / mode
        for run_dir in sorted(mode_dir.glob("run_[0-9][0-9]")):
            if not (run_dir / "summary.csv").is_file() or not (run_dir / "fuzzer_stats").is_file():
                continue
            rows.append(collect_run(mode, run_dir))
    return rows


def stability_score(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    errors = sum(
        int(row["saved_crashes"])
        + int(row["saved_hangs"])
        + int(row["nv_err_exec"])
        + int(row["body_score_rpc_fail"])
        for row in rows
    )
    total_valid = sum(max(1, int(row["nv_total_valid_exec"])) for row in rows)
    if errors == 0:
        return 1.0
    return max(0.0, 1.0 - (errors / total_valid))


def main() -> int:
    rows = collect_runs()
    if not rows:
        raise FileNotFoundError(f"no mode/run_XX summary/fuzzer_stats pairs found under {BASE_DIR}")

    runs_by_mode = {mode: [row for row in rows if row["mode"] == mode] for mode in MODES}
    missing_modes = [mode for mode, mode_rows in runs_by_mode.items() if not mode_rows]
    if missing_modes:
        raise FileNotFoundError(f"missing stability runs for modes: {', '.join(missing_modes)}")

    BASE_DIR.mkdir(parents=True, exist_ok=True)
    with DETAILS_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=DETAIL_HEADER, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            output_row = dict(row)
            output_row["nv_err_rate"] = f"{float(row['nv_err_rate']):.6f}"
            writer.writerow({key: output_row[key] for key in DETAIL_HEADER})

    total_err_exec = sum(int(row["nv_err_exec"]) for row in rows)
    saved_crashes_total = sum(int(row["saved_crashes"]) for row in rows)
    saved_hangs_total = sum(int(row["saved_hangs"]) for row in rows)
    scoring_error_total = sum(int(row["body_score_rpc_fail"]) for row in rows)
    mode_scores = {mode: stability_score(mode_rows) for mode, mode_rows in runs_by_mode.items()}
    overall_stability_score = min(mode_scores.values()) if mode_scores else 0.0
    fanogan_rows = runs_by_mode["rule_fanogan"] + runs_by_mode["rule_ae_fanogan"]
    fanogan_errors = sum(int(row["body_score_rpc_fail"]) for row in fanogan_rows)
    fanogan_execs = sum(int(row["execs_done"]) for row in fanogan_rows)
    ae_execs = sum(int(row["execs_done"]) for row in runs_by_mode["rule_ae"])
    if fanogan_errors:
        fanogan_observation = "fanogan_online_path_has_scoring_errors_keep_ae_v1_primary"
    elif fanogan_execs < ae_execs:
        fanogan_observation = "fanogan_online_path_stable_without_scoring_error_but_short_sample_count_keep_ae_v1_primary"
    else:
        fanogan_observation = "fanogan_online_path_stable_without_scoring_error_continue_evaluation"

    runs_per_mode_values = {mode: len(mode_rows) for mode, mode_rows in runs_by_mode.items()}
    summary_row = {
        "modes": len(MODES),
        "runs_per_mode": min(runs_per_mode_values.values()),
        "total_runs": len(rows),
        "total_execs_done": sum(int(row["execs_done"]) for row in rows),
        "total_valid_exec": sum(int(row["nv_total_valid_exec"]) for row in rows),
        "total_err_exec": total_err_exec,
        "max_nv_err_rate": f"{max(float(row['nv_err_rate']) for row in rows):.6f}",
        "saved_crashes_total": saved_crashes_total,
        "saved_hangs_total": saved_hangs_total,
        "scoring_error_total": scoring_error_total,
        "rule_only_stability_score": f"{mode_scores['rule_only']:.6f}",
        "rule_ae_stability_score": f"{mode_scores['rule_ae']:.6f}",
        "rule_fanogan_stability_score": f"{mode_scores['rule_fanogan']:.6f}",
        "rule_ae_fanogan_stability_score": f"{mode_scores['rule_ae_fanogan']:.6f}",
        "overall_stability_score": f"{overall_stability_score:.6f}",
        "ae_primary_recommendation": "keep_ae_v1_as_primary"
        if overall_stability_score == 1.0
        else "investigate_online_filter_stability",
        "fanogan_online_stability_observation": fanogan_observation,
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
        "runs_by_mode": runs_by_mode,
        "summary": summary_row,
        "boundary": [
            "SE-fAnoGAN-ES-style online filter four-mode short stability only",
            "not full SE-fAnoGAN-ES",
            "not full GAN/fAnoGAN",
            "mock target is not real Alfresco service",
            "not all scenarios are AFL++ mutation-chain covered",
            "not long-duration stability testing",
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
