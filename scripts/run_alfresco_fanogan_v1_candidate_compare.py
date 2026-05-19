#!/usr/bin/env python3
"""Compare Alfresco fAnoGAN v1 candidate scoring with AE v1.

This is an offline min-calibration comparison. It reuses the AE v1 feature
extractor and synthetic invalid sample set, does not contact Alfresco, and does
not run AFL++ fuzzing.
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

from model_stage.alfresco_ae_v1_scorer import AlfrescoAEV1Scorer  # noqa: E402
from model_stage.alfresco_fanogan_v1_candidate_scorer import AlfrescoFanoganV1CandidateScorer  # noqa: E402
from scripts.run_alfresco_ae_v1_threshold_sweep import (  # noqa: E402
    CONTENT_BAD_MARKER,
    all_samples,
    validate_metadata_rule,
    validate_text_rule,
    validate_upload_rule,
)


OUT_DIR = ROOT / "out" / "alfresco_fanogan_v1_candidate_compare"
SUMMARY_CSV = OUT_DIR / "summary.csv"
DETAILS_CSV = OUT_DIR / "details.csv"
COMPARE_CSV = OUT_DIR / "compare_with_ae.csv"
RECOMMENDATION_TXT = OUT_DIR / "recommendation.txt"

SUMMARY_SOURCE = "python_static_loop"
EXECUTION_SCOPE = "alfresco_fanogan_v1_candidate_min_calibration"
METRIC_SEMANTICS = (
    "Python static-loop Alfresco fAnoGAN v1 candidate validity scoring; "
    "not a full SE-fAnoGAN-ES and not a full AFL++ mutation-chain execution."
)


def rule_result(sample: Any) -> tuple[bool, str]:
    if sample.scenario == "metadata_update":
        return validate_metadata_rule(sample.payload)
    if sample.scenario == "content_update":
        return validate_text_rule(sample.content, CONTENT_BAD_MARKER)
    if sample.scenario == "multipart_upload":
        content_or_none = None if sample.error_type == "filedata_missing" else sample.content
        return validate_upload_rule(sample.filename, content_or_none, sample.fields)
    raise ValueError(f"unsupported scenario: {sample.scenario}")


def ae_score_sample(scorer: AlfrescoAEV1Scorer, sample: Any) -> dict[str, Any]:
    if sample.scenario == "metadata_update":
        return scorer.score_metadata_payload(sample.payload if isinstance(sample.payload, dict) else {})
    if sample.scenario == "content_update":
        return scorer.score_text_content(sample.content)
    if sample.scenario == "multipart_upload":
        return scorer.score_multipart_upload(sample.filename, sample.content, sample.fields)
    raise ValueError(f"unsupported scenario: {sample.scenario}")


def fanogan_score_sample(scorer: AlfrescoFanoganV1CandidateScorer, sample: Any) -> dict[str, Any]:
    if sample.scenario == "metadata_update":
        return scorer.score_metadata_payload(sample.payload if isinstance(sample.payload, dict) else {})
    if sample.scenario == "content_update":
        return scorer.score_text_content(sample.content)
    if sample.scenario == "multipart_upload":
        return scorer.score_multipart_upload(sample.filename, sample.content, sample.fields)
    raise ValueError(f"unsupported scenario: {sample.scenario}")


def metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    false_accept = 0
    false_reject = 0
    correct = 0
    pass_count = 0
    reject_count = 0
    for row in rows:
        decision_pass = bool(row[key])
        expected_valid = bool(row["expected_valid"])
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
    accuracy = correct / len(rows) if rows else 0.0
    return {
        "pass": pass_count,
        "reject": reject_count,
        "false_accept": false_accept,
        "false_reject": false_reject,
        "accuracy": accuracy,
    }


def write_summary(rows: list[dict[str, Any]], model_type: str) -> None:
    rule = metrics(rows, "rule_pass")
    ae = metrics(rows, "ae_pass")
    fanogan = metrics(rows, "fanogan_pass")
    rule_fanogan = metrics(rows, "rule_fanogan_pass")

    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(
            [
                "mode",
                "total_samples",
                "expected_valid",
                "expected_invalid",
                "rule_only_pass",
                "rule_only_reject",
                "ae_v1_pass",
                "ae_v1_reject",
                "fanogan_pass",
                "fanogan_reject",
                "rule_fanogan_pass",
                "rule_fanogan_reject",
                "false_accept",
                "false_reject",
                "accuracy",
                "model_type",
                "summary_source",
                "execution_scope",
                "metric_semantics",
            ]
        )
        writer.writerow(
            [
                "rule_score",
                len(rows),
                sum(1 for row in rows if row["expected_valid"]),
                sum(1 for row in rows if not row["expected_valid"]),
                rule["pass"],
                rule["reject"],
                ae["pass"],
                ae["reject"],
                fanogan["pass"],
                fanogan["reject"],
                rule_fanogan["pass"],
                rule_fanogan["reject"],
                rule_fanogan["false_accept"],
                rule_fanogan["false_reject"],
                f"{rule_fanogan['accuracy']:.6f}",
                model_type,
                SUMMARY_SOURCE,
                EXECUTION_SCOPE,
                METRIC_SEMANTICS,
            ]
        )


def write_details(rows: list[dict[str, Any]], model_type: str) -> None:
    with DETAILS_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(
            [
                "scenario",
                "sample_name",
                "sample_origin",
                "expected_valid",
                "rule_pass",
                "ae_score",
                "ae_decision",
                "fanogan_score",
                "fanogan_decision",
                "rule_fanogan_decision",
                "error_type",
                "model_type",
                "feature_vector",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["scenario"],
                    row["sample_name"],
                    row["sample_origin"],
                    str(row["expected_valid"]).lower(),
                    str(row["rule_pass"]).lower(),
                    f"{row['ae_score']:.6f}",
                    "pass" if row["ae_pass"] else "reject",
                    f"{row['fanogan_score']:.6f}",
                    "pass" if row["fanogan_pass"] else "reject",
                    "pass" if row["rule_fanogan_pass"] else "reject",
                    row["error_type"] if row["rule_pass"] else row["rule_reason"],
                    model_type,
                    json.dumps(row["feature_vector"], ensure_ascii=False, separators=(",", ":")),
                ]
            )


def write_compare(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    strategies = {
        "rule_only": "rule_pass",
        "ae_only": "ae_pass",
        "rule_ae": "rule_ae_pass",
        "fanogan_only": "fanogan_pass",
        "rule_fanogan": "rule_fanogan_pass",
    }
    result = {name: metrics(rows, key) for name, key in strategies.items()}

    with COMPARE_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["strategy", "false_accept", "false_reject", "accuracy", "notes"])
        for name in strategies:
            item = result[name]
            if name in {"rule_ae", "rule_fanogan"}:
                notes = "rule+score strategy combines rule filtering with model score"
            else:
                notes = "single strategy baseline"
            writer.writerow(
                [
                    name,
                    item["false_accept"],
                    item["false_reject"],
                    f"{item['accuracy']:.6f}",
                    notes,
                ]
            )
    return result


def write_recommendation(compare: dict[str, dict[str, Any]]) -> str:
    rule_ae = compare["rule_ae"]
    rule_fanogan = compare["rule_fanogan"]
    improved = (
        rule_fanogan["false_accept"] < rule_ae["false_accept"]
        or rule_fanogan["false_reject"] < rule_ae["false_reject"]
    )
    if improved:
        recommendation = "promote_fanogan_candidate_for_extended_evaluation"
        reason = "fAnoGAN candidate improves false_accept/false_reject under current sample set"
    else:
        recommendation = "keep_ae_v1_as_primary"
        reason = "fAnoGAN candidate does not outperform AE v1 on current samples"

    content = (
        f"recommendation: {recommendation}\n"
        f"reason: {reason}\n"
        "boundary: candidate only; not full SE-fAnoGAN-ES; not full GAN/fAnoGAN completed\n"
    )
    RECOMMENDATION_TXT.write_text(content, encoding="utf-8")
    return content


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ae_scorer = AlfrescoAEV1Scorer()
    fanogan_scorer = AlfrescoFanoganV1CandidateScorer()
    model_type = str(fanogan_scorer.meta.get("model_type", "gan_style_statistical_candidate"))

    rows: list[dict[str, Any]] = []
    for sample in all_samples():
        rule_pass, rule_reason = rule_result(sample)
        ae_result = ae_score_sample(ae_scorer, sample)
        fanogan_result = fanogan_score_sample(fanogan_scorer, sample)
        ae_pass = bool(ae_result["pass"])
        fanogan_pass = bool(fanogan_result["pass"])
        rows.append(
            {
                "scenario": sample.scenario,
                "sample_name": sample.name,
                "sample_origin": sample.sample_origin,
                "expected_valid": sample.expected_valid,
                "rule_pass": rule_pass,
                "rule_reason": rule_reason,
                "ae_score": float(ae_result["score"]),
                "ae_pass": ae_pass,
                "rule_ae_pass": bool(rule_pass and ae_pass),
                "fanogan_score": float(fanogan_result["score"]),
                "fanogan_pass": fanogan_pass,
                "rule_fanogan_pass": bool(rule_pass and fanogan_pass),
                "error_type": sample.error_type,
                "feature_vector": fanogan_result["feature_vector"],
            }
        )

    write_summary(rows, model_type)
    write_details(rows, model_type)
    compare = write_compare(rows)
    recommendation = write_recommendation(compare)
    print(f"[OK] Wrote {SUMMARY_CSV}")
    print(f"[OK] Wrote {DETAILS_CSV}")
    print(f"[OK] Wrote {COMPARE_CSV}")
    print(f"[OK] Wrote {RECOMMENDATION_TXT}")
    print(recommendation.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
