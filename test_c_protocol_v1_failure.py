#!/usr/bin/env python3
"""Reproduce exact R39 C Protocol V1 failure locally before repair."""

import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SCORER_PYTHON = "/home/dministrator/miniconda3/envs/aflpp-se-calib-pip/bin/python3"
SCORER_SCRIPT = REPO_ROOT / "model_stage" / "nv_valid_server_real.py"

def start_scorer():
    """Start canonical scorer subprocess."""
    tmpdir = tempfile.mkdtemp(prefix="test_c_v1_")
    socket_path = Path(tmpdir) / "scorer.sock"

    env = {
        "NV_VALID_SOCK": str(socket_path),
        "NV_VALIDITY_BACKEND": "sefanogan_es_reference",
        "PYTHONPATH": str(REPO_ROOT),
    }

    # Canonical artifact binding
    canonical_base = Path.home() / "alfresco-audit-artifacts" / "sefanogan-es-round3-20260901-" / "training_runs" / "seed-20260519"
    env["SEFANOGAN_REFERENCE_CHECKPOINT"] = str(canonical_base / "sefanogan_es_reference.pt")
    env["SEFANOGAN_REFERENCE_META_PATH"] = str(canonical_base / "sefanogan_es_reference.json")

    stdout_path = Path(tmpdir) / "scorer_stdout.txt"
    stderr_path = Path(tmpdir) / "scorer_stderr.txt"

    with open(stdout_path, "w") as out, open(stderr_path, "w") as err:
        proc = subprocess.Popen(
            [SCORER_PYTHON, str(SCORER_SCRIPT)],
            env=env,
            cwd=str(REPO_ROOT),
            stdout=out,
            stderr=err,
        )

    # Wait for socket
    start = time.time()
    while time.time() - start < 5.0:
        if socket_path.exists():
            return proc, socket_path, stdout_path, stderr_path, tmpdir
        if proc.poll() is not None:
            raise RuntimeError(f"Scorer died with exit code {proc.returncode}")
        time.sleep(0.1)

    raise TimeoutError("Scorer socket did not appear")


def send_c_protocol_v1_request(socket_path, http_request_bytes):
    """Send exact C Protocol V1 request: [4-byte length][raw HTTP bytes]."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)  # Give scorer time to fail

    try:
        sock.connect(str(socket_path))

        # Exact C protocol: 4-byte little-endian length + raw buffer
        length = len(http_request_bytes)
        header = struct.pack("<I", length)

        sock.sendall(header)
        sock.sendall(http_request_bytes)

        # Try to receive response
        resp = sock.recv(4096)
        sock.close()

        if resp:
            return True, resp.decode("utf-8", errors="ignore").strip()
        else:
            return False, "NO_RESPONSE"

    except socket.timeout:
        sock.close()
        return False, "TIMEOUT"
    except Exception as ex:
        sock.close()
        return False, f"EXCEPTION: {type(ex).__name__}: {ex}"


def main():
    print("=" * 80)
    print("STEP 2: REPRODUCE C PROTOCOL V1 FAILURE")
    print("=" * 80)
    print()

    # Start canonical scorer
    print("Starting canonical scorer subprocess...")
    proc, socket_path, stdout_path, stderr_path, tmpdir = start_scorer()
    print(f"Scorer PID: {proc.pid}")
    print(f"Socket: {socket_path}")
    print(f"Tmpdir: {tmpdir}")
    print()

    # Representative content_update HTTP request (exactly what AFL++ sends)
    http_request = b"""PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/workspace://SpacesStore/test-node-id/content HTTP/1.1
Host: alfresco.example.com
Authorization: Bearer test-token
Content-Type: text/plain; charset=utf-8
Content-Length: 60

\xe8\xbf\x99\xe6\x98\xaf\xe4\xb8\x80\xe6\xae\xb5\xe6\xb5\x8b\xe8\xaf\x95\xe6\x96\x87\xe6\x9c\xac\xef\xbc\x8c\xe7\x94\xa8\xe4\xba\x8e\xe9\xaa\x8c\xe8\xaf\x81\xe7\xb3\xbb\xe7\xbb\x9f\xe7\x9a\x84\xe5\x86\x85\xe5\xae\xb9\xe6\x9b\xb4\xe6\x96\xb0\xe5\x8a\x9f\xe8\x83\xbd\xe3\x80\x82"""

    print("Sending C Protocol V1 request (raw HTTP bytes)...")
    print(f"Request length: {len(http_request)} bytes")
    print(f"Request start: {http_request[:80]}...")
    print()

    # Send Protocol V1 request
    ok, response = send_c_protocol_v1_request(socket_path, http_request)

    print(f"RPC OK: {ok}")
    print(f"Response: {response}")
    print()

    # Give scorer time to write error to stdout/stderr
    time.sleep(0.5)

    # Read scorer output
    stdout_content = stdout_path.read_text()
    stderr_content = stderr_path.read_text()

    print("Scorer stdout:")
    print("-" * 80)
    print(stdout_content if stdout_content else "(empty)")
    print("-" * 80)
    print()

    print("Scorer stderr:")
    print("-" * 80)
    print(stderr_content if stderr_content else "(empty)")
    print("-" * 80)
    print()

    # Classify error
    error_class = "UNKNOWN"
    failure_stage = "UNKNOWN"

    if not ok:
        if "JSONDecodeError" in stdout_content or "JSONDecodeError" in stderr_content:
            error_class = "JSONDecodeError"
            failure_stage = "REQUEST_DESERIALIZATION"
        elif "json" in stdout_content.lower() or "json" in stderr_content.lower():
            error_class = "JSON_PARSE_ERROR"
            failure_stage = "REQUEST_DESERIALIZATION"
        elif response == "TIMEOUT":
            error_class = "NO_RESPONSE_TIMEOUT"
            failure_stage = "NO_RESPONSE_SENT"

    print("=" * 80)
    print("STEP 2 RESULTS")
    print("=" * 80)
    print(f"PRE_REPAIR_C_TO_SCORER_RPC_OK = {'YES' if ok else 'NO'}")
    print(f"PRE_REPAIR_SCORER_ERROR_CLASS = {error_class}")
    print(f"PRE_REPAIR_FAILURE_STAGE = {failure_stage}")
    print()

    # Cleanup
    proc.terminate()
    proc.wait(timeout=2.0)

    # Verify this is RED (failure reproduced)
    if ok:
        print("UNEXPECTED: C Protocol V1 request succeeded!")
        print("Expected failure due to protocol mismatch.")
        return 1

    if error_class != "JSONDecodeError":
        print(f"WARNING: Expected JSONDecodeError, got {error_class}")
        print("Check scorer output above for actual error.")
        return 1

    print("SUCCESS: C Protocol V1 failure reproduced exactly as expected.")
    print("Scorer attempted to parse raw HTTP request as JSON → JSONDecodeError")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
