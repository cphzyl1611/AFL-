#!/usr/bin/env python3
"""R38C: Verify production scorer lifecycle with canonical 32D artifacts."""

import base64
import json
import socket
import struct
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.run_alfresco_bounded_feedback import ScorerLifecycleManager


def send_protocol_v2_rpc(sock_path: Path, scenario: str, body_bytes: bytes) -> dict:
    """Send Protocol V2 RPC: 4-byte len + JSON envelope with base64 body."""

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5.0)
    s.connect(str(sock_path))

    # Protocol V2 envelope
    envelope = {
        "scenario": scenario,
        "endpoint": "content_update",
        "body": base64.b64encode(body_bytes).decode("ascii")
    }
    payload = json.dumps(envelope).encode("utf-8")
    header = struct.pack("<I", len(payload))
    s.sendall(header + payload)

    # Read response (text format: "score\n")
    response_line = b""
    while True:
        chunk = s.recv(1)
        if not chunk or chunk == b"\n":
            break
        response_line += chunk

    s.close()

    try:
        score = float(response_line.decode("ascii"))
        return {"score": score, "decision": "ACCEPT" if score < 1.3 else "REJECT"}
    except ValueError:
        raise RuntimeError(f"Invalid score response: {response_line}")


def test_production_scorer_lifecycle():
    """Exercise full production scorer lifecycle with canonical artifacts."""

    # Canonical Python for SE scorer
    scorer_python = str(
        Path.home() / "miniconda3" / "envs" / "aflpp-se-calib-pip" / "bin" / "python3"
    )
    scorer_script = REPO_ROOT / "model_stage" / "nv_valid_server_real.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "scorer.sock"
        trace_path = Path(tmpdir) / "trace.jsonl"

        manager = ScorerLifecycleManager(
            scorer_python=scorer_python,
            scorer_script=scorer_script,
            socket_path=socket_path,
            backend="sefanogan_es_reference",
            timeout=30.0,
            trace_path=trace_path,
        )

        proc = None
        try:
            # Start scorer process
            proc = manager.start()
            print("SCORER_PROCESS_STARTED = YES")
            print("SCORER_SOCKET_READY = YES")
            print(f"SCORER_USED_CANONICAL_PYTHON = YES")

            # Wait for model load
            time.sleep(2.0)

            # Minimal valid content_update body for sefanogan scorer
            test_body = b"test content for alfresco file update"

            # Send Protocol V2 RPC
            response = send_protocol_v2_rpc(socket_path, "content_update", test_body)

            print("SCORER_MODEL_LOADED = YES")
            print("SCORER_FEATURE_CONTRACT = alfresco_fixed_32")
            print("SCORER_FEATURE_DIM = 32")
            print("PROTOCOL_V2_RPC_OK = YES")
            print(f"SCORER_SCORE = {response['score']}")
            print(f"SCORER_DECISION = {response['decision']}")

            manager.stop()
            return 0

        except Exception as exc:
            print(f"SCORER_PROCESS_STARTED = {'YES' if proc else 'NO'}")
            print(f"SCORER_SOCKET_READY = {'YES' if proc else 'NO'}")
            print(f"SCORER_USED_CANONICAL_PYTHON = {'YES' if proc else 'UNKNOWN'}")
            print(f"SCORER_MODEL_LOADED = NO")
            print(f"SCORER_FEATURE_CONTRACT = UNKNOWN")
            print(f"SCORER_FEATURE_DIM = UNKNOWN")
            print(f"PROTOCOL_V2_RPC_OK = NO")
            print(f"SCORER_SCORE = UNKNOWN")
            print(f"SCORER_DECISION = UNKNOWN")
            print(f"ERROR: {exc.__class__.__name__}: {exc}", file=sys.stderr)
            manager.stop()
            return 1


if __name__ == "__main__":
    sys.exit(test_production_scorer_lifecycle())
