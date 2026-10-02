#!/usr/bin/env python3
"""Mock scorer for R30 dry run validation - tests orchestration only."""
import json
import os
import socket
import struct
import sys
import time
from pathlib import Path

SOCK = os.getenv("NV_VALID_SOCK", "/tmp/nv_valid_mock.sock")
FMT = os.getenv("NV_RPC_FMT", "text").strip().lower()
MAX_IN = int(os.getenv("NV_RPC_MAX_IN", "262144"))

def main():
    # Remove stale socket
    sock_path = Path(SOCK)
    if sock_path.exists():
        sock_path.unlink()

    # Create Unix socket server
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(5)

    print(f"Mock scorer listening on {SOCK}", flush=True)

    while True:
        try:
            conn, _ = server.accept()
            data = conn.recv(MAX_IN)
            if not data:
                conn.close()
                continue

            # Mock response: always return valid score
            if FMT == "binary":
                response = struct.pack("<d", 1.0)
            else:
                response = json.dumps({"score": 1.0}).encode("utf-8")

            conn.sendall(response)
            conn.close()
        except KeyboardInterrupt:
            break
        except Exception:
            pass

    server.close()
    sock_path.unlink()

if __name__ == "__main__":
    main()
