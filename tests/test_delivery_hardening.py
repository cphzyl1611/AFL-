"""Regression contracts for the bounded Task 4 delivery path."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeliveryHardeningTest(unittest.TestCase):
    def test_dependency_manifests_are_explicit(self) -> None:
        self.assertTrue((ROOT / "requirements.txt").is_file())
        dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertIn("pytest==9.1.1", dev)
        self.assertTrue((ROOT / "requirements-live.txt").is_file())
        self.assertTrue((ROOT / "docs/DEPENDENCIES.md").is_file())

    def test_offline_runner_has_bounded_explicit_scope(self) -> None:
        script = (ROOT / "scripts/run_task4_offline.sh").read_text(encoding="utf-8")
        self.assertNotIn("unittest discover", script)
        self.assertNotIn("pytest tests/", script)
        self.assertIn("-u HTTP_PROXY", script)
        self.assertIn("tests/test_delivery_hardening.py", script)
        self.assertIn("tests/test_o2oa_create_update_e2e.py", script)
        self.assertIn("OFFLINE_TEST_TIMEOUT", script)
        self.assertIn("FEEDBACK_TEST_TIMEOUT", script)
        self.assertIn("c_validation_rejection_clears_pending_without_execution", script)

    def test_preflight_does_not_follow_excluded_trees_or_symlinks(self) -> None:
        script = (ROOT / "scripts/delivery_preflight_check.py").read_text(encoding="utf-8")
        self.assertIn("followlinks=False", script)
        for name in (".git", "venv", "task4-evidence", "reproduce-results", "out"):
            self.assertIn(f'"{name}"', script)

    def test_sample_wrapper_is_bounded_and_fail_closed(self) -> None:
        script = (ROOT / "scripts/run_task4_sample.py").read_text(encoding="utf-8")
        self.assertIn('"enable_validity": 1', script)
        self.assertIn("DELIVERY_SMOKE_ONLY", script)
        self.assertIn("NOT_FOR_PERFORMANCE_CLAIM", script)
        self.assertIn("OUT.exists()", script)
        self.assertIn("old absolute worktree path", script)

    def test_runtime_baseline_points_at_release_candidate(self) -> None:
        data = json.loads((ROOT / "runtime_baseline_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(data["checkpoint_commit"], "6e52afc4dfe20b21126d10c06888e54833a5e021")
        self.assertEqual(len(data["files"]), 7)
        for entry in data["files"]:
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")

    def test_delivery_guide_mentions_live_boundary_and_output_contract(self) -> None:
        guide = (ROOT / "docs/DELIVERY_GUIDE.md").read_text(encoding="utf-8")
        for term in (
            "run_task4_offline.sh",
            "run_task4_sample.sh",
            "O2OA",
            "Alfresco",
            "Cov",
            "Rec",
            "mode-0600",
            "DELIVERY_SMOKE_ONLY",
        ):
            self.assertIn(term, guide)


if __name__ == "__main__":
    unittest.main()
