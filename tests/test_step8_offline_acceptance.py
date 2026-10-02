#!/usr/bin/env python3
"""Step 8: Offline acceptance test for content_update scorer participation.

This test simulates a minimal content_update execution with mock scorer to verify:
1. nv_body_valid_stats.json shows body_score_rpc_ok > 0
2. scorer_trace.jsonl exists with backend evidence
3. validate_model_comparison_participation returns verdict=PASS
4. metadata_update regression (no degradation)

IMPORTANT: This is an OFFLINE test. No real Alfresco, no real fuzzing.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.run_alfresco_bounded_feedback import (
    validate_model_comparison_participation,
    parse_scorer_trace,
    parse_nv_body_valid_stats,
)


class MockScorerServer:
    """Mock scorer that returns fixed scores over Unix socket."""

    def __init__(self, socket_path: Path, backend: str = "alfresco_ae_v1"):
        self.socket_path = Path(socket_path)
        self.backend = backend
        self.trace_path = socket_path.parent / "scorer_trace.jsonl"
        self.server_socket = None
        self.thread = None
        self.running = False
        self.invocation_count = 0

    def start(self):
        """Start mock scorer in background thread."""
        if self.socket_path.exists():
            self.socket_path.unlink()

        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(str(self.socket_path))
        self.server_socket.listen(5)
        self.server_socket.settimeout(0.5)

        self.running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

        # Wait for readiness
        for _ in range(20):
            if self.socket_path.exists():
                return
            time.sleep(0.05)
        raise RuntimeError("Mock scorer failed to start")

    def _serve(self):
        """Accept connections and return mock scores."""
        while self.running:
            try:
                conn, _ = self.server_socket.accept()
                self._handle_connection(conn)
            except socket.timeout:
                continue
            except Exception:
                if self.running:
                    raise

    def _handle_connection(self, conn):
        """Handle one RPC request."""
        try:
            # Read length prefix (4 bytes)
            length_bytes = conn.recv(4)
            if len(length_bytes) != 4:
                return
            payload_len = int.from_bytes(length_bytes, "little")

            # Read payload
            payload = conn.recv(payload_len)
            if len(payload) != payload_len:
                return

            # Parse request
            try:
                request = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                # Raw body (not JSON) - still valid
                request = {"body": payload.decode("utf-8", errors="replace")}

            # Generate mock score (always below threshold for acceptance)
            score = 0.05  # Well below typical thresholds

            # Write trace
            self.invocation_count += 1
            trace_record = {
                "backend": self.backend,
                "endpoint": request.get("endpoint", "unknown"),
                "score": score,
                "invocation": self.invocation_count,
            }
            with open(self.trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_record) + "\n")

            # Send response (plain float format, matching nv_valid_server_mock.py)
            response = f"{score:.6f}\n".encode("ascii")
            conn.sendall(response)
        finally:
            conn.close()

    def stop(self):
        """Stop mock scorer."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.server_socket:
            self.server_socket.close()
        if self.socket_path.exists():
            self.socket_path.unlink()


class TestStep8OfflineAcceptance(unittest.TestCase):
    """Offline acceptance tests for content_update scorer participation."""

    def test_content_update_produces_scorer_participation_evidence(self):
        """Verify content_update execution produces required scorer evidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Setup mock scorer
            scorer_socket = tmpdir / "scorer.sock"
            scorer = MockScorerServer(scorer_socket, backend="alfresco_ae_v1")
            scorer.start()

            try:
                # Setup harness environment for content_update
                stats_path = tmpdir / "nv_body_valid_stats.json"
                env = dict(os.environ)
                env.update({
                    "NV_BODY_SCORE_ENDPOINT": f"unix://{scorer_socket}",
                    "NV_BODY_SCORE_THRESHOLD": "0.5",
                    "NV_BODY_VALID_STATS": str(stats_path),
                    "NV_STATUS_PATH": str(tmpdir / "status.json"),
                    "NV_VALIDITY_BACKEND": "alfresco_ae_v1",
                })

                # Create minimal HTTP seed for content_update (raw text body)
                seed_content = (
                    b"PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/"
                    b"test-node-id/content HTTP/1.1\r\n"
                    b"Host: 127.0.0.1\r\n"
                    b"Content-Type: text/plain\r\n"
                    b"Content-Length: 16\r\n"
                    b"\r\n"
                    b"Updated content!"
                )

                # Run harness (will fail to connect to Alfresco, but scorer should be invoked)
                proc = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "nv_http_harness.py")],
                    input=seed_content,
                    env=env,
                    capture_output=True,
                    timeout=5,
                )

                # Harness will fail (no Alfresco), but scorer should have been invoked
                # Check evidence artifacts

                # 1. Verify nv_body_valid_stats.json exists and shows scorer invocation
                self.assertTrue(
                    stats_path.exists(),
                    "nv_body_valid_stats.json should exist after execution"
                )

                stats = parse_nv_body_valid_stats(stats_path)
                self.assertGreater(
                    stats.get("body_score_rpc_ok", 0), 0,
                    "body_score_rpc_ok should be > 0 after execution"
                )
                self.assertEqual(
                    stats.get("body_score_rpc_fail", -1), 0,
                    "body_score_rpc_fail should be 0 (no RPC failures)"
                )

                # 2. Verify scorer_trace.jsonl exists and contains backend evidence
                trace_path = scorer.trace_path
                self.assertTrue(
                    trace_path.exists(),
                    "scorer_trace.jsonl should exist after execution"
                )

                trace = parse_scorer_trace(trace_path)
                self.assertGreater(
                    len(trace), 0,
                    "scorer_trace.jsonl should contain at least one record"
                )
                self.assertEqual(
                    trace[0].get("backend"), "alfresco_ae_v1",
                    "Trace record should contain correct backend"
                )
                self.assertIn(
                    "score", trace[0],
                    "Trace record should contain score field"
                )

                # 3. Verify validate_model_comparison_participation returns PASS
                participation = validate_model_comparison_participation(
                    stats, trace, "alfresco_ae_v1"
                )
                self.assertEqual(
                    participation["verdict"], "PASS",
                    f"Participation should be PASS, got: {participation}"
                )
                self.assertEqual(
                    len(participation["reason_codes"]), 0,
                    f"Should have no reason codes, got: {participation['reason_codes']}"
                )

            finally:
                scorer.stop()

    def test_metadata_update_scorer_participation_unchanged(self):
        """Verify metadata_update scorer participation still works (regression)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Setup mock scorer
            scorer_socket = tmpdir / "scorer.sock"
            scorer = MockScorerServer(scorer_socket, backend="alfresco_ae_v1")
            scorer.start()

            try:
                # Setup harness environment for metadata_update (body_only_mode=1)
                stats_path = tmpdir / "nv_body_valid_stats.json"
                env = dict(os.environ)
                env.update({
                    "NV_BODY_SCORE_ENDPOINT": f"unix://{scorer_socket}",
                    "NV_BODY_SCORE_THRESHOLD": "0.5",
                    "NV_BODY_VALID_STATS": str(stats_path),
                    "NV_STATUS_PATH": str(tmpdir / "status.json"),
                    "NV_VALIDITY_BACKEND": "alfresco_ae_v1",
                    "NV_ENDPOINT_NAME": "metadata_update",
                    "NV_BODY_RULES": str(REPO_ROOT / "validity" / "alfresco_metadata_update_rules.json"),
                })

                # Create minimal target config for metadata_update (body_only_mode=1)
                target_config = {
                    "platform": "alfresco",
                    "base": "http://127.0.0.1:8080",
                    "body_only_mode": 1,
                    "default_endpoint": "metadata_update",
                    "endpoints": [
                        {
                            "name": "metadata_update",
                            "method": "PUT",
                            "path": "/alfresco/api/-default-/public/alfresco/versions/1/nodes/test-id"
                        }
                    ]
                }
                config_path = tmpdir / "target.json"
                config_path.write_text(json.dumps(target_config), encoding="utf-8")
                env["NV_TARGET_CONFIG"] = str(config_path)

                # Create minimal JSON body seed for metadata_update
                seed_body = json.dumps({
                    "properties": {
                        "cm:title": "Test Title",
                        "cm:description": "Test Description"
                    }
                }).encode("utf-8")

                # Run harness
                proc = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "nv_http_harness.py")],
                    input=seed_body,
                    env=env,
                    capture_output=True,
                    timeout=5,
                )

                # Harness will fail (no Alfresco), but scorer should have been invoked
                # Check evidence artifacts

                # Verify scorer was invoked (regression: metadata_update still works)
                self.assertTrue(
                    stats_path.exists(),
                    "metadata_update should still produce stats"
                )

                stats = parse_nv_body_valid_stats(stats_path)
                self.assertGreater(
                    stats.get("body_score_rpc_ok", 0), 0,
                    "metadata_update scorer participation should be unchanged"
                )

                # Verify trace
                trace_path = scorer.trace_path
                self.assertTrue(trace_path.exists(), "Trace should exist")
                trace = parse_scorer_trace(trace_path)
                self.assertGreater(len(trace), 0, "Trace should have records")

                # Verify participation
                participation = validate_model_comparison_participation(
                    stats, trace, "alfresco_ae_v1"
                )
                self.assertEqual(
                    participation["verdict"], "PASS",
                    "metadata_update participation should still be PASS"
                )

            finally:
                scorer.stop()


if __name__ == "__main__":
    unittest.main()
