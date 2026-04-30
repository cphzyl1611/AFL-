#!/usr/bin/env python3
import os, socket, struct, time

SOCK = os.getenv("NV_VALID_SOCK", "/tmp/nv_valid.sock")

def recv_exact(conn, n):
    buf=b""
    while len(buf)<n:
        chunk=conn.recv(n-len(buf))
        if not chunk:
            raise ConnectionError("EOF")
        buf += chunk
    return buf

def main():
    try: os.unlink(SOCK)
    except FileNotFoundError: pass

    s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(SOCK)
    os.chmod(SOCK, 0o666)
    s.listen(16)
    print("[mock] listening", SOCK, flush=True)

    while True:
        conn,_=s.accept()
        try:
            hdr=recv_exact(conn, 4)
            (n,) = struct.unpack("<I", hdr)
            payload = recv_exact(conn, n) if n else b""

            # 简单给个可控分数：包含 "docId" 就高一点，否则低一点
            score = 1.0 if b"docId" in payload else 0.0

            # 回 8 字节 double（本机 little-endian IEEE754，Linux x86_64 OK）
            conn.sendall(struct.pack("d", score))
        except Exception as e:
            # 出错直接断开
            try:
                conn.close()
            except: pass
        finally:
            try:
                conn.close()
            except: pass

if __name__ == "__main__":
    main()