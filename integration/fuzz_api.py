#!/usr/bin/env python3
"""Platform API for fuzzing component - fuzz_test_submit/query/stop/report_query.

This module implements the required platform interface contracts:
- fuzz_test_submit: Create and launch fuzzing tasks
- fuzz_test_query: Query task status
- fuzz_test_stop: Stop running tasks
- fuzz_test_report_query: Query and filter reports

Architecture: Delegates to existing runner infrastructure (scripts/run_o2oa_bounded_final.sh pattern)
without reimplementing fuzzing logic. No HTTP server logic in AFL++ core.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Task registry
TASKS: dict[str, dict[str, Any]] = {}
TASK_LOCK = threading.Lock()

# Allowed values for strict validation
# Formal API contract enums (per design specification)
ALLOWED_TARGET_TYPES = ["http_api", "file_upload", "protocol_message"]
ALLOWED_SEED_SOURCES = ["captured_traffic", "seed_file", "manual"]
ALLOWED_MUTATION_SCOPES = ["field_value", "boundary", "structure"]

# Capability status for each formal enum value
# OPERATIONAL = fully implemented and can be dispatched
# NOT_IMPLEMENTED = schema-valid but operational dispatch will fail
TARGET_TYPE_CAPABILITY = {
    "http_api": "OPERATIONAL",
    "file_upload": "OPERATIONAL",  # Maps to multipart_upload scenario
    "protocol_message": "NOT_IMPLEMENTED",
}

SEED_SOURCE_CAPABILITY = {
    "captured_traffic": "NOT_IMPLEMENTED",
    "seed_file": "OPERATIONAL",
    "manual": "OPERATIONAL",
}

# Internal scenario mapping for target_type dispatch
TARGET_TYPE_TO_SCENARIO = {
    "http_api": "platform_api",
    "file_upload": "multipart_upload",
    # protocol_message has no mapping yet
}
TASK_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

def utc_now() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()

def validate_task_name(name: Any) -> str:
    """Validate task_name format (optional field)."""
    if name is None or name == "":
        return f"task_{uuid.uuid4().hex[:8]}"
    if not isinstance(name, str):
        raise ValueError("task_name must be a string")
    if not TASK_NAME_PATTERN.match(name):
        raise ValueError("task_name must be 1-64 alphanumeric/underscore/hyphen chars")
    return name

def validate_submit_request(req: dict[str, Any]) -> dict[str, Any]:
    """Strict validation for fuzz_test_submit request.

    Phase 1: Schema validation - accepts all formally valid enum values
    Phase 2: Capability check - rejects unimplemented operational modes

    Returns normalized/validated request dict.
    Raises ValueError on validation failure.
    """
    # Required fields - SCHEMA VALIDATION (formal contract)
    target_type = req.get("target_type")
    if not isinstance(target_type, str) or target_type not in ALLOWED_TARGET_TYPES:
        raise ValueError(f"target_type must be one of {ALLOWED_TARGET_TYPES}")

    target_endpoint = req.get("target_endpoint")
    if not isinstance(target_endpoint, str) or not target_endpoint.strip():
        raise ValueError("target_endpoint is required and must be non-empty string")

    seed_source = req.get("seed_source")
    if not isinstance(seed_source, str) or seed_source not in ALLOWED_SEED_SOURCES:
        raise ValueError(f"seed_source must be one of {ALLOWED_SEED_SOURCES}")

    seed_location = req.get("seed_location")
    if not isinstance(seed_location, str) or not seed_location.strip():
        raise ValueError("seed_location is required and must be non-empty string")

    # Validate mutation_scope
    mutation_scope = req.get("mutation_scope")
    if not isinstance(mutation_scope, list):
        raise ValueError("mutation_scope must be a list")
    if not mutation_scope:
        raise ValueError("mutation_scope must not be empty")
    for scope in mutation_scope:
        if scope not in ALLOWED_MUTATION_SCOPES:
            raise ValueError(f"invalid mutation_scope: {scope}, allowed: {ALLOWED_MUTATION_SCOPES}")

    # Validate max_test_cases (positive integer)
    max_test_cases = req.get("max_test_cases")
    if not isinstance(max_test_cases, int) or max_test_cases <= 0:
        raise ValueError("max_test_cases must be a positive integer")

    # Validate time_budget (positive number)
    time_budget = req.get("time_budget")
    if not isinstance(time_budget, (int, float)) or time_budget <= 0:
        raise ValueError("time_budget must be a positive number")

    # Optional: task_name
    task_name = validate_task_name(req.get("task_name"))

    # CAPABILITY CHECK (operational support) - separate from schema validation
    # Schema validation passed - now check if we can actually dispatch this request
    if TARGET_TYPE_CAPABILITY[target_type] != "OPERATIONAL":
        raise ValueError(f"target_type '{target_type}' is not yet implemented (status: {TARGET_TYPE_CAPABILITY[target_type]})")

    if SEED_SOURCE_CAPABILITY[seed_source] != "OPERATIONAL":
        raise ValueError(f"seed_source '{seed_source}' is not yet implemented (status: {SEED_SOURCE_CAPABILITY[seed_source]})")

    return {
        "target_type": target_type,
        "target_endpoint": target_endpoint.strip(),
        "seed_source": seed_source,
        "seed_location": seed_location.strip(),
        "mutation_scope": list(mutation_scope),
        "max_test_cases": max_test_cases,
        "time_budget": time_budget,
        "task_name": task_name,
    }

def safe_path_check(location: str) -> Path:
    """Validate seed_location stays within repository.

    Prevents path traversal attacks.
    """
    if "\x00" in location:
        raise ValueError("path contains null byte")
    if ".." in location.split("/"):
        raise ValueError("path traversal not allowed")

    candidate = Path(location)
    if candidate.is_absolute():
        full = candidate.resolve()
    else:
        full = (REPO_ROOT / candidate).resolve()

    try:
        full.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("path must stay inside repository") from exc

    return full

def build_fuzzing_command(validated: dict[str, Any], task_id: str, out_dir: Path) -> list[str]:
    """Build AFL++ fuzzing command from validated request.

    Delegates to existing runner pattern without reimplementing fuzzing logic.
    """
    # Validate seed location
    seed_path = safe_path_check(validated["seed_location"])
    if not seed_path.exists():
        raise ValueError(f"seed_location does not exist: {validated['seed_location']}")

    # Map target_type to internal scenario
    target_type = validated["target_type"]
    scenario = TARGET_TYPE_TO_SCENARIO.get(target_type)
    if scenario is None:
        raise ValueError(f"target_type '{target_type}' has no scenario mapping")

    # Determine input_format based on scenario
    if scenario == "multipart_upload":
        input_format = "full_http_multipart"
    else:
        input_format = "json_body"

    # Build task.json for this run
    task_json = out_dir / "task.json"
    task_config = {
        "target_type": target_type,
        "target_endpoint": validated["target_endpoint"],
        "scenario": scenario,
        "input_format": input_format,
        "seed_source": validated["seed_source"],
        "seed_location": str(seed_path),
        "mutation_scope": validated["mutation_scope"],
        "max_test_cases": validated["max_test_cases"],
        "time_budget": int(validated["time_budget"]),
        "enable_validity": 0,
        "input_format": "json_body",
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    task_json.write_text(json.dumps(task_config, indent=2), encoding="utf-8")

    # Build command using existing AFL++ infrastructure
    # This delegates to afl-fuzz + nv_http_harness.py pattern
    afl_fuzz = REPO_ROOT / "afl-fuzz"
    if not afl_fuzz.exists():
        raise RuntimeError("afl-fuzz not found; run 'make' first")

    harness = REPO_ROOT / "nv_http_harness.py"
    if not harness.exists():
        raise RuntimeError("nv_http_harness.py not found")

    # Return command that will be executed by run_task
    # Using timeout to enforce time_budget
    timeout_sec = int(validated["time_budget"])
    return [
        "timeout", f"{timeout_sec}s",
        "env",
        f"AFL_NO_UI=1",
        f"AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1",
        f"AFL_FAST_CAL=1",
        f"AFL_PYTHON_MODULE=nv_json_mutator",
        f"PYTHONPATH={REPO_ROOT}",
        f"NV_BODY_ONLY_MODE=1",
        f"NV_TASK_PATH={task_json}",
        f"NV_STATUS_PATH={out_dir}/nv_http_status.json",
        f"NV_STATUS_LEDGER_PATH={out_dir}/nv_http_status.jsonl",
        f"NV_STATE_TRACE_PATH={out_dir}/nv_state_trace.jsonl",
        f"NV_MAB_JOURNAL_PATH={out_dir}/mab_journal.jsonl",
        f"NV_BODY_RULES=",
        str(afl_fuzz),
        "-n",
        "-i", str(seed_path),
        "-o", str(out_dir),
        "--",
        sys.executable,
        str(harness),
    ]

def run_task(task_id: str) -> None:
    """Background thread to run fuzzing task."""
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            return
        command = task["_command"]
        out_dir = Path(task["_out_dir"])
        log_path = Path(task["_log_path"])
        task["status"] = "running"
        task["started_at"] = utc_now()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
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
    except Exception as exc:
        returncode = -1
        with TASK_LOCK:
            task = TASKS.get(task_id)
            if task is not None:
                task["_error"] = str(exc)

    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            return

        # Determine final status
        if task.get("status") == "stopped":
            final_status = "stopped"
        elif returncode == 0:
            final_status = "completed"
        elif returncode == 124:  # timeout exit code
            final_status = "completed"  # timeout is expected completion
        else:
            final_status = "failed"

        task["status"] = final_status
        task["returncode"] = returncode
        task["finished_at"] = utc_now()
        task.pop("_process", None)

def fuzz_test_submit(request: dict[str, Any]) -> dict[str, Any]:
    """Submit a new fuzzing task.

    Required fields:
    - target_type: "http_api" (other types not yet implemented)
    - target_endpoint: endpoint name
    - seed_source: "seed_file" | "manual"
    - seed_location: path to seed(s)
    - mutation_scope: list of "field_value" | "boundary" | "structure"
    - max_test_cases: positive integer
    - time_budget: positive number (seconds)

    Optional fields:
    - task_name: alphanumeric identifier (auto-generated if not provided)

    Returns:
    - process_result: "success" | "error"
    - task_id: unique task identifier (if success)
    - error: error message (if error)
    """
    try:
        validated = validate_submit_request(request)
    except ValueError as exc:
        return {
            "process_result": "error",
            "error": str(exc),
        }

    task_id = uuid.uuid4().hex
    task_name = validated["task_name"]
    out_dir = REPO_ROOT / "out" / f"api_{task_id}_{task_name}"
    log_path = out_dir / "api_task.log"

    try:
        command = build_fuzzing_command(validated, task_id, out_dir)
    except (ValueError, RuntimeError) as exc:
        return {
            "process_result": "error",
            "error": str(exc),
        }

    task = {
        "task_id": task_id,
        "task_name": task_name,
        "status": "created",
        "request": validated,
        "out_dir": str(out_dir.relative_to(REPO_ROOT)),
        "log_path": str(log_path.relative_to(REPO_ROOT)),
        "created_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "returncode": None,
        "_command": command,
        "_out_dir": str(out_dir),
        "_log_path": str(log_path),
    }

    with TASK_LOCK:
        TASKS[task_id] = task

    # Start background execution
    thread = threading.Thread(target=run_task, args=(task_id,), daemon=True)
    thread.start()

    return {
        "process_result": "success",
        "task_id": task_id,
    }

def parse_fuzzer_stats(stats_path: Path) -> dict[str, Any]:
    """Parse fuzzer_stats file into dict."""
    if not stats_path.exists():
        return {}

    stats = {}
    for line in stats_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        stats[key.strip()] = value.strip()
    return stats

def derive_query_description(task: dict[str, Any]) -> str:
    """Derive human-readable query description from task state."""
    status = task["status"]
    request = task.get("request", {})
    endpoint = request.get("target_endpoint", "unknown")

    if status == "created":
        return f"Task created for endpoint '{endpoint}', not yet started"
    elif status == "running":
        started = task.get("started_at", "unknown")
        return f"Task running for endpoint '{endpoint}', started at {started}"
    elif status == "completed":
        return f"Task completed successfully for endpoint '{endpoint}'"
    elif status == "stopped":
        return f"Task stopped by user for endpoint '{endpoint}'"
    elif status == "failed":
        rc = task.get("returncode", "unknown")
        return f"Task failed for endpoint '{endpoint}' with exit code {rc}"
    else:
        return f"Task status: {status}"

def fuzz_test_query(request: dict[str, Any]) -> dict[str, Any]:
    """Query fuzzing task status.

    Required fields:
    - task_id: task identifier from submit

    Returns:
    - process_result: "success" | "error"
    - query_description: human-readable status (if success)
    - task_id: echoed task_id (if success)
    - status: "created" | "running" | "completed" | "stopped" | "failed" | "not_found"
    - Additional metrics derived from fuzzer_stats and eval_report.json
    """
    task_id = request.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return {
            "process_result": "error",
            "error": "task_id is required",
        }

    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            return {
                "process_result": "success",
                "task_id": task_id,
                "status": "not_found",
                "query_description": f"Task {task_id} not found",
            }

        # Build response from task state
        response = {
            "process_result": "success",
            "task_id": task_id,
            "status": task["status"],
            "query_description": derive_query_description(task),
            "created_at": task["created_at"],
            "started_at": task.get("started_at"),
            "finished_at": task.get("finished_at"),
            "out_dir": task["out_dir"],
        }

        # Derive metrics from real fuzzer artifacts (never invent metrics)
        out_dir = Path(task["_out_dir"])
        stats_path = out_dir / "fuzzer_stats"
        eval_path = out_dir / "eval_report.json"

        if stats_path.exists():
            stats = parse_fuzzer_stats(stats_path)
            response["metrics"] = {
                "execs_done": stats.get("execs_done", "0"),
                "bitmap_cvg": stats.get("bitmap_cvg", "0.00%"),
                "valid_exec": stats.get("nv_total_valid_exec", "0"),
                "err_count": stats.get("nv_err_exec", "0"),
                "rec_count": stats.get("nv_rec_success", "0"),
            }

        if eval_path.exists():
            try:
                eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
                response["evaluation"] = {
                    "coverage": eval_data.get("security_state_cov", {}),
                    "validity": eval_data.get("validity", {}),
                    "error": eval_data.get("err", {}),
                    "recovery": eval_data.get("rec", {}),
                }
            except (json.JSONDecodeError, IOError):
                pass

        return response

def fuzz_test_stop(request: dict[str, Any]) -> dict[str, Any]:
    """Stop a running fuzzing task.

    Required fields:
    - task_id: task identifier from submit

    Returns:
    - process_result: "success" | "error"
    - task_id: echoed task_id (if success)
    - status: final task status after stop attempt

    Behavior:
    - Graceful stop via SIGTERM
    - Idempotent for terminal tasks (completed/stopped/failed)
    - Never terminates unrelated processes
    """
    task_id = request.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return {
            "process_result": "error",
            "error": "task_id is required",
        }

    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            return {
                "process_result": "error",
                "error": f"task not found: {task_id}",
            }

        # Idempotent for terminal states
        if task["status"] in ("completed", "stopped", "failed"):
            return {
                "process_result": "success",
                "task_id": task_id,
                "status": task["status"],
                "message": "task already in terminal state",
            }

        proc = task.get("_process")
        if proc is not None and proc.poll() is None:
            # Graceful stop
            try:
                proc.terminate()
                # Wait briefly for graceful shutdown
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            except Exception as exc:
                return {
                    "process_result": "error",
                    "error": f"failed to stop task: {exc}",
                }

            task["status"] = "stopped"
            task["finished_at"] = utc_now()

        return {
            "process_result": "success",
            "task_id": task_id,
            "status": task["status"],
        }

def filter_reports_by_task_id(task_id: str) -> list[dict[str, Any]]:
    """Find reports for specific task_id."""
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            return []

    out_dir = Path(task["_out_dir"])
    if not out_dir.exists():
        return []

    reports = []

    # eval_report.json
    eval_path = out_dir / "eval_report.json"
    if eval_path.exists():
        reports.append({
            "task_id": task_id,
            "task_name": task.get("task_name", ""),
            "report_name": "eval_report.json",
            "generate_time": datetime.fromtimestamp(
                eval_path.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
            "download_url": f"/api/reports/download/{task_id}/eval_report.json",
        })

    # fuzzer_stats
    stats_path = out_dir / "fuzzer_stats"
    if stats_path.exists():
        reports.append({
            "task_id": task_id,
            "task_name": task.get("task_name", ""),
            "report_name": "fuzzer_stats",
            "generate_time": datetime.fromtimestamp(
                stats_path.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
            "download_url": f"/api/reports/download/{task_id}/fuzzer_stats",
        })

    return reports

def filter_reports_by_task_name(task_name: str) -> list[dict[str, Any]]:
    """Find reports matching task_name."""
    reports = []
    with TASK_LOCK:
        for tid, task in TASKS.items():
            if task.get("task_name") == task_name:
                reports.extend(filter_reports_by_task_id(tid))
    return reports

def filter_reports_by_time_range(time_range: dict[str, Any]) -> list[dict[str, Any]]:
    """Find reports within time range.

    time_range format: {"start": "ISO timestamp", "end": "ISO timestamp"}
    """
    try:
        start_str = time_range.get("start")
        end_str = time_range.get("end")

        if not start_str or not end_str:
            raise ValueError("time_range requires both 'start' and 'end'")

        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"invalid time_range format: {exc}") from exc

    reports = []
    with TASK_LOCK:
        for tid, task in TASKS.items():
            created = task.get("created_at")
            if not created:
                continue
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if start_dt <= created_dt <= end_dt:
                    reports.extend(filter_reports_by_task_id(tid))
            except ValueError:
                continue

    return reports

def fuzz_test_report_query(request: dict[str, Any]) -> dict[str, Any]:
    """Query fuzzing reports with filtering.

    At least one filter required:
    - task_id: specific task identifier
    - task_name: task name match
    - time_range: {"start": ISO timestamp, "end": ISO timestamp}

    Returns:
    - process_result: "success" | "error"
    - total_count: number of matching reports
    - report_list: list of report items

    Report item:
    - task_id, task_name, report_name, generate_time, download_url

    Security: download_url paths are validated; path traversal prevented
    """
    task_id = request.get("task_id")
    task_name = request.get("task_name")
    time_range = request.get("time_range")

    if not any([task_id, task_name, time_range]):
        return {
            "process_result": "error",
            "error": "at least one filter required: task_id, task_name, or time_range",
        }

    try:
        if task_id:
            if not isinstance(task_id, str):
                raise ValueError("task_id must be a string")
            reports = filter_reports_by_task_id(task_id)
        elif task_name:
            if not isinstance(task_name, str):
                raise ValueError("task_name must be a string")
            reports = filter_reports_by_task_name(task_name)
        elif time_range:
            if not isinstance(time_range, dict):
                raise ValueError("time_range must be an object")
            reports = filter_reports_by_time_range(time_range)
        else:
            reports = []
    except ValueError as exc:
        return {
            "process_result": "error",
            "error": str(exc),
        }

    return {
        "process_result": "success",
        "total_count": len(reports),
        "report_list": reports,
    }

def get_report_file(task_id: str, report_name: str) -> tuple[bytes | None, str | None]:
    """Safely retrieve report file content.

    Returns (content, error_message).
    Prevents path traversal by validating report_name against whitelist.
    Prevents symlink escapes by checking resolved path stays inside out_dir.
    """
    # Whitelist allowed report names
    allowed_reports = {"eval_report.json", "fuzzer_stats", "fuzzer_stats.csv"}
    if report_name not in allowed_reports:
        return None, f"report not in whitelist: {report_name}"

    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            return None, f"task not found: {task_id}"

    out_dir = Path(task["_out_dir"]).resolve()
    report_path = (out_dir / report_name).resolve()

    # Prevent path traversal and symlink escapes
    try:
        report_path.relative_to(out_dir)
    except ValueError:
        return None, "path traversal attempt detected"

    if not report_path.exists():
        return None, f"report not found: {report_name}"

    # Additional check: verify it's a regular file, not a symlink to outside
    if report_path.is_symlink():
        # Follow symlink and check target is still inside out_dir
        try:
            real_path = report_path.resolve(strict=True)
            real_path.relative_to(out_dir)
        except (ValueError, OSError):
            return None, "symlink escape attempt detected"

    try:
        content = report_path.read_bytes()
        return content, None
    except IOError as exc:
        return None, f"failed to read report: {exc}"

# CLI entry point for testing
def main() -> int:
    """CLI entry point for manual testing."""
    import argparse

    parser = argparse.ArgumentParser(description="Fuzzing Platform API")
    parser.add_argument("command", choices=["submit", "query", "stop", "report_query"])
    parser.add_argument("--request", type=str, help="JSON request string")
    parser.add_argument("--request-file", type=Path, help="JSON request file")

    args = parser.parse_args()

    if args.request:
        request = json.loads(args.request)
    elif args.request_file:
        request = json.loads(args.request_file.read_text(encoding="utf-8"))
    else:
        print("error: --request or --request-file required", file=sys.stderr)
        return 1

    if args.command == "submit":
        response = fuzz_test_submit(request)
    elif args.command == "query":
        response = fuzz_test_query(request)
    elif args.command == "stop":
        response = fuzz_test_stop(request)
    elif args.command == "report_query":
        response = fuzz_test_report_query(request)
    else:
        print(f"error: unknown command: {args.command}", file=sys.stderr)
        return 1

    print(json.dumps(response, indent=2, ensure_ascii=False))
    return 0 if response.get("process_result") == "success" else 1

if __name__ == "__main__":
    raise SystemExit(main())
