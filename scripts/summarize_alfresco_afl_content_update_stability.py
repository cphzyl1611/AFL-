#!/usr/bin/env python3
"""Summarize short stability runs for the Alfresco AFL++ mock smoke."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = Path(os.environ.get("STABILITY_OUT_DIR", ROOT / "out" / "alfresco_afl_content_update_stability"))
SUMMARY_CSV = BASE_DIR / "stability_summary.csv"
DETAILS_CSV = BASE_DIR / "stability_details.csv"
REPORT_JSON = BASE_DIR / "stability_report.json"
SUMMARY_SOURCE = "afl_fuzz_stability"
EXECUTION_SCOPE = "alfresco_content_update_mock_afl_mutation_chain_short_stability"
METRIC_SEMANTICS = (
    "Short stability experiment over representative AFL++ mutation-chain smoke; "
    "mock target only, not all scenarios and not real Alfresco service."
)

DETAIL_HEADER = [
    "run_id",
    "run_time",
    "execs_done",
    "execs_per_sec",
    "nv_total_valid_exec",
    "nv_err_exec",
    "nv_err_rate",
    "saved_crashes",
    "saved_hangs",
    "body_rule_pass",
    "body_rule_reject",
    "summary_source",
    "execution_scope",
]

SUMMARY_HEADER = [
    "runs",
    "total_execs_done",
    "total_valid_exec",
    "total_err_exec",
    "mean_nv_err_rate",
    "max_nv_err_rate",
    "min_execs_done",
    "max_execs_done",
    "median_execs_done",
    "iqr_execs_done",
    "saved_crashes_total",
    "saved_hangs_total",
    "stability_score",
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


def read_summary_row(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        row = next(reader, None)
    if row is None:
        raise ValueError(f"empty summary: {path}")
    return dict(row)


def percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = pos - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def collect_runs(base_dir: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for run_dir in sorted(base_dir.glob("run_[0-9][0-9]")):
        summary_path = run_dir / "summary.csv"
        stats_path = run_dir / "fuzzer_stats"
        if not summary_path.is_file() or not stats_path.is_file():
            continue
        summary = read_summary_row(summary_path)
        stats = parse_key_value_file(stats_path)
        runs.append(
            {
                "run_id": run_dir.name,
                "run_time": int_value(stats.get("run_time")),
                "execs_done": int_value(stats.get("execs_done")),
                "execs_per_sec": stats.get("execs_per_sec", "0"),
                "nv_total_valid_exec": int_value(summary.get("nv_total_valid_exec")),
                "nv_err_exec": int_value(summary.get("nv_err_exec")),
                "nv_err_rate": float_value(summary.get("nv_err_rate")),
                "saved_crashes": int_value(summary.get("saved_crashes")),
                "saved_hangs": int_value(summary.get("saved_hangs")),
                "body_rule_pass": int_value(summary.get("body_rule_pass")),
                "body_rule_reject": int_value(summary.get("body_rule_reject")),
                "summary_source": summary.get("summary_source", ""),
                "execution_scope": summary.get("execution_scope", ""),
                "summary_path": str(summary_path),
                "fuzzer_stats_path": str(stats_path),
            }
        )
    return runs


def main() -> int:
    runs = collect_runs(BASE_DIR)
    if not runs:
        raise FileNotFoundError(f"no run_XX summary/fuzzer_stats pairs found under {BASE_DIR}")

    BASE_DIR.mkdir(parents=True, exist_ok=True)
    with DETAILS_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=DETAIL_HEADER, lineterminator="\n")
        writer.writeheader()
        for item in runs:
            writer.writerow({key: item[key] for key in DETAIL_HEADER})

    execs_done_values = [int(item["execs_done"]) for item in runs]
    nv_err_rates = [float(item["nv_err_rate"]) for item in runs]
    q1 = percentile(execs_done_values, 0.25)
    q3 = percentile(execs_done_values, 0.75)
    iqr_execs_done = q3 - q1
    total_valid_exec = sum(int(item["nv_total_valid_exec"]) for item in runs)
    total_err_exec = sum(int(item["nv_err_exec"]) for item in runs)
    saved_crashes_total = sum(int(item["saved_crashes"]) for item in runs)
    saved_hangs_total = sum(int(item["saved_hangs"]) for item in runs)
    mean_nv_err_rate = sum(nv_err_rates) / len(nv_err_rates)
    max_nv_err_rate = max(nv_err_rates)
    if all(rate == 0.0 for rate in nv_err_rates):
        stability_score = 1.0
    else:
        q1_err = percentile([int(rate * 1_000_000) for rate in nv_err_rates], 0.25) / 1_000_000
        q3_err = percentile([int(rate * 1_000_000) for rate in nv_err_rates], 0.75) / 1_000_000
        stability_score = max(0.0, 1.0 - (q3_err - q1_err))

    summary_row = {
        "runs": len(runs),
        "total_execs_done": sum(execs_done_values),
        "total_valid_exec": total_valid_exec,
        "total_err_exec": total_err_exec,
        "mean_nv_err_rate": f"{mean_nv_err_rate:.6f}",
        "max_nv_err_rate": f"{max_nv_err_rate:.6f}",
        "min_execs_done": min(execs_done_values),
        "max_execs_done": max(execs_done_values),
        "median_execs_done": f"{median(execs_done_values):.0f}",
        "iqr_execs_done": f"{iqr_execs_done:.0f}",
        "saved_crashes_total": saved_crashes_total,
        "saved_hangs_total": saved_hangs_total,
        "stability_score": f"{stability_score:.6f}",
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
        "runs": runs,
        "summary": summary_row,
        "boundary": [
            "representative AFL++ mutation-chain short stability only",
            "not long-duration stability testing",
            "mock target is not real Alfresco service",
            "not all scenarios are AFL++ mutation-chain covered",
            "does not change AE v1 primary mechanism",
        ],
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[OK] Wrote {SUMMARY_CSV}")
    print(f"[OK] Wrote {DETAILS_CSV}")
    print(f"[OK] Wrote {REPORT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
