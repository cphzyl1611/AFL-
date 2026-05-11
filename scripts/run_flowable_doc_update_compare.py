#!/usr/bin/env python3
import base64
import csv
import json
import os
import socket
import struct
import sys
import time
from pathlib import Path
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integration.decision_engine import DecisionEngine, load_profile_decision_config

IN_DIR = Path(os.getenv("IN_DIR", str(ROOT / "in" / "flowable_doc_update_dataset")))
OUT_DIR = Path(os.getenv("OUT_DIR", str(ROOT / "out" / "flowable_doc_update_compare")))
OUT_DIR.mkdir(parents=True, exist_ok=True)

FLOWABLE_BASE = os.getenv("FLOWABLE_BASE", "http://127.0.0.1:8080").rstrip("/")
FLOWABLE_USER = os.getenv("FLOWABLE_USER", "rest-admin")
FLOWABLE_PASS = os.getenv("FLOWABLE_PASS", "test")

NV_BODY_SCORE_ENDPOINT = os.getenv("NV_BODY_SCORE_ENDPOINT", "unix:///tmp/nv_valid_flowable.sock")
NV_DECISION_PROFILE_PATH = os.getenv(
    "NV_DECISION_PROFILE_PATH",
    str(ROOT / "integration" / "platform_profiles" / "flowable_document_process.json"),
)

SUMMARY_SOURCE = "python_static_loop"
EXECUTION_SCOPE = "flowable_document_update_min_calibration"
METRIC_SEMANTICS = (
    "Python static-loop Flowable document-process request replay; "
    "not a full AFL++ mutation-chain execution."
)

SUMMARY_CSV = OUT_DIR / "summary.csv"
FLOWABLE_PROCESS_START_PATH = "/flowable-rest/service/runtime/process-instances"

BOOTSTRAP_CREATE_BODY = {
    "processDefinitionKey": "documentProcess",
    "businessKey": "DOC-UPDATE-BOOTSTRAP",
    "returnVariables": True,
    "variables": [
        {
            "name": "docTitle",
            "type": "string",
            "value": "变量更新批量回放启动文档",
        },
        {
            "name": "docContent",
            "type": "string",
            "value": "用于 Flowable 电子公文流程替代场景的变量更新批量回放。",
        },
        {
            "name": "drafter",
            "type": "string",
            "value": "rest-admin",
        },
        {
            "name": "department",
            "type": "string",
            "value": "office",
        },
        {
            "name": "securityLevel",
            "type": "string",
            "value": "normal",
        },
        {
            "name": "docStatus",
            "type": "string",
            "value": "draft",
        },
    ],
}


def load_runtime_decision_config():
    if NV_DECISION_PROFILE_PATH:
        try:
            return load_profile_decision_config(NV_DECISION_PROFILE_PATH)
        except Exception:
            pass

    return {
        "t_low": 1.0,
        "t_high": 1.0,
        "enable_second_stage": False,
    }


def score_via_unix_socket(body: bytes) -> float:
    endpoint = NV_BODY_SCORE_ENDPOINT
    if endpoint.startswith("unix://"):
        endpoint = endpoint[len("unix://"):]

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3.0)
    s.connect(endpoint)
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
            raise ValueError("empty score response")
        return float(text)
    finally:
        s.close()


def is_http_success(code: int) -> bool:
    return 200 <= code < 300


def flowable_request(method: str, path: str, body: bytes):
    url = FLOWABLE_BASE + path
    token = base64.b64encode(f"{FLOWABLE_USER}:{FLOWABLE_PASS}".encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {token}",
    }
    req = request.Request(url, data=body, headers=headers, method=method)
    t0 = time.time()
    try:
        with request.urlopen(req, timeout=5) as resp:
            latency_ms = int((time.time() - t0) * 1000)
            return resp.getcode(), latency_ms, resp.read().decode("utf-8", errors="ignore")
    except error.HTTPError as e:
        latency_ms = int((time.time() - t0) * 1000)
        return e.code, latency_ms, e.read().decode("utf-8", errors="ignore")
    except Exception:
        latency_ms = int((time.time() - t0) * 1000)
        return 0, latency_ms, ""


def variable_map(items):
    if not isinstance(items, list):
        return None

    mapped = {}
    for item in items:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        if not isinstance(name, str):
            return None
        if "type" in item and not isinstance(item.get("type"), str):
            return None
        mapped[name] = item.get("value")
    return mapped


def valid_string(value, min_len=None, max_len=None) -> bool:
    if not isinstance(value, str):
        return False
    if min_len is not None and len(value) < min_len:
        return False
    if max_len is not None and len(value) > max_len:
        return False
    return True


def validate_body_rule(body: bytes) -> bool:
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return False

    variables = variable_map(payload)
    if variables is None:
        return False

    if not valid_string(variables.get("docTitle"), 1, 200):
        return False
    if not valid_string(variables.get("docContent"), 1, 10000):
        return False

    if "modifyReason" in variables and not isinstance(variables["modifyReason"], str):
        return False
    if "docStatus" in variables and variables["docStatus"] not in {
        "draft",
        "updated",
        "submitted",
        "completed",
    }:
        return False

    return True


def apply_score_decision(decision_engine: DecisionEngine, body: bytes, stats: dict):
    try:
        score = score_via_unix_socket(body)
        stats["body_score_rpc_ok"] += 1
    except Exception:
        stats["body_score_rpc_fail"] += 1
        stats["body_score_reject"] += 1
        return

    try:
        decision, _meta = decision_engine.decide(score, body)
    except Exception:
        decision = "reject"

    if decision == "pass":
        stats["body_score_pass"] += 1
    else:
        stats["body_score_reject"] += 1


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


def start_document_process(stats: dict):
    body = json.dumps(BOOTSTRAP_CREATE_BODY, ensure_ascii=False).encode("utf-8")
    code, latency_ms, text = flowable_request("POST", FLOWABLE_PROCESS_START_PATH, body)
    stats["last_http_code"] = code
    stats["last_latency_ms"] = latency_ms

    if not is_http_success(code):
        stats["nv_err_exec"] += 1
        return None

    try:
        payload = json.loads(text)
    except Exception:
        stats["nv_err_exec"] += 1
        return None

    process_instance_id = payload.get("id") or payload.get("processInstanceId")
    if not isinstance(process_instance_id, str) or not process_instance_id:
        stats["nv_err_exec"] += 1
        return None

    return process_instance_id


def main():
    stats = initial_stats()
    decision_engine = DecisionEngine(load_runtime_decision_config())

    process_instance_id = start_document_process(stats)
    if not process_instance_id:
        write_summary(stats)
        return

    seeds = sorted(IN_DIR.glob("*.json"))
    if not seeds:
        stats["nv_err_exec"] += 1
        write_summary(stats)
        return

    encoded_id = parse.quote(process_instance_id, safe="")
    update_path = (
        f"/flowable-rest/service/runtime/process-instances/{encoded_id}/variables"
    )

    for seed in seeds:
        body = seed.read_bytes()
        stats["nv_total_valid_exec"] += 1

        if validate_body_rule(body):
            stats["body_rule_pass"] += 1
        else:
            stats["body_rule_reject"] += 1

        apply_score_decision(decision_engine, body, stats)

        code, latency_ms, _text = flowable_request("PUT", update_path, body)
        stats["last_http_code"] = code
        stats["last_latency_ms"] = latency_ms
        if not is_http_success(code):
            stats["nv_err_exec"] += 1

    write_summary(stats)


if __name__ == "__main__":
    main()
