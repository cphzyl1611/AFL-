#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, json, os, signal, socket, sys, time
from typing import Any, Dict, List

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

def pick_first(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return v
    return None

def deep_get(d: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def main():
    ap = argparse.ArgumentParser(description="Generic protocol harness for AFL++ (profile + env fallback)")
    ap.add_argument("--profile", default="", help="path to profile.json")
    ap.add_argument("--host", default="", help="override host")
    ap.add_argument("--port", type=int, default=0, help="override port")
    ap.add_argument("--transport", default="", help="tcp or udp")
    ap.add_argument("--timeout-ms", type=int, default=0, help="override timeout ms")
    ap.add_argument("input", nargs="?", default="-", help="@@ file path or '-' for stdin")
    args = ap.parse_args()

    prof: Dict[str, Any] = {}
    if args.profile:
        prof = load_json_file(args.profile)

    proto = prof.get("proto") or {}

    transport = pick_first(args.transport, proto.get("transport"), os.getenv("FUZZ_PROTO", "tcp")) or "tcp"
    host = pick_first(args.host, proto.get("host"), os.getenv("FUZZ_PROTO_HOST", "127.0.0.1")) or "127.0.0.1"
    port = pick_first(args.port if args.port > 0 else None, proto.get("port"), int(os.getenv("FUZZ_PROTO_PORT", "9000"))) or 9000

    timeout_ms = pick_first(args.timeout_ms if args.timeout_ms > 0 else None,
                            prof.get("timeout_ms"),
                            int(os.getenv("FUZZ_TIMEOUT_MS", "2000"))) or 2000
    timeout = float(timeout_ms) / 1000.0

    expect_reply = bool(pick_first(proto.get("expect_reply"), os.getenv("FUZZ_EXPECT_REPLY", "1") == "1") or True)
    recv_bytes = int(pick_first(proto.get("recv_bytes"), int(os.getenv("FUZZ_RECV_BYTES", "4096"))) or 4096)

    policy = prof.get("policy") or {}
    timeout_as_hang = bool(pick_first(policy.get("timeout_as_hang"), os.getenv("FUZZ_TIMEOUT_AS_HANG", "1") == "1") or True)
    conn_error_as_crash = bool(pick_first(policy.get("conn_error_as_crash"), os.getenv("FUZZ_CONN_ERR_AS_CRASH", "1") == "1") or True)

    payload = read_input_bytes([sys.argv[0], args.input])

    try:
        if transport.lower() == "udp":
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(timeout)
            s.sendto(payload, (host, port))
            if expect_reply:
                _ = s.recvfrom(recv_bytes)
            s.close()
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            s.sendall(payload)
            if expect_reply:
                _ = s.recv(recv_bytes)
            s.close()

    except socket.timeout:
        if timeout_as_hang:
            time.sleep(timeout + 2.0)
            return 0
        die_as_crash("timeout")
        return 0

    except Exception as e:
        if conn_error_as_crash:
            die_as_crash(f"conn_error:{e}")
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())
