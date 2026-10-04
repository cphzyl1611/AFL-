#!/usr/bin/env python3
"""Offline tests for platform interface contracts (fuzz_test_submit/query/stop/report_query).

Tests verify that the API server and MCP adapter implementations meet the documented
interface contracts without requiring live O2OA/Alfresco environment.
"""

from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from integration.api_server import (
    create_task, task_snapshot, task_report, SCENARIOS, LOCAL_SUMMARIES
)


class TestAPIServerInterfaceContracts(unittest.TestCase):
    """Test api_server.py fuzz_test_* interface contracts."""

    def test_submit_interface_dry_run(self):
        """fuzz_test_submit: verify task creation returns task_id and status."""
        out_dir = "out/test_api_submit"
        task = create_task("nv_mab_smoke", out_dir, dry_run=True)
        self.assertIn("task_id", task)
        self.assertIn("status", task)
        self.assertEqual(task["status"], "dry_run")
        self.assertIn("scenario", task)
        self.assertEqual(task["scenario"], "nv_mab_smoke")

    def test_query_interface(self):
        """fuzz_test_query: verify task_snapshot returns running/completed/error fields."""
        out_dir = "out/test_api_query"
        task = create_task("nv_mab_smoke", out_dir, dry_run=True)
        snap = task_snapshot(task)
        self.assertIn("task_id", snap)
        self.assertIn("status", snap)
        self.assertIn("returncode", snap)
        self.assertIn("started_at", snap)
        self.assertIn("finished_at", snap)
        self.assertIn("out_dir", snap)
        self.assertIn("log_path", snap)

    def test_report_query_interface(self):
        """fuzz_test_report_query: verify report list returns summary/report file locations."""
        out_dir = "out/test_api_report"
        task = create_task("nv_mab_smoke", out_dir, dry_run=True)
        report = task_report(task)
        self.assertIn("task_id", report)
        self.assertIn("status", report)
        self.assertIn("summary_files", report)
        self.assertIn("report_files", report)
        self.assertIsInstance(report["summary_files"], list)
        self.assertIsInstance(report["report_files"], list)

    def test_unsupported_scenario_graceful(self):
        """fuzz_test_submit: unsupported scenario returns unsupported_runtime status."""
        out_dir = "out/test_api_unsupported"
        task = create_task("flowable_doc_create", out_dir, dry_run=True)
        self.assertEqual(task["status"], "unsupported_runtime")
        self.assertIn("notes", task)

    def test_supported_scenarios_list(self):
        """Verify SCENARIOS list matches documented capabilities."""
        self.assertIn("nv_mab_smoke", SCENARIOS)
        self.assertIn("nv_mab_stability", SCENARIOS)
        self.assertIn("alfresco_metadata_update", SCENARIOS)
        self.assertIn("alfresco_ae_v1_score_service", SCENARIOS)

    def test_api_server_health_endpoint(self):
        """Start api_server and verify /health responds."""
        proc = subprocess.Popen(
            [sys.executable, str(REPO_ROOT / "integration" / "api_server.py"),
             "--host", "127.0.0.1", "--port", "18082"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO_ROOT
        )
        time.sleep(1.5)
        try:
            result = subprocess.run(
                ["curl", "-s", "http://127.0.0.1:18082/health"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                self.assertEqual(data.get("status"), "ok")
                self.assertIn("service", data)
            else:
                self.skipTest("curl failed or api_server did not start")
        finally:
            proc.terminate()
            proc.wait(timeout=3)


class TestMCPAdapterInterfaceContracts(unittest.TestCase):
    """Test mcp_adapter.py tool interface contracts."""

    def test_get_capabilities_tool(self):
        """get_capabilities: verify tool list and boundaries."""
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "integration" / "mcp_adapter.py")],
            input=json.dumps({"tool": "get_capabilities"}),
            capture_output=True,
            text=True,
            cwd=REPO_ROOT
        )
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("tools", data)
        self.assertIn("boundaries", data)
        tool_names = [t["name"] for t in data["tools"]]
        self.assertIn("score_alfresco_ae_v1_sample", tool_names)
        self.assertIn("list_reports", tool_names)
        self.assertIn("query_evidence", tool_names)

    def test_list_reports_tool(self):
        """list_reports: verify report whitelist structure."""
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "integration" / "mcp_adapter.py")],
            input=json.dumps({"tool": "list_reports"}),
            capture_output=True,
            text=True,
            cwd=REPO_ROOT
        )
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("reports", data)
        self.assertIsInstance(data["reports"], list)
        for report in data["reports"]:
            self.assertIn("path", report)
            self.assertIn("exists", report)

    def test_query_evidence_whitelist_enforcement(self):
        """query_evidence: reject non-whitelisted paths."""
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "integration" / "mcp_adapter.py")],
            input=json.dumps({"tool": "query_evidence", "arguments": {"path": "/etc/passwd"}}),
            capture_output=True,
            text=True,
            cwd=REPO_ROOT
        )
        data = json.loads(result.stdout)
        self.assertEqual(data.get("status"), "reject")
        self.assertIn("error", data)

    def test_query_evidence_whitelisted_path(self):
        """query_evidence: accept whitelisted evidence path."""
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "integration" / "mcp_adapter.py")],
            input=json.dumps({
                "tool": "query_evidence",
                "arguments": {"path": "out/alfresco_ae_v1_score_compare/summary.csv"}
            }),
            capture_output=True,
            text=True,
            cwd=REPO_ROOT
        )
        data = json.loads(result.stdout)
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("path", data)
        self.assertIn("exists", data)
        self.assertIn("header", data)


class TestReportOutputContracts(unittest.TestCase):
    """Test eval_report.json and fuzzer_stats output contracts."""

    def test_eval_report_json_structure(self):
        """Verify eval_report.json contains all required fields."""
        # Find a real eval_report.json from existing test runs
        candidates = list((REPO_ROOT / "out").rglob("eval_report.json"))
        if not candidates:
            self.skipTest("No eval_report.json found in out/")

        report_path = candidates[0]
        data = json.loads(report_path.read_text(encoding="utf-8"))

        # Task metadata
        self.assertIn("task", data)
        task = data["task"]
        self.assertIn("target_type_name", task)
        self.assertIn("target_endpoint", task)
        self.assertIn("mutation_scope", task)
        self.assertIn("max_test_cases", task)
        self.assertIn("time_budget_sec", task)

        # Coverage
        self.assertIn("security_state_cov", data)
        cov = data["security_state_cov"]
        self.assertIn("security_state_total", cov)
        self.assertIn("security_state_new_total", cov)
        self.assertIn("security_state_seed_credit", cov)

        # MAB
        self.assertIn("mab", data)
        mab = data["mab"]
        self.assertIn("total_pulls", mab)
        self.assertIn("arms", mab)
        self.assertEqual(len(mab["arms"]), 3)

        # Validity
        self.assertIn("validity", data)
        validity = data["validity"]
        self.assertIn("valid_cnt", validity)
        self.assertIn("invalid_cnt", validity)
        self.assertIn("invalid_rate", validity)

        # Err
        self.assertIn("err", data)
        err = data["err"]
        self.assertIn("err_exec", err)
        self.assertIn("err_rate", err)

        # Rec
        self.assertIn("rec", data)
        rec = data["rec"]
        self.assertIn("rec_total", rec)
        self.assertIn("rec_success", rec)
        self.assertIn("rec_rate", rec)
        self.assertIn("rec_avg_ms", rec)

        # Exec summary
        self.assertIn("exec", data)
        exec_data = data["exec"]
        self.assertIn("valid_exec", exec_data)
        self.assertIn("total_execs", exec_data)

    def test_fuzzer_stats_nv_fields(self):
        """Verify fuzzer_stats contains all NV fields."""
        # Find a real fuzzer_stats from existing test runs
        candidates = list((REPO_ROOT / "out").rglob("fuzzer_stats"))
        if not candidates:
            self.skipTest("No fuzzer_stats found in out/")

        stats_path = candidates[0]
        content = stats_path.read_text(encoding="utf-8")

        # Task fields
        self.assertIn("nv_task_path", content)
        self.assertIn("nv_target_type", content)
        self.assertIn("nv_max_test_cases", content)
        self.assertIn("nv_time_budget_sec", content)

        # MAB fields
        self.assertIn("nv_mab_total_pulls", content)
        self.assertIn("nv_mab_arm0_pulls", content)
        self.assertIn("nv_mab_arm1_pulls", content)
        self.assertIn("nv_mab_arm2_pulls", content)

        # Security state coverage
        self.assertIn("security_state_total", content)
        self.assertIn("security_state_new_total", content)
        self.assertIn("security_state_seed_credit", content)

        # Validity
        self.assertIn("nv_valid_cnt", content)
        self.assertIn("nv_invalid_cnt", content)
        self.assertIn("nv_invalid_rate", content)

        # Err/Rec
        self.assertIn("nv_total_valid_exec", content)
        self.assertIn("nv_err_exec", content)
        self.assertIn("nv_err_rate", content)
        self.assertIn("nv_rec_total", content)
        self.assertIn("nv_rec_success", content)
        self.assertIn("nv_rec_rate", content)
        self.assertIn("nv_rec_avg_ms", content)

        # SS scheduler
        self.assertIn("ss_new_bits_any", content)
        self.assertIn("ss_new_bits_kept", content)


if __name__ == "__main__":
    unittest.main()
