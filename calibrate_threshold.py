#!/usr/bin/env python3
import os, glob, socket, struct, argparse, math

def rpc_score(sock_path: str, payload: bytes, fmt: str) -> float:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1.0)
    s.connect(sock_path)

    # 发送：4B big-endian len + payload（server 支持这个）
    s.sendall(struct.pack(">I", len(payload)))
    if payload:
        s.sendall(payload)

    # 读取返回
    if fmt == "binary":
        b = b""
        while len(b) < 8:
            chunk = s.recv(8 - len(b))
            if not chunk:
                break
            b += chunk
        s.close()
        if len(b) != 8:
            return float("nan")
        return struct.unpack("<d", b)[0]
    else:
        # text
        buf = b""
        while b"\n" not in buf and len(buf) < 128:
            chunk = s.recv(128)
            if not chunk:
                break
            buf += chunk
        s.close()
        try:
            line = buf.splitlines()[0].decode("ascii", errors="ignore").strip()
            return float(line)
        except Exception:
            return float("nan")

def percentile(xs, p):
    xs = sorted(xs)
    if not xs: return float("nan")
    k = (len(xs) - 1) * p
    f = math.floor(k); c = math.ceil(k)
    if f == c: return xs[int(k)]
    return xs[f] * (c - k) + xs[c] * (k - f)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", default="in_http")
    ap.add_argument("--sock", default="/tmp/nv_valid.sock")
    ap.add_argument("--fmt", default=os.getenv("NV_RPC_FMT","text"))
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.in_dir, "*.http")))
    if not files:
        raise SystemExit(f"no seeds in {args.in_dir}")

    scores = []
    for f in files:
        payload = open(f, "rb").read()
        sc = rpc_score(args.sock, payload, args.fmt)
        scores.append(sc)
        print(f"{os.path.basename(f)}\tscore={sc}")

    vals = [x for x in scores if x == x and abs(x) != float("inf")]
    p95 = percentile(vals, 0.95)
    p99 = percentile(vals, 0.99)
    print(f"\n[CALIB] n={len(vals)} p95={p95:.6f} p99={p99:.6f}")
    print("[SUGGEST] set NV_VALIDITY_THRESHOLD around p99 (or p95 if you want stricter filtering)")

if __name__ == "__main__":
    main()