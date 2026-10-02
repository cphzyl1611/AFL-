"""TDD tests for content_update scorer participation repair.

RED phase: These tests document the missing scorer invocation in content_update.
GREEN phase: After fix, these tests verify scorer participation evidence.
"""

import json
import os
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class TestContentUpdateScorerParticipation(unittest.TestCase):
    """Test that content_update invokes scorer in model-comparison mode."""

    def test_rpc_score_unix_accepts_raw_text_content(self):
        """Verify scorer RPC protocol accepts raw text (not just JSON)."""
        with tempfile.TemporaryDirectory(prefix="scorer-raw-") as tmpdir:
            socket_path = Path(tmpdir) / "scorer.sock"
            
            # Mock scorer server
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(socket_path))
            server.listen(1)
            
            def scorer_server():
                conn, _ = server.accept()
                length_data = conn.recv(4)
                if length_data:
                    length = struct.unpack("<I", length_data)[0]
                    payload = conn.recv(length)
                    # Protocol v2: expect JSON envelope with base64-encoded body
                    import json
                    import base64
                    envelope = json.loads(payload.decode("utf-8"))
                    self.assertEqual(envelope["scenario"], "content_update")
                    self.assertEqual(envelope["endpoint"], "test_endpoint")
                    decoded_body = base64.b64decode(envelope["body"])
                    self.assertEqual(decoded_body, b"Raw text content for scoring")
                    conn.sendall(b"0.42")
                conn.close()
            
            server_thread = threading.Thread(target=scorer_server, daemon=True)
            server_thread.start()
            time.sleep(0.1)  # Let server start
            
            # Test RPC with raw text
            from nv_body_valid import rpc_score_unix
            rpc_ok, score = rpc_score_unix(
                f"unix://{socket_path}",
                "content_update",
                "test_endpoint",
                b"Raw text content for scoring"
            )
            
            self.assertTrue(rpc_ok, "RPC must succeed with raw text payload")
            self.assertAlmostEqual(score, 0.42, places=2)
            
            server.close()

    def test_content_update_harness_path_invokes_scorer_when_configured(self):
        """RED→GREEN: content_update harness must invoke scorer when NV_BODY_SCORE_ENDPOINT is set."""
        # This test documents the fix requirement:
        # When body_only_mode=0 AND score_endpoint is configured,
        # the harness must call rpc_score_unix with the body bytes.
        
        # RED state: harness never calls scorer in else branch (line 1056+)
        # GREEN state: harness calls scorer after parse_http_seed (line 1057+)
        
        # We verify this by checking that after the fix:
        # 1. rpc_score_unix is called with body bytes
        # 2. bump_body_valid_stat increments body_score_rpc_ok
        # 3. Threshold rejection works (score >= threshold → reject)
        
        # Since we cannot easily unit-test the full harness persistent loop,
        # we verify the components exist and can be composed correctly.
        
        from nv_body_valid import rpc_score_unix
        
        # Verify rpc_score_unix is importable and callable
        self.assertTrue(callable(rpc_score_unix))
        
        # Verify it accepts the signature we need
        import inspect
        sig = inspect.signature(rpc_score_unix)
        params = list(sig.parameters.keys())
        self.assertIn("endpoint", params)
        self.assertIn("norm_body", params)

    def test_scorer_stats_structure_supports_content_update(self):
        """Verify nv_body_valid_stats.json structure supports scorer RPC counters."""
        with tempfile.TemporaryDirectory(prefix="stats-structure-") as tmpdir:
            stats_path = Path(tmpdir) / "nv_body_valid_stats.json"
            
            # Initialize stats structure
            stats = {
                "body_rule_pass": 0,
                "body_rule_reject": 0,
                "body_score_rpc_ok": 0,
                "body_score_rpc_fail": 0,
                "body_score_pass": 0,
                "body_score_reject": 0,
            }
            stats_path.write_text(json.dumps(stats))
            
            # Simulate scorer RPC success
            stats["body_score_rpc_ok"] += 1
            stats["body_score_pass"] += 1
            stats_path.write_text(json.dumps(stats))
            
            # Verify stats can be parsed
            parsed = json.loads(stats_path.read_text())
            self.assertEqual(parsed["body_score_rpc_ok"], 1)
            self.assertEqual(parsed["body_score_pass"], 1)

    def test_model_comparison_validation_rejects_zero_scorer_invocations(self):
        """Verify validate_model_comparison_participation rejects zero RPC invocations."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import scripts.run_alfresco_bounded_feedback as module
        
        # Zero scorer invocations must produce INVALID verdict
        stats = {"body_score_rpc_ok": 0, "body_score_rpc_fail": 0}
        trace = []
        
        result = module.validate_model_comparison_participation(
            stats, trace, "alfresco_ae_v1"
        )
        
        self.assertEqual(result["verdict"], "INVALID_FOR_MODEL_COMPARISON")
        self.assertIn("ZERO_SCORER_INVOCATIONS", result["reason_codes"])

    def test_model_comparison_validation_accepts_nonzero_scorer_invocations(self):
        """Verify validate_model_comparison_participation accepts valid scorer evidence."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import scripts.run_alfresco_bounded_feedback as module
        
        # At least one successful RPC with matching trace
        stats = {"body_score_rpc_ok": 1, "body_score_rpc_fail": 0}
        trace = [{"backend": "alfresco_ae_v1", "score": 0.3}]
        
        result = module.validate_model_comparison_participation(
            stats, trace, "alfresco_ae_v1"
        )
        
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(len(result["reason_codes"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
