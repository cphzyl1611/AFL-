#!/usr/bin/env python3
"""Summarize AFL++ online filter smoke evidence."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = Path(os.environ.get("OUT_DIR", ROOT / "out" / "alfresco_afl_online_filter_smoke_latest"))
SUMMARY_CSV = OUT_DIR / "summary.csv"
EVAL_REPORT_JSON = OUT_DIR / "eval_report.json"
FILTER_STATS = OUT_DIR / "filter_stats.jsonl"
SUMMARY_SOURCE = "afl_fuzz_online_filter"
EXECUTION_SCOPE = "alfresco_content_update_mock_afl_online_filter_smoke"
METRIC_SEMANTICS = (
    "Representative AFL++ mutation-chain smoke with SE-fAnoGAN-ES-style online filter prototype; "
    "mock target only, not full SE-fAnoGAN-ES and not real Alfresco service."
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
    "online_filter_mode",
    "sent_to_target",
    "filtered_by_rule",
    "filtered_by_ae",
    "filtered_by_fanogan",
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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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
    records = read_jsonl(FILTER_STATS)

    execs_done = int_stat(stats, "execs_done")
    saved_hangs = int_stat(stats, "saved_hangs")
    saved_crashes = int_stat(stats, "saved_crashes")
    run_time = int_stat(stats, "run_time")
    nv_total_valid_exec = int_stat(stats, "nv_total_valid_exec", execs_done) or execs_done
    nv_err_exec = saved_crashes + saved_hangs
    nv_err_rate = (nv_err_exec / nv_total_valid_exec) if nv_total_valid_exec else 0.0
    body_rule_pass = sum(1 for item in records if bool(item.get("rule_pass")))
    body_rule_reject = sum(1 for item in records if not bool(item.get("rule_pass")))
    body_score_pass = sum(1 for item in records if item.get("final_decision") == "pass")
    body_score_reject = sum(1 for item in records if item.get("final_decision") == "reject")
    body_score_rpc_ok = sum(
        1
        for item in records
        if item.get("ae_decision") not in {"not_run", None}
        or item.get("fanogan_decision") not in {"not_run", None}
    )
    body_score_rpc_fail = sum(1 for item in records if str(item.get("reject_reason", "")).endswith("scoring_error"))
    sent_to_target = sum(1 for item in records if bool(item.get("sent_to_target")))
    filtered_by_rule = sum(1 for item in records if str(item.get("reject_reason", "")).startswith("rule_"))
    filtered_by_ae = sum(1 for item in records if str(item.get("reject_reason", "")).startswith("ae_"))
    filtered_by_fanogan = sum(1 for item in records if str(item.get("reject_reason", "")).startswith("fanogan_"))
    last_latency_ms = int(records[-1].get("latency_ms", 0)) if records else 0
    mode = str(records[-1].get("mode", os.environ.get("ONLINE_FILTER_MODE", "rule_ae"))) if records else os.environ.get("ONLINE_FILTER_MODE", "rule_ae")

    row = [
        "afl_online_filter_smoke",
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
        body_score_pass,
        body_score_reject,
        body_score_rpc_ok,
        body_score_rpc_fail,
        SUMMARY_SOURCE,
        EXECUTION_SCOPE,
        METRIC_SEMANTICS,
        mode,
        sent_to_target,
        filtered_by_rule,
        filtered_by_ae,
        filtered_by_fanogan,
    ]

    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerow(row)

    report = {
        "summary_source": SUMMARY_SOURCE,
        "execution_scope": EXECUTION_SCOPE,
        "metric_semantics": METRIC_SEMANTICS,
        "out_dir": str(OUT_DIR),
        "fuzzer_stats_path": str(fuzzer_stats_path),
        "filter_stats_path": str(FILTER_STATS),
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
        "online_filter": {
            "mode": mode,
            "records": len(records),
            "body_rule_pass": body_rule_pass,
            "body_rule_reject": body_rule_reject,
            "body_score_pass": body_score_pass,
            "body_score_reject": body_score_reject,
            "body_score_rpc_ok": body_score_rpc_ok,
            "body_score_rpc_fail": body_score_rpc_fail,
            "sent_to_target": sent_to_target,
            "filtered_by_rule": filtered_by_rule,
            "filtered_by_ae": filtered_by_ae,
            "filtered_by_fanogan": filtered_by_fanogan,
        },
        "boundary": [
            "SE-fAnoGAN-ES-style online filter prototype only",
            "not full SE-fAnoGAN-ES",
            "mock target is not real Alfresco service",
            "not all scenarios are AFL++ mutation-chain covered",
            "AE v1 remains primary",
        ],
    }
    EVAL_REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[OK] Wrote {SUMMARY_CSV}")
    print(f"[OK] Wrote {EVAL_REPORT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
