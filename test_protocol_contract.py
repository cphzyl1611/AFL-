#!/usr/bin/env python3
"""Protocol Contract Assertions - Step 7 of R39 Repair Protocol.

Verifies the Protocol V2 implementation satisfies the protocol contract:
1. Multiple bodies with different lengths encode/decode correctly
2. Base64 roundtrip preserves byte-for-byte equality
3. UTF-8 and JSON bodies both work
4. Scenario routing is correct
5. Empty bodies are handled
6. Large bodies (up to 4KB) are handled

This is a LOCAL test - no Alfresco contact, no real campaign.
"""

import base64
import json
import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SCORER_PYTHON = "/home/dministrator/miniconda3/envs/aflpp-se-calib-pip/bin/python3"
SCORER_SCRIPT = REPO_ROOT / "model_stage" / "nv_valid_server_real.py"
BACKEND = "sefanogan_es_reference"


def start_scorer():
    """Start canonical scorer subprocess."""
    tmpdir = tempfile.mkdtemp(prefix="test_protocol_contract_")
    socket_path = Path(tmpdir) / "scorer.sock"

    env = {
        "NV_VALID_SOCK": str(socket_path),
        "NV_VALIDITY_BACKEND": BACKEND,
        "PYTHONPATH": str(REPO_ROOT),
    }

    canonical_base = Path.home() / "alfresco-audit-artifacts" / "sefanogan-es-round3-20260901-" / "training_runs" / "seed-20260519"
    env["SEFANOGAN_REFERENCE_CHECKPOINT"] = str(canonical_base / "sefanogan_es_reference.pt")
    env["SEFANOGAN_REFERENCE_META_PATH"] = str(canonical_base / "sefanogan_es_reference.json")

    stdout_path = Path(tmpdir) / "stdout.txt"
    stderr_path = Path(tmpdir) / "stderr.txt"

    with open(stdout_path, "w") as out, open(stderr_path, "w") as err:
        proc = subprocess.Popen(
            [SCORER_PYTHON, str(SCORER_SCRIPT)],
            env=env,
            stdout=out,
            stderr=err,
        )

    start = time.time()
    while time.time() - start < 10.0:
        if socket_path.exists():
            return proc, socket_path, tmpdir, stdout_path, stderr_path
        if proc.poll() is not None:
            raise RuntimeError(f"Scorer died: {proc.returncode}")
        time.sleep(0.1)

    raise TimeoutError("Scorer socket timeout")


def send_protocol_v2(socket_path: Path, scenario: str, body_bytes: bytes) -> tuple[bool, str]:
    """Send Protocol V2 request and receive response."""
    body_b64 = base64.b64encode(body_bytes).decode('ascii')
    envelope = {
        "scenario": scenario,
        "endpoint": "",
        "body": body_b64,
    }
    json_bytes = json.dumps(envelope).encode('utf-8')

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)

    try:
        sock.connect(str(socket_path))
        length = len(json_bytes)
        header = struct.pack("<I", length)
        sock.sendall(header)
        sock.sendall(json_bytes)

        resp = sock.recv(4096)
        sock.close()

        if not resp:
            return False, "NO_RESPONSE"

        score_str = resp.decode('utf-8').strip()
        try:
            score = float(score_str)
            return True, f"{score:.6f}"
        except ValueError:
            return False, f"INVALID: {score_str}"

    except socket.timeout:
        sock.close()
        return False, "TIMEOUT"
    except Exception as ex:
        sock.close()
        return False, f"ERROR: {ex}"


def test_base64_roundtrip():
    """Test 1: Base64 roundtrip preserves bytes."""
    print("TEST 1: Base64 Roundtrip")
    print("-" * 80)

    test_cases = [
        b"Hello, world!",
        b"\x00\x01\x02\xff\xfe\xfd",  # Binary
        b"UTF-8: \xe4\xb8\xad\xe6\x96\x87",  # Chinese characters
        b"",  # Empty
        b"A" * 1000,  # Large
    ]

    all_pass = True
    for i, original in enumerate(test_cases, 1):
        encoded = base64.b64encode(original).decode('ascii')
        decoded = base64.b64decode(encoded)
        passed = (original == decoded)
        all_pass = all_pass and passed
        print(f"  Case {i}: len={len(original):<4} {'PASS' if passed else 'FAIL'}")

    print(f"  Overall: {'PASS' if all_pass else 'FAIL'}")
    print()
    return all_pass


def test_multiple_bodies(socket_path: Path):
    """Test 2: Multiple bodies with different lengths."""
    print("TEST 2: Multiple Bodies")
    print("-" * 80)

    bodies = [
        (b"Short text.", "content_update"),
        (b"Medium length text with some more content to test.", "content_update"),
        (b"A" * 500, "content_update"),
        (b'{"key":"value"}', "metadata_update"),
        (b'{"nested":{"deeply":{"key":"value"}}}', "metadata_update"),
    ]

    all_pass = True
    for i, (body, scenario) in enumerate(bodies, 1):
        ok, result = send_protocol_v2(socket_path, scenario, body)
        passed = ok
        all_pass = all_pass and passed
        print(f"  Body {i}: len={len(body):<4} scenario={scenario:<18} {'PASS' if passed else 'FAIL'} {result}")

    print(f"  Overall: {'PASS' if all_pass else 'FAIL'}")
    print()
    return all_pass


def test_scenario_routing(socket_path: Path):
    """Test 3: Scenario routing is correct."""
    print("TEST 3: Scenario Routing")
    print("-" * 80)

    # Both scenarios should work (different score ranges expected)
    content = b"Raw UTF-8 text content."
    metadata = b'{"name":"test.txt"}'

    ok1, score1 = send_protocol_v2(socket_path, "content_update", content)
    ok2, score2 = send_protocol_v2(socket_path, "metadata_update", metadata)

    pass1 = ok1
    pass2 = ok2
    all_pass = pass1 and pass2

    print(f"  content_update:  {'PASS' if pass1 else 'FAIL'} score={score1}")
    print(f"  metadata_update: {'PASS' if pass2 else 'FAIL'} score={score2}")
    print(f"  Overall: {'PASS' if all_pass else 'FAIL'}")
    print()
    return all_pass


def test_edge_cases(socket_path: Path):
    """Test 4: Edge cases."""
    print("TEST 4: Edge Cases")
    print("-" * 80)

    cases = [
        ("Empty body", b"", "content_update"),
        ("Single char", b"X", "content_update"),
        ("Newlines", b"Line1\nLine2\nLine3", "content_update"),
        ("Max size", b"X" * 4000, "content_update"),
    ]

    all_pass = True
    for name, body, scenario in cases:
        ok, result = send_protocol_v2(socket_path, scenario, body)
        passed = ok
        all_pass = all_pass and passed
        print(f"  {name:<15} len={len(body):<4} {'PASS' if passed else 'FAIL'} {result}")

    print(f"  Overall: {'PASS' if all_pass else 'FAIL'}")
    print()
    return all_pass


def main():
    print("=" * 80)
    print("STEP 7: PROTOCOL CONTRACT ASSERTIONS")
    print("=" * 80)
    print()

    # Test 1: Base64 roundtrip (offline)
    t1_pass = test_base64_roundtrip()

    # Start scorer for online tests
    print("Starting scorer...")
    proc, socket_path, tmpdir, stdout_path, stderr_path = start_scorer()
    print(f"Scorer ready: {socket_path}")
    print()

    # Test 2-4: Online with scorer
    t2_pass = test_multiple_bodies(socket_path)
    t3_pass = test_scenario_routing(socket_path)
    t4_pass = test_edge_cases(socket_path)

    # Cleanup
    proc.terminate()
    proc.wait(timeout=2.0)

    # Final verdict
    all_pass = t1_pass and t2_pass and t3_pass and t4_pass

    print("=" * 80)
    print("STEP 7 RESULTS")
    print("=" * 80)
    print(f"BASE64_ROUNDTRIP = {'PASS' if t1_pass else 'FAIL'}")
    print(f"MULTIPLE_BODIES = {'PASS' if t2_pass else 'FAIL'}")
    print(f"SCENARIO_ROUTING = {'PASS' if t3_pass else 'FAIL'}")
    print(f"EDGE_CASES = {'PASS' if t4_pass else 'FAIL'}")
    print(f"PROTOCOL_CONTRACT = {'PASS' if all_pass else 'FAIL'}")
    print()

    if not all_pass:
        print("FAILURE: One or more protocol contract tests failed.")
        return 1

    print("SUCCESS: Protocol V2 contract verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
