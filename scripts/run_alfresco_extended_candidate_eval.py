#!/usr/bin/env python3
"""Run extended offline Alfresco AE v1 vs fAnoGAN candidate evaluation.

This script reads the local extended sample manifest and scores each sample
with the existing AE v1 scorer and fAnoGAN v1 candidate scorer. It does not
contact Alfresco, does not run fuzzing, and does not train a deep model.
"""

from __future__ import annotations

import base64
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_stage.alfresco_ae_v1_scorer import AlfrescoAEV1Scorer  # noqa: E402
from model_stage.alfresco_fanogan_v1_candidate_scorer import AlfrescoFanoganV1CandidateScorer  # noqa: E402
from scripts.run_alfresco_ae_v1_threshold_sweep import (  # noqa: E402
    CONTENT_BAD_MARKER,
    validate_metadata_rule,
    validate_text_rule,
    validate_upload_rule,
)


DATASET_DIR = ROOT / "in" / "alfresco_extended_eval_dataset"
MANIFEST_PATH = DATASET_DIR / "manifest.json"
PREVIOUS_COMPARE = ROOT / "out" / "alfresco_fanogan_v1_candidate_compare" / "compare_with_ae.csv"
OUT_DIR = ROOT / "out" / "alfresco_extended_candidate_eval"
SUMMARY_CSV = OUT_DIR / "summary.csv"
DETAILS_CSV = OUT_DIR / "details.csv"
COMPARE_CSV = OUT_DIR / "compare_with_previous.csv"
RECOMMENDATION_TXT = OUT_DIR / "recommendation.txt"

SUMMARY_SOURCE = "python_static_loop"
EXECUTION_SCOPE = "alfresco_extended_candidate_eval"
METRIC_SEMANTICS = (
    "Offline Alfresco extended candidate evaluation; "
    "not full SE-fAnoGAN-ES and not full AFL++ mutation-chain execution."
)


@dataclass(frozen=True)
class ExtendedSample:
    scenario: str
    rel_file: str
    sample_type: str
    expected_valid: bool
    error_type: str
    payload: Any
    content: bytes
    filename: str
    fields: dict[str, Any]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_manifest() -> list[dict[str, Any]]:
    data = load_json(MANIFEST_PATH)
    if not isinstance(data, list):
        raise ValueError("manifest must be a list")
    return data


def load_upload_json(path: Path) -> tuple[str, bytes, dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: upload JSON sample must be object")
    filename = str(data.get("filename", path.name))
    fields = data.get("fields", {})
    if not isinstance(fields, dict):
        fields = {}
    if "content_b64" in data:
        content = base64.b64decode(str(data["content_b64"]))
    else:
        content = str(data.get("content", "")).encode("utf-8")
    return filename, content, fields


def load_sample(entry: dict[str, Any]) -> ExtendedSample:
    scenario = str(entry.get("scenario", ""))
    rel_file = str(entry.get("file", ""))
    path = DATASET_DIR / rel_file
    if not path.is_file():
        raise FileNotFoundError(path)
    expected_valid = bool(entry.get("expected_valid"))
    sample_type = str(entry.get("sample_type", ""))
    error_type = str(entry.get("error_type", ""))

    if scenario == "metadata_update":
        payload = load_json(path)
        return ExtendedSample(scenario, rel_file, sample_type, expected_valid, error_type, payload, b"", "", {})

    if scenario == "content_update":
        body = path.read_bytes()
        return ExtendedSample(scenario, rel_file, sample_type, expected_valid, error_type, None, body, "", {})

    if scenario == "multipart_upload":
        if path.suffix == ".json":
            filename, body, fields = load_upload_json(path)
        else:
            filename = str(entry.get("filename") or path.name)
            fields = entry.get("fields", {"nodeType": "cm:content", "autoRename": "true"})
            if not isinstance(fields, dict):
                fields = {"nodeType": "cm:content", "autoRename": "true"}
            body = path.read_bytes()
        return ExtendedSample(scenario, rel_file, sample_type, expected_valid, error_type, None, body, filename, fields)

    raise ValueError(f"unsupported scenario: {scenario}")


def rule_result(sample: ExtendedSample) -> tuple[bool, str]:
    if sample.scenario == "metadata_update":
        return validate_metadata_rule(sample.payload)
    if sample.scenario == "content_update":
        return validate_text_rule(sample.content, CONTENT_BAD_MARKER)
    if sample.scenario == "multipart_upload":
        return validate_upload_rule(sample.filename, sample.content, sample.fields)
    raise ValueError(f"unsupported scenario: {sample.scenario}")


def ae_score_sample(scorer: AlfrescoAEV1Scorer, sample: ExtendedSample) -> dict[str, Any]:
    if sample.scenario == "metadata_update":
        return scorer.score_metadata_payload(sample.payload if isinstance(sample.payload, dict) else {})
    if sample.scenario == "content_update":
        return scorer.score_text_content(sample.content)
    if sample.scenario == "multipart_upload":
        return scorer.score_multipart_upload(sample.filename, sample.content, sample.fields)
    raise ValueError(f"unsupported scenario: {sample.scenario}")


def fanogan_score_sample(scorer: AlfrescoFanoganV1CandidateScorer, sample: ExtendedSample) -> dict[str, Any]:
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
    return {
        "pass": pass_count,
        "reject": reject_count,
        "false_accept": false_accept,
        "false_reject": false_reject,
        "accuracy": correct / len(rows) if rows else 0.0,
    }


def recommendation_for(compare: dict[str, dict[str, Any]]) -> tuple[str, str]:
    rule_ae = compare["rule_ae"]
    rule_fanogan = compare["rule_fanogan"]
    improved = (
        rule_fanogan["false_accept"] < rule_ae["false_accept"]
        or rule_fanogan["false_reject"] < rule_ae["false_reject"]
    )
    if improved:
        return (
            "promote_fanogan_candidate_for_extended_evaluation",
            "fAnoGAN candidate improves false_accept/false_reject on the extended sample set",
        )
    return (
        "keep_ae_v1_as_primary",
        "fAnoGAN candidate does not outperform AE v1 on the extended sample set",
    )


def compare_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "rule_only": metrics(rows, "rule_pass"),
        "ae_only": metrics(rows, "ae_pass"),
        "rule_ae": metrics(rows, "rule_ae_pass"),
        "fanogan_only": metrics(rows, "fanogan_pass"),
        "rule_fanogan": metrics(rows, "rule_fanogan_pass"),
    }


def previous_metrics() -> dict[str, dict[str, Any]]:
    if not PREVIOUS_COMPARE.is_file():
        return {}
    with PREVIOUS_COMPARE.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        result: dict[str, dict[str, Any]] = {}
        for row in reader:
            strategy = str(row.get("strategy", ""))
            if strategy in {"rule_ae", "rule_fanogan"}:
                result[strategy] = {
                    "false_accept": int(row.get("false_accept", 0)),
                    "false_reject": int(row.get("false_reject", 0)),
                    "accuracy": float(row.get("accuracy", 0.0)),
                }
        return result


def write_summary(rows: list[dict[str, Any]], compare: dict[str, dict[str, Any]], recommendation: str) -> None:
    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(
            [
                "total_samples",
                "expected_valid",
                "expected_invalid",
                "rule_only_false_accept",
                "rule_only_false_reject",
                "ae_only_false_accept",
                "ae_only_false_reject",
                "rule_ae_false_accept",
                "rule_ae_false_reject",
                "fanogan_only_false_accept",
                "fanogan_only_false_reject",
                "rule_fanogan_false_accept",
                "rule_fanogan_false_reject",
                "rule_ae_accuracy",
                "rule_fanogan_accuracy",
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
                compare["rule_only"]["false_accept"],
                compare["rule_only"]["false_reject"],
                compare["ae_only"]["false_accept"],
                compare["ae_only"]["false_reject"],
                compare["rule_ae"]["false_accept"],
                compare["rule_ae"]["false_reject"],
                compare["fanogan_only"]["false_accept"],
                compare["fanogan_only"]["false_reject"],
                compare["rule_fanogan"]["false_accept"],
                compare["rule_fanogan"]["false_reject"],
                f"{compare['rule_ae']['accuracy']:.6f}",
                f"{compare['rule_fanogan']['accuracy']:.6f}",
                recommendation,
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
                "file",
                "sample_type",
                "expected_valid",
                "error_type",
                "rule_pass",
                "ae_score",
                "ae_decision",
                "fanogan_score",
                "fanogan_decision",
                "rule_ae_decision",
                "rule_fanogan_decision",
                "model_type",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["scenario"],
                    row["file"],
                    row["sample_type"],
                    str(row["expected_valid"]).lower(),
                    row["error_type"] if row["error_type"] else row["rule_reason"],
                    str(row["rule_pass"]).lower(),
                    f"{row['ae_score']:.6f}",
                    "pass" if row["ae_pass"] else "reject",
                    f"{row['fanogan_score']:.6f}",
                    "pass" if row["fanogan_pass"] else "reject",
                    "pass" if row["rule_ae_pass"] else "reject",
                    "pass" if row["rule_fanogan_pass"] else "reject",
                    model_type,
                ]
            )


def write_compare_with_previous(current: dict[str, dict[str, Any]], previous: dict[str, dict[str, Any]]) -> None:
    fanogan_gain = (
        current["rule_fanogan"]["false_accept"] < current["rule_ae"]["false_accept"]
        or current["rule_fanogan"]["false_reject"] < current["rule_ae"]["false_reject"]
    )
    with COMPARE_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["scope", "strategy", "false_accept", "false_reject", "accuracy", "fanogan_gain", "notes"])
        for strategy in ("rule_ae", "rule_fanogan"):
            if strategy in previous:
                item = previous[strategy]
                writer.writerow(
                    [
                        "previous_candidate_eval",
                        strategy,
                        item["false_accept"],
                        item["false_reject"],
                        f"{item['accuracy']:.6f}",
                        "false",
                        "from out/alfresco_fanogan_v1_candidate_compare/compare_with_ae.csv",
                    ]
                )
        for strategy in ("rule_ae", "rule_fanogan"):
            item = current[strategy]
            writer.writerow(
                [
                    "current_extended_eval",
                    strategy,
                    item["false_accept"],
                    item["false_reject"],
                    f"{item['accuracy']:.6f}",
                    str(fanogan_gain).lower() if strategy == "rule_fanogan" else "false",
                    "extended Alfresco dataset",
                ]
            )


def write_recommendation(recommendation: str, reason: str) -> None:
    RECOMMENDATION_TXT.write_text(
        (
            f"recommendation: {recommendation}\n"
            f"reason: {reason}\n"
            "boundary: extended offline evaluation only; not full SE-fAnoGAN-ES; not full GAN/fAnoGAN completed\n"
        ),
        encoding="utf-8",
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ae_scorer = AlfrescoAEV1Scorer()
    fanogan_scorer = AlfrescoFanoganV1CandidateScorer()
    model_type = str(fanogan_scorer.meta.get("model_type", "gan_style_statistical_candidate"))

    rows: list[dict[str, Any]] = []
    for entry in load_manifest():
        sample = load_sample(entry)
        rule_pass, rule_reason = rule_result(sample)
        ae_result = ae_score_sample(ae_scorer, sample)
        fanogan_result = fanogan_score_sample(fanogan_scorer, sample)
        ae_pass = bool(ae_result["pass"])
        fanogan_pass = bool(fanogan_result["pass"])
        rows.append(
            {
                "scenario": sample.scenario,
                "file": sample.rel_file,
                "sample_type": sample.sample_type,
                "expected_valid": sample.expected_valid,
                "error_type": sample.error_type,
                "rule_pass": rule_pass,
                "rule_reason": rule_reason,
                "ae_score": float(ae_result["score"]),
                "ae_pass": ae_pass,
                "rule_ae_pass": bool(rule_pass and ae_pass),
                "fanogan_score": float(fanogan_result["score"]),
                "fanogan_pass": fanogan_pass,
                "rule_fanogan_pass": bool(rule_pass and fanogan_pass),
            }
        )

    compare = compare_metrics(rows)
    recommendation, reason = recommendation_for(compare)
    write_summary(rows, compare, recommendation)
    write_details(rows, model_type)
    write_compare_with_previous(compare, previous_metrics())
    write_recommendation(recommendation, reason)

    print(f"[OK] Wrote {SUMMARY_CSV}")
    print(f"[OK] Wrote {DETAILS_CSV}")
    print(f"[OK] Wrote {COMPARE_CSV}")
    print(f"[OK] Wrote {RECOMMENDATION_TXT}")
    print(f"recommendation: {recommendation}")
    print(f"reason: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
