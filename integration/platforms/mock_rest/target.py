#!/usr/bin/env python3
"""AFL target bridge for the loopback ``mock_rest`` adapter.

The bridge owns only request parsing and the adapter business lifecycle.  AFL++
still allocates validity, status, state, reward, MAB, seed, and report
accounting through its existing environment contracts.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import sys
from dataclasses import replace
from pathlib import Path

from integration.platforms.base import ExecutionIdentity
from integration.platforms.abort import marker_path_from_env, preflight_abort, write_abort_marker
from integration.platforms.mock_rest.adapter import MockRestAdapter
import nv_http_harness
from nv_state_probe import update_state


def _split_request(raw: bytes) -> tuple[str, str, dict[str, str]]:
    text = raw.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    first_index = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first_index is None:
        return "", "", {}
    first = lines[first_index].strip()
    if first.startswith(("{", "[")):
        return "POST /api/items", text, {}
    index = first_index + 1
    while index < len(lines) and lines[index].strip():
        index += 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    headers: dict[str, str] = {}
    for line in lines[first_index + 1:index]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
    return first, "\n".join(lines[index:]), headers


def _read_input() -> bytes:
    source = sys.argv[1] if len(sys.argv) > 1 else "-"
    if source != "-":
        return Path(source).read_bytes()
    return sys.stdin.buffer.read()


def _event(path: str, value: dict) -> None:
    target = os.getenv("DEEP2FUZZ_ADAPTER_EVENTS", "")
    if not target:
        return
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def _notify_supervisor() -> None:
    value = os.getenv("DEEP2FUZZ_SUPERVISOR_PID", "")
    if not value.isdigit() or int(value) <= 0:
        return
    try:
        os.kill(int(value), signal.SIGUSR1)
    except (OSError, ProcessLookupError):
        return


def main() -> int:
    # A terminal marker is checked before reading or interpreting a testcase,
    # constructing the adapter, or making any platform request.  This closes
    # the race between cleanup failure and supervisor process termination.
    prior_abort = preflight_abort()
    if prior_abort is not None:
        _notify_supervisor()
        return 0

    raw = _read_input()
    first, body_text, headers = _split_request(raw)
    parts = first.split()
    method = parts[0].upper() if parts else "POST"
    path = parts[1] if len(parts) > 1 else "/api/items"
    try:
        body = json.loads(body_text) if body_text.strip() else {}
        if not isinstance(body, dict):
            raise ValueError("request body must be an object")
    except (ValueError, json.JSONDecodeError):
        body = {"reject_before_target": True}

    seq = nv_http_harness.next_exec_seq()
    if seq <= 0:
        return 1
    seed_id = headers.get("x-deep2fuzz-seed-id", os.getenv("DEEP2FUZZ_SEED_ID", ""))
    arm_value = headers.get("x-deep2fuzz-mutation-arm", "arm-" + os.getenv("NV_CUR_ARM", "0"))
    arm = arm_value if arm_value.startswith("arm-") else ""
    if not seed_id.startswith("seed-") or len(seed_id) != 17 or any(char not in "0123456789abcdef" for char in seed_id[5:]):
        raise ValueError("core runner must provide the mock seed identity")
    if arm not in {"arm-0", "arm-1", "arm-2"}:
        raise ValueError("AFL++ must provide a valid NV_CUR_ARM")
    identity = ExecutionIdentity(
        os.getenv("DEEP2FUZZ_TASK_ID", "phase1-1-mock"),
        os.getenv("DEEP2FUZZ_RUN_ID", "run"),
        seq,
        seed_id,
        arm,
    )
    # Recheck immediately before adapter construction/contact.  The first
    # check protects the whole invocation; this second check narrows the race
    # if the supervisor publishes abort while testcase parsing is in progress.
    prior_abort = preflight_abort()
    if prior_abort is not None:
        _notify_supervisor()
        return 0
    adapter = MockRestAdapter({"base_url": os.environ["DEEP2FUZZ_MOCK_URL"]})
    operations: list[dict] = []
    created_object_id = None
    cleanup_object_id = None
    absence_verified = False

    if method != "POST" or path != "/api/items":
        result = adapter.interpret_response("create", 404, {"error": "unexpected_route"}, identity)
        cleanup_ok = True
    else:
        result = adapter.create(body, identity)
        operations.append({"operation": "create", "http_code": result.http_code, "success": result.business_success})
        cleanup_ok = True
        if result.business_success and result.object_id:
            object_id = result.object_id
            created_object_id = object_id
            read1 = adapter.readback(object_id, identity)
            operations.append({"operation": "readback", "success": read1.success})
            update_payload = dict(body)
            update_payload["phase1_1_updated"] = True
            updated = adapter.update(object_id, update_payload, identity)
            operations.append({"operation": "update", "http_code": updated.http_code, "success": updated.business_success})
            read2 = adapter.readback(object_id, identity)
            operations.append({"operation": "readback_update", "success": read2.success})
            cleaned = adapter.cleanup(object_id, identity)
            cleanup_object_id = cleaned.object_id
            if cleaned.success:
                absent = adapter.readback(object_id, identity)
                cleanup_ok = bool(cleaned.absent and absent.absent)
                absence_verified = bool(absent.absent)
                operations.append({"operation": "cleanup", "success": True, "absent": absent.absent})
            else:
                cleanup_ok = False
                operations.append({"operation": "cleanup", "success": False, "absent": False})
            if not read1.success or not read2.success:
                result = replace(
                    updated,
                    http_code=200,
                    response_class="2xx",
                    business_success=False,
                    semantic_failure=True,
                    error_kind="readback_mismatch",
                    safe_message="readback did not match the created object",
                )
            result = updated if updated.semantic_failure or not updated.business_success else result

    response_class = result.response_class
    # The final adapter operation is the content update.  Report its stable
    # endpoint template, while the adapter still executes exact object-ID URLs.
    did_update = any(row.get("operation") == "update" for row in operations)
    status_method = "PUT" if did_update and identity.mutation_arm != "arm-0" else method
    response_path = "/api/items/*" if status_method == "PUT" else path
    state = update_state(status_method, response_path, response_class, result.error_kind or ("ok" if result.business_success else "rejected"), "mock_rest")
    _event("adapter", {"identity": identity.__dict__, "operations": operations, "result": {
        "http_code": result.http_code, "response_class": result.response_class,
        "business_success": result.business_success, "expected_rejection": result.expected_rejection,
        "semantic_failure": result.semantic_failure, "object_id_present": bool(result.object_id),
    }, "created_object_id": created_object_id, "cleanup_object_id": cleanup_object_id,
        "absence_verified": absence_verified, "cleanup": cleanup_ok})
    cleanup_abort = not cleanup_ok
    if cleanup_abort:
        marker = marker_path_from_env()
        if marker is not None:
            write_abort_marker(marker, identity.__dict__, object_id=created_object_id, safe_message="cleanup failed")
    original_next_exec_seq = nv_http_harness.next_exec_seq
    original_append_status_record = nv_http_harness.append_status_record
    nv_http_harness.next_exec_seq = lambda: identity.exec_seq

    def append_identified_status(record):
        record.update({
            "task_id": identity.task_id,
            "run_id": identity.run_id,
            "seed_id": identity.seed_id,
            "mutation_arm": identity.mutation_arm,
        })
        return original_append_status_record(record)

    nv_http_harness.append_status_record = append_identified_status
    try:
        nv_http_harness.write_status(
            status_method, response_path, result.http_code,
            body_hash16=int(hashlib.sha256(raw).hexdigest()[:4], 16),
            ncov_delta=int(state.get("ncov_delta", 0)), ncov_total=int(state.get("ncov_total", 0)),
            is_exception=1 if result.semantic_failure else 0,
            validation_reject=0,
        )
    finally:
        nv_http_harness.next_exec_seq = original_next_exec_seq
        nv_http_harness.append_status_record = original_append_status_record
    if cleanup_abort:
        _notify_supervisor()
    return 0 if cleanup_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
