"""Run-scoped, fail-closed abort marker for platform execution.

The marker is deliberately separate from AFL++ accounting.  It only prevents
new adapter contact after a business lifecycle failure and lets the supervisor
terminate the bounded campaign while preserving the evidence already written.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


_REQUIRED_IDENTITY = ("task_id", "run_id", "exec_seq", "seed_id", "mutation_arm")


def marker_path_from_env() -> Path | None:
    value = os.environ.get("DEEP2FUZZ_ABORT_MARKER", "").strip()
    return Path(value) if value else None


def read_abort_marker(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    marker = Path(path)
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("terminal") is not True:
        return None
    if payload.get("reason") != "CLEANUP_FAILED":
        return None
    if any(key not in payload for key in _REQUIRED_IDENTITY):
        return None
    if not isinstance(payload.get("exec_seq"), int) or payload["exec_seq"] <= 0:
        return None
    return payload


def write_abort_marker(
    path: str | Path,
    identity: Mapping[str, Any],
    *,
    object_id: str | None = None,
    safe_message: str = "cleanup failed",
) -> dict[str, Any]:
    """Atomically publish a sanitized terminal marker.

    Object identifiers are hashed because a marker is control metadata, not a
    business evidence dump.  The first valid terminal marker wins.
    """
    missing = [key for key in _REQUIRED_IDENTITY if key not in identity]
    if missing:
        raise ValueError(f"missing abort identity: {', '.join(missing)}")
    if isinstance(identity["exec_seq"], bool) or not isinstance(identity["exec_seq"], int) or identity["exec_seq"] <= 0:
        raise ValueError("abort exec_seq must be positive")
    marker = Path(path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    existing = read_abort_marker(marker)
    if existing is not None:
        return existing
    payload: dict[str, Any] = {
        "terminal": True,
        "reason": "CLEANUP_FAILED",
        "task_id": str(identity["task_id"]),
        "run_id": str(identity["run_id"]),
        "exec_seq": int(identity["exec_seq"]),
        "seed_id": str(identity["seed_id"]),
        "mutation_arm": str(identity["mutation_arm"]),
        "source": "platform_adapter",
        "safe_message": str(safe_message),
    }
    if object_id is not None:
        payload["object_id_sha256"] = hashlib.sha256(str(object_id).encode("utf-8")).hexdigest()

    fd, temporary = tempfile.mkstemp(prefix=f".{marker.name}.", suffix=".tmp", dir=marker.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, marker)
        try:
            directory_fd = os.open(marker.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return payload


def record_abort_observation(payload: Mapping[str, Any]) -> None:
    destination = os.environ.get("DEEP2FUZZ_ABORT_OBSERVATIONS", "").strip()
    if not destination:
        return
    observation = {"terminal": True, "reason": str(payload.get("reason", "CLEANUP_FAILED")), "action": "platform_contact_skipped"}
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(observation, sort_keys=True, separators=(",", ":")) + "\n")


def preflight_abort() -> dict[str, Any] | None:
    payload = read_abort_marker(marker_path_from_env())
    if payload is not None:
        record_abort_observation(payload)
    return payload
