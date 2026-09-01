"""Contracts for the one-shot Alfresco multipart bounded reproduction entry."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "reproduce_alfresco_multipart_bounded.py"
CANONICAL = REPO_ROOT / "in" / "alfresco_multipart_upload_bounded"


def load_module():
    spec = importlib.util.spec_from_file_location("multipart_reproduction", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("reproduction script cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CanonicalMultipartSeedTest(unittest.TestCase):
    def test_positive_manifest_is_canonical_and_negatives_are_separate(self) -> None:
        module = load_module()
        result = module.validate_canonical_seed_set(CANONICAL)
        self.assertEqual(result["positive_names"], ["seed_0.http", "seed_1.http", "seed_2.http"])
        self.assertEqual(
            result["negative_names"],
            ["negative_boundary_mismatch.http", "negative_missing_filedata.http"],
        )
        self.assertEqual(result["positive_count"], 3)
        self.assertTrue(result["regular_files"])
        self.assertTrue(result["exact_manifest_view"])
        self.assertTrue(result["positive_parseable"])
        self.assertTrue(result["negative_rejected"])


class MultipartReproductionTest(unittest.TestCase):
    def test_dry_run_never_invokes_negative_or_arm_runners(self) -> None:
        module = load_module()
        calls = []
        with tempfile.TemporaryDirectory(prefix="multipart-repro-dry-") as tmp:
            report = module.reproduce(
                repo_root=REPO_ROOT,
                output_root=Path(tmp) / "out",
                allow_real_write=False,
                negative_runner=lambda **kwargs: calls.append(("negative", kwargs)),
                arm_runner=lambda **kwargs: calls.append(("arm", kwargs)),
            )
        self.assertEqual(calls, [])
        self.assertEqual(report["status"], "dry_run_pass")
        self.assertEqual(report["execution_order"], ["negative", "field_value", "boundary", "structure"])

    def test_real_write_runs_negative_then_three_arms_in_order(self) -> None:
        module = load_module()
        calls = []

        def negative_runner(**kwargs):
            calls.append(("negative", kwargs["output_root"].name))
            return {
                "status": "pass",
                "http_sent": 0,
                "nodes_created": 0,
                "validation_rejects": 2,
            }

        def arm_runner(**kwargs):
            arm = kwargs["mutation_scope"]
            calls.append((arm, kwargs["run_root"].name))
            return {
                "status": "pass",
                "mutation_scope": arm,
                "selected_seed_count": 2,
                "http_201": 1,
                "readback_pass": 1,
                "runner_exit_code": 0,
            }

        with tempfile.TemporaryDirectory(prefix="multipart-repro-real-") as tmp:
            report = module.reproduce(
                repo_root=REPO_ROOT,
                output_root=Path(tmp) / "out",
                allow_real_write=True,
                negative_runner=negative_runner,
                arm_runner=arm_runner,
            )
            saved = json.loads((Path(tmp) / "out" / "multipart_reproduction_report.json").read_text())

        self.assertEqual([name for name, _ in calls], ["negative", "field_value", "boundary", "structure"])
        self.assertEqual(report["status"], "pass")
        self.assertEqual(saved["status"], "pass")
        serialized = json.dumps(saved, sort_keys=True)
        self.assertNotIn("ALFRESCO_PASS", serialized)
        self.assertNotIn("Authorization", serialized)

    def test_real_write_stops_after_first_failed_arm(self) -> None:
        module = load_module()
        calls = []

        def negative_runner(**kwargs):
            calls.append("negative")
            return {"status": "pass", "http_sent": 0, "nodes_created": 0, "validation_rejects": 2}

        def arm_runner(**kwargs):
            arm = kwargs["mutation_scope"]
            calls.append(arm)
            return {"status": "failed" if arm == "boundary" else "pass", "mutation_scope": arm}

        with tempfile.TemporaryDirectory(prefix="multipart-repro-stop-") as tmp:
            report = module.reproduce(
                repo_root=REPO_ROOT,
                output_root=Path(tmp) / "out",
                allow_real_write=True,
                negative_runner=negative_runner,
                arm_runner=arm_runner,
            )
        self.assertEqual(calls, ["negative", "field_value", "boundary"])
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failed_stage"], "boundary")

    def test_cli_dry_run_imports_repo_modules_when_invoked_by_path(self) -> None:
        import os
        import subprocess
        import sys

        with tempfile.TemporaryDirectory(prefix="multipart-cli-dry-") as tmp:
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--output-root", str(Path(tmp) / "out")],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"status": "dry_run_pass"', completed.stdout)

    def test_negative_stage_uses_real_harness_contract_without_upload(self) -> None:
        module = load_module()
        calls = []

        class FakeClient:
            parent_node_id = "parent-1"

            def list_children(self, parent_id):
                self.assert_parent = parent_id
                return [{"id": str(index)} for index in range(5)]

            def upload_multipart(self, **kwargs):
                calls.append("upload")
                raise AssertionError("negative validation must not upload")

        with tempfile.TemporaryDirectory(prefix="multipart-negative-contract-") as tmp:
            result = module.run_negative_validation(
                canonical_root=CANONICAL,
                output_root=Path(tmp) / "negative",
                client=FakeClient(),
                parent_id="parent-1",
                before_children=5,
            )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["http_sent"], 0)
        self.assertEqual(result["nodes_created"], 0)
        self.assertEqual(result["validation_rejects"], 2)
        self.assertEqual(calls, [])

    def test_negative_stage_fails_closed_without_parent_count_observation(self) -> None:
        module = load_module()

        class FakeClient:
            def list_children(self, parent_id):
                return []

            def upload_multipart(self, **kwargs):
                raise AssertionError("negative validation must not upload")

        with tempfile.TemporaryDirectory(prefix="multipart-negative-no-parent-") as tmp:
            result = module.run_negative_validation(
                canonical_root=CANONICAL,
                output_root=Path(tmp) / "negative",
                client=FakeClient(),
                before_children=0,
            )
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["parent_children_observed"])


if __name__ == "__main__":
    unittest.main()
