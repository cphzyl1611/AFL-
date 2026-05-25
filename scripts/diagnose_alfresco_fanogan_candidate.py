#!/usr/bin/env python3
"""Diagnose Alfresco fAnoGAN candidate underperformance.

The script is offline and read-only with respect to model/evidence inputs. It
checks feature/meta consistency, recomputes decision metrics from details.csv,
and performs fAnoGAN threshold sensitivity analysis.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_stage.alfresco_feature_extractor import feature_names  # noqa: E402


DETAILS_CSV = ROOT / "out" / "alfresco_extended_candidate_eval" / "details.csv"
SUMMARY_CSV = ROOT / "out" / "alfresco_extended_candidate_eval" / "summary.csv"
AE_META = ROOT / "model_stage" / "models" / "alfresco_ae_v1_meta.json"
FANOGAN_META = ROOT / "model_stage" / "models" / "alfresco_fanogan_v1_candidate_meta.json"
MANIFEST = ROOT / "in" / "alfresco_extended_eval_dataset" / "manifest.json"

OUT_DIR = ROOT / "out" / "alfresco_fanogan_candidate_diagnosis"
DIAGNOSIS_SUMMARY = OUT_DIR / "diagnosis_summary.csv"
FALSE_REJECT_SAMPLES = OUT_DIR / "false_reject_samples.csv"
THRESHOLD_SENSITIVITY = OUT_DIR / "threshold_sensitivity.csv"
RECOMMENDATION_TXT = OUT_DIR / "recommendation.txt"

ALLOWED_SCENARIOS = {"metadata_update", "content_update", "multipart_upload"}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def bool_from_cell(value: str) -> bool:
    lowered = str(value).strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise ValueError(f"invalid bool cell: {value!r}")


def read_details() -> list[dict[str, Any]]:
    with DETAILS_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        rows: list[dict[str, Any]] = []
        for row in csv.DictReader(fh):
            rows.append(
                {
                    **row,
                    "expected_valid_bool": bool_from_cell(row["expected_valid"]),
                    "rule_pass_bool": bool_from_cell(row["rule_pass"]),
                    "ae_score_float": float(row["ae_score"]),
                    "fanogan_score_float": float(row["fanogan_score"]),
                    "ae_pass_bool": row["ae_decision"] == "pass",
                    "fanogan_pass_bool": row["fanogan_decision"] == "pass",
                    "rule_ae_pass_bool": row["rule_ae_decision"] == "pass",
                    "rule_fanogan_pass_bool": row["rule_fanogan_decision"] == "pass",
                }
            )
        return rows


def read_summary_row() -> dict[str, str] | None:
    if not SUMMARY_CSV.is_file():
        return None
    with SUMMARY_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return next(reader, None)


def metrics(rows: list[dict[str, Any]], key: str, threshold: float | None = None) -> dict[str, Any]:
    false_accept = 0
    false_reject = 0
    correct = 0
    pass_count = 0
    reject_count = 0

    for row in rows:
        if threshold is None:
            decision_pass = bool(row[key])
        else:
            decision_pass = bool(row["rule_pass_bool"] and row["fanogan_score_float"] <= threshold)
        expected_valid = bool(row["expected_valid_bool"])
        if decision_pass:
            pass_count += 1
        else:
            reject_count += 1
        if decision_pass and not expected_valid:
            false_accept += 1
        elif not decision_pass and expected_valid:
            false_reject += 1
        else:
            correct += 1
    return {
        "pass": pass_count,
        "reject": reject_count,
        "false_accept": false_accept,
        "false_reject": false_reject,
        "accuracy": correct / len(rows) if rows else 0.0,
    }


def manifest_checks() -> tuple[bool, str]:
    data = load_json(MANIFEST)
    if not isinstance(data, list):
        return False, "manifest top-level value is not list"
    counts = {scenario: 0 for scenario in ALLOWED_SCENARIOS}
    binary_like = 0
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            return False, f"entry {index} is not object"
        scenario = item.get("scenario")
        if scenario not in ALLOWED_SCENARIOS:
            return False, f"entry {index} invalid scenario {scenario!r}"
        counts[str(scenario)] += 1
        if not isinstance(item.get("expected_valid"), bool):
            return False, f"entry {index} expected_valid is not bool"
        rel_file = item.get("file")
        if not isinstance(rel_file, str):
            return False, f"entry {index} file is not string"
        path = MANIFEST.parent / rel_file
        if not path.is_file():
            return False, f"entry {index} missing file {rel_file}"
        if path.suffix in {".bin", ".exe"}:
            binary_like += 1
    return True, f"entries={len(data)} metadata={counts['metadata_update']} content={counts['content_update']} multipart={counts['multipart_upload']} binary_like={binary_like}"


def feature_checks(ae_meta: dict[str, Any], fanogan_meta: dict[str, Any]) -> tuple[list[tuple[str, str, str]], bool]:
    extractor_names = feature_names()
    ae_names = list(ae_meta.get("feature_names", []))
    fanogan_names = list(fanogan_meta.get("feature_names", []))
    ae_dim = len(ae_names)
    fanogan_dim = int(fanogan_meta.get("feature_dim", len(fanogan_names)))
    dim_match = ae_dim == fanogan_dim == len(fanogan_names) == len(extractor_names)
    names_match = ae_names == fanogan_names == extractor_names
    rows = [
        (
            "feature_dim_match",
            "PASS" if dim_match else "FAIL",
            f"extractor_dim={len(extractor_names)} ae_dim={ae_dim} fanogan_dim={fanogan_dim} fanogan_names={len(fanogan_names)}",
        ),
        (
            "feature_names_match",
            "PASS" if names_match else "FAIL",
            "AE, fAnoGAN candidate, and extractor feature_names are identical" if names_match else "feature_names mismatch",
        ),
    ]
    return rows, bool(dim_match and names_match)


def mapping_and_decision_checks(rows: list[dict[str, Any]]) -> tuple[list[tuple[str, str, str]], bool]:
    scenario_ok = all(row["scenario"] in ALLOWED_SCENARIOS for row in rows)
    rule_fanogan_ok = all(
        row["rule_fanogan_pass_bool"] == bool(row["rule_pass_bool"] and row["fanogan_pass_bool"])
        for row in rows
    )
    rule_ae_ok = all(
        row["rule_ae_pass_bool"] == bool(row["rule_pass_bool"] and row["ae_pass_bool"])
        for row in rows
    )
    expected_valid_ok = all(str(row["expected_valid"]).strip().lower() in {"true", "false"} for row in rows)
    detail = f"rows={len(rows)} scenarios={sorted({row['scenario'] for row in rows})}"
    checks = [
        ("scenario_mapping_ok", "PASS" if scenario_ok else "FAIL", detail),
        ("rule_fanogan_definition_ok", "PASS" if rule_fanogan_ok else "FAIL", "rule_fanogan_pass == rule_pass and fanogan_pass"),
        ("rule_ae_definition_ok", "PASS" if rule_ae_ok else "FAIL", "rule_ae_pass == rule_pass and ae_pass"),
        ("expected_valid_bool_ok", "PASS" if expected_valid_ok else "FAIL", "details expected_valid cells are true/false"),
    ]
    return checks, bool(scenario_ok and rule_fanogan_ok and rule_ae_ok and expected_valid_ok)


def metrics_check(rows: list[dict[str, Any]]) -> tuple[tuple[str, str, str], dict[str, dict[str, Any]], bool]:
    recomputed = {
        "rule_only": metrics(rows, "rule_pass_bool"),
        "ae_only": metrics(rows, "ae_pass_bool"),
        "rule_ae": metrics(rows, "rule_ae_pass_bool"),
        "fanogan_only": metrics(rows, "fanogan_pass_bool"),
        "rule_fanogan": metrics(rows, "rule_fanogan_pass_bool"),
    }
    summary = read_summary_row()
    if not summary:
        return ("metrics_recomputed_ok", "WARN", "summary.csv missing; metrics recomputed from details only"), recomputed, True

    expected = {
        "rule_only_false_accept": recomputed["rule_only"]["false_accept"],
        "rule_only_false_reject": recomputed["rule_only"]["false_reject"],
        "ae_only_false_accept": recomputed["ae_only"]["false_accept"],
        "ae_only_false_reject": recomputed["ae_only"]["false_reject"],
        "rule_ae_false_accept": recomputed["rule_ae"]["false_accept"],
        "rule_ae_false_reject": recomputed["rule_ae"]["false_reject"],
        "fanogan_only_false_accept": recomputed["fanogan_only"]["false_accept"],
        "fanogan_only_false_reject": recomputed["fanogan_only"]["false_reject"],
        "rule_fanogan_false_accept": recomputed["rule_fanogan"]["false_accept"],
        "rule_fanogan_false_reject": recomputed["rule_fanogan"]["false_reject"],
    }
    mismatches = [
        f"{key}: summary={summary.get(key)} recomputed={value}"
        for key, value in expected.items()
        if int(summary.get(key, -1)) != int(value)
    ]
    if mismatches:
        return ("metrics_recomputed_ok", "FAIL", "; ".join(mismatches[:8])), recomputed, False
    return ("metrics_recomputed_ok", "PASS", "details recomputation matches summary.csv false_accept/false_reject fields"), recomputed, True


def false_reject_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        if not row["expected_valid_bool"]:
            continue
        if row["rule_ae_pass_bool"] and row["rule_fanogan_pass_bool"]:
            continue
        if not row["rule_ae_pass_bool"] and not row["rule_fanogan_pass_bool"]:
            difference_type = "both_reject"
        elif row["rule_ae_pass_bool"] and not row["rule_fanogan_pass_bool"]:
            difference_type = "fanogan_only_reject"
        else:
            difference_type = "ae_only_reject"
        result.append({**row, "difference_type": difference_type})
    return result


def threshold_rows(rows: list[dict[str, Any]], threshold_high: float, rule_ae_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    multipliers = [1.0, 1.1, 1.25, 1.5, 2.0, 3.0]
    result = []
    for multiplier in multipliers:
        threshold = threshold_high * multiplier
        item = metrics(rows, "rule_fanogan_pass_bool", threshold=threshold)
        if item["false_accept"] > 0:
            notes = "introduces_false_accept"
        elif item["false_reject"] <= rule_ae_metrics["false_reject"]:
            notes = "matches_or_beats_rule_ae_without_false_accept"
        else:
            notes = "still_more_false_reject_than_rule_ae"
        result.append(
            {
                "threshold": threshold,
                "multiplier": multiplier,
                "false_accept": item["false_accept"],
                "false_reject": item["false_reject"],
                "accuracy": item["accuracy"],
                "notes": notes,
            }
        )
    return result


def diagnosis_recommendation(
    implementation_ok: bool,
    sensitivity: list[dict[str, Any]],
    rule_ae_metrics: dict[str, Any],
) -> tuple[str, str]:
    if not implementation_ok:
        return (
            "possible_implementation_issue_found",
            "Feature/meta/decision/metrics checks found an inconsistency; inspect diagnosis_summary.csv.",
        )

    no_false_accept_matches = [
        row
        for row in sensitivity
        if row["false_accept"] == 0 and row["false_reject"] <= rule_ae_metrics["false_reject"]
    ]
    if no_false_accept_matches:
        best = no_false_accept_matches[0]
        return (
            "fanogan_candidate_underperforms_due_to_threshold_strictness",
            (
                "No code inconsistency found. Raising candidate threshold can match or beat rule_ae "
                f"without false_accept; first such multiplier={best['multiplier']:.2f}, threshold={best['threshold']:.6f}."
            ),
        )

    overlap_matches = [
        row
        for row in sensitivity
        if row["false_reject"] <= rule_ae_metrics["false_reject"] and row["false_accept"] > 0
    ]
    if overlap_matches:
        return (
            "fanogan_candidate_underperforms_due_to_score_distribution_overlap",
            "Matching rule_ae false_reject requires accepting invalid samples, indicating score distribution overlap.",
        )

    return (
        "no_code_bug_found_keep_ae_v1_primary",
        "No implementation issue found, and threshold sweep does not improve over AE v1 under tested candidates.",
    )


def write_diagnosis_summary(rows: list[tuple[str, str, str]]) -> None:
    with DIAGNOSIS_SUMMARY.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["check_item", "status", "detail"])
        writer.writerows(rows)


def write_false_reject_samples(rows: list[dict[str, Any]]) -> None:
    with FALSE_REJECT_SAMPLES.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(
            [
                "scenario",
                "file",
                "sample_type",
                "expected_valid",
                "rule_pass",
                "ae_score",
                "fanogan_score",
                "ae_decision",
                "fanogan_decision",
                "rule_ae_decision",
                "rule_fanogan_decision",
                "difference_type",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["scenario"],
                    row["file"],
                    row["sample_type"],
                    row["expected_valid"],
                    row["rule_pass"],
                    f"{row['ae_score_float']:.6f}",
                    f"{row['fanogan_score_float']:.6f}",
                    row["ae_decision"],
                    row["fanogan_decision"],
                    row["rule_ae_decision"],
                    row["rule_fanogan_decision"],
                    row["difference_type"],
                ]
            )


def write_threshold_sensitivity(rows: list[dict[str, Any]]) -> None:
    with THRESHOLD_SENSITIVITY.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["threshold", "false_accept", "false_reject", "accuracy", "notes"])
        for row in rows:
            writer.writerow(
                [
                    f"{row['threshold']:.6f}",
                    row["false_accept"],
                    row["false_reject"],
                    f"{row['accuracy']:.6f}",
                    row["notes"],
                ]
            )


def write_recommendation(recommendation: str, reason: str) -> None:
    RECOMMENDATION_TXT.write_text(
        (
            f"recommendation: {recommendation}\n"
            f"action: keep_ae_v1_as_primary\n"
            f"reason: {reason}\n"
            "boundary: diagnostic threshold sensitivity only; not full SE-fAnoGAN-ES; no model promotion\n"
        ),
        encoding="utf-8",
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ae_meta = load_json(AE_META)
    fanogan_meta = load_json(FANOGAN_META)
    rows = read_details()

    summary_rows: list[tuple[str, str, str]] = []
    feature_summary, feature_ok = feature_checks(ae_meta, fanogan_meta)
    summary_rows.extend(feature_summary)

    manifest_ok, manifest_detail = manifest_checks()
    summary_rows.append(("manifest_path_binary_ok", "PASS" if manifest_ok else "FAIL", manifest_detail))

    mapping_summary, mapping_ok = mapping_and_decision_checks(rows)
    summary_rows.extend(mapping_summary)

    metrics_summary, recomputed, metrics_ok = metrics_check(rows)
    summary_rows.append(metrics_summary)

    false_rejects = false_reject_rows(rows)
    fanogan_only = [row for row in false_rejects if row["difference_type"] == "fanogan_only_reject"]
    summary_rows.append(
        (
            "false_reject_samples_count",
            "INFO",
            f"unique={len(false_rejects)} rule_ae={recomputed['rule_ae']['false_reject']} rule_fanogan={recomputed['rule_fanogan']['false_reject']}",
        )
    )
    summary_rows.append(
        (
            "fanogan_extra_false_reject_count",
            "INFO",
            f"fanogan_only_reject={len(fanogan_only)}",
        )
    )

    threshold_high = float(fanogan_meta["threshold_high"])
    sensitivity = threshold_rows(rows, threshold_high, recomputed["rule_ae"])
    implementation_ok = feature_ok and manifest_ok and mapping_ok and metrics_ok
    recommendation, reason = diagnosis_recommendation(implementation_ok, sensitivity, recomputed["rule_ae"])
    summary_rows.append(("suspected_issue_type", "INFO", recommendation))

    write_diagnosis_summary(summary_rows)
    write_false_reject_samples(false_rejects)
    write_threshold_sensitivity(sensitivity)
    write_recommendation(recommendation, reason)

    print(f"[OK] Wrote {DIAGNOSIS_SUMMARY}")
    print(f"[OK] Wrote {FALSE_REJECT_SAMPLES}")
    print(f"[OK] Wrote {THRESHOLD_SENSITIVITY}")
    print(f"[OK] Wrote {RECOMMENDATION_TXT}")
    print(f"recommendation: {recommendation}")
    print(f"reason: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
