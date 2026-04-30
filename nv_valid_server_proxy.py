#!/usr/bin/env python3
import os, socket, struct, json, re

SOCK = os.getenv("NV_VALID_SOCK", "/tmp/nv_valid.sock")
# 可选：读取 NV_TARGET_CONFIG 里 endpoints 做 allowlist（简单版先写死/或只看 path 格式）
NEED_DOCID = ("/api/doc/submit", "/api/doc/approve", "/api/doc/query")

def score_http(payload: bytes) -> float:
    # 1) 首行
    try:
        text = payload.decode("utf-8", errors="ignore")
    except Exception:
        return 0.0

    lines = text.splitlines()
    # 跳过开头空行
    i0 = 0
    while i0 < len(lines) and lines[i0].strip() == "":
        i0 += 1
    if i0 >= len(lines):
        return 0.0

    first = lines[i0].strip().split()
    if len(first) < 2:
        return 0.0
    method = first[0].upper()
    path = first[1]
    if not path.startswith("/"):
        return 0.0

    # 2) 基础方法白名单
    if method not in ("GET","POST","PUT","DELETE","PATCH"):
        return 0.0

    # 3) body（空行后）
    # 找到第一个空行作为 header/body 分隔
    sep = None
    for j in range(i0+1, len(lines)):
        if lines[j].strip() == "":
            sep = j
            break
    body = "\n".join(lines[sep+1:]).strip() if sep is not None else ""

    s = 0.2  # base

    # 4) docId 规则（submit/approve/query 要求出现 docId）
    if any(path.startswith(x) for x in NEED_DOCID):
        if "docId" not in body:
            return 0.05
        s += 0.35

    # 5) JSON 解析奖励（只要 body 非空且以 {/[ 开头就尝试）
    if body:
        b0 = body.lstrip()[:1]
        if b0 in ("{","["):
            try:
                json.loads(body)
                s += 0.35
            except Exception:
                return 0.1
        else:
            # 非 JSON body：扣分
            return 0.1
    else:
        # 无 body：GET 可以接受，POST/PUT/PATCH 轻扣
        if method in ("POST","PUT","PATCH"):
            s -= 0.1

    # 6) path 形态奖励（更像真实接口）
    if re.match(r"^/api/[a-zA-Z0-9_/]+$", path):
        s += 0.15

    # clamp
    if s < 0.0: s = 0.0
    if s > 1.0: s = 1.0
    return float(s)

def main():
    try:
        os.unlink(SOCK)
    except FileNotFoundError:
        pass

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(SOCK)
    s.listen(64)
    print("[OK] proxy validity listening:", SOCK)

    while True:
        c,_ = s.accept()
        try:
            hdr = c.recv(4)
            if len(hdr) != 4:
                c.close(); continue
            n = struct.unpack("<I", hdr)[0]
            data = b""
            while len(data) < n:
                chunk = c.recv(n-len(data))
                if not chunk:
                    break
                data += chunk

            sc = score_http(data)
            c.sendall(struct.pack("<d", sc))
        finally:
            c.close()

if __name__ == "__main__":
    main()