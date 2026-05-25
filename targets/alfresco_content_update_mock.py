#!/usr/bin/env python3
"""Local mock target for Alfresco text/plain content update semantics.

This target is intended for short AFL++ mutation-chain smoke only. It does not
contact Alfresco and never treats malformed input as a crash. Inputs are read
from @@ file path or stdin, classified with simple content-update rules, and
recorded to an optional JSONL stats path.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path


MAX_CONTENT_BYTES = 4096
BAD_MARKER = b"__EXPECTED_INVALID_EMPTY_CONTENT__"


def byte_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts: dict[int, int] = {}
    for byte in data:
        counts[byte] = counts.get(byte, 0) + 1
    total = float(len(data))
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def classify_content(data: bytes) -> tuple[bool, str]:
    if not data:
        return False, "empty_content"
    if BAD_MARKER in data:
        return False, "preset_invalid_marker"
    if b"\x00" in data:
        return False, "nul_byte"
    if len(data) > MAX_CONTENT_BYTES:
        return False, "content_too_large"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False, "non_utf8"
    if not text.strip():
        return False, "whitespace_only"
    printable_count = sum(1 for char in text if char.isprintable() or char in "\r\n\t")
    printable_ratio = printable_count / max(len(text), 1)
    if printable_ratio < 0.85:
        return False, "low_printable_ratio"
    if len(data) >= 64 and byte_entropy(data) > 7.2:
        return False, "high_entropy_binary_like"
    return True, "ok"


def read_input() -> bytes:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        return Path(sys.argv[1]).read_bytes()
    return sys.stdin.buffer.read()


def append_stats(valid: bool, reason: str, size: int, latency_ms: int) -> None:
    stats_path = os.environ.get("ALFRESCO_AFL_MOCK_STATS_PATH") or os.environ.get("AFL_MOCK_STATS_PATH")
    if not stats_path:
        return
    record = {
        "valid": valid,
        "reason": reason,
        "content_size": size,
        "latency_ms": latency_ms,
        "ts": int(time.time()),
    }
    with open(stats_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    start = time.perf_counter()
    data = read_input()
    valid, reason = classify_content(data)
    latency_ms = int((time.perf_counter() - start) * 1000)
    append_stats(valid, reason, len(data), latency_ms)
    print(
        json.dumps(
            {
                "target": "alfresco_content_update_mock",
                "valid": valid,
                "reason": reason,
                "content_size": len(data),
                "latency_ms": latency_ms,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
