#!/usr/bin/env python3
"""Local mock target for Alfresco metadata_update application/json semantics.

This target is for short AFL++ smoke only. It parses one @@ file or stdin,
classifies JSON metadata with deterministic local rules, and never contacts a
real Alfresco service.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any


ALLOWED_FIELDS = {"name", "title", "description", "properties"}
MAX_NAME_LEN = 255
MAX_TITLE_LEN = 512
MAX_DESCRIPTION_LEN = 4096
MAX_PROPERTY_STRING_LEN = 4096
MAX_PAYLOAD_BYTES = 8192


def classify_metadata(data: bytes) -> tuple[bool, str]:
    if not data:
        return False, "empty_payload"
    if len(data) > MAX_PAYLOAD_BYTES:
        return False, "payload_too_large"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False, "non_utf8"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return False, "invalid_json"
    if not isinstance(payload, dict):
        return False, "not_object"

    unknown_fields = set(payload) - ALLOWED_FIELDS
    if unknown_fields:
        return False, "unknown_field"

    for field, max_len in (
        ("name", MAX_NAME_LEN),
        ("title", MAX_TITLE_LEN),
        ("description", MAX_DESCRIPTION_LEN),
    ):
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, str):
            return False, f"invalid_{field}_type"
        if len(value) > max_len:
            return False, f"{field}_too_long"

    properties = payload.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            return False, "invalid_properties_type"
        for key, value in properties.items():
            if not isinstance(key, str):
                return False, "invalid_property_key_type"
            if not isinstance(value, (str, int, float, bool)) and value is not None:
                return False, "invalid_property_value_type"
            if isinstance(value, str) and len(value) > MAX_PROPERTY_STRING_LEN:
                return False, "property_value_too_long"

    return True, "valid"


def read_input() -> bytes:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        return Path(sys.argv[1]).read_bytes()
    return sys.stdin.buffer.read()


def append_stats(valid: bool, reason: str, size: int, latency_ms: int) -> None:
    stats_path = os.environ.get("ALFRESCO_METADATA_AFL_MOCK_STATS_PATH") or os.environ.get("AFL_MOCK_STATS_PATH")
    if not stats_path:
        return
    record = {
        "scenario": "metadata_update",
        "valid": valid,
        "reason": reason,
        "payload_size": size,
        "latency_ms": latency_ms,
        "ts": int(time.time()),
    }
    with open(stats_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    start = time.perf_counter()
    data = read_input()
    valid, reason = classify_metadata(data)
    latency_ms = int((time.perf_counter() - start) * 1000)
    append_stats(valid, reason, len(data), latency_ms)
    print(
        json.dumps(
            {
                "target": "alfresco_metadata_update_mock",
                "scenario": "metadata_update",
                "valid": valid,
                "reason": reason,
                "payload_size": len(data),
                "latency_ms": latency_ms,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
