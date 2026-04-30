#!/usr/bin/env python3
import os, socket, struct, json

SOCK="/tmp/nv_valid.sock"

def score_rule(payload: bytes) -> float:
    # 规则占位：能 parse JSON body -> 低分；否则高分
    try:
        s = payload.decode("utf-8", errors="ignore")
        # 简单抓 body
        if "\n\n" in s:
            body = s.split("\n\n",1)[1].strip()
        else:
            body = ""
        if body.startswith("{") or body.startswith("["):
            json.loads(body)
            return 0.1
        return 0.8
    except Exception:
        return 0.9

def main():
    try:
        os.unlink(SOCK)
    except FileNotFoundError:
        pass

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(SOCK)
    s.listen(16)
    print("[OK] listening", SOCK)

    while True:
        c, _ = s.accept()
        try:
            raw = c.recv(4)
            if len(raw) != 4:
                c.close(); continue
            (ln,) = struct.unpack("<I", raw)
            data = b""
            while len(data) < ln:
                chunk = c.recv(ln - len(data))
                if not chunk:
                    break
                data += chunk
            sc = float(score_rule(data))
            c.sendall(struct.pack("<d", sc))
        finally:
            c.close()

if __name__ == "__main__":
    main()