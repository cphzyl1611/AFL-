#!/usr/bin/env python3
"""Threshold sweep and false-decision analysis for Alfresco AE v1.

This script is fully local: it does not contact Alfresco, does not run fuzzing,
and does not train a deep model. It evaluates rule_only, ae_only, and rule+AE
decisions across existing seed samples plus synthetic invalid samples.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_stage.alfresco_ae_v1_scorer import AlfrescoAEV1Scorer  # noqa: E402


METADATA_DIR = ROOT / "in" / "alfresco_metadata_update_dataset"
CONTENT_DIR = ROOT / "in" / "alfresco_content_update_dataset"
UPLOAD_DIR = ROOT / "in" / "alfresco_multipart_upload_dataset"
OUT_DIR = ROOT / "out" / "alfresco_ae_v1_threshold_sweep"
SUMMARY_CSV = OUT_DIR / "summary.csv"
DETAILS_CSV = OUT_DIR / "details.csv"
SCORE_DISTRIBUTION_CSV = OUT_DIR / "score_distribution.csv"

CONTENT_BAD_MARKER = "__EXPECTED_INVALID_EMPTY_CONTENT__"
UPLOAD_BAD_MARKER = "__EXPECTED_INVALID_EMPTY_UPLOAD__"
MAX_CONTENT_BYTES = 4096


@dataclass(frozen=True)
class Sample:
    scenario: str
    name: str
    sample_origin: str
    expected_valid: bool
    error_type: str
    payload: Any
    content: bytes
    filename: str
    fields: dict[str, Any]


def valid_string(value: Any, min_len: int | None = None, max_len: int | None = None) -> bool:
    if not isinstance(value, str):
        return False
    if min_len is not None and len(value) < min_len:
        return False
    if max_len is not None and len(value) > max_len:
        return False
    return True


def validate_metadata_rule(payload: Any) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "root_not_object"
    if not valid_string(payload.get("name"), 1, 255):
        return False, "name_must_be_string_len_1_255"
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        return False, "properties_must_be_object"
    if not valid_string(properties.get("cm:title"), 1, 200):
        return False, "cm_title_must_be_string_len_1_200"
    if "cm:description" in properties and not valid_string(properties.get("cm:description"), 0, 1000):
        return False, "cm_description_must_be_string_len_0_1000"
    return True, "ok"


def validate_text_rule(body: bytes, marker: str = CONTENT_BAD_MARKER) -> tuple[bool, str]:
    if body.decode("utf-8", errors="ignore").strip() == marker:
        return False, "expected_negative_marker"
    if not body:
        return False, "empty_content"
    if len(body) > MAX_CONTENT_BYTES:
        return False, "content_too_large"
    if b"\x00" in body:
        return False, "binary_nul_byte"
    try:
        body.decode("utf-8")
    except UnicodeDecodeError:
        return False, "not_utf8_text"
    if body.decode("utf-8", errors="ignore").strip() == "":
        return False, "blank_content"
    return True, "ok"


def validate_upload_rule(filename: str, content: bytes | None, fields: dict[str, Any]) -> tuple[bool, str]:
    if not filename.endswith(".txt"):
        return False, "filename_not_txt"
    if not isinstance(fields, dict):
        return False, "fields_not_object"
    if fields.get("nodeType") != "cm:content":
        return False, "nodeType_not_cm_content"
    if "autoRename" not in fields:
        return False, "autoRename_missing"
    auto_rename = fields.get("autoRename")
    auto_rename_true = auto_rename is True or str(auto_rename).strip().lower() in {"true", "1", "yes"}
    if not auto_rename_true:
        return False, "autoRename_not_true"
    if content is None:
        return False, "filedata_missing"
    return validate_text_rule(content, UPLOAD_BAD_MARKER)


def seed_samples() -> list[Sample]:
    samples: list[Sample] = []

    for path in sorted(METADATA_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected_valid = "bad" not in path.stem
        samples.append(
            Sample(
                scenario="metadata_update",
                name=path.name,
                sample_origin="seed",
                expected_valid=expected_valid,
                error_type="seed_expected_negative" if not expected_valid else "valid_seed",
                payload=payload,
                content=b"",
                filename="",
                fields={},
            )
        )

    for path in sorted(CONTENT_DIR.glob("*.txt")):
        body = path.read_bytes()
        expected_valid = "bad" not in path.stem
        samples.append(
            Sample(
                scenario="content_update",
                name=path.name,
                sample_origin="seed",
                expected_valid=expected_valid,
                error_type="seed_expected_negative" if not expected_valid else "valid_seed",
                payload=None,
                content=body,
                filename="",
                fields={},
            )
        )

    for path in sorted(UPLOAD_DIR.glob("*.txt")):
        body = path.read_bytes()
        expected_valid = "bad" not in path.stem
        samples.append(
            Sample(
                scenario="multipart_upload",
                name=path.name,
                sample_origin="seed",
                expected_valid=expected_valid,
                error_type="seed_expected_negative" if not expected_valid else "valid_seed",
                payload=None,
                content=body,
                filename=f"score_{path.name}",
                fields={"nodeType": "cm:content", "autoRename": "true"},
            )
        )

    return samples


def synthetic_invalid_metadata() -> list[Sample]:
    base_properties = {"cm:title": "标题", "cm:description": "说明"}
    cases = [
        ("missing_name", {"properties": base_properties}),
        ("name_object", {"name": {"invalid": "object"}, "properties": base_properties}),
        ("properties_missing", {"name": "official_doc.txt"}),
        ("title_array", {"name": "official_doc.txt", "properties": {"cm:title": ["bad"], "cm:description": "说明"}}),
        ("description_object", {"name": "official_doc.txt", "properties": {"cm:title": "标题", "cm:description": {"bad": "object"}}}),
        ("name_too_long", {"name": "n" * 300, "properties": base_properties}),
        ("empty_title", {"name": "official_doc.txt", "properties": {"cm:title": "", "cm:description": "说明"}}),
    ]
    return [
        Sample(
            scenario="metadata_update",
            name=f"synthetic_{name}",
            sample_origin="synthetic_invalid",
            expected_valid=False,
            error_type=name,
            payload=payload,
            content=b"",
            filename="",
            fields={},
        )
        for name, payload in cases
    ]


def high_entropy_bytes(length: int = 512) -> bytes:
    alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    return bytes(alphabet[(index * 37 + 11) % len(alphabet)] for index in range(length))


def synthetic_invalid_content() -> list[Sample]:
    long_text = ("超长内容" * 1500).encode("utf-8")
    cases = [
        ("empty_content", b""),
        ("nul_byte", b"abc\x00def"),
        ("non_utf8_bytes", b"\xff\xfe\xfa\xfb"),
        ("too_long_text", long_text),
        ("high_entropy_random_bytes", high_entropy_bytes()),
        ("blank_whitespace", b" \n\t  \r\n"),
    ]
    return [
        Sample(
            scenario="content_update",
            name=f"synthetic_{name}",
            sample_origin="synthetic_invalid",
            expected_valid=False,
            error_type=name,
            payload=None,
            content=content,
            filename="",
            fields={},
        )
        for name, content in cases
    ]


def synthetic_invalid_upload() -> list[Sample]:
    valid_content = "上传文档内容".encode("utf-8")
    valid_fields = {"nodeType": "cm:content", "autoRename": "true"}
    long_text = ("上传超长内容" * 1200).encode("utf-8")
    cases = [
        ("filename_not_txt", "official_doc.bin", valid_content, valid_fields),
        ("missing_nodeType", "official_doc.txt", valid_content, {"autoRename": "true"}),
        ("nodeType_not_cm_content", "official_doc.txt", valid_content, {"nodeType": "cm:folder", "autoRename": "true"}),
        ("autoRename_missing", "official_doc.txt", valid_content, {"nodeType": "cm:content"}),
        ("autoRename_false", "official_doc.txt", valid_content, {"nodeType": "cm:content", "autoRename": "false"}),
        ("filedata_missing", "official_doc.txt", None, valid_fields),
        ("nul_byte_content", "official_doc.txt", b"abc\x00def", valid_fields),
        ("too_long_content", "official_doc.txt", long_text, valid_fields),
    ]
    return [
        Sample(
            scenario="multipart_upload",
            name=f"synthetic_{name}",
            sample_origin="synthetic_invalid",
            expected_valid=False,
            error_type=name,
            payload=None,
            content=content or b"",
            filename=filename,
            fields=fields,
        )
        for name, filename, content, fields in cases
    ]


def all_samples() -> list[Sample]:
    return seed_samples() + synthetic_invalid_metadata() + synthetic_invalid_content() + synthetic_invalid_upload()


def score_sample(scorer: AlfrescoAEV1Scorer, sample: Sample) -> tuple[bool, str, float, list[float]]:
    if sample.scenario == "metadata_update":
        rule_pass, rule_reason = validate_metadata_rule(sample.payload)
        result = scorer.score_metadata_payload(sample.payload if isinstance(sample.payload, dict) else {})
    elif sample.scenario == "content_update":
        rule_pass, rule_reason = validate_text_rule(sample.content, CONTENT_BAD_MARKER)
        result = scorer.score_text_content(sample.content)
    elif sample.scenario == "multipart_upload":
        content_or_none = None if sample.error_type == "filedata_missing" else sample.content
        rule_pass, rule_reason = validate_upload_rule(sample.filename, content_or_none, sample.fields)
        result = scorer.score_multipart_upload(sample.filename, sample.content, sample.fields)
    else:
        raise ValueError(f"unsupported scenario: {sample.scenario}")
    return rule_pass, rule_reason, float(result["score"]), list(result["feature_vector"])


def threshold_candidates(scorer: AlfrescoAEV1Scorer) -> list[float]:
    raw = [
        0.5,
        1.0,
        scorer.threshold_low,
        scorer.threshold_high,
        scorer.threshold_high * 1.25,
        scorer.threshold_high * 1.5,
        2.0,
        3.0,
    ]
    return sorted({round(float(value), 6) for value in raw})


def metrics_for_strategy(samples: list[dict[str, Any]], decision_key: str) -> tuple[int, int, int, int, float]:
    false_accept = 0
    false_reject = 0
    correct = 0
    pass_count = 0
    reject_count = 0
    for item in samples:
        decision_pass = bool(item[decision_key])
        expected_valid = bool(item["expected_valid"])
        pass_count += 1 if decision_pass else 0
        reject_count += 0 if decision_pass else 1
        if decision_pass and not expected_valid:
            false_accept += 1
        elif not decision_pass and expected_valid:
            false_reject += 1
        else:
            correct += 1
    accuracy = correct / len(samples) if samples else 0.0
    return pass_count, reject_count, false_accept, false_reject, accuracy


def write_summary(thresholds: list[float], scored: list[dict[str, Any]]) -> None:
    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(
            [
                "threshold",
                "total_samples",
                "expected_valid",
                "expected_invalid",
                "rule_only_pass",
                "rule_only_reject",
                "ae_only_pass",
                "ae_only_reject",
                "rule_ae_pass",
                "rule_ae_reject",
                "rule_only_false_accept",
                "rule_only_false_reject",
                "ae_only_false_accept",
                "ae_only_false_reject",
                "false_accept",
                "false_reject",
                "accuracy",
                "notes",
            ]
        )
        for threshold in thresholds:
            items: list[dict[str, Any]] = []
            for item in scored:
                ae_pass = item["ae_score"] <= threshold
                items.append(
                    {
                        **item,
                        "ae_only_pass": ae_pass,
                        "rule_ae_pass": bool(item["rule_pass"] and ae_pass),
                    }
                )
            rule_pass, rule_reject, rule_fa, rule_fr, _rule_acc = metrics_for_strategy(items, "rule_pass")
            ae_pass, ae_reject, ae_fa, ae_fr, _ae_acc = metrics_for_strategy(items, "ae_only_pass")
            rule_ae_pass, rule_ae_reject, rule_ae_fa, rule_ae_fr, rule_ae_acc = metrics_for_strategy(items, "rule_ae_pass")
            writer.writerow(
                [
                    f"{threshold:.6f}",
                    len(items),
                    sum(1 for item in items if item["expected_valid"]),
                    sum(1 for item in items if not item["expected_valid"]),
                    rule_pass,
                    rule_reject,
                    ae_pass,
                    ae_reject,
                    rule_ae_pass,
                    rule_ae_reject,
                    rule_fa,
                    rule_fr,
                    ae_fa,
                    ae_fr,
                    rule_ae_fa,
                    rule_ae_fr,
                    f"{rule_ae_acc:.6f}",
                    "false_accept/false_reject/accuracy are for rule+AE; extra columns show rule_only and ae_only errors.",
                ]
            )


def write_details(thresholds: list[float], scored: list[dict[str, Any]]) -> None:
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
                "threshold",
                "ae_pass",
                "rule_ae_decision",
                "error_type",
                "feature_vector",
            ]
        )
        for threshold in thresholds:
            for item in scored:
                ae_pass = item["ae_score"] <= threshold
                rule_ae_pass = bool(item["rule_pass"] and ae_pass)
                writer.writerow(
                    [
                        item["scenario"],
                        item["sample_name"],
                        item["sample_origin"],
                        str(item["expected_valid"]).lower(),
                        str(item["rule_pass"]).lower(),
                        f"{item['ae_score']:.6f}",
                        f"{threshold:.6f}",
                        str(ae_pass).lower(),
                        "pass" if rule_ae_pass else "reject",
                        item["error_type"] if item["rule_pass"] else item["rule_reason"],
                        json.dumps(item["feature_vector"], ensure_ascii=False, separators=(",", ":")),
                    ]
                )


def write_score_distribution(scored: list[dict[str, Any]]) -> None:
    grouped: dict[tuple[str, str, bool], list[float]] = {}
    for item in scored:
        key = (item["scenario"], item["sample_origin"], bool(item["expected_valid"]))
        grouped.setdefault(key, []).append(float(item["ae_score"]))

    with SCORE_DISTRIBUTION_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["scenario", "sample_origin", "expected_valid", "min_score", "median_score", "max_score", "count"])
        for (scenario, origin, expected_valid), scores in sorted(grouped.items()):
            writer.writerow(
                [
                    scenario,
                    origin,
                    str(expected_valid).lower(),
                    f"{min(scores):.6f}",
                    f"{statistics.median(scores):.6f}",
                    f"{max(scores):.6f}",
                    len(scores),
                ]
            )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scorer = AlfrescoAEV1Scorer()
    samples = all_samples()
    scored: list[dict[str, Any]] = []
    for sample in samples:
        rule_pass, rule_reason, ae_score, feature_vector = score_sample(scorer, sample)
        scored.append(
            {
                "scenario": sample.scenario,
                "sample_name": sample.name,
                "sample_origin": sample.sample_origin,
                "expected_valid": sample.expected_valid,
                "rule_pass": rule_pass,
                "rule_reason": rule_reason,
                "ae_score": ae_score,
                "error_type": sample.error_type,
                "feature_vector": [round(float(value), 6) for value in feature_vector],
            }
        )

    thresholds = threshold_candidates(scorer)
    write_summary(thresholds, scored)
    write_details(thresholds, scored)
    write_score_distribution(scored)
    print(f"[OK] Wrote {SUMMARY_CSV}")
    print(f"[OK] Wrote {DETAILS_CSV}")
    print(f"[OK] Wrote {SCORE_DISTRIBUTION_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
