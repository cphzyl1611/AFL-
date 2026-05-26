#!/usr/bin/env python3
"""Local mock target for Alfresco multipart_upload semantics.

This target is intended for short AFL++ online-filter smoke only. It parses one
@@ file or stdin as a small multipart/form-data upload, classifies it with local
rules, and never contacts a real Alfresco service.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any


MAX_BODY_BYTES = 16384
MAX_FILE_BYTES = 4096
ALLOWED_CONTENT_TYPES = {"", "text/plain", "application/octet-stream", "application/json"}
FILE_FIELD_NAMES = {"filedata", "file"}
BOUNDARY_RE = re.compile(br'boundary="?([^";\r\n]+)"?', re.IGNORECASE)
PARAM_RE = re.compile(r'([A-Za-z0-9_-]+)="?([^";]*)"?')


def byte_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts: dict[int, int] = {}
    for byte in data:
        counts[byte] = counts.get(byte, 0) + 1
    total = float(len(data))
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _detect_boundary(data: bytes) -> tuple[bytes | None, str]:
    header_match = BOUNDARY_RE.search(data[:1024])
    if header_match:
        return header_match.group(1).strip(), ""

    for line in data.splitlines()[:20]:
        stripped = line.strip()
        if not stripped.startswith(b"--") or stripped in {b"--", b"----"}:
            continue
        token = stripped[2:]
        if token.endswith(b"--"):
            token = token[:-2]
        token = token.strip()
        if token:
            return token, ""
    return None, "missing_boundary"


def _boundary_is_valid(boundary: bytes) -> bool:
    if not boundary or len(boundary) > 70:
        return False
    return not any(byte <= 32 or byte >= 127 for byte in boundary)


def _parse_header_params(value: str) -> dict[str, str]:
    return {key: val for key, val in PARAM_RE.findall(value)}


def _decode_headers(raw_headers: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    text = raw_headers.decode("utf-8", errors="replace")
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def _is_binary_noise(content: bytes) -> bool:
    if b"\x00" in content:
        return True
    if len(content) >= 64 and byte_entropy(content) > 7.2:
        return True
    decoded = content.decode("utf-8", errors="replace")
    if not decoded:
        return False
    printable = sum(1 for char in decoded if char.isprintable() or char in "\r\n\t")
    return printable / max(len(decoded), 1) < 0.85


def analyze_multipart_upload(data: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {
        "valid": False,
        "reason": "",
        "filename": "",
        "content_type": "",
        "content": b"",
        "fields": {},
    }

    if not data:
        result["reason"] = "empty_body"
        return result
    if len(data) > MAX_BODY_BYTES:
        result["reason"] = "too_large"
        return result
    if b"\x00" in data:
        result["reason"] = "invalid_encoding"
        return result

    boundary, boundary_error = _detect_boundary(data)
    if boundary is None:
        result["reason"] = boundary_error
        return result
    if not _boundary_is_valid(boundary):
        result["reason"] = "invalid_boundary"
        return result

    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    delimiter = b"--" + boundary
    if delimiter not in normalized:
        result["reason"] = "invalid_boundary"
        return result

    chunks = normalized.split(delimiter)
    if len(chunks) < 3 or not any(chunk.startswith(b"--") for chunk in chunks[1:]):
        result["reason"] = "invalid_boundary"
        return result

    found_file_field_without_filename = False
    fields: dict[str, str] = {}

    for raw_chunk in chunks[1:]:
        if raw_chunk.startswith(b"--"):
            break
        chunk = raw_chunk.lstrip(b"\n")
        if not chunk.strip():
            continue
        if b"\n\n" not in chunk:
            continue
        raw_headers, body = chunk.split(b"\n\n", 1)
        headers = _decode_headers(raw_headers)
        disposition = headers.get("content-disposition", "")
        params = _parse_header_params(disposition)
        field_name = params.get("name", "")
        filename = params.get("filename", "")
        content_type = headers.get("content-type", "").strip().lower()
        content = body.rstrip(b"\n")

        if field_name in FILE_FIELD_NAMES:
            if not filename:
                found_file_field_without_filename = True
                continue
            result["filename"] = filename
            result["content_type"] = content_type
            result["content"] = content
            result["fields"] = fields
            break

        if field_name:
            try:
                fields[field_name] = content.decode("utf-8").strip()
            except UnicodeDecodeError:
                fields[field_name] = ""

    if not result["filename"]:
        result["reason"] = "missing_filename" if found_file_field_without_filename else "missing_file_part"
        result["fields"] = fields
        return result

    filename_value = str(result["filename"])
    if "/" in filename_value or "\\" in filename_value or "\x00" in filename_value:
        result["reason"] = "invalid_filename"
        result["fields"] = fields
        return result

    content_type_value = str(result["content_type"])
    if content_type_value not in ALLOWED_CONTENT_TYPES:
        result["reason"] = "invalid_content_type"
        result["fields"] = fields
        return result

    content_bytes = bytes(result["content"])
    if not content_bytes:
        result["reason"] = "empty_file"
        result["fields"] = fields
        return result
    if len(content_bytes) > MAX_FILE_BYTES:
        result["reason"] = "too_large"
        result["fields"] = fields
        return result

    if content_type_value in {"text/plain", "application/json"}:
        try:
            decoded = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            result["reason"] = "invalid_encoding"
            result["fields"] = fields
            return result
        if not decoded.strip():
            result["reason"] = "empty_file"
            result["fields"] = fields
            return result
        if _is_binary_noise(content_bytes):
            result["reason"] = "invalid_encoding"
            result["fields"] = fields
            return result
        if content_type_value == "application/json":
            try:
                json.loads(decoded)
            except json.JSONDecodeError:
                result["reason"] = "invalid_encoding"
                result["fields"] = fields
                return result
    elif _is_binary_noise(content_bytes):
        result["reason"] = "invalid_encoding"
        result["fields"] = fields
        return result

    result["valid"] = True
    result["reason"] = "valid"
    result["fields"] = fields
    return result


def classify_multipart_upload(data: bytes) -> tuple[bool, str]:
    analysis = analyze_multipart_upload(data)
    return bool(analysis["valid"]), str(analysis["reason"])


def read_input() -> bytes:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        return Path(sys.argv[1]).read_bytes()
    return sys.stdin.buffer.read()


def append_stats(analysis: dict[str, Any], size: int, latency_ms: int) -> None:
    stats_path = os.environ.get("ALFRESCO_MULTIPART_AFL_MOCK_STATS_PATH") or os.environ.get("AFL_MOCK_STATS_PATH")
    if not stats_path:
        return
    record = {
        "scenario": "multipart_upload",
        "valid": bool(analysis.get("valid")),
        "reason": analysis.get("reason"),
        "payload_size": size,
        "filename_detected": analysis.get("filename", ""),
        "content_type_detected": analysis.get("content_type", ""),
        "latency_ms": latency_ms,
        "ts": int(time.time()),
    }
    with open(stats_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    start = time.perf_counter()
    data = read_input()
    analysis = analyze_multipart_upload(data)
    latency_ms = int((time.perf_counter() - start) * 1000)
    append_stats(analysis, len(data), latency_ms)
    print(
        json.dumps(
            {
                "target": "alfresco_multipart_upload_mock",
                "scenario": "multipart_upload",
                "valid": bool(analysis.get("valid")),
                "reason": analysis.get("reason"),
                "payload_size": len(data),
                "filename_detected": analysis.get("filename", ""),
                "content_type_detected": analysis.get("content_type", ""),
                "latency_ms": latency_ms,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0 if analysis.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
