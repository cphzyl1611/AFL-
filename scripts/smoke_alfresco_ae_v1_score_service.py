#!/usr/bin/env python3
"""Smoke test the local Alfresco AE v1 score service.

The script starts the localhost score service, probes /health, /model, and
/score for the three supported Alfresco scenarios, then terminates the child
process. It does not contact Alfresco and does not run fuzzing.
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
PORT = 18181
BASE_URL = f"http://{HOST}:{PORT}"


class SmokeError(RuntimeError):
    pass


def http_json(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
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
            output = process.communicate(timeout=2)[0].decode("utf-8", errors="replace")
            raise SmokeError(f"score service exited early with code {process.returncode}: {output}")
        try:
            status, body = http_json("GET", "/health")
            if status == 200 and body.get("status") == "ok":
                return
        except Exception as exc:  # noqa: BLE001 - retry until deadline.
            last_error = exc
        time.sleep(0.2)
    raise SmokeError(f"score service was not ready before timeout: {last_error}")


def score_samples() -> list[dict[str, Any]]:
    return [
        {
            "scenario": "metadata_update",
            "payload": {
                "name": "official_doc.txt",
                "properties": {
                    "cm:title": "标题",
                    "cm:description": "说明",
                },
            },
        },
        {
            "scenario": "content_update",
            "content": "正文内容",
        },
        {
            "scenario": "multipart_upload",
            "filename": "official_doc.txt",
            "fields": {
                "nodeType": "cm:content",
                "autoRename": "true",
            },
            "content": "上传文件内容",
        },
    ]


def run_smoke() -> None:
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
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
    )
    try:
        wait_until_ready(process)

        status, health = http_json("GET", "/health")
        expect(status == 200, f"/health status={status}")
        expect(health.get("service") == "alfresco_ae_v1_score_service", "/health service mismatch")

        status, model = http_json("GET", "/model")
        expect(status == 200, f"/model status={status}")
        expect(model.get("model_name") == "alfresco_ae_v1", "/model model_name mismatch")
        expect(model.get("model_type") == "ae_like_statistical_baseline", "/model model_type mismatch")

        for sample in score_samples():
            status, score = http_json("POST", "/score", sample)
            expect(status == 200, f"/score status={status} for {sample['scenario']}")
            expect("score" in score, "/score missing score")
            expect(score.get("decision") in {"pass", "reject"}, "/score decision mismatch")
            expect(score.get("model_type") == "ae_like_statistical_baseline", "/score model_type mismatch")
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
        print(f"ALFRESCO_AE_V1_SCORE_SERVICE_SMOKE_FAIL: {exc}", file=sys.stderr)
        return 1
    print("ALFRESCO_AE_V1_SCORE_SERVICE_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
