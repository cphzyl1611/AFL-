#!/usr/bin/env python3
import os
import socket
import struct
import json
import hashlib
import re
from typing import Any

SOCK = os.getenv("NV_VALID_SOCK", "/tmp/nv_valid.sock")
FMT = os.getenv("NV_RPC_FMT", "text").strip().lower()          # text | binary
MAX_IN = int(os.getenv("NV_RPC_MAX_IN", "262144"))             # 256KB
CFG_PATH = os.getenv("NV_TARGET_CONFIG", "").strip()

# ---------------- allowlist / config ----------------
ALLOW = set()
NEED_DOCID = set()


def _load_cfg():
    global ALLOW, NEED_DOCID
    if not CFG_PATH:
        return
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        eps = cfg.get("endpoints", [])
        if not isinstance(eps, list):
            return
        for ep in eps:
            if not isinstance(ep, dict):
                continue
            m = str(ep.get("method", "")).upper().strip()
            p = str(ep.get("path", "")).strip()
            tag = str(ep.get("tag", "")).strip().lower()
            if not m or not p:
                continue
            if not p.startswith("/"):
                p = "/" + p
            ALLOW.add((m, p))

            if (
                "submit" in p.lower()
                or "approve" in p.lower()
                or "query" in p.lower()
                or tag in ("doc_submit", "doc_approve", "doc_query")
            ):
                NEED_DOCID.add((m, p))
    except Exception:
        pass


_load_cfg()

# ---------------- helpers ----------------
SPECIAL_CHARS = set("!@#$%^&*?~|\\/`'\";:<>,+=")
KNOWN_KEYS = {
    "docStatusList",
    "categoryIdList",
    "key",
    "startTime",
    "endTime",
    "calendarIds",
    "credentialList",
}


def recv_exact(conn: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("unexpected EOF")
        data += chunk
    return data


def recv_one(conn: socket.socket) -> bytes:
    conn.settimeout(1.0)
    hdr = recv_exact(conn, 4)
    n = struct.unpack("<I", hdr)[0]
    if n <= 0 or n > MAX_IN:
        raise ValueError(f"invalid payload length: {n}")
    return recv_exact(conn, n)


def send_score(conn: socket.socket, score: float):
    if FMT == "binary":
        conn.sendall(struct.pack("<d", float(score)))
    else:
        conn.sendall(f"{float(score):.6f}\n".encode("ascii"))


def _stable_jitter(buf: bytes, span: float = 0.08) -> float:
    h = hashlib.md5(buf).digest()
    v = int.from_bytes(h[:2], "little") / 65535.0
    return (v - 0.5) * 2.0 * span


def json_depth(x: Any, d: int = 0) -> int:
    if isinstance(x, dict):
        if not x:
            return d + 1
        return max(json_depth(v, d + 1) for v in x.values())
    if isinstance(x, list):
        if not x:
            return d + 1
        return max(json_depth(v, d + 1) for v in x)
    return d + 1


def json_key_count(x: Any) -> int:
    if isinstance(x, dict):
        total = len(x)
        for v in x.values():
            total += json_key_count(v)
        return total
    if isinstance(x, list):
        return sum(json_key_count(v) for v in x)
    return 0


def max_string_len_in_json(x: Any) -> int:
    m = 0

    def walk(v: Any):
        nonlocal m
        if isinstance(v, dict):
            for k, vv in v.items():
                if isinstance(k, str):
                    m = max(m, len(k))
                walk(vv)
        elif isinstance(v, list):
            for vv in v:
                walk(vv)
        elif isinstance(v, str):
            m = max(m, len(v))

    walk(x)
    return m


def _json_shape_score(obj: Any) -> float:
    depth = json_depth(obj)
    key_cnt = json_key_count(obj)
    max_str = max_string_len_in_json(obj)

    list_cnt = 0
    node_cnt = 0

    def walk(v: Any):
        nonlocal list_cnt, node_cnt
        node_cnt += 1
        if isinstance(v, dict):
            for vv in v.values():
                walk(vv)
        elif isinstance(v, list):
            list_cnt += 1
            for vv in v:
                walk(vv)

    walk(obj)

    score = 0.0

    if depth >= 8:
        score += 2.5
    elif depth >= 6:
        score += 1.5
    elif depth >= 4:
        score += 0.6

    if key_cnt >= 80:
        score += 2.0
    elif key_cnt >= 40:
        score += 1.2
    elif key_cnt >= 20:
        score += 0.5

    if node_cnt >= 200:
        score += 1.8
    elif node_cnt >= 80:
        score += 1.0
    elif node_cnt >= 40:
        score += 0.4

    if list_cnt >= 10:
        score += 0.6

    if max_str >= 1024:
        score += 2.0
    elif max_str >= 256:
        score += 1.0
    elif max_str >= 128:
        score += 0.4

    return score


def _max_run_length(s: str) -> int:
    if not s:
        return 0
    best = 1
    cur = 1
    for i in range(1, len(s)):
        if s[i] == s[i - 1]:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 1
    return best


def _special_ratio(s: str) -> float:
    if not s:
        return 0.0
    cnt = sum(1 for ch in s if ch in SPECIAL_CHARS)
    return cnt / max(1, len(s))


def _space_ratio(s: str) -> float:
    if not s:
        return 0.0
    cnt = sum(1 for ch in s if ch.isspace())
    return cnt / max(1, len(s))


def _case_flip_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 2:
        return 0.0
    flips = 0
    for i in range(1, len(letters)):
        if letters[i].islower() != letters[i - 1].islower():
            flips += 1
    return flips / max(1, len(letters) - 1)


def _string_anomaly_score(s: str) -> float:
    if not isinstance(s, str):
        return 0.0
    if s == "":
        return 0.2

    score = 0.0
    n = len(s)

    # 长度
    if n > 256:
        score += 2.0
    elif n > 128:
        score += 1.2
    elif n > 64:
        score += 0.6

    # 连续重复字符
    run = _max_run_length(s)
    if run >= 40:
        score += 1.2
    elif run >= 20:
        score += 0.5
    elif run >= 10:
        score += 0.2

    # 特殊字符密度
    sp = _special_ratio(s)
    if sp >= 0.50:
        score += 2.0
    elif sp >= 0.25:
        score += 1.0
    elif sp >= 0.10:
        score += 0.4

    # 空白字符比例
    sr = _space_ratio(s)
    if sr >= 0.30:
        score += 0.8
    elif sr >= 0.10:
        score += 0.3

    # 大小写交替模式
    cfr = _case_flip_ratio(s)
    if cfr >= 0.80 and n >= 20:
        score += 0.8
    elif cfr >= 0.60 and n >= 12:
        score += 0.4

    # 很窄字符集导致的高重复模式
    unique_cnt = len(set(s))
    if n >= 80 and unique_cnt <= 2:
        score += 0.8
    elif n >= 40 and unique_cnt <= 2:
        score += 0.3

    return score


def _normalize_scalar_for_repeat(v: Any) -> str:
    if isinstance(v, str):
        return f"s:{v}"
    if isinstance(v, bool):
        return f"b:{v}"
    if isinstance(v, (int, float)):
        return f"n:{v}"
    if v is None:
        return "null"
    return f"t:{type(v).__name__}"


def _list_repeat_score(arr: list) -> float:
    if not arr:
        return 0.0

    vals = [_normalize_scalar_for_repeat(v) if not isinstance(v, (dict, list)) else type(v).__name__ for v in arr]
    uniq = len(set(vals))
    total = len(vals)
    max_dup = max(vals.count(v) for v in set(vals))

    score = 0.0

    # 整体重复度
    if total >= 10:
        ratio = max_dup / total
        if ratio >= 0.90:
            score += 1.8
        elif ratio >= 0.70:
            score += 1.0
        elif ratio >= 0.50:
            score += 0.4

    # 规模
    if total >= 20:
        score += 1.0
    elif total >= 10:
        score += 0.4
    elif total >= 5:
        score += 0.1

    # 元素本身异常
    weird_items = 0
    long_items = 0
    for item in arr[:30]:
        if isinstance(item, str):
            if len(item) > 64:
                long_items += 1
            if _special_ratio(item) > 0.20:
                weird_items += 1
            if _max_run_length(item) >= 8:
                weird_items += 1

    if long_items >= 3:
        score += 1.0
    elif long_items >= 1:
        score += 0.4

    if weird_items >= 5:
        score += 1.0
    elif weird_items >= 2:
        score += 0.5

    return score


def _key_name_weird_score(key: str) -> float:
    if not isinstance(key, str):
        return 0.0
    if re.match(r"^[A-Za-z0-9_\-\u4e00-\u9fff]+$", key):
        return 0.0
    if re.match(r"^[A-Za-z0-9_\-]+$", key):
        return 0.0
    return 0.5


def score_mock(buf: bytes) -> float:
    """
    body-only 模式评分：
    分数越高 => 越异常/无效
    """
    try:
        text = buf.decode("utf-8", errors="strict").strip()
    except Exception:
        return 10.0

    if not text:
        return 2.5

    if not (text.startswith("{") or text.startswith("[")):
        return 8.0

    try:
        obj = json.loads(text)
    except Exception:
        return 6.0

    if not isinstance(obj, (dict, list)):
        return 7.0

    sc = 0.1
    sc += 0.5 * _json_shape_score(obj)

    long_string_fields = 0
    suspicious_string_fields = 0
    large_list_fields = 0
    repeated_list_fields = 0
    unknown_cnt = 0

    if isinstance(obj, dict):
        keys = set(obj.keys())
        unknown_cnt = sum(1 for k in keys if k not in KNOWN_KEYS)

        if unknown_cnt >= 5:
            sc += 2.0
        elif unknown_cnt >= 3:
            sc += 1.2
        elif unknown_cnt >= 1:
            sc += 0.4

        weird_key_cnt = 0
        empty_str_cnt = 0

        for k, v in obj.items():
            if isinstance(k, str):
                weird_key_cnt += 1 if _key_name_weird_score(k) > 0 else 0
                sc += _key_name_weird_score(k)

            if isinstance(v, str):
                if v == "":
                    empty_str_cnt += 1
                ss = _string_anomaly_score(v)
                sc += ss

                if len(v) > 64:
                    long_string_fields += 1
                if ss >= 0.8:
                    suspicious_string_fields += 1

                # key 字段更敏感一些
                if k == "key":
                    if len(v) > 128:
                        sc += 0.5
                    if len(v) > 192:
                        sc += 0.8
                    if _special_ratio(v) >= 0.20:
                        sc += 0.6
                    if _max_run_length(v) >= 20:
                        sc += 0.4

            elif isinstance(v, list):
                ls = _list_repeat_score(v)
                sc += ls

                if len(v) >= 10:
                    large_list_fields += 1
                if ls >= 0.8:
                    repeated_list_fields += 1

                # 对当前 O2OA 相关字段稍微加一点敏感度
                if k in ("docStatusList", "categoryIdList", "calendarIds", "credentialList"):
                    if len(v) >= 10:
                        sc += 0.1
                    if len(v) >= 20:
                        sc += 0.3

            elif isinstance(v, dict):
                if len(v) > 10:
                    sc += 0.8

        if empty_str_cnt >= 2:
            sc += 0.6
        elif empty_str_cnt == 1:
            sc += 0.2

        if weird_key_cnt >= 2:
            sc += 0.8
        elif weird_key_cnt == 1:
            sc += 0.3

        # 类型异常的额外惩罚
        if "docStatusList" in obj and not isinstance(obj.get("docStatusList"), list):
            sc += 2.0
        if "categoryIdList" in obj and not isinstance(obj.get("categoryIdList"), list):
            sc += 2.0
        if "key" in obj and not isinstance(obj.get("key"), str):
            sc += 2.0

        # 多字段组合异常：这是这版增强的关键
        if long_string_fields >= 1 and large_list_fields >= 1:
            sc += 0.3
        if suspicious_string_fields >= 1 and repeated_list_fields >= 1:
            sc += 0.4
        if repeated_list_fields >= 2:
            sc += 0.3
        if repeated_list_fields >= 2:
            sc += 0.3
        if unknown_cnt >= 2 and suspicious_string_fields >= 1:
            sc += 0.3

    elif isinstance(obj, list):
        sc += _list_repeat_score(obj)
        if len(obj) >= 20:
            sc += 0.8
        elif len(obj) >= 10:
            sc += 0.3

    # 保留极小稳定扰动，避免完全相同分数过多
    sc += _stable_jitter(buf, span=0.05)

    # 下限保护
    if sc < 0.1:
        sc = 0.1

    return float(sc)


def serve():
    try:
        os.unlink(SOCK)
    except FileNotFoundError:
        pass

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(SOCK)
    os.chmod(SOCK, 0o666)
    s.listen(16)
    print(f"[OK] nv_valid_server_mock listening: {SOCK} (fmt={FMT}) allow={len(ALLOW)}", flush=True)

    while True:
        conn, _ = s.accept()
        with conn:
            try:
                buf = recv_one(conn)
                sc = score_mock(buf)
                send_score(conn, sc)
            except Exception:
                # 让客户端按 rpc_fail 处理
                pass


if __name__ == "__main__":
    serve()