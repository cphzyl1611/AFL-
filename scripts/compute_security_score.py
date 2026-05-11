#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_OUT_JSON = "docs/review/evidence/security_score_summary.json"
DEFAULT_OUT_CSV = "docs/review/evidence/security_score_summary.csv"

WEIGHTS = {
    "error_score": 0.35,
    "validity_score": 0.20,
    "score_rpc_health": 0.15,
    "coverage_proxy_score": 0.15,
    "stability_score": 0.15,
}

CSV_FIELDS = [
    "source_summary",
    "mode",
    "nv_total_valid_exec",
    "nv_err_exec",
    "nv_err_rate",
    "body_rule_pass",
    "body_rule_reject",
    "body_score_rpc_ok",
    "body_score_rpc_fail",
    "saved_hangs",
    "saved_crashes",
    "last_http_code",
    "last_ncov_total",
    "error_score",
    "validity_score",
    "score_rpc_health",
    "coverage_proxy_score",
    "stability_score",
    "final_score_0_100",
    "unavailable_metrics",
    "metric_semantics",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute an engineering 0-100 security score from summary.csv files."
    )
    parser.add_argument(
        "--summary",
        action="append",
        default=[],
        help="Path to a summary.csv file. Can be repeated.",
    )
    parser.add_argument("--out-json", default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-csv", default=DEFAULT_OUT_CSV)
    return parser.parse_args()


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value: Any) -> Optional[int]:
    number = to_float(value)
    if number is None:
        return None
    return int(number)


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def rounded(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 6)


def compute_final(scores: Dict[str, Optional[float]]) -> Optional[float]:
    weighted_sum = 0.0
    used_weight = 0.0
    for name, weight in WEIGHTS.items():
        value = scores.get(name)
        if value is None:
            continue
        weighted_sum += value * weight
        used_weight += weight
    if used_weight <= 0:
        return None
    return weighted_sum / used_weight


def build_record(source: Path, row: Dict[str, str]) -> Dict[str, Any]:
    nv_total_valid_exec = to_int(row.get("nv_total_valid_exec"))
    nv_err_exec = to_int(row.get("nv_err_exec"))
    nv_err_rate = to_float(row.get("nv_err_rate"))
    if nv_err_rate is None and nv_total_valid_exec and nv_err_exec is not None:
        nv_err_rate = nv_err_exec / nv_total_valid_exec

    body_rule_pass = to_int(row.get("body_rule_pass"))
    body_rule_reject = to_int(row.get("body_rule_reject"))
    body_score_rpc_ok = to_int(row.get("body_score_rpc_ok"))
    body_score_rpc_fail = to_int(row.get("body_score_rpc_fail"))
    saved_hangs = to_int(row.get("saved_hangs"))
    saved_crashes = to_int(row.get("saved_crashes"))
    last_http_code = to_int(row.get("last_http_code"))
    last_ncov_total = to_int(row.get("last_ncov_total"))

    unavailable: List[str] = []

    error_score = None
    if nv_err_rate is None:
        unavailable.append("error_score")
    else:
        error_score = 100.0 * (1.0 - clamp(nv_err_rate, 0.0, 1.0))

    validity_score = None
    if body_rule_pass is None or body_rule_reject is None:
        unavailable.append("validity_score")
    else:
        rule_total = body_rule_pass + body_rule_reject
        if rule_total > 0:
            validity_score = 100.0 * body_rule_pass / rule_total
        else:
            unavailable.append("validity_score")

    score_rpc_health = None
    if body_score_rpc_ok is None or body_score_rpc_fail is None:
        unavailable.append("score_rpc_health")
    else:
        rpc_total = body_score_rpc_ok + body_score_rpc_fail
        if rpc_total > 0:
            score_rpc_health = 100.0 * body_score_rpc_ok / rpc_total
        else:
            unavailable.append("score_rpc_health")

    coverage_proxy_score = None
    if last_ncov_total is None or last_ncov_total <= 0:
        unavailable.append("coverage_proxy_score")
    else:
        coverage_proxy_score = min(last_ncov_total / 100.0, 1.0) * 100.0

    stability_score = None
    if saved_hangs is None or saved_crashes is None:
        unavailable.append("stability_score")
    else:
        stability_score = max(0.0, 100.0 - 20.0 * saved_hangs - 30.0 * saved_crashes)

    score_map = {
        "error_score": error_score,
        "validity_score": validity_score,
        "score_rpc_health": score_rpc_health,
        "coverage_proxy_score": coverage_proxy_score,
        "stability_score": stability_score,
    }

    final_score = compute_final(score_map)
    if final_score is None:
        unavailable.append("final_score_0_100")

    return {
        "source_summary": str(source),
        "mode": row.get("mode", ""),
        "nv_total_valid_exec": nv_total_valid_exec,
        "nv_err_exec": nv_err_exec,
        "nv_err_rate": rounded(nv_err_rate),
        "body_rule_pass": body_rule_pass,
        "body_rule_reject": body_rule_reject,
        "body_score_rpc_ok": body_score_rpc_ok,
        "body_score_rpc_fail": body_score_rpc_fail,
        "saved_hangs": saved_hangs,
        "saved_crashes": saved_crashes,
        "last_http_code": last_http_code,
        "last_ncov_total": last_ncov_total,
        "error_score": rounded(error_score),
        "validity_score": rounded(validity_score),
        "score_rpc_health": rounded(score_rpc_health),
        "coverage_proxy_score": rounded(coverage_proxy_score),
        "stability_score": rounded(stability_score),
        "final_score_0_100": rounded(final_score),
        "unavailable_metrics": sorted(set(unavailable)),
        "metric_semantics": (
            "Engineering security score v1 from existing summary.csv fields. "
            "coverage_proxy_score is a coverage proxy, not full code coverage. "
            f"source_metric_semantics={row.get('metric_semantics', '')}"
        ),
    }


def read_summary(path_text: str, warnings: List[str]) -> List[Dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        warnings.append(f"unavailable summary: {path}")
        return []

    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [build_record(path, row) for row in reader]
    except Exception as exc:
        warnings.append(f"failed to read summary {path}: {exc}")
        return []


def write_outputs(records: List[Dict[str, Any]], warnings: List[str], out_json: Path, out_csv: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": "engineering_security_score_v1",
        "description": (
            "Engineering 0-100 scoring prototype for stage acceptance and "
            "cross-run comparison. It is not a final authoritative security level."
        ),
        "weights": WEIGHTS,
        "records": records,
        "warnings": warnings,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for rec in records:
            row = dict(rec)
            row["unavailable_metrics"] = ";".join(row.get("unavailable_metrics", []))
            writer.writerow(row)


def main() -> int:
    args = parse_args()
    warnings: List[str] = []
    records: List[Dict[str, Any]] = []

    if not args.summary:
        warnings.append("no summary input provided")

    for summary in args.summary:
        records.extend(read_summary(summary, warnings))

    write_outputs(records, warnings, Path(args.out_json), Path(args.out_csv))
    print(f"[OK] records={len(records)} json={args.out_json} csv={args.out_csv}")
    for warning in warnings:
        print(f"[WARN] {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
