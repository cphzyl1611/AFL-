#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, json, os, signal, sys, time
from typing import Any, Dict, List, Optional

try:
    import requests
except Exception:
    requests = None


def die_as_crash(reason: str) -> None:
    # 让 AFL++ 记录为 crash（SIGSEGV=11）
    os.kill(os.getpid(), signal.SIGSEGV)


def read_input_bytes(argv: List[str]) -> bytes:
    # 支持 @@ 或 stdin（argv 最后一个参数若为文件路径）
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


def deep_get(d: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def merge_dict(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    # b 覆盖 a（浅合并足够应对 headers/cookies 等）
    out = dict(a)
    out.update(b or {})
    return out


def pick_first(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return v
    return None


def main():
    ap = argparse.ArgumentParser(description="Generic HTTP harness for AFL++ (profile + env fallback)")
    ap.add_argument("--profile", default="", help="path to profile.json")
    ap.add_argument("--endpoint", default="", help="override endpoint URL")
    ap.add_argument("--method", default="", help="override HTTP method")
    ap.add_argument("--timeout-ms", type=int, default=0, help="override timeout ms")
    ap.add_argument("input", nargs="?", default="-", help="@@ file path or '-' for stdin")
    args = ap.parse_args()

    prof: Dict[str, Any] = {}
    if args.profile:
        prof = load_json_file(args.profile)

    # 统一读取：CLI > profile > env > default
    endpoint = pick_first(
        args.endpoint,
        prof.get("endpoint"),
        os.getenv("FUZZ_TARGET_ENDPOINT", "").strip()
    )
    if not endpoint:
        print("endpoint is empty (use --endpoint / profile.endpoint / FUZZ_TARGET_ENDPOINT)", file=sys.stderr)
        return 2

    method = pick_first(
        args.method.upper() if args.method else "",
        (prof.get("method") or "").upper(),
        os.getenv("FUZZ_HTTP_METHOD", "POST").upper()
    ) or "POST"

    timeout_ms = pick_first(
        args.timeout_ms if args.timeout_ms > 0 else None,
        prof.get("timeout_ms"),
        int(os.getenv("FUZZ_TIMEOUT_MS", "2000"))
    ) or 2000
    timeout = float(timeout_ms) / 1000.0

    # headers / auth
    headers = merge_dict(env_json("FUZZ_HTTP_HEADERS_JSON", {}), prof.get("headers") or {})
    # 如果都没给，默认 JSON
    headers.setdefault("Content-Type", "application/json")

    bearer = pick_first(
        deep_get(prof, ["auth", "bearer"], ""),
        os.getenv("FUZZ_AUTH_BEARER", "").strip()
    ) or ""
    if bearer:
        headers.setdefault("Authorization", f"Bearer {bearer}")

    cookies = merge_dict(env_json("FUZZ_HTTP_COOKIES_JSON", {}), deep_get(prof, ["auth", "cookies"], {}) or {})

    policy = prof.get("policy") or {}
    strict_json = bool(pick_first(policy.get("strict_json"), os.getenv("FUZZ_STRICT_JSON", "") == "1") or False)
    crash_on_5xx = bool(pick_first(policy.get("crash_on_5xx"), os.getenv("FUZZ_CRASH_ON_5XX", "1") == "1") or True)
    timeout_as_hang = bool(pick_first(policy.get("timeout_as_hang"), os.getenv("FUZZ_TIMEOUT_AS_HANG", "1") == "1") or True)
    conn_error_as_crash = bool(pick_first(policy.get("conn_error_as_crash"), os.getenv("FUZZ_CONN_ERR_AS_CRASH", "1") == "1") or True)

    bad_keywords = pick_first(policy.get("bad_keywords"), env_json("FUZZ_BAD_KEYWORDS_JSON", None))
    if not bad_keywords:
        bad_keywords = ["Traceback", "Exception", "NullPointer", "StackOverflow", "panic", "ERROR"]

    invalid_status_as_invalid = pick_first(policy.get("invalid_status_as_invalid"), env_json("FUZZ_INVALID_STATUS_JSON", None))
    if invalid_status_as_invalid is None:
        invalid_status_as_invalid = [400, 401, 403, 404, 405, 415, 422, 429, 301, 302]

    http_cfg = prof.get("http") or {}
    data_mode = pick_first(http_cfg.get("data_mode"), os.getenv("FUZZ_HTTP_DATA_MODE", "raw")) or "raw"
    query_params = merge_dict(env_json("FUZZ_HTTP_QUERY_JSON", {}), http_cfg.get("query_params") or {})
    extra_form = merge_dict(env_json("FUZZ_HTTP_FORM_JSON", {}), http_cfg.get("extra_form") or {})

    body = read_input_bytes([sys.argv[0], args.input])

    # strict JSON：解析失败直接丢弃（exit 0），避免全是 400 垃圾样本
    if strict_json:
        try:
            json.loads(body.decode("utf-8"))
        except Exception:
            return 0

    if requests is None:
        print("requests not installed: pip3 install requests", file=sys.stderr)
        return 2

    try:
        if data_mode == "json":
            # 尝试把 body 当 JSON（失败则丢弃）
            try:
                j = json.loads(body.decode("utf-8", errors="strict"))
            except Exception:
                return 0
            r = requests.request(method, endpoint, json=j, params=query_params,
                                 headers=headers, cookies=cookies, timeout=timeout,
                                 verify=False, allow_redirects=False)
        elif data_mode == "form":
            # body 作为表单某个字段也行：这里把 body 放进 "payload"
            form = dict(extra_form)
            form["payload"] = body.decode("utf-8", errors="ignore")
            r = requests.request(method, endpoint, data=form, params=query_params,
                                 headers=headers, cookies=cookies, timeout=timeout,
                                 verify=False, allow_redirects=False)
        else:
            # raw bytes 直接作为 body
            r = requests.request(method, endpoint, data=body, params=query_params,
                                 headers=headers, cookies=cookies, timeout=timeout,
                                 verify=False, allow_redirects=False)

        status = r.status_code
        resp = r.content[:4096]

    except requests.Timeout:
        if timeout_as_hang:
            time.sleep(timeout + 2.0)  # 交给 AFL++ -t 判 hang
            return 0
        die_as_crash("timeout")
        return 0

    except Exception as e:
        if conn_error_as_crash:
            die_as_crash(f"conn_error:{e}")
        return 0

    # 把常见“无效响应”视为无效样本（exit 0），别误报成 crash
    if status in invalid_status_as_invalid:
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
