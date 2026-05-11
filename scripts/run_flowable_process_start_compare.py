#!/usr/bin/env python3
import os
import csv
import json
import time
import base64
import socket
import struct
from pathlib import Path
from urllib import request, error

from integration.decision_engine import DecisionEngine, load_profile_decision_config

ROOT = Path.home() / "AFLplusplus"
IN_DIR = Path(os.getenv("IN_DIR", str(ROOT / "in" / "flowable_process_start")))
OUT_DIR = Path(os.getenv("OUT_DIR", str(ROOT / "out" / "flowable_process_start_compare")))
OUT_DIR.mkdir(parents=True, exist_ok=True)

FLOWABLE_BASE = os.getenv("FLOWABLE_BASE", "http://127.0.0.1:8080").rstrip("/")
FLOWABLE_PATH = os.getenv("FLOWABLE_PATH", "/flowable-rest/service/runtime/process-instances")
FLOWABLE_USER = os.getenv("FLOWABLE_USER", "rest-admin")
FLOWABLE_PASS = os.getenv("FLOWABLE_PASS", "test")

NV_BODY_SCORE_ENDPOINT = os.getenv("NV_BODY_SCORE_ENDPOINT", "unix:///tmp/nv_valid_flowable.sock")
NV_BODY_SCORE_THRESHOLD = float(os.getenv("NV_BODY_SCORE_THRESHOLD", "1.0"))
DUR = int(os.getenv("DUR", "20"))
SLEEP_MS = int(os.getenv("FLOWABLE_SLEEP_MS", "50"))
SUMMARY_SOURCE = "python_static_loop"
EXECUTION_SCOPE = "flowable_min_calibration"
METRIC_SEMANTICS = (
    "Python static-loop Flowable request replay; not a full AFL++ mutation-chain execution"
)

SUMMARY_CSV = OUT_DIR / "summary.csv"
STATS_JSON = Path("/tmp/nv_body_valid_stats.json")

def load_runtime_decision_config(default_threshold: float):
    profile_path = os.getenv("NV_DECISION_PROFILE_PATH", "").strip()
    if profile_path:
        try:
            return load_profile_decision_config(profile_path)
        except Exception:
            pass

    return {
        "t_low": float(default_threshold),
        "t_high": float(default_threshold),
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
        return float(data.decode("ascii", errors="ignore").strip())
    finally:
        s.close()

def post_flowable(body: bytes):
    url = FLOWABLE_BASE + FLOWABLE_PATH
    token = base64.b64encode(f"{FLOWABLE_USER}:{FLOWABLE_PASS}".encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {token}",
    }
    req = request.Request(url, data=body, headers=headers, method="POST")
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

def main():
    seeds = sorted(IN_DIR.glob("*.json"))
    if not seeds:
        raise SystemExit(f"[ERR] no seeds found in {IN_DIR}")

    decision_engine = DecisionEngine(load_runtime_decision_config(NV_BODY_SCORE_THRESHOLD))

    nv_total_valid_exec = 0
    body_rule_pass = 0
    body_rule_reject = 0
    body_score_pass = 0
    body_score_reject = 0
    body_score_rpc_ok = 0
    body_score_rpc_fail = 0
    last_http_code = 0
    last_latency_ms = 0

    deadline = time.time() + DUR
    idx = 0

    while time.time() < deadline:
        seed = seeds[idx % len(seeds)]
        idx += 1
        body = seed.read_bytes()
        nv_total_valid_exec += 1
        body_rule_pass += 1

        try:
            score = score_via_unix_socket(body)
            body_score_rpc_ok += 1
        except Exception:
            body_score_rpc_fail += 1
            time.sleep(SLEEP_MS / 1000.0)
            continue

        decision, _meta = decision_engine.decide(score, body)

        if decision == "pass":
            body_score_pass += 1
            code, latency, _ = post_flowable(body)
            last_http_code = code
            last_latency_ms = latency
        else:
            body_score_reject += 1

        time.sleep(SLEEP_MS / 1000.0)

    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "mode","nv_total_valid_exec","nv_err_exec","nv_err_rate",
            "saved_hangs","saved_crashes","last_http_code","last_latency_ms",
            "last_ncov_total","body_rule_pass","body_rule_reject",
            "body_score_pass","body_score_reject","body_score_rpc_ok","body_score_rpc_fail",
            "summary_source","execution_scope","metric_semantics"
        ])
        writer.writerow([
            "rule_score", nv_total_valid_exec, 0, "0.000000",
            0, 0, last_http_code, last_latency_ms,
            0, body_rule_pass, body_rule_reject,
            body_score_pass, body_score_reject, body_score_rpc_ok, body_score_rpc_fail,
            SUMMARY_SOURCE, EXECUTION_SCOPE, METRIC_SEMANTICS
        ])

    stats = {
        "body_rule_pass": body_rule_pass,
        "body_rule_reject": body_rule_reject,
        "body_score_pass": body_score_pass,
        "body_score_reject": body_score_reject,
        "body_score_rpc_ok": body_score_rpc_ok,
        "body_score_rpc_fail": body_score_rpc_fail,
    }
    STATS_JSON.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")

    print(f"[OK] Wrote {SUMMARY_CSV}")
    print(SUMMARY_CSV.read_text(encoding='utf-8').strip())

if __name__ == "__main__":
    main()
