#!/usr/bin/env python3
"""Replay Alfresco text/plain content update seeds against a local Alfresco API.

This is a min-calibration static-loop runner for the standard Alfresco document
content update endpoint. It is not a full AFL++ mutation-chain execution and it
does not perform multipart upload fuzzing.
"""

from __future__ import annotations

import base64
import csv
import json
import os
import time
import uuid
from pathlib import Path
from urllib import error, parse, request


ROOT = Path(__file__).resolve().parents[1]

IN_DIR = Path(os.getenv("IN_DIR", str(ROOT / "in" / "alfresco_content_update_dataset")))
OUT_DIR = Path(os.getenv("OUT_DIR", str(ROOT / "out" / "alfresco_content_update_manual_latest")))
OUT_DIR.mkdir(parents=True, exist_ok=True)

ALFRESCO_BASE = os.getenv("ALFRESCO_BASE", "http://127.0.0.1:8080").rstrip("/")


def require_runtime_secret(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise RuntimeError(f"{name} must be supplied through the runtime environment")
    return value


ALFRESCO_USER = require_runtime_secret("ALFRESCO_USER")
ALFRESCO_PASS = require_runtime_secret("ALFRESCO_PASS")

SUMMARY_SOURCE = "python_static_loop"
EXECUTION_SCOPE = "alfresco_content_update_min_calibration"
METRIC_SEMANTICS = (
    "Python static-loop Alfresco text/plain content update replay; "
    "not a full AFL++ mutation-chain execution."
)

SUMMARY_CSV = OUT_DIR / "summary.csv"
DETAILS_CSV = OUT_DIR / "details.csv"
FIXTURE_CREATE_PATH = "/alfresco/api/-default-/public/alfresco/versions/1/nodes/-my-/children"
CONTENT_UPDATE_PATH_TEMPLATE = (
    "/alfresco/api/-default-/public/alfresco/versions/1/nodes/{nodeId}/content"
    "?majorVersion=false&comment=content-update-min-calibration"
)
EXPECTED_NEGATIVE_MARKER = "__EXPECTED_INVALID_EMPTY_CONTENT__"
MAX_CONTENT_BYTES = 4096


def is_http_success(code: int) -> bool:
    return 200 <= code < 300


def auth_header() -> str:
    token = base64.b64encode(f"{ALFRESCO_USER}:{ALFRESCO_PASS}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def compact_message(text: str, limit: int = 240) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def is_transport_unavailable(code: int, text: str) -> bool:
    if code != 0:
        return False
    lowered = (text or "").lower()
    markers = [
        "connection refused",
        "timed out",
        "timeout",
        "no route to host",
        "network is unreachable",
        "name or service not known",
        "operation not permitted",
    ]
    return any(marker in lowered for marker in markers)


def http_request(method: str, path: str, body: bytes, content_type: str) -> tuple[int, int, str]:
    url = ALFRESCO_BASE + path
    headers = {
        "Authorization": auth_header(),
        "Content-Type": content_type,
        "Accept": "application/json",
    }
    req = request.Request(url, data=body, headers=headers, method=method)
    t0 = time.time()
    try:
        with request.urlopen(req, timeout=10) as resp:
            latency_ms = int((time.time() - t0) * 1000)
            return resp.getcode(), latency_ms, resp.read().decode("utf-8", errors="ignore")
    except error.HTTPError as exc:
        latency_ms = int((time.time() - t0) * 1000)
        return exc.code, latency_ms, exc.read().decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001 - stored in details.csv.
        latency_ms = int((time.time() - t0) * 1000)
        return 0, latency_ms, str(exc)


def build_multipart_form(fields: list[tuple[str, str]], file_field: str, filename: str, file_bytes: bytes) -> tuple[bytes, str]:
    boundary = "----nv-alfresco-" + uuid.uuid4().hex
    chunks: list[bytes] = []

    for name, value in fields:
        chunks.append(f"--{boundary}\r\n".encode("ascii"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}\r\n".encode("ascii"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{filename}"\r\n'
        ).encode("ascii")
    )
    chunks.append(b"Content-Type: text/plain; charset=utf-8\r\n\r\n")
    chunks.append(file_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))

    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def create_fixture_document() -> tuple[str | None, int, int, str]:
    fixture_name = f"alfresco_content_fixture_{int(time.time())}_{os.getpid()}.txt"
    fixture_body = "Alfresco content update fixture for local min calibration.\n".encode("utf-8")
    fields = [
        ("name", fixture_name),
        ("nodeType", "cm:content"),
        ("autoRename", "true"),
    ]
    body, content_type = build_multipart_form(fields, "filedata", fixture_name, fixture_body)
    code, latency_ms, text = http_request("POST", FIXTURE_CREATE_PATH, body, content_type)
    if not is_http_success(code):
        return None, code, latency_ms, compact_message(text)

    try:
        payload = json.loads(text)
    except Exception:
        return None, code, latency_ms, "fixture_create_invalid_json_response"

    entry = payload.get("entry") if isinstance(payload, dict) else None
    if not isinstance(entry, dict):
        entry = payload if isinstance(payload, dict) else {}

    node_id = entry.get("id")
    if not isinstance(node_id, str) or not node_id:
        return None, code, latency_ms, "fixture_create_missing_node_id"

    return node_id, code, latency_ms, ""


def validate_content_rule(path: Path, body: bytes) -> tuple[bool, str, bool]:
    expected_negative = path.name == "seed_bad_0.txt" or body.decode("utf-8", errors="ignore").strip() == EXPECTED_NEGATIVE_MARKER

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


def write_summary(stats: dict[str, int], mode: str = "rule_score") -> None:
    total = stats["nv_total_valid_exec"]
    err_rate = (stats["nv_err_exec"] / total) if total else 0.0
    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
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
                mode,
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
        writer = csv.writer(fh)
        writer.writerow(
            [
                "seed_file",
                "is_expected_negative",
                "rule_pass",
                "sent_to_target",
                "http_code",
                "latency_ms",
                "error",
                "response_node_id",
                "content_size",
            ]
        )
        writer.writerows(rows)


def extract_response_node_id(text: str) -> str:
    try:
        payload = json.loads(text)
    except Exception:
        return ""
    entry = payload.get("entry") if isinstance(payload, dict) else None
    if isinstance(entry, dict) and isinstance(entry.get("id"), str):
        return entry["id"]
    if isinstance(payload, dict) and isinstance(payload.get("id"), str):
        return payload["id"]
    return ""


def main() -> int:
    stats = initial_stats()
    details: list[list[object]] = []

    node_id, code, latency_ms, fixture_error = create_fixture_document()
    stats["last_http_code"] = code
    stats["last_latency_ms"] = latency_ms
    if not node_id:
        mode = "skipped" if is_transport_unavailable(code, fixture_error) else "rule_score"
        if mode != "skipped":
            stats["nv_err_exec"] += 1
        details.append(
            [
                "__fixture__",
                "false",
                "false",
                "false",
                code,
                latency_ms,
                fixture_error or "fixture_create_failed",
                "",
                0,
            ]
        )
        write_summary(stats, mode=mode)
        write_details(details)
        print(f"[SKIP] Alfresco fixture unavailable: {fixture_error}" if mode == "skipped" else f"[FAIL] Fixture create failed: {fixture_error}")
        print(f"[OK] Wrote {SUMMARY_CSV}")
        print(f"[OK] Wrote {DETAILS_CSV}")
        return 0 if mode == "skipped" else 1

    seeds = sorted(IN_DIR.glob("*.txt"))
    if not seeds:
        stats["nv_err_exec"] += 1
        details.append(["__seeds__", "false", "false", "false", 0, 0, f"no seeds found in {IN_DIR}", "", 0])
        write_summary(stats)
        write_details(details)
        return 1

    encoded_node_id = parse.quote(node_id, safe="")
    update_path = CONTENT_UPDATE_PATH_TEMPLATE.format(nodeId=encoded_node_id)

    for seed in seeds:
        body = seed.read_bytes()
        stats["nv_total_valid_exec"] += 1
        rule_ok, rule_reason, expected_negative = validate_content_rule(seed, body)

        if rule_ok:
            stats["body_rule_pass"] += 1
        else:
            stats["body_rule_reject"] += 1
            if not expected_negative:
                stats["nv_err_exec"] += 1
            details.append(
                [
                    seed.name,
                    str(expected_negative).lower(),
                    "false",
                    "false",
                    0,
                    0,
                    "preset_invalid_seed_rule_reject" if expected_negative else f"rule_reject:{rule_reason}",
                    "",
                    len(body),
                ]
            )
            continue

        code, latency_ms, text = http_request(
            "PUT",
            update_path,
            body,
            "text/plain; charset=utf-8",
        )
        stats["last_http_code"] = code
        stats["last_latency_ms"] = latency_ms
        error_message = ""
        if not is_http_success(code):
            stats["nv_err_exec"] += 1
            error_message = compact_message(text)

        details.append(
            [
                seed.name,
                "false",
                "true",
                "true",
                code,
                latency_ms,
                error_message,
                extract_response_node_id(text),
                len(body),
            ]
        )

    write_summary(stats)
    write_details(details)
    print(f"[OK] Wrote {SUMMARY_CSV}")
    print(f"[OK] Wrote {DETAILS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
