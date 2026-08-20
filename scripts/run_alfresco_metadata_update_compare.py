#!/usr/bin/env python3
import base64
import csv
import json
import os
import socket
import struct
import sys
import time
import uuid
from pathlib import Path
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integration.decision_engine import DecisionEngine, load_profile_decision_config

IN_DIR = Path(os.getenv("IN_DIR", str(ROOT / "in" / "alfresco_metadata_update_dataset")))
OUT_DIR = Path(os.getenv("OUT_DIR", str(ROOT / "out" / "alfresco_metadata_update_manual")))
OUT_DIR.mkdir(parents=True, exist_ok=True)

ALFRESCO_BASE = os.getenv("ALFRESCO_BASE", "http://127.0.0.1:8080").rstrip("/")


def require_runtime_secret(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise RuntimeError(f"{name} must be supplied through the runtime environment")
    return value


ALFRESCO_USER = require_runtime_secret("ALFRESCO_USER")
ALFRESCO_PASS = require_runtime_secret("ALFRESCO_PASS")

NV_BODY_SCORE_ENDPOINT = os.getenv("NV_BODY_SCORE_ENDPOINT", "").strip()
NV_DECISION_PROFILE_PATH = os.getenv(
    "NV_DECISION_PROFILE_PATH",
    str(ROOT / "integration" / "platform_profiles" / "alfresco_metadata_update.json"),
)

SUMMARY_SOURCE = "python_static_loop"
EXECUTION_SCOPE = "alfresco_metadata_update_min_calibration"
METRIC_SEMANTICS = (
    "Python static-loop Alfresco metadata update request replay; "
    "not a full AFL++ mutation-chain execution."
)

SUMMARY_CSV = OUT_DIR / "summary.csv"
DETAILS_CSV = OUT_DIR / "details.csv"
FIXTURE_CREATE_PATH = (
    "/alfresco/api/-default-/public/alfresco/versions/1/nodes/-my-/children"
)
METADATA_UPDATE_PATH_TEMPLATE = (
    "/alfresco/api/-default-/public/alfresco/versions/1/nodes/{nodeId}"
)


def is_http_success(code: int) -> bool:
    return 200 <= code < 300


def auth_header() -> str:
    token = base64.b64encode(f"{ALFRESCO_USER}:{ALFRESCO_PASS}".encode()).decode()
    return f"Basic {token}"


def compact_message(text: str, limit: int = 240) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def http_request(method: str, path: str, body: bytes, content_type: str):
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
    except error.HTTPError as e:
        latency_ms = int((time.time() - t0) * 1000)
        return e.code, latency_ms, e.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        latency_ms = int((time.time() - t0) * 1000)
        return 0, latency_ms, str(exc)


def build_multipart_form(fields, file_field: str, filename: str, file_bytes: bytes):
    boundary = "----nv-alfresco-" + uuid.uuid4().hex
    chunks = []

    for name, value in fields:
        chunks.append(f"--{boundary}\r\n".encode("ascii"))
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii")
        )
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}\r\n".encode("ascii"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{filename}"\r\n'
        ).encode("ascii")
    )
    chunks.append(b"Content-Type: text/plain\r\n\r\n")
    chunks.append(file_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))

    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def create_fixture_document():
    fixture_name = f"alfresco_metadata_fixture_{int(time.time())}_{os.getpid()}.txt"
    fixture_path = OUT_DIR / fixture_name
    fixture_body = (
        "Alfresco metadata update fixture for local min calibration.\n"
    ).encode("utf-8")
    fixture_path.write_bytes(fixture_body)

    fields = [
        ("name", fixture_name),
        ("nodeType", "cm:content"),
        ("autoRename", "true"),
    ]
    body, content_type = build_multipart_form(
        fields, "filedata", fixture_name, fixture_body
    )
    code, latency_ms, text = http_request(
        "POST", FIXTURE_CREATE_PATH, body, content_type
    )
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


def valid_string(value, min_len=None, max_len=None) -> bool:
    if not isinstance(value, str):
        return False
    if min_len is not None and len(value) < min_len:
        return False
    if max_len is not None and len(value) > max_len:
        return False
    return True


def validate_metadata_rule(body: bytes):
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return False, "invalid_json"

    if not isinstance(payload, dict):
        return False, "root_not_object"

    if not valid_string(payload.get("name"), 1, 255):
        return False, "name_must_be_string_len_1_255"

    properties = payload.get("properties")
    if not isinstance(properties, dict):
        return False, "properties_must_be_object"

    if not valid_string(properties.get("cm:title"), 1, 200):
        return False, "cm_title_must_be_string_len_1_200"

    if "cm:description" in properties and not valid_string(
        properties.get("cm:description"), 0, 1000
    ):
        return False, "cm_description_must_be_string_len_0_1000"

    return True, "ok"


def load_runtime_decision_config():
    if NV_DECISION_PROFILE_PATH:
        try:
            config = load_profile_decision_config(NV_DECISION_PROFILE_PATH)
            if "t_low" in config and "t_high" in config:
                return config
        except Exception:
            pass

    return {
        "t_low": 1.0,
        "t_high": 1.0,
        "enable_second_stage": False,
    }


def score_via_unix_socket(body: bytes) -> float:
    endpoint = NV_BODY_SCORE_ENDPOINT
    if not endpoint:
        raise RuntimeError("score_endpoint_not_configured")
    if not endpoint.startswith("unix://"):
        raise RuntimeError("unsupported_score_endpoint")

    sock_path = endpoint[len("unix://"):]
    if not sock_path.startswith("/"):
        sock_path = "/" + sock_path

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3.0)
    s.connect(sock_path)
    try:
        s.sendall(struct.pack("<I", len(body)) + body)
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(64)
            if not chunk:
                break
            data += chunk
        text = data.decode("ascii", errors="ignore").strip()
        if not text:
            raise ValueError("empty_score_response")
        return float(text)
    finally:
        s.close()


def apply_score_decision(decision_engine: DecisionEngine, body: bytes, stats: dict):
    if not NV_BODY_SCORE_ENDPOINT:
        return "not_configured", "not_configured"

    try:
        score = score_via_unix_socket(body)
        stats["body_score_rpc_ok"] += 1
    except Exception:
        stats["body_score_rpc_fail"] += 1
        return "unavailable", "fail"

    try:
        decision, _meta = decision_engine.decide(score, body)
    except Exception:
        decision = "reject"

    if decision == "pass":
        stats["body_score_pass"] += 1
    else:
        stats["body_score_reject"] += 1

    return decision, "ok"


def initial_stats():
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


def write_summary(stats: dict):
    total = stats["nv_total_valid_exec"]
    err_rate = (stats["nv_err_exec"] / total) if total else 0.0

    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
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


def write_details(rows):
    with DETAILS_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "seed_file",
                "rule_decision",
                "http_code",
                "latency_ms",
                "score_decision",
                "score_rpc_status",
                "is_expected_negative",
                "error_message",
            ]
        )
        writer.writerows(rows)


def main():
    stats = initial_stats()
    details = []
    decision_engine = DecisionEngine(load_runtime_decision_config())

    node_id, code, latency_ms, fixture_error = create_fixture_document()
    stats["last_http_code"] = code
    stats["last_latency_ms"] = latency_ms
    if not node_id:
        stats["nv_err_exec"] += 1
        details.append(
            [
                "__fixture__",
                "not_applicable",
                code,
                latency_ms,
                "not_scored",
                "not_configured",
                "false",
                fixture_error or "fixture_create_failed",
            ]
        )
        write_summary(stats)
        write_details(details)
        return

    seeds = sorted(IN_DIR.glob("*.json"))
    if not seeds:
        stats["nv_err_exec"] += 1
        details.append(
            [
                "__seeds__",
                "not_applicable",
                0,
                0,
                "not_scored",
                "not_configured",
                "false",
                f"no seeds found in {IN_DIR}",
            ]
        )
        write_summary(stats)
        write_details(details)
        return

    encoded_node_id = parse.quote(node_id, safe="")
    update_path = METADATA_UPDATE_PATH_TEMPLATE.format(nodeId=encoded_node_id)

    for seed in seeds:
        body = seed.read_bytes()
        stats["nv_total_valid_exec"] += 1
        expected_negative = seed.name == "seed_bad_0.json"

        rule_ok, rule_reason = validate_metadata_rule(body)
        if rule_ok:
            stats["body_rule_pass"] += 1
            rule_decision = "pass"
        else:
            stats["body_rule_reject"] += 1
            rule_decision = f"reject:{rule_reason}"
            details.append(
                [
                    seed.name,
                    rule_decision,
                    0,
                    0,
                    "not_scored",
                    "not_configured",
                    str(expected_negative).lower(),
                    "preset_invalid_seed_rule_reject"
                    if expected_negative
                    else f"rule_reject:{rule_reason}",
                ]
            )
            if not expected_negative:
                stats["nv_err_exec"] += 1
            continue

        score_decision, score_rpc_status = apply_score_decision(
            decision_engine, body, stats
        )

        code, latency_ms, text = http_request(
            "PUT", update_path, body, "application/json"
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
                rule_decision,
                code,
                latency_ms,
                score_decision,
                score_rpc_status,
                str(expected_negative).lower(),
                error_message,
            ]
        )

    write_summary(stats)
    write_details(details)
    print(f"[OK] Wrote {SUMMARY_CSV}")
    print(f"[OK] Wrote {DETAILS_CSV}")


if __name__ == "__main__":
    main()
