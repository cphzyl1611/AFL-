#!/usr/bin/env python3
"""Mock scorer for R30 dry run validation - avoids numpy dependency."""

import os
import socket
import json
import sys
from pathlib import Path

def main():
    sock_path = os.environ.get("NV_VALID_SOCK", "/tmp/nv_valid.sock")
    trace_path = os.environ.get("NV_SCORER_TRACE_PATH")

    # Remove stale socket
    if os.path.exists(sock_path):
        os.unlink(sock_path)

    # Create Unix socket
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(sock_path)
    sock.listen(5)

    print(f"Mock scorer listening on {sock_path}", file=sys.stderr, flush=True)

    request_count = 0

    try:
        while True:
            conn, _ = sock.accept()
            try:
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break

                if data:
                    request_count += 1

                    # Parse request
                    try:
                        body = json.loads(data.decode("utf-8").strip())
                    except:
                        body = {}

                    # Return mock score
                    score = 0.8
                    response = json.dumps({"score": score}) + "\n"
                    conn.sendall(response.encode("utf-8"))

                    # Write trace
                    if trace_path:
                        with open(trace_path, "a") as f:
                            f.write(json.dumps({
                                "request_id": request_count,
                                "score": score,
                                "body_keys": list(body.keys()) if isinstance(body, dict) else []
                            }) + "\n")

            finally:
                conn.close()

    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        if os.path.exists(sock_path):
            os.unlink(sock_path)

if __name__ == "__main__":
    main()
