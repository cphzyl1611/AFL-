#!/usr/bin/env python3
"""Smoke test for the local lightweight fuzzing API.

The script starts integration/api_server.py on 127.0.0.1:18081, probes a small
set of JSON endpoints, then terminates the child process. It does not run real
fuzzing and does not contact external services.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = 18081
BASE_URL = f"http://{HOST}:{PORT}"


class SmokeError(RuntimeError):
    pass


def http_json(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=5) as response:
            raw = response.read()
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SmokeError(f"{method} {path} did not return JSON: {raw[:200]!r}") from exc
    if not isinstance(parsed, dict):
        raise SmokeError(f"{method} {path} returned non-object JSON")
    return status, parsed


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def wait_until_ready(process: subprocess.Popen[bytes]) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        if process.poll() is not None:
            raise SmokeError(f"API server exited early with code {process.returncode}")
        try:
            status, body = http_json("GET", "/health")
            if status == 200 and body.get("status") == "ok":
                return
        except Exception as exc:  # noqa: BLE001 - keep retrying until deadline.
            last_error = exc
        time.sleep(0.2)
    raise SmokeError(f"API server was not ready before timeout: {last_error}")


def run_smoke() -> None:
    command = [
        sys.executable,
        "integration/api_server.py",
        "--host",
        HOST,
        "--port",
        str(PORT),
    ]
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
    )
    try:
        wait_until_ready(process)

        status, health = http_json("GET", "/health")
        expect(status == 200, f"/health status={status}")
        expect(health.get("service") == "fuzzing-module-api", "/health service mismatch")

        status, capabilities = http_json("GET", "/capabilities")
        expect(status == 200, f"/capabilities status={status}")
        scenarios = capabilities.get("scenarios")
        expect(isinstance(scenarios, list), "/capabilities scenarios is not a list")
        expect("nv_mab_smoke" in scenarios, "/capabilities missing nv_mab_smoke")

        status, reports = http_json("GET", "/reports")
        expect(status == 200, f"/reports status={status}")
        expect(isinstance(reports.get("reports"), list), "/reports missing report list")

        status, submit = http_json("POST", "/fuzz/submit", {"scenario": "nv_mab_smoke", "dry_run": True})
        expect(status == 200, f"/fuzz/submit dry_run status={status}")
        expect(submit.get("status") == "dry_run", "/fuzz/submit did not return dry_run")
        command_result = submit.get("command")
        expect(isinstance(command_result, list) and command_result, "/fuzz/submit missing command")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        process.communicate(timeout=5)


def main() -> int:
    try:
        run_smoke()
    except Exception as exc:  # noqa: BLE001 - CLI should report any failure.
        print(f"API_SMOKE_FAIL: {exc}", file=sys.stderr)
        return 1
    print("API_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
