#!/usr/bin/env python3
"""Focused tests for fuzz_api.py platform interface contracts.

Tests verify:
- Valid/invalid submit requests
- Task ID continuity
- Running/completed/not-found query states
- Graceful/idempotent stop
- Report filtering (task_id/task_name/time_range)
- Malformed request rejection
- Path traversal rejection
- Secret non-disclosure
- Delegation to existing runner logic
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from integration import fuzz_api


class TestSubmitValidation(unittest.TestCase):
    """Test fuzz_test_submit validation."""

    def test_valid_submit_request(self):
        """Valid submit request passes validation."""
        request = {
            "target_type": "http_api",
            "target_endpoint": "test_endpoint",
            "seed_source": "seed_file",
            "seed_location": "in/o2oa_body",
            "mutation_scope": ["field_value", "boundary"],
            "max_test_cases": 10,
            "time_budget": 30,
            "task_name": "test_task_01",
        }

        validated = fuzz_api.validate_submit_request(request)
        self.assertEqual(validated["target_type"], "http_api")
        self.assertEqual(validated["target_endpoint"], "test_endpoint")
        self.assertEqual(validated["mutation_scope"], ["field_value", "boundary"])
        self.assertEqual(validated["max_test_cases"], 10)
        self.assertEqual(validated["time_budget"], 30)
        self.assertEqual(validated["task_name"], "test_task_01")

    def test_invalid_target_type(self):
        """Invalid target_type rejected."""
        request = {
            "target_type": "invalid_type",
            "target_endpoint": "test",
            "seed_source": "seed_file",
            "seed_location": "in",
            "mutation_scope": ["field_value"],
            "max_test_cases": 10,
            "time_budget": 30,
        }

        with self.assertRaises(ValueError) as ctx:
            fuzz_api.validate_submit_request(request)
        self.assertIn("target_type", str(ctx.exception))

    def test_missing_required_field(self):
        """Missing required field rejected."""
        request = {
            "target_type": "http_api",
            # missing target_endpoint
            "seed_source": "seed_file",
            "seed_location": "in",
            "mutation_scope": ["field_value"],
            "max_test_cases": 10,
            "time_budget": 30,
        }

        with self.assertRaises(ValueError) as ctx:
            fuzz_api.validate_submit_request(request)
        self.assertIn("target_endpoint", str(ctx.exception))

    def test_invalid_mutation_scope(self):
        """Invalid mutation_scope rejected."""
        request = {
            "target_type": "http_api",
            "target_endpoint": "test",
            "seed_source": "seed_file",
            "seed_location": "in",
            "mutation_scope": ["invalid_scope"],
            "max_test_cases": 10,
            "time_budget": 30,
        }

        with self.assertRaises(ValueError) as ctx:
            fuzz_api.validate_submit_request(request)
        self.assertIn("mutation_scope", str(ctx.exception))

    def test_negative_max_test_cases(self):
        """Negative max_test_cases rejected."""
        request = {
            "target_type": "http_api",
            "target_endpoint": "test",
            "seed_source": "seed_file",
            "seed_location": "in",
            "mutation_scope": ["field_value"],
            "max_test_cases": -1,
            "time_budget": 30,
        }

        with self.assertRaises(ValueError) as ctx:
            fuzz_api.validate_submit_request(request)
        self.assertIn("max_test_cases", str(ctx.exception))

    def test_auto_generated_task_name(self):
        """Task name auto-generated if not provided."""
        request = {
            "target_type": "http_api",
            "target_endpoint": "test",
            "seed_source": "seed_file",
            "seed_location": "in",
            "mutation_scope": ["field_value"],
            "max_test_cases": 10,
            "time_budget": 30,
        }

        validated = fuzz_api.validate_submit_request(request)
        self.assertTrue(validated["task_name"].startswith("task_"))


class TestPathTraversalPrevention(unittest.TestCase):
    """Test path traversal attack prevention."""

    def test_path_traversal_rejected(self):
        """Path traversal in seed_location rejected."""
        with self.assertRaises(ValueError) as ctx:
            fuzz_api.safe_path_check("../../etc/passwd")
        self.assertIn("path traversal", str(ctx.exception).lower())

    def test_null_byte_rejected(self):
        """Null byte in path rejected."""
        with self.assertRaises(ValueError) as ctx:
            fuzz_api.safe_path_check("in/test\x00/seed")
        self.assertIn("null byte", str(ctx.exception).lower())

    def test_absolute_path_outside_repo_rejected(self):
        """Absolute path outside repo rejected."""
        with self.assertRaises(ValueError) as ctx:
            fuzz_api.safe_path_check("/etc/passwd")
        self.assertIn("inside repository", str(ctx.exception).lower())

    def test_valid_relative_path_accepted(self):
        """Valid relative path accepted."""
        result = fuzz_api.safe_path_check("in/o2oa_body")
        self.assertIsInstance(result, Path)
        self.assertTrue(str(result).startswith(str(REPO_ROOT)))


class TestTaskIDContinuity(unittest.TestCase):
    """Test task_id stability across operations."""

    def setUp(self):
        """Clear task registry before each test."""
        fuzz_api.TASKS.clear()

    def test_submit_returns_stable_task_id(self):
        """Submit returns stable task_id."""
        # Use actual seed directory inside repository
        seed_dir = REPO_ROOT / "in" / "o2oa_body"
        if not seed_dir.exists():
            self.skipTest("in/o2oa_body seed directory not found")

        request = {
            "target_type": "http_api",
            "target_endpoint": "test",
            "seed_source": "seed_file",
            "seed_location": str(seed_dir.relative_to(REPO_ROOT)),
            "mutation_scope": ["field_value"],
            "max_test_cases": 1,
            "time_budget": 1,
        }

        # Mock run_task to prevent actual fuzzing
        with mock.patch.object(fuzz_api, "run_task"):
            response = fuzz_api.fuzz_test_submit(request)

        self.assertEqual(response["process_result"], "success")
        self.assertIn("task_id", response)

        task_id = response["task_id"]
        self.assertIsInstance(task_id, str)
        self.assertTrue(len(task_id) > 0)

        # Query with same task_id should succeed
        query_response = fuzz_api.fuzz_test_query({"task_id": task_id})
        self.assertEqual(query_response["process_result"], "success")
        self.assertEqual(query_response["task_id"], task_id)


class TestQueryStates(unittest.TestCase):
    """Test fuzz_test_query state detection."""

    def setUp(self):
        """Clear task registry."""
        fuzz_api.TASKS.clear()

    def test_query_not_found(self):
        """Query non-existent task returns not_found."""
        response = fuzz_api.fuzz_test_query({"task_id": "nonexistent"})
        self.assertEqual(response["process_result"], "success")
        self.assertEqual(response["status"], "not_found")

    def test_query_created_state(self):
        """Query task in created state."""
        task_id = "test_task_123"
        fuzz_api.TASKS[task_id] = {
            "task_id": task_id,
            "task_name": "test",
            "status": "created",
            "request": {"target_endpoint": "test_ep"},
            "out_dir": "out/test",
            "created_at": fuzz_api.utc_now(),
            "_out_dir": str(REPO_ROOT / "out" / "test"),
        }

        response = fuzz_api.fuzz_test_query({"task_id": task_id})
        self.assertEqual(response["process_result"], "success")
        self.assertEqual(response["status"], "created")
        self.assertIn("query_description", response)

    def test_query_running_state(self):
        """Query task in running state."""
        task_id = "test_task_456"
        fuzz_api.TASKS[task_id] = {
            "task_id": task_id,
            "task_name": "test",
            "status": "running",
            "request": {"target_endpoint": "test_ep"},
            "out_dir": "out/test",
            "created_at": fuzz_api.utc_now(),
            "started_at": fuzz_api.utc_now(),
            "_out_dir": str(REPO_ROOT / "out" / "test"),
        }

        response = fuzz_api.fuzz_test_query({"task_id": task_id})
        self.assertEqual(response["process_result"], "success")
        self.assertEqual(response["status"], "running")
        self.assertIn("started_at", response)

    def test_query_completed_state(self):
        """Query task in completed state."""
        task_id = "test_task_789"
        fuzz_api.TASKS[task_id] = {
            "task_id": task_id,
            "task_name": "test",
            "status": "completed",
            "request": {"target_endpoint": "test_ep"},
            "out_dir": "out/test",
            "created_at": fuzz_api.utc_now(),
            "started_at": fuzz_api.utc_now(),
            "finished_at": fuzz_api.utc_now(),
            "returncode": 0,
            "_out_dir": str(REPO_ROOT / "out" / "test"),
        }

        response = fuzz_api.fuzz_test_query({"task_id": task_id})
        self.assertEqual(response["process_result"], "success")
        self.assertEqual(response["status"], "completed")
        self.assertIn("finished_at", response)


class TestGracefulStop(unittest.TestCase):
    """Test fuzz_test_stop graceful termination."""

    def setUp(self):
        """Clear task registry."""
        fuzz_api.TASKS.clear()

    def test_stop_nonexistent_task(self):
        """Stop non-existent task returns error."""
        response = fuzz_api.fuzz_test_stop({"task_id": "nonexistent"})
        self.assertEqual(response["process_result"], "error")
        self.assertIn("not found", response["error"])

    def test_stop_idempotent_for_completed(self):
        """Stop completed task is idempotent."""
        task_id = "completed_task"
        fuzz_api.TASKS[task_id] = {
            "task_id": task_id,
            "status": "completed",
            "returncode": 0,
        }

        response = fuzz_api.fuzz_test_stop({"task_id": task_id})
        self.assertEqual(response["process_result"], "success")
        self.assertEqual(response["status"], "completed")
        self.assertIn("already in terminal state", response.get("message", ""))

    def test_stop_idempotent_for_stopped(self):
        """Stop already-stopped task is idempotent."""
        task_id = "stopped_task"
        fuzz_api.TASKS[task_id] = {
            "task_id": task_id,
            "status": "stopped",
        }

        response = fuzz_api.fuzz_test_stop({"task_id": task_id})
        self.assertEqual(response["process_result"], "success")
        self.assertEqual(response["status"], "stopped")


class TestReportFiltering(unittest.TestCase):
    """Test fuzz_test_report_query filtering logic."""

    def setUp(self):
        """Clear task registry."""
        fuzz_api.TASKS.clear()

    def test_no_filter_rejected(self):
        """report_query without filters rejected."""
        response = fuzz_api.fuzz_test_report_query({})
        self.assertEqual(response["process_result"], "error")
        self.assertIn("at least one filter", response["error"])

    def test_filter_by_task_id(self):
        """Filter reports by task_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            (out_dir / "eval_report.json").write_text("{}")

            task_id = "task_with_report"
            fuzz_api.TASKS[task_id] = {
                "task_id": task_id,
                "task_name": "test_task",
                "_out_dir": str(out_dir),
            }

            response = fuzz_api.fuzz_test_report_query({"task_id": task_id})
            self.assertEqual(response["process_result"], "success")
            self.assertGreaterEqual(response["total_count"], 1)
            self.assertIsInstance(response["report_list"], list)

            if response["total_count"] > 0:
                report = response["report_list"][0]
                self.assertEqual(report["task_id"], task_id)
                self.assertIn("download_url", report)

    def test_filter_by_task_name(self):
        """Filter reports by task_name."""
        task_id = "task_abc"
        task_name = "my_test_task"
        fuzz_api.TASKS[task_id] = {
            "task_id": task_id,
            "task_name": task_name,
            "_out_dir": "/nonexistent",
        }

        response = fuzz_api.fuzz_test_report_query({"task_name": task_name})
        self.assertEqual(response["process_result"], "success")
        self.assertIsInstance(response["report_list"], list)

    def test_invalid_time_range_rejected(self):
        """Invalid time_range format rejected."""
        response = fuzz_api.fuzz_test_report_query({"time_range": {"start": "invalid"}})
        self.assertEqual(response["process_result"], "error")
        self.assertIn("time_range", response["error"])


class TestReportPathTraversal(unittest.TestCase):
    """Test report download path traversal prevention."""

    def setUp(self):
        """Clear task registry."""
        fuzz_api.TASKS.clear()

    def test_non_whitelisted_report_rejected(self):
        """Non-whitelisted report name rejected."""
        task_id = "test_task"
        fuzz_api.TASKS[task_id] = {
            "task_id": task_id,
            "_out_dir": str(REPO_ROOT / "out" / "test"),
        }

        content, error = fuzz_api.get_report_file(task_id, "../../../etc/passwd")
        self.assertIsNone(content)
        self.assertIn("not in whitelist", error)

    def test_whitelisted_report_accepted(self):
        """Whitelisted report name accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            report_path = out_dir / "eval_report.json"
            report_path.write_text('{"test": true}')

            task_id = "test_task"
            fuzz_api.TASKS[task_id] = {
                "task_id": task_id,
                "_out_dir": str(out_dir),
            }

            content, error = fuzz_api.get_report_file(task_id, "eval_report.json")
            self.assertIsNone(error)
            self.assertIsNotNone(content)
            self.assertEqual(content, b'{"test": true}')


class TestSecretNonDisclosure(unittest.TestCase):
    """Test that credentials/tokens are not leaked."""

    def test_query_response_no_env_vars(self):
        """Query response does not leak environment variables."""
        task_id = "task_xyz_789"
        fuzz_api.TASKS[task_id] = {
            "task_id": task_id,
            "task_name": "test",
            "status": "created",
            "request": {
                "target_endpoint": "test",
                "seed_location": "in/test",
            },
            "out_dir": "out/test",
            "created_at": fuzz_api.utc_now(),
            "_out_dir": str(REPO_ROOT / "out" / "test"),
            "_command": ["env", "NV_TOKEN=MySecretToken123", "afl-fuzz"],
        }

        response = fuzz_api.fuzz_test_query({"task_id": task_id})
        response_str = json.dumps(response)

        # Ensure no token/secret values in response
        self.assertNotIn("NV_TOKEN", response_str)
        self.assertNotIn("MySecretToken123", response_str)
        self.assertNotIn("_command", response_str)


class TestDelegationToRunner(unittest.TestCase):
    """Test that API delegates to existing runner logic."""

    def test_build_command_uses_afl_fuzz(self):
        """build_fuzzing_command delegates to afl-fuzz."""
        # Use actual seed directory inside repository
        seed_dir = REPO_ROOT / "in" / "o2oa_body"
        if not seed_dir.exists():
            self.skipTest("in/o2oa_body seed directory not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "out"
            validated = {
                "target_type": "http_api",
                "target_endpoint": "test",
                "seed_location": str(seed_dir.relative_to(REPO_ROOT)),
                "seed_source": "seed_dir",
                "mutation_scope": ["field_value"],
                "max_test_cases": 10,
                "time_budget": 30,
                "task_name": "test",
            }

            command = fuzz_api.build_fuzzing_command(validated, "test_id", out_dir)

            # Verify command uses afl-fuzz binary
            self.assertIn("afl-fuzz", " ".join(command))
            self.assertIn("nv_http_harness.py", " ".join(command))

            # Verify environment variables set
            cmd_str = " ".join(command)
            self.assertIn("AFL_NO_UI", cmd_str)
            self.assertIn("AFL_PYTHON_MODULE=nv_json_mutator", cmd_str)
            self.assertIn("NV_TASK_PATH", cmd_str)


if __name__ == "__main__":
    unittest.main()
