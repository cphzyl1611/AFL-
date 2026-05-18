#!/usr/bin/env python3
"""Run local rule + Alfresco AE v1 scoring over three Alfresco seed sets."""

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


METADATA_DIR = ROOT / "in" / "alfresco_metadata_update_dataset"
CONTENT_DIR = ROOT / "in" / "alfresco_content_update_dataset"
UPLOAD_DIR = ROOT / "in" / "alfresco_multipart_upload_dataset"
OUT_DIR = ROOT / "out" / "alfresco_ae_v1_score_compare"
SUMMARY_CSV = OUT_DIR / "summary.csv"
DETAILS_CSV = OUT_DIR / "details.csv"

SUMMARY_SOURCE = "python_static_loop"
EXECUTION_SCOPE = "alfresco_ae_v1_score_min_calibration"
METRIC_SEMANTICS = (
    "Python static-loop Alfresco AE v1 validity scoring; "
    "not a full AFL++ mutation-chain execution."
)

CONTENT_BAD_MARKER = "__EXPECTED_INVALID_EMPTY_CONTENT__"
UPLOAD_BAD_MARKER = "__EXPECTED_INVALID_EMPTY_UPLOAD__"
MAX_CONTENT_BYTES = 4096


def valid_string(value: Any, min_len: int | None = None, max_len: int | None = None) -> bool:
    if not isinstance(value, str):
        return False
    if min_len is not None and len(value) < min_len:
        return False
    if max_len is not None and len(value) > max_len:
        return False
    return True


def validate_metadata_rule(payload: Any) -> tuple[bool, str, bool]:
    expected_negative = False
    if not isinstance(payload, dict):
        return False, "root_not_object", expected_negative

    name = payload.get("name")
    properties = payload.get("properties")
    if not valid_string(name, 1, 255):
        expected_negative = True
        return False, "name_must_be_string_len_1_255", expected_negative
    if not isinstance(properties, dict):
        expected_negative = True
        return False, "properties_must_be_object", expected_negative
    if not valid_string(properties.get("cm:title"), 1, 200):
        expected_negative = True
        return False, "cm_title_must_be_string_len_1_200", expected_negative
    if "cm:description" in properties and not valid_string(properties.get("cm:description"), 0, 1000):
        expected_negative = True
        return False, "cm_description_must_be_string_len_0_1000", expected_negative
    return True, "ok", expected_negative


def validate_text_rule(path: Path, body: bytes, marker: str) -> tuple[bool, str, bool]:
    expected_negative = path.name == "seed_bad_0.txt" or body.decode("utf-8", errors="ignore").strip() == marker
    if expected_negative:
        return False, "expected_negative_marker", True
    if not body:
        return False, "empty_content", False
    if len(body) > MAX_CONTENT_BYTES:
        return False, "content_too_large", False
    if b"\x00" in body:
        return False, "binary_nul_byte", False
    try:
        body.decode("utf-8")
    except UnicodeDecodeError:
        return False, "not_utf8_text", False
    return True, "ok", False


def validate_upload_rule(path: Path, body: bytes, uploaded_name: str) -> tuple[bool, str, bool]:
    rule_ok, reason, expected_negative = validate_text_rule(path, body, UPLOAD_BAD_MARKER)
    if not rule_ok:
        return rule_ok, reason, expected_negative
    if not uploaded_name.endswith(".txt"):
        return False, "filename_not_txt", False
    return True, "ok", False


def initial_stats() -> dict[str, int]:
    return {
        "nv_total_valid_exec": 0,
        "nv_err_exec": 0,
        "last_http_code": 0,
        "last_latency_ms": 0,
        "body_rule_pass": 0,
        "body_rule_reject": 0,
        "body_score_pass": 0,
        "body_score_reject": 0,
        "body_score_rpc_ok": 0,
        "body_score_rpc_fail": 0,
    }


def write_summary(stats: dict[str, int]) -> None:
    total = stats["nv_total_valid_exec"]
    err_rate = (stats["nv_err_exec"] / total) if total else 0.0
    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(
            [
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
        )
        writer.writerow(
            [
                "rule_score",
                total,
                stats["nv_err_exec"],
                f"{err_rate:.6f}",
                0,
                0,
                stats["last_http_code"],
                stats["last_latency_ms"],
                0,
                stats["body_rule_pass"],
                stats["body_rule_reject"],
                stats["body_score_pass"],
                stats["body_score_reject"],
                stats["body_score_rpc_ok"],
                stats["body_score_rpc_fail"],
                SUMMARY_SOURCE,
                EXECUTION_SCOPE,
                METRIC_SEMANTICS,
            ]
        )


def write_details(rows: list[list[object]]) -> None:
    with DETAILS_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(
            [
                "scenario",
                "seed_file",
                "expected_negative",
                "rule_pass",
                "ae_score",
                "ae_pass",
                "decision",
                "reason",
                "feature_vector",
            ]
        )
        writer.writerows(rows)


def add_score_row(
    rows: list[list[object]],
    stats: dict[str, int],
    scenario: str,
    seed_file: str,
    expected_negative: bool,
    rule_ok: bool,
    rule_reason: str,
    score_result: dict[str, Any],
) -> None:
    stats["nv_total_valid_exec"] += 1
    if rule_ok:
        stats["body_rule_pass"] += 1
    else:
        stats["body_rule_reject"] += 1

    stats["body_score_rpc_ok"] += 1
    raw_ae_pass = bool(score_result.get("pass", False))
    final_pass = bool(rule_ok and raw_ae_pass)
    if final_pass:
        stats["body_score_pass"] += 1
        decision = "pass"
        reason = str(score_result.get("reason", "score_within_threshold"))
    else:
        stats["body_score_reject"] += 1
        decision = "reject"
        reason = f"rule_reject:{rule_reason}" if not rule_ok else str(score_result.get("reason", "score_above_threshold"))

    rows.append(
        [
            scenario,
            seed_file,
            str(expected_negative).lower(),
            str(rule_ok).lower(),
            f"{float(score_result.get('score', 0.0)):.6f}",
            str(final_pass).lower(),
            decision,
            reason,
            json.dumps(score_result.get("feature_vector", []), ensure_ascii=False, separators=(",", ":")),
        ]
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scorer = AlfrescoAEV1Scorer()
    stats = initial_stats()
    rows: list[list[object]] = []

    try:
        for path in sorted(METADATA_DIR.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            rule_ok, rule_reason, expected_negative = validate_metadata_rule(payload)
            score_result = scorer.score_metadata_payload(payload if isinstance(payload, dict) else {})
            add_score_row(rows, stats, "metadata_update", path.name, expected_negative or "bad" in path.stem, rule_ok, rule_reason, score_result)

        for path in sorted(CONTENT_DIR.glob("*.txt")):
            body = path.read_bytes()
            rule_ok, rule_reason, expected_negative = validate_text_rule(path, body, CONTENT_BAD_MARKER)
            score_result = scorer.score_text_content(body)
            add_score_row(rows, stats, "content_update", path.name, expected_negative, rule_ok, rule_reason, score_result)

        for path in sorted(UPLOAD_DIR.glob("*.txt")):
            body = path.read_bytes()
            uploaded_name = f"score_{path.name}"
            fields = {"nodeType": "cm:content", "autoRename": "true"}
            rule_ok, rule_reason, expected_negative = validate_upload_rule(path, body, uploaded_name)
            score_result = scorer.score_multipart_upload(uploaded_name, body, fields)
            add_score_row(rows, stats, "multipart_upload", path.name, expected_negative, rule_ok, rule_reason, score_result)
    except Exception as exc:  # noqa: BLE001 - fail loudly but still write evidence.
        stats["nv_err_exec"] += 1
        stats["body_score_rpc_fail"] += 1
        rows.append(["__runner__", "__error__", "false", "false", "0.000000", "false", "reject", str(exc), "[]"])

    write_summary(stats)
    write_details(rows)
    print(f"[OK] Wrote {SUMMARY_CSV}")
    print(f"[OK] Wrote {DETAILS_CSV}")
    return 0 if stats["nv_err_exec"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
