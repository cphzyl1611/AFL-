#!/usr/bin/env python3
"""Local integration API for the fuzzing module.

This is a lightweight localhost-only API for stage-delivery integration tests.
It is not a production platform gateway and does not expose arbitrary shell
execution or arbitrary filesystem reads.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18081
SERVICE_VERSION = "stage-delivery"

SCENARIOS = [
    "nv_mab_smoke",
    "nv_mab_stability",
    "nv_mab_ablation",
    "alfresco_metadata_update",
    "flowable_doc_create",
    "flowable_doc_update",
    "o2oa_smoke_optional",
]

LOCAL_SUMMARIES = {
    "nv_mab_smoke": Path("out/nv_mab_smoke_summary.csv"),
    "nv_mab_stability": Path("out/nv_mab_stability_summary.csv"),
    "nv_mab_ablation": Path("out/nv_mab_ablation_summary.csv"),
}

SCENARIO_REPORTS = {
    "nv_mab_smoke": [
        Path("docs/review/NV_MAB反馈变异策略阶段性收口报告.md"),
    ],
    "nv_mab_stability": [
        Path("docs/review/NV_MAB轻量稳定性与最小消融验证报告.md"),
    ],
    "nv_mab_ablation": [
        Path("docs/review/NV_MAB轻量稳定性与最小消融验证报告.md"),
    ],
}

KEY_REPORTS = [
    Path("docs/review/模糊测试模块项目要求完成证明与复现说明.md"),
    Path("docs/review/文档类业务接口能力阶段性收口报告.md"),
    Path("docs/review/动态异构冗余判定机制阶段性收口报告.md"),
    Path("docs/review/NV_MAB反馈变异策略阶段性收口报告.md"),
    Path("docs/review/NV_MAB轻量稳定性与最小消融验证报告.md"),
    Path("docs/review/Flowable电子公文替代场景验证报告.md"),
    Path("docs/review/Alfresco元数据更新接口接入验证报告.md"),
    Path("docs/review/真实服务环境smoke验证报告.md"),
]

TASKS: dict[str, dict[str, Any]] = {}
TASK_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def json_error(message: str, status: int = 400, **extra: Any) -> tuple[int, dict[str, Any]]:
    body = {"error": message}
    body.update(extra)
    return status, body


def parse_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    raw_len = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw_len)
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
    if length > 1024 * 1024:
        raise ValueError("request body too large")
    data = handler.rfile.read(length) if length else b"{}"
    try:
        body = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON body") from exc
    if not isinstance(body, dict):
        raise ValueError("JSON body must be an object")
    return body


def safe_out_dir(value: Any, task_id: str) -> tuple[str, Path]:
    raw = value if isinstance(value, str) and value.strip() else f"out/api_{task_id}"
    if "\x00" in raw:
        raise ValueError("out_dir contains NUL byte")
    candidate = Path(raw)
    full = candidate if candidate.is_absolute() else REPO_ROOT / candidate
    full = full.resolve()
    try:
        rel = full.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("out_dir must stay inside repository") from exc
    return rel.as_posix(), full


def build_command(scenario: str) -> list[str]:
    summary = LOCAL_SUMMARIES[scenario]
    summary_abs = (REPO_ROOT / summary).resolve()
    code = (
        "from pathlib import Path; import sys; "
        "p=Path(sys.argv[1]); "
        "print(p.as_posix()); "
        "sys.exit(0 if p.is_file() else 2)"
    )
    return [sys.executable, "-c", code, summary_abs.as_posix()]


def task_snapshot(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "returncode": task.get("returncode"),
        "started_at": task.get("started_at"),
        "finished_at": task.get("finished_at"),
        "out_dir": task.get("out_dir"),
        "log_path": task.get("log_path"),
    }


def run_task(task_id: str) -> None:
    with TASK_LOCK:
        task = TASKS[task_id]
        command = list(task["command"])
        out_dir = Path(task["_out_dir_abs"])
        log_path = Path(task["_log_path_abs"])
        task["status"] = "running"
        task["started_at"] = utc_now()

    out_dir.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        proc = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            shell=False,
        )
        with TASK_LOCK:
            task = TASKS.get(task_id)
            if task is not None:
                task["_process"] = proc
        returncode = proc.wait()

    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            return
        if task.get("status") == "stopped":
            task["returncode"] = returncode
        else:
            task["returncode"] = returncode
            task["status"] = "completed" if returncode == 0 else "failed"
        task["finished_at"] = utc_now()
        task.pop("_process", None)


def create_task(scenario: str, out_dir_value: Any, dry_run: bool) -> dict[str, Any]:
    task_id = uuid.uuid4().hex[:12]
    out_dir_rel, out_dir_abs = safe_out_dir(out_dir_value, task_id)

    if scenario not in SCENARIOS:
        raise ValueError(f"unsupported scenario: {scenario}")

    if scenario not in LOCAL_SUMMARIES:
        task = {
            "task_id": task_id,
            "status": "unsupported_runtime",
            "scenario": scenario,
            "out_dir": out_dir_rel,
            "command": [],
            "created_at": utc_now(),
            "notes": "Runtime execution is not enabled in lightweight API. Use manual reproduce guide.",
        }
        with TASK_LOCK:
            TASKS[task_id] = task
        return task

    command = build_command(scenario)
    log_abs = out_dir_abs / "api_task.log"
    task = {
        "task_id": task_id,
        "status": "dry_run" if dry_run else "created",
        "scenario": scenario,
        "out_dir": out_dir_rel,
        "command": command,
        "created_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "returncode": None,
        "log_path": rel_path(log_abs),
        "_out_dir_abs": out_dir_abs.as_posix(),
        "_log_path_abs": log_abs.as_posix(),
    }

    with TASK_LOCK:
        TASKS[task_id] = task

    if not dry_run:
        thread = threading.Thread(target=run_task, args=(task_id,), daemon=True)
        thread.start()

    return task


def task_report(task: dict[str, Any]) -> dict[str, Any]:
    scenario = task.get("scenario")
    summary_files: list[str] = []
    report_files: list[str] = []
    if scenario in LOCAL_SUMMARIES:
        summary = REPO_ROOT / LOCAL_SUMMARIES[scenario]
        if summary.exists():
            summary_files.append(rel_path(summary))
    for report in SCENARIO_REPORTS.get(scenario, []):
        full = REPO_ROOT / report
        if full.exists():
            report_files.append(rel_path(full))
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "out_dir": task.get("out_dir"),
        "summary_files": summary_files,
        "report_files": report_files,
        "notes": task.get("notes", "Lightweight API report; evidence files are returned by whitelist only."),
    }


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "FuzzingModuleAPI/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def send_json(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            status, body = self.route_get(path)
        except Exception as exc:  # defensive JSON error boundary
            status, body = json_error("internal error", 500, detail=str(exc))
        self.send_json(status, body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            body_obj = parse_json_body(self)
            status, body = self.route_post(path, body_obj)
        except ValueError as exc:
            status, body = json_error(str(exc), 400)
        except Exception as exc:  # defensive JSON error boundary
            status, body = json_error("internal error", 500, detail=str(exc))
        self.send_json(status, body)

    def route_get(self, path: str) -> tuple[int, dict[str, Any]]:
        if path == "/health":
            return 200, {"status": "ok", "service": "fuzzing-module-api", "version": SERVICE_VERSION}

        if path == "/capabilities":
            return 200, {
                "scenarios": SCENARIOS,
                "notes": {
                    "o2oa_smoke_optional": "requires NV_TOKEN and authorized local O2OA environment",
                    "lightweight_api": "local evidence query and fixed-command integration wrapper; not a full platform gateway",
                },
            }

        if path == "/reports":
            reports = []
            for report in KEY_REPORTS:
                full = REPO_ROOT / report
                reports.append({"path": report.as_posix(), "exists": full.exists()})
            return 200, {"reports": reports}

        parts = [p for p in path.split("/") if p]
        if len(parts) == 3 and parts[:2] == ["fuzz", "tasks"]:
            task_id = unquote(parts[2])
            with TASK_LOCK:
                task = TASKS.get(task_id)
                if task is None:
                    return json_error("task not found", 404, task_id=task_id)
                return 200, task_snapshot(task)

        if len(parts) == 4 and parts[:2] == ["fuzz", "tasks"] and parts[3] == "report":
            task_id = unquote(parts[2])
            with TASK_LOCK:
                task = TASKS.get(task_id)
                if task is None:
                    return json_error("task not found", 404, task_id=task_id)
                return 200, task_report(task)

        return json_error("not found", 404)

    def route_post(self, path: str, body_obj: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if path == "/fuzz/submit":
            scenario = body_obj.get("scenario")
            if not isinstance(scenario, str):
                return json_error("scenario is required", 400)
            dry_run = bool(body_obj.get("dry_run", False))
            task = create_task(scenario, body_obj.get("out_dir"), dry_run)
            return 200, {
                "task_id": task["task_id"],
                "status": task["status"],
                "scenario": task["scenario"],
                "out_dir": task["out_dir"],
                "command": task.get("command", []),
                "created_at": task["created_at"],
                "notes": task.get("notes"),
            }

        parts = [p for p in path.split("/") if p]
        if len(parts) == 4 and parts[:2] == ["fuzz", "tasks"] and parts[3] == "stop":
            task_id = unquote(parts[2])
            with TASK_LOCK:
                task = TASKS.get(task_id)
                if task is None:
                    return json_error("task not found", 404, task_id=task_id)
                proc = task.get("_process")
                if proc is not None and proc.poll() is None:
                    proc.terminate()
                    task["status"] = "stopped"
                    task["finished_at"] = utc_now()
                return 200, {"task_id": task_id, "status": task["status"]}

        return json_error("not found", 404)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local lightweight fuzzing module API")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ApiHandler)
    print(f"fuzzing-module-api listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
