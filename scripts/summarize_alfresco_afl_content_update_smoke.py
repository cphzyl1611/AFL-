#!/usr/bin/env python3
"""Summarize representative AFL++ content_update mock smoke evidence."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = Path(os.environ.get("OUT_DIR", ROOT / "out" / "alfresco_afl_content_update_smoke_latest"))
SUMMARY_CSV = OUT_DIR / "summary.csv"
EVAL_REPORT_JSON = OUT_DIR / "eval_report.json"
MOCK_STATS = OUT_DIR / "mock_stats.jsonl"
SUMMARY_SOURCE = "afl_fuzz"
EXECUTION_SCOPE = "alfresco_content_update_mock_afl_mutation_chain_smoke"
METRIC_SEMANTICS = (
    "Representative AFL++ mutation-chain smoke over Alfresco content_update mock semantics; "
    "not all scenarios and not real Alfresco service."
)
HEADER = [
    "mode",
    "nv_total_valid_exec",
    "nv_err_exec",
    "nv_err_rate",
    "saved_hangs",
    "saved_crashes",
    "last_http_code",
    "last_latency_ms",
    "last_ncov_total",
    "body_rule_pass",
    "body_rule_reject",
    "body_score_pass",
    "body_score_reject",
    "body_score_rpc_ok",
    "body_score_rpc_fail",
    "summary_source",
    "execution_scope",
    "metric_semantics",
]


def find_fuzzer_stats(out_dir: Path) -> Path:
    candidates = sorted(out_dir.glob("**/fuzzer_stats"))
    if not candidates:
        raise FileNotFoundError(f"missing fuzzer_stats under {out_dir}")
    return candidates[0]


def parse_fuzzer_stats(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def read_mock_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.is_file():
        return records
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                item = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
    return records


def int_stat(stats: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(float(stats.get(key, default)))
    except ValueError:
        return default


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fuzzer_stats_path = find_fuzzer_stats(OUT_DIR)
    stats = parse_fuzzer_stats(fuzzer_stats_path)
    records = read_mock_records(MOCK_STATS)

    execs_done = int_stat(stats, "execs_done")
    saved_hangs = int_stat(stats, "saved_hangs")
    saved_crashes = int_stat(stats, "saved_crashes")
    run_time = int_stat(stats, "run_time")
    body_rule_pass = sum(1 for item in records if bool(item.get("valid")))
    body_rule_reject = sum(1 for item in records if not bool(item.get("valid")))
    nv_total_valid_exec = int_stat(stats, "nv_total_valid_exec", execs_done) or execs_done
    nv_err_exec = saved_crashes + saved_hangs
    nv_err_rate = (nv_err_exec / nv_total_valid_exec) if nv_total_valid_exec else 0.0
    last_latency_ms = int(records[-1].get("latency_ms", 0)) if records else 0

    row = [
        "afl_mock_smoke",
        nv_total_valid_exec,
        nv_err_exec,
        f"{nv_err_rate:.6f}",
        saved_hangs,
        saved_crashes,
        0,
        last_latency_ms,
        int_stat(stats, "edges_found"),
        body_rule_pass,
        body_rule_reject,
        0,
        0,
        0,
        0,
        SUMMARY_SOURCE,
        EXECUTION_SCOPE,
        METRIC_SEMANTICS,
    ]

    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerow(row)

    report = {
        "scenario": "alfresco_content_update_mock",
        "summary_source": SUMMARY_SOURCE,
        "execution_scope": EXECUTION_SCOPE,
        "metric_semantics": METRIC_SEMANTICS,
        "out_dir": str(OUT_DIR),
        "fuzzer_stats_path": str(fuzzer_stats_path),
        "mock_stats_path": str(MOCK_STATS),
        "summary_csv": str(SUMMARY_CSV),
        "fuzzer_stats": {
            "execs_done": execs_done,
            "execs_per_sec": stats.get("execs_per_sec", "0"),
            "paths_total": stats.get("paths_total", stats.get("corpus_count", "0")),
            "corpus_count": stats.get("corpus_count", stats.get("paths_total", "0")),
            "saved_crashes": saved_crashes,
            "saved_hangs": saved_hangs,
            "run_time": run_time,
            "edges_found": int_stat(stats, "edges_found"),
        },
        "mock_stats": {
            "records": len(records),
            "body_rule_pass": body_rule_pass,
            "body_rule_reject": body_rule_reject,
        },
        "boundary": [
            "representative AFL++ mutation-chain smoke only",
            "mock target is not real Alfresco service",
            "not all scenarios are AFL++ mutation-chain covered",
            "does not change AE v1 primary mechanism",
        ],
    }
    EVAL_REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[OK] Wrote {SUMMARY_CSV}")
    print(f"[OK] Wrote {EVAL_REPORT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
