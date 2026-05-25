#!/usr/bin/env python3
"""Calibrate Alfresco torch fAnoGAN-style threshold and validate on holdout.

This script is offline. It does not retrain the model, contact Alfresco, or run
fuzzing. It reads the extended Alfresco sample manifest, scores samples with the
existing AE v1 and fAnoGAN candidate scorers, selects a candidate threshold on a
deterministic calibration split, and compares rule+AE with rule+fAnoGAN on a
separate holdout split.
"""

from __future__ import annotations

import csv
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_stage.alfresco_ae_v1_scorer import AlfrescoAEV1Scorer  # noqa: E402
from model_stage.alfresco_fanogan_v1_candidate_scorer import AlfrescoFanoganV1CandidateScorer  # noqa: E402
from scripts.run_alfresco_extended_candidate_eval import (  # noqa: E402
    ExtendedSample,
    ae_score_sample,
    fanogan_score_sample,
    load_manifest,
    load_sample,
    rule_result,
)


OUT_DIR = ROOT / "out" / "alfresco_fanogan_threshold_holdout_eval"
CALIBRATION_SUMMARY = OUT_DIR / "calibration_summary.csv"
HOLDOUT_SUMMARY = OUT_DIR / "holdout_summary.csv"
HOLDOUT_DETAILS = OUT_DIR / "holdout_details.csv"
RECOMMENDATION_TXT = OUT_DIR / "recommendation.txt"

SEED = 20260519
SUMMARY_SOURCE = "python_static_loop"
EXECUTION_SCOPE = "alfresco_fanogan_threshold_holdout_eval"
METRIC_SEMANTICS = (
    "Offline torch fAnoGAN-style threshold calibration and holdout validation; "
    "not full SE-fAnoGAN-ES and not full AFL++ mutation-chain execution."
)


def stratified_split(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[tuple[str, bool], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        groups[(str(entry.get("scenario", "")), bool(entry.get("expected_valid")))].append(entry)

    rng = random.Random(SEED)
    calibration: list[dict[str, Any]] = []
    holdout: list[dict[str, Any]] = []
    for key in sorted(groups):
        group = sorted(groups[key], key=lambda item: str(item.get("file", "")))
        rng.shuffle(group)
        if len(group) == 1:
            holdout.extend(group)
            continue
        split_index = max(1, len(group) // 2)
        if split_index >= len(group):
            split_index = len(group) - 1
        calibration.extend(group[:split_index])
        holdout.extend(group[split_index:])
    return (
        sorted(calibration, key=lambda item: (str(item.get("scenario", "")), str(item.get("file", "")))),
        sorted(holdout, key=lambda item: (str(item.get("scenario", "")), str(item.get("file", "")))),
    )


def ensure_split_coverage(calibration: list[dict[str, Any]], holdout: list[dict[str, Any]]) -> None:
    expected = {"metadata_update", "content_update", "multipart_upload"}
    calibration_scenarios = {str(item.get("scenario", "")) for item in calibration}
    holdout_scenarios = {str(item.get("scenario", "")) for item in holdout}
    if not expected.issubset(calibration_scenarios):
        raise RuntimeError(f"calibration split missing scenarios: {sorted(expected - calibration_scenarios)}")
    if not expected.issubset(holdout_scenarios):
        raise RuntimeError(f"holdout split missing scenarios: {sorted(expected - holdout_scenarios)}")


def score_entries(
    split_name: str,
    entries: list[dict[str, Any]],
    ae_scorer: AlfrescoAEV1Scorer,
    fanogan_scorer: AlfrescoFanoganV1CandidateScorer,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        sample = load_sample(entry)
        rows.append(score_sample(split_name, sample, ae_scorer, fanogan_scorer))
    return rows


def score_sample(
    split_name: str,
    sample: ExtendedSample,
    ae_scorer: AlfrescoAEV1Scorer,
    fanogan_scorer: AlfrescoFanoganV1CandidateScorer,
) -> dict[str, Any]:
    rule_pass, rule_reason = rule_result(sample)
    ae_result = ae_score_sample(ae_scorer, sample)
    fanogan_result = fanogan_score_sample(fanogan_scorer, sample)
    ae_pass = bool(ae_result["pass"])
    fanogan_pass = bool(fanogan_result["pass"])
    return {
        "split": split_name,
        "scenario": sample.scenario,
        "file": sample.rel_file,
        "sample_type": sample.sample_type,
        "expected_valid": bool(sample.expected_valid),
        "error_type": sample.error_type if sample.error_type else rule_reason,
        "rule_pass": bool(rule_pass),
        "ae_score": float(ae_result["score"]),
        "ae_pass": ae_pass,
        "fanogan_score": float(fanogan_result["score"]),
        "fanogan_default_pass": fanogan_pass,
        "rule_ae_pass": bool(rule_pass and ae_pass),
        "rule_fanogan_default_pass": bool(rule_pass and fanogan_pass),
    }


def metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    false_accept = 0
    false_reject = 0
    correct = 0
    for row in rows:
        decision_pass = bool(row[key])
        expected_valid = bool(row["expected_valid"])
        if decision_pass and not expected_valid:
            false_accept += 1
        elif not decision_pass and expected_valid:
            false_reject += 1
        else:
            correct += 1
    return {
        "false_accept": false_accept,
        "false_reject": false_reject,
        "accuracy": correct / len(rows) if rows else 0.0,
    }


def metrics_for_threshold(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    evaluated: list[dict[str, Any]] = []
    for row in rows:
        evaluated.append({**row, "rule_fanogan_calibrated_pass": bool(row["rule_pass"] and row["fanogan_score"] <= threshold)})
    return metrics(evaluated, "rule_fanogan_calibrated_pass")


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = rank - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def threshold_candidates(rows: list[dict[str, Any]], threshold_high: float) -> list[tuple[float, str]]:
    candidates: list[tuple[float, str]] = [
        (threshold_high, "current_threshold_high"),
        (threshold_high * 1.1, "threshold_high_x1.10"),
        (threshold_high * 1.25, "threshold_high_x1.25"),
        (threshold_high * 1.5, "threshold_high_x1.50"),
        (threshold_high * 2.0, "threshold_high_x2.00"),
        (threshold_high * 2.5, "threshold_high_x2.50"),
        (threshold_high * 3.0, "threshold_high_x3.00"),
    ]
    scores = [float(row["fanogan_score"]) for row in rows]
    for pct in (80.0, 85.0, 90.0, 95.0, 97.5):
        candidates.append((percentile(scores, pct), f"calibration_score_p{pct:g}"))

    unique: dict[str, str] = {}
    for value, label in candidates:
        rounded = f"{value:.6f}"
        unique.setdefault(rounded, label)
    return [(float(value), label) for value, label in sorted(unique.items(), key=lambda item: float(item[0]))]


def select_threshold(rows: list[dict[str, Any]], threshold_high: float) -> tuple[float, str, list[dict[str, Any]]]:
    evaluated: list[dict[str, Any]] = []
    for threshold, candidate_source in threshold_candidates(rows, threshold_high):
        item = metrics_for_threshold(rows, threshold)
        evaluated.append(
            {
                "threshold": threshold,
                "candidate_source": candidate_source,
                "false_accept": item["false_accept"],
                "false_reject": item["false_reject"],
                "accuracy": item["accuracy"],
            }
        )

    zero_false_accept = [row for row in evaluated if row["false_accept"] == 0]
    if zero_false_accept:
        selected = sorted(zero_false_accept, key=lambda row: (row["false_reject"], row["threshold"]))[0]
        reason = "selected lowest false_reject among false_accept=0 candidates; tie-breaker lower threshold"
    else:
        selected = sorted(evaluated, key=lambda row: (-row["accuracy"], row["false_accept"], row["false_reject"], row["threshold"]))[0]
        reason = "all candidates have false_accept>0; selected highest accuracy with lowest false_accept"
    return float(selected["threshold"]), reason, evaluated


def apply_calibrated_decision(rows: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        calibrated_pass = bool(row["fanogan_score"] <= threshold)
        result.append(
            {
                **row,
                "fanogan_calibrated_pass": calibrated_pass,
                "rule_fanogan_calibrated_pass": bool(row["rule_pass"] and calibrated_pass),
            }
        )
    return result


def recommendation_for(rule_ae: dict[str, Any], calibrated: dict[str, Any]) -> tuple[str, str]:
    improved_without_higher_risk = (
        calibrated["false_accept"] <= rule_ae["false_accept"]
        and calibrated["false_reject"] <= rule_ae["false_reject"]
        and (
            calibrated["false_accept"] < rule_ae["false_accept"]
            or calibrated["false_reject"] < rule_ae["false_reject"]
        )
    )
    if improved_without_higher_risk:
        return (
            "promote_fanogan_candidate_for_extended_evaluation",
            "calibrated fAnoGAN candidate improves holdout false_accept/false_reject without increasing the other error type",
        )
    return (
        "keep_ae_v1_as_primary",
        "calibrated fAnoGAN candidate does not clearly outperform AE v1 on the holdout split",
    )


def write_calibration_summary(rows: list[dict[str, Any]], selected_threshold: float, selection_reason: str) -> None:
    with CALIBRATION_SUMMARY.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["threshold", "false_accept", "false_reject", "accuracy", "selected", "reason"])
        for row in rows:
            selected = abs(float(row["threshold"]) - selected_threshold) < 1e-9
            writer.writerow(
                [
                    f"{row['threshold']:.6f}",
                    row["false_accept"],
                    row["false_reject"],
                    f"{row['accuracy']:.6f}",
                    str(selected).lower(),
                    selection_reason if selected else row["candidate_source"],
                ]
            )


def write_holdout_details(rows: list[dict[str, Any]]) -> None:
    with HOLDOUT_DETAILS.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(
            [
                "split",
                "scenario",
                "file",
                "sample_type",
                "expected_valid",
                "error_type",
                "rule_pass",
                "ae_score",
                "ae_decision",
                "fanogan_score",
                "fanogan_default_decision",
                "fanogan_calibrated_decision",
                "rule_ae_decision",
                "rule_fanogan_default_decision",
                "rule_fanogan_calibrated_decision",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["split"],
                    row["scenario"],
                    row["file"],
                    row["sample_type"],
                    str(row["expected_valid"]).lower(),
                    row["error_type"],
                    str(row["rule_pass"]).lower(),
                    f"{row['ae_score']:.6f}",
                    "pass" if row["ae_pass"] else "reject",
                    f"{row['fanogan_score']:.6f}",
                    "pass" if row["fanogan_default_pass"] else "reject",
                    "pass" if row["fanogan_calibrated_pass"] else "reject",
                    "pass" if row["rule_ae_pass"] else "reject",
                    "pass" if row["rule_fanogan_default_pass"] else "reject",
                    "pass" if row["rule_fanogan_calibrated_pass"] else "reject",
                ]
            )


def write_holdout_summary(
    rows: list[dict[str, Any]],
    threshold: float,
    recommendation: str,
    rule_ae: dict[str, Any],
    default: dict[str, Any],
    calibrated: dict[str, Any],
) -> None:
    with HOLDOUT_SUMMARY.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(
            [
                "total_samples",
                "expected_valid",
                "expected_invalid",
                "rule_ae_false_accept",
                "rule_ae_false_reject",
                "rule_ae_accuracy",
                "rule_fanogan_default_false_accept",
                "rule_fanogan_default_false_reject",
                "rule_fanogan_default_accuracy",
                "rule_fanogan_calibrated_false_accept",
                "rule_fanogan_calibrated_false_reject",
                "rule_fanogan_calibrated_accuracy",
                "chosen_threshold",
                "recommendation",
                "summary_source",
                "execution_scope",
                "metric_semantics",
            ]
        )
        writer.writerow(
            [
                len(rows),
                sum(1 for row in rows if row["expected_valid"]),
                sum(1 for row in rows if not row["expected_valid"]),
                rule_ae["false_accept"],
                rule_ae["false_reject"],
                f"{rule_ae['accuracy']:.6f}",
                default["false_accept"],
                default["false_reject"],
                f"{default['accuracy']:.6f}",
                calibrated["false_accept"],
                calibrated["false_reject"],
                f"{calibrated['accuracy']:.6f}",
                f"{threshold:.6f}",
                recommendation,
                SUMMARY_SOURCE,
                EXECUTION_SCOPE,
                METRIC_SEMANTICS,
            ]
        )


def write_recommendation(recommendation: str, reason: str, threshold: float) -> None:
    RECOMMENDATION_TXT.write_text(
        (
            f"recommendation: {recommendation}\n"
            f"chosen_threshold: {threshold:.6f}\n"
            f"reason: {reason}\n"
            "boundary: holdout validation only; not full SE-fAnoGAN-ES; no automatic replacement of AE v1\n"
        ),
        encoding="utf-8",
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = load_manifest()
    calibration_entries, holdout_entries = stratified_split(entries)
    ensure_split_coverage(calibration_entries, holdout_entries)

    ae_scorer = AlfrescoAEV1Scorer()
    fanogan_scorer = AlfrescoFanoganV1CandidateScorer()
    default_threshold = float(fanogan_scorer.threshold_high)

    calibration_rows = score_entries("calibration", calibration_entries, ae_scorer, fanogan_scorer)
    holdout_rows = score_entries("holdout", holdout_entries, ae_scorer, fanogan_scorer)

    chosen_threshold, selection_reason, calibration_threshold_rows = select_threshold(calibration_rows, default_threshold)
    calibrated_calibration_rows = apply_calibrated_decision(calibration_rows, chosen_threshold)
    calibrated_holdout_rows = apply_calibrated_decision(holdout_rows, chosen_threshold)

    calibration_metrics = metrics(calibrated_calibration_rows, "rule_fanogan_calibrated_pass")
    for row in calibration_threshold_rows:
        if abs(float(row["threshold"]) - chosen_threshold) < 1e-9:
            row["false_accept"] = calibration_metrics["false_accept"]
            row["false_reject"] = calibration_metrics["false_reject"]
            row["accuracy"] = calibration_metrics["accuracy"]
            break

    rule_ae = metrics(calibrated_holdout_rows, "rule_ae_pass")
    default = metrics(calibrated_holdout_rows, "rule_fanogan_default_pass")
    calibrated = metrics(calibrated_holdout_rows, "rule_fanogan_calibrated_pass")
    recommendation, reason = recommendation_for(rule_ae, calibrated)

    write_calibration_summary(calibration_threshold_rows, chosen_threshold, selection_reason)
    write_holdout_summary(calibrated_holdout_rows, chosen_threshold, recommendation, rule_ae, default, calibrated)
    write_holdout_details(calibrated_calibration_rows + calibrated_holdout_rows)
    write_recommendation(recommendation, reason, chosen_threshold)

    print(f"[OK] calibration_samples={len(calibration_rows)}")
    print(f"[OK] holdout_samples={len(holdout_rows)}")
    print(f"[OK] chosen_threshold={chosen_threshold:.6f}")
    print(f"[OK] recommendation={recommendation}")
    print(f"[OK] wrote {CALIBRATION_SUMMARY}")
    print(f"[OK] wrote {HOLDOUT_SUMMARY}")
    print(f"[OK] wrote {HOLDOUT_DETAILS}")
    print(f"[OK] wrote {RECOMMENDATION_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
