#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, json, os, signal, sys, time
from typing import Any, Dict, List

import requests


def die_as_crash(reason: str) -> None:
    os.kill(os.getpid(), signal.SIGSEGV)


def read_input_bytes(argv: List[str]) -> bytes:
    if len(argv) >= 2 and argv[-1] != "-" and os.path.isfile(argv[-1]):
        with open(argv[-1], "rb") as f:
            return f.read()
    return sys.stdin.buffer.read()


def load_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def env_json(name: str, default: Any) -> Any:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return json.loads(v)
    except Exception:
        return default


def merge_dict(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    out.update(b or {})
    return out


def deep_get(d: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def pick_first(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return v
    return None


def main():
    ap = argparse.ArgumentParser(description="Generic upload harness for AFL++ (profile + env fallback)")
    ap.add_argument("--profile", default="", help="path to profile.json")
    ap.add_argument("--endpoint", default="", help="override endpoint URL")
    ap.add_argument("--timeout-ms", type=int, default=0, help="override timeout ms")
    ap.add_argument("input", nargs="?", default="-", help="@@ file path or '-' for stdin")
    args = ap.parse_args()

    prof: Dict[str, Any] = {}
    if args.profile:
        prof = load_json_file(args.profile)

    endpoint = pick_first(args.endpoint, prof.get("endpoint"), os.getenv("FUZZ_TARGET_ENDPOINT", "").strip())
    if not endpoint:
        print("endpoint is empty", file=sys.stderr)
        return 2

    timeout_ms = pick_first(args.timeout_ms if args.timeout_ms > 0 else None,
                            prof.get("timeout_ms"),
                            int(os.getenv("FUZZ_TIMEOUT_MS", "5000"))) or 5000
    timeout = float(timeout_ms) / 1000.0

    headers = merge_dict(env_json("FUZZ_HTTP_HEADERS_JSON", {}), prof.get("headers") or {})

    bearer = pick_first(deep_get(prof, ["auth", "bearer"], ""), os.getenv("FUZZ_AUTH_BEARER", "").strip()) or ""
    if bearer:
        headers.setdefault("Authorization", f"Bearer {bearer}")

    cookies = merge_dict(env_json("FUZZ_HTTP_COOKIES_JSON", {}), deep_get(prof, ["auth", "cookies"], {}) or {})

    upload = prof.get("upload") or {}
    field = pick_first(upload.get("field"), os.getenv("FUZZ_UPLOAD_FIELD", "file")) or "file"
    filename = pick_first(upload.get("filename"), os.getenv("FUZZ_UPLOAD_FILENAME", "fuzz.bin")) or "fuzz.bin"
    mime = pick_first(upload.get("mime"), os.getenv("FUZZ_UPLOAD_MIME", "application/octet-stream")) or "application/octet-stream"
    extra_form = merge_dict(env_json("FUZZ_UPLOAD_FORM_JSON", {}), upload.get("extra_form") or {})

    policy = prof.get("policy") or {}
    crash_on_5xx = bool(pick_first(policy.get("crash_on_5xx"), os.getenv("FUZZ_CRASH_ON_5XX", "1") == "1") or True)
    timeout_as_hang = bool(pick_first(policy.get("timeout_as_hang"), os.getenv("FUZZ_TIMEOUT_AS_HANG", "1") == "1") or True)
    conn_error_as_crash = bool(pick_first(policy.get("conn_error_as_crash"), os.getenv("FUZZ_CONN_ERR_AS_CRASH", "1") == "1") or True)
    bad_keywords = pick_first(policy.get("bad_keywords"), env_json("FUZZ_BAD_KEYWORDS_JSON", None)) or ["Traceback", "Exception", "ERROR"]

    file_bytes = read_input_bytes([sys.argv[0], args.input])

    try:
        files = {field: (filename, file_bytes, mime)}
        r = requests.post(endpoint, data=extra_form, files=files,
                          headers=headers, cookies=cookies,
                          timeout=timeout, verify=False, allow_redirects=False)
        status = r.status_code
        resp = r.content[:4096]

    except requests.Timeout:
        if timeout_as_hang:
            time.sleep(timeout + 2.0)
            return 0
        die_as_crash("timeout")
        return 0

    except Exception as e:
        if conn_error_as_crash:
            die_as_crash(f"conn_error:{e}")
        return 0

    # 上传接口很多 4xx 属于无效样本，不当 crash
    if status in [400, 401, 403, 404, 405, 415, 422, 429, 301, 302]:
        return 0

    if crash_on_5xx and 500 <= status <= 599:
        die_as_crash(f"http_{status}")

    text = resp.decode("utf-8", errors="ignore")
    for kw in bad_keywords:
        if kw and kw in text:
            die_as_crash(f"kw:{kw}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
