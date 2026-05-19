#!/usr/bin/env python3
"""Validate Alfresco AE v1 seed scoring through the local HTTP score service."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_alfresco_ae_v1_score_compare import (  # noqa: E402
    CONTENT_BAD_MARKER,
    CONTENT_DIR,
    METADATA_DIR,
    UPLOAD_BAD_MARKER,
    UPLOAD_DIR,
    validate_metadata_rule,
    validate_text_rule,
    validate_upload_rule,
)


HOST = "127.0.0.1"
PORT = 18181
BASE_URL = f"http://{HOST}:{PORT}"
OUT_DIR = ROOT / "out" / "alfresco_ae_v1_service_compare"
SUMMARY_CSV = OUT_DIR / "summary.csv"
DETAILS_CSV = OUT_DIR / "details.csv"

SUMMARY_SOURCE = "python_static_loop"
EXECUTION_SCOPE = "alfresco_ae_v1_score_service_min_calibration"
METRIC_SEMANTICS = (
    "Python static-loop Alfresco AE v1 score service validation; "
    "not a full AFL++ mutation-chain execution."
)


class ServiceCompareError(RuntimeError):
    pass


def http_json(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any], float]:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    start = time.perf_counter()
    try:
        with opener.open(request, timeout=5) as response:
            raw = response.read()
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    latency_ms = (time.perf_counter() - start) * 1000.0
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ServiceCompareError(f"{method} {path} did not return JSON: {raw[:200]!r}") from exc
    if not isinstance(parsed, dict):
        raise ServiceCompareError(f"{method} {path} returned non-object JSON")
    return status, parsed, latency_ms


def wait_until_ready(process: subprocess.Popen[bytes]) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        if process.poll() is not None:
            output = process.communicate(timeout=2)[0].decode("utf-8", errors="replace")
            raise ServiceCompareError(f"score service exited early with code {process.returncode}: {output}")
        try:
            status, body, _ = http_json("GET", "/health")
            if status == 200 and body.get("status") == "ok":
                return
        except Exception as exc:  # noqa: BLE001 - retry until deadline.
            last_error = exc
        time.sleep(0.2)
    raise ServiceCompareError(f"score service was not ready before timeout: {last_error}")


def start_service() -> subprocess.Popen[bytes]:
    command = [
        sys.executable,
        "model_stage/alfresco_ae_v1_score_service.py",
        "--host",
        HOST,
        "--port",
        str(PORT),
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
    )
    wait_until_ready(process)
    return process


def stop_service(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    process.communicate(timeout=5)


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
                "http_code",
                "score",
                "score_pass",
                "decision",
                "reason",
                "service_latency_ms",
            ]
        )
        writer.writerows(rows)


def update_result(
    rows: list[list[object]],
    stats: dict[str, int],
    scenario: str,
    seed_file: str,
    expected_negative: bool,
    rule_ok: bool,
    rule_reason: str,
    status: int,
    response: dict[str, Any],
    latency_ms: float,
) -> None:
    stats["nv_total_valid_exec"] += 1
    stats["last_http_code"] = status
    stats["last_latency_ms"] = int(round(latency_ms))
    if rule_ok:
        stats["body_rule_pass"] += 1
    else:
        stats["body_rule_reject"] += 1

    rpc_ok = status == 200 and "score" in response
    if rpc_ok:
        stats["body_score_rpc_ok"] += 1
    else:
        stats["body_score_rpc_fail"] += 1
        stats["nv_err_exec"] += 1

    service_pass = bool(response.get("pass", False)) if rpc_ok else False
    final_pass = bool(rule_ok and service_pass)
    if final_pass:
        stats["body_score_pass"] += 1
        decision = "pass"
        reason = str(response.get("reason", "score_within_threshold"))
    else:
        stats["body_score_reject"] += 1
        decision = "reject"
        reason = f"rule_reject:{rule_reason}" if not rule_ok else str(response.get("reason", response.get("error", "score_reject")))

    rows.append(
        [
            scenario,
            seed_file,
            str(expected_negative).lower(),
            str(rule_ok).lower(),
            status,
            f"{float(response.get('score', 0.0)):.6f}" if rpc_ok else "0.000000",
            str(final_pass).lower(),
            decision,
            reason,
            f"{latency_ms:.3f}",
        ]
    )


def score_sample(
    rows: list[list[object]],
    stats: dict[str, int],
    scenario: str,
    seed_file: str,
    expected_negative: bool,
    rule_ok: bool,
    rule_reason: str,
    request_body: dict[str, Any],
) -> None:
    status, response, latency_ms = http_json("POST", "/score", request_body)
    update_result(rows, stats, scenario, seed_file, expected_negative, rule_ok, rule_reason, status, response, latency_ms)


def run_compare() -> tuple[dict[str, int], list[list[object]]]:
    stats = initial_stats()
    rows: list[list[object]] = []

    for path in sorted(METADATA_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rule_ok, rule_reason, expected_negative = validate_metadata_rule(payload)
        score_sample(
            rows,
            stats,
            "metadata_update",
            path.name,
            expected_negative or "bad" in path.stem,
            rule_ok,
            rule_reason,
            {"scenario": "metadata_update", "payload": payload if isinstance(payload, dict) else {}},
        )

    for path in sorted(CONTENT_DIR.glob("*.txt")):
        body = path.read_bytes()
        rule_ok, rule_reason, expected_negative = validate_text_rule(path, body, CONTENT_BAD_MARKER)
        score_sample(
            rows,
            stats,
            "content_update",
            path.name,
            expected_negative,
            rule_ok,
            rule_reason,
            {"scenario": "content_update", "content": body.decode("utf-8", errors="replace")},
        )

    for path in sorted(UPLOAD_DIR.glob("*.txt")):
        body = path.read_bytes()
        uploaded_name = f"score_service_{path.name}"
        fields = {"nodeType": "cm:content", "autoRename": "true"}
        rule_ok, rule_reason, expected_negative = validate_upload_rule(path, body, uploaded_name)
        score_sample(
            rows,
            stats,
            "multipart_upload",
            path.name,
            expected_negative,
            rule_ok,
            rule_reason,
            {
                "scenario": "multipart_upload",
                "filename": uploaded_name,
                "fields": fields,
                "content": body.decode("utf-8", errors="replace"),
            },
        )

    return stats, rows


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    process = start_service()
    try:
        stats, rows = run_compare()
    except Exception as exc:  # noqa: BLE001 - write evidence for failure.
        stats = initial_stats()
        stats["nv_total_valid_exec"] = 1
        stats["nv_err_exec"] = 1
        stats["body_score_rpc_fail"] = 1
        rows = [["__runner__", "__error__", "false", "false", 0, "0.000000", "false", "reject", str(exc), "0.000"]]
    finally:
        stop_service(process)

    write_summary(stats)
    write_details(rows)
    print(f"[OK] Wrote {SUMMARY_CSV}")
    print(f"[OK] Wrote {DETAILS_CSV}")
    return 0 if stats["nv_err_exec"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
