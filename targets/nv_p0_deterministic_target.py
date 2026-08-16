#!/usr/bin/env python3
"""Deterministic local target for the P0 MAB / security-state feedback tests.

This is NOT a platform experiment target.  It exists so the capability chain

    task/profile -> seed -> NC_MAB arm -> mutation -> validity -> target
    -> security-state feedback -> MAB reward -> fuzzer_stats / eval_report.json

can be exercised end to end without any network dependency and with a
completely reproducible response for a given input.

Two profiles are provided.  Their body schemas and endpoint paths are taken
from the validity rules this repository already ships for the corresponding
real platforms (``validity/o2oa_query_rules.json`` and
``validity/alfresco_metadata_update_rules.json``), so the same capability
chain can be run over two different platform semantics.  They are local
deterministic adapters modelled on those schemas -- they are not the real
O2OA or Alfresco services.

Response classification is a pure function of the request body, so a given
input always yields the same security state.
"""

from __future__ import annotations

import json
import os
import sys
import time
import zlib
from typing import Any


STATUS_PATH = os.getenv("NV_STATUS_PATH", "/tmp/nv_http_status.json")
STATE_LOG = os.getenv("NV_P0_STATE_LOG", "")
PROFILE = os.getenv("NV_P0_PROFILE", "o2oa_cms_doc_list")


# --------------------------------------------------------------------------
# profiles
# --------------------------------------------------------------------------

PROFILES: dict[str, dict[str, Any]] = {
    # modelled on validity/o2oa_query_rules.json :: endpoints.cms_doc_list
    "o2oa_cms_doc_list": {
        "method": "PUT",
        "base": "/x_cms_assemble_control/jaxrs/document/filter/list",
        "required": ["docStatusList", "categoryIdList", "key"],
        "max_string": 256,
        "max_items": 20,
    },
    # modelled on validity/alfresco_metadata_update_rules.json
    "alfresco_metadata_update": {
        "method": "PUT",
        "base": "/alfresco/api/-default-/public/alfresco/versions/1/nodes/meta",
        "required": ["name", "properties"],
        "max_string": 255,
        "max_items": 20,
    },
}

MAX_DEPTH = 3
MAX_KEYS = 12

# The request line is part of the mutated input, so an unconstrained method
# would turn every random byte string into its own "security state".  The
# state space has to stay bounded and meaningful, so anything outside the
# whitelist collapses to a single INVALID method.
KNOWN_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def normalize_method(first_line: str, default: str) -> str:
    parts = first_line.split()
    if not parts:
        return default
    candidate = parts[0].strip().upper()
    return candidate if candidate in KNOWN_METHODS else "INVALID"


def profile() -> dict[str, Any]:
    return PROFILES.get(PROFILE, PROFILES["o2oa_cms_doc_list"])


# --------------------------------------------------------------------------
# request parsing (matches the wire format nv_json_mutator.py emits)
# --------------------------------------------------------------------------

def read_input() -> bytes:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        try:
            with open(sys.argv[1], "rb") as fh:
                return fh.read()
        except OSError:
            return b""
    return sys.stdin.buffer.read()


def split_request(raw: bytes) -> tuple[str, str]:
    """Return (first_line, body). Tolerates a bare JSON body."""
    text = raw.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return "", ""
    first = lines[i].strip()
    if first.startswith("{") or first.startswith("["):
        return "", text
    i += 1
    while i < len(lines) and lines[i].strip():  # headers
        i += 1
    while i < len(lines) and not lines[i].strip():  # blank separator
        i += 1
    return first, "\n".join(lines[i:])


# --------------------------------------------------------------------------
# deterministic classification
# --------------------------------------------------------------------------

def json_depth(value: Any, depth: int = 1) -> int:
    if isinstance(value, dict):
        return max([depth] + [json_depth(v, depth + 1) for v in value.values()])
    if isinstance(value, list):
        return max([depth] + [json_depth(v, depth + 1) for v in value])
    return depth


def route(body: Any, cfg: dict[str, Any]) -> str:
    """Sub-route selected by a discriminator that exists in the real schema."""
    base = cfg["base"]
    if not isinstance(body, dict):
        return base + "/unknown"

    if PROFILE == "o2oa_cms_doc_list":
        status_list = body.get("docStatusList")
        key = body.get("key")
        if isinstance(key, str) and key:
            return base + "/search"
        if isinstance(status_list, list) and status_list:
            return base + "/status"
        return base + "/all"

    props = body.get("properties")
    if isinstance(props, dict):
        if props.get("cm:title") is not None:
            return base + "/title"
        if props.get("cm:description") is not None:
            return base + "/desc"
    return base + "/plain"


def classify(body_text: str, cfg: dict[str, Any]) -> tuple[Any, str, int, str]:
    """Return (parsed_body, path, http_code, reason). Pure function."""
    try:
        body = json.loads(body_text) if body_text.strip() else None
    except Exception:
        return None, cfg["base"] + "/unknown", 400, "parse_error"

    path = route(body, cfg)

    if not isinstance(body, dict):
        return body, path, 400, "not_an_object"

    if path.endswith("/unknown"):
        return body, path, 404, "unroutable"

    missing = [k for k in cfg["required"] if k not in body]
    if missing:
        return body, path, 422, "missing_" + missing[0]

    # structural anomaly -> server side exception
    if json_depth(body) > MAX_DEPTH or len(body) > MAX_KEYS:
        return body, path, 500, "structural_overflow"

    # boundary checks over the fields the real rulesets constrain
    for key, value in body.items():
        if isinstance(value, str) and len(value) > cfg["max_string"]:
            return body, path, 413, "string_too_long_" + key
        if isinstance(value, list) and len(value) > cfg["max_items"]:
            return body, path, 413, "list_too_long_" + key
        if isinstance(value, bool):
            return body, path, 400, "bool_not_allowed_" + key
        if isinstance(value, int) and (value < 0 or value > 2147483647):
            return body, path, 416, "int_out_of_range_" + key

    if PROFILE == "alfresco_metadata_update":
        props = body.get("properties")
        if not isinstance(props, dict):
            return body, path, 400, "properties_not_object"
        title = props.get("cm:title")
        if title is not None and not isinstance(title, str):
            return body, path, 400, "title_type"
        if isinstance(title, str) and len(title) > 200:
            return body, path, 413, "title_too_long"
    else:
        for key in ("docStatusList", "categoryIdList"):
            if not isinstance(body.get(key), list):
                return body, path, 400, key + "_type"
        if not isinstance(body.get("key"), str):
            return body, path, 400, "key_type"

    return body, path, 200, "accepted"


def http_class(code: int) -> str:
    if 200 <= code < 300:
        return "2xx"
    if 300 <= code < 400:
        return "3xx"
    if 400 <= code < 500:
        return "4xx"
    if 500 <= code < 600:
        return "5xx"
    return "other"


def write_status(method: str, path: str, code: int, body_hash16: int,
                 is_exception: int, recovered: int, recover_ms: int) -> None:
    payload = {
        "method": method,
        "path": path,
        "http_code": code,
        "class": http_class(code),
        "timeout": 0,
        "recovered": recovered,
        "latency_ms": 0,
        "body_hash16": body_hash16,
        # deliberately zero: the P0 reward must come from the security state,
        # not from the harness-side coverage proxy.
        "ncov_delta": 0,
        "ncov_total": 0,
        "nall": 0,
        "ts_ms": int(time.time() * 1000),
        "is_exception": is_exception,
        "recover_ms": recover_ms,
    }
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, STATUS_PATH)


def main() -> int:
    cfg = profile()
    raw = read_input()
    first, body_text = split_request(raw)
    method = normalize_method(first, cfg["method"])

    _body, path, code, reason = classify(body_text, cfg)
    cls = http_class(code)
    is_exception = 1 if cls == "5xx" else 0
    recovered = 1 if is_exception else 0
    recover_ms = 1 if is_exception else 0
    body_hash16 = zlib.crc32(body_text.encode("utf-8", errors="ignore")) & 0xFFFF

    write_status(method, path, code, body_hash16, is_exception, recovered,
                 recover_ms)

    if STATE_LOG:
        # NOTE: the selected bandit arm is deliberately not recorded here.
        # afl-fuzz exports NV_CUR_ARM with setenv() in its own process, but
        # the target is spawned from a forkserver created before that call,
        # so the variable never reaches this process.  Arm attribution lives
        # in the fuzzer (NV_JSON_ARM_USED handshake with the in-process
        # Python mutator) and is reported through fuzzer_stats.
        record = {
            "profile": PROFILE,
            "method": method,
            "path": path,
            "http_code": code,
            "class": cls,
            "reason": reason,
            "security_state_id": f"{method} {path}|{cls}",
        }
        with open(STATE_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False,
                                separators=(",", ":")) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
