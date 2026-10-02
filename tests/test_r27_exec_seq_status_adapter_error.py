"""R27 TDD regression: HttpBodyAdapterError must publish status/exec_seq.

R26C reported that HttpBodyAdapterError rejection path returns early without
calling write_status(), breaking the execution identity contract required by
the C-side MAB consumer.

This test proves:
1. HttpBodyAdapterError path currently does NOT write status
2. HttpBodyAdapterError path currently does NOT advance exec_seq
3. Normal validation reject path DOES write status/exec_seq
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


class R27HttpBodyAdapterErrorStatusTest(unittest.TestCase):
    """Prove HttpBodyAdapterError breaks exec_seq contract (pre-repair)."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="r27_")
        self.status_path = os.path.join(self.tmpdir, "status.json")
        self.status_ledger_path = self.status_path + ".jsonl"
        self.seq_sidecar_path = self.status_path + ".seq"

        # Minimal config for body_only_mode=1
        self.cfg_path = os.path.join(self.tmpdir, "task.json")
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump({
                "base": "http://127.0.0.1:9999",
                "body_only_mode": 1,
                "default_endpoint": "content_update",
                "endpoints": [
                    {"name": "content_update", "method": "POST", "path": "/api/content"}
                ],
                "scenario": "metadata_update"
            }, f)

        # Minimal validity rules that require specific fields
        self.rules_path = os.path.join(self.tmpdir, "rules.json")
        with open(self.rules_path, "w", encoding="utf-8") as f:
            json.dump({
                "endpoints": {
                    "content_update": {
                        "required": ["nodeId", "properties"],
                        "max_depth": 10
                    }
                }
            }, f)

        os.environ["NV_STATUS_PATH"] = self.status_path
        os.environ["NV_STATUS_LEDGER_PATH"] = self.status_ledger_path
        os.environ["NV_TARGET_CONFIG"] = self.cfg_path
        os.environ["NV_ENDPOINT_NAME"] = "content_update"
        os.environ["NV_BODY_RULES"] = self.rules_path
        os.environ.pop("NV_BODY_SCORE_ENDPOINT", None)

        # Import AFTER environment is set up so STATUS_PATH is captured correctly
        import nv_http_harness
        self.harness = nv_http_harness

        # Force reload to pick up the new STATUS_PATH
        import importlib
        importlib.reload(self.harness)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _read_status(self) -> dict | None:
        """Read the status snapshot if it exists."""
        if not os.path.exists(self.status_path):
            return None
        with open(self.status_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _read_exec_seq_sidecar(self) -> int:
        """Read the exec_seq counter sidecar."""
        if not os.path.exists(self.seq_sidecar_path):
            return 0
        with open(self.seq_sidecar_path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
            return int(raw) if raw else 0

    def test_adapter_error_missing_delimiter_does_not_write_status(self) -> None:
        """HttpBodyAdapterError path must write status after repair."""
        # Testcase: full HTTP seed with no envelope delimiter -> adapter error
        testcase = b"POST /api/content HTTP/1.1\nContent-Type: application/json\n{}"

        from io import BytesIO
        original_stdin = sys.stdin
        try:
            mock_stdin = type('MockStdin', (), {'buffer': BytesIO(testcase)})()
            sys.stdin = mock_stdin  # type: ignore
            exit_code = self.harness.main()
        finally:
            sys.stdin = original_stdin

        # Harness returns 0 for validation reject
        self.assertEqual(exit_code, 0)

        # POST-REPAIR EXPECTATION: status MUST be written
        status = self._read_status()
        self.assertIsNotNone(
            status,
            "HttpBodyAdapterError path MUST write status after repair"
        )
        self.assertEqual(status["validation_reject"], 1)
        self.assertIn("exec_seq", status)
        self.assertGreater(status["exec_seq"], 0)

    def test_adapter_error_does_not_advance_exec_seq(self) -> None:
        """HttpBodyAdapterError must publish exec_seq after repair."""
        testcase = b"POST /api/content\nContent-Type: application/json\n{}"

        from io import BytesIO
        original_stdin = sys.stdin

        exec_seq_before = self._read_exec_seq_sidecar()
        try:
            mock_stdin = type('MockStdin', (), {'buffer': BytesIO(testcase)})()
            sys.stdin = mock_stdin  # type: ignore
            self.harness.main()
        finally:
            sys.stdin = original_stdin
        exec_seq_after = self._read_exec_seq_sidecar()

        # POST-REPAIR EXPECTATION: exec_seq MUST advance
        self.assertGreater(
            exec_seq_after,
            exec_seq_before,
            "HttpBodyAdapterError path must advance exec_seq after repair"
        )

    def test_normal_validation_reject_DOES_write_status_with_exec_seq(self) -> None:
        """Baseline: normal validation rejection publishes status/exec_seq."""
        # Valid HTTP envelope, but JSON body fails validation rules
        testcase = b"POST /api/content\n\n{\"invalid_structure\": true}"

        from io import BytesIO
        original_stdin = sys.stdin

        exec_seq_before = self._read_exec_seq_sidecar()
        try:
            mock_stdin = type('MockStdin', (), {'buffer': BytesIO(testcase)})()
            sys.stdin = mock_stdin  # type: ignore
            exit_code = self.harness.main()
        finally:
            sys.stdin = original_stdin
        exec_seq_after = self._read_exec_seq_sidecar()

        self.assertEqual(exit_code, 0)

        # Normal reject DOES write status
        status = self._read_status()
        self.assertIsNotNone(status, "Normal reject must write status")
        self.assertEqual(status["validation_reject"], 1)
        self.assertIn("exec_seq", status)
        self.assertGreater(status["exec_seq"], 0)

        # exec_seq DOES advance
        self.assertGreater(
            exec_seq_after,
            exec_seq_before,
            "Normal reject must advance exec_seq"
        )


if __name__ == "__main__":
    unittest.main()
