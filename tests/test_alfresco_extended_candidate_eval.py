import json
import py_compile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "in/alfresco_extended_eval_dataset/manifest.json"


class AlfrescoExtendedCandidateEvalTest(unittest.TestCase):
    def test_manifest_entries_are_valid(self) -> None:
        self.assertTrue(MANIFEST.is_file())
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 60)

        allowed_scenarios = {"metadata_update", "content_update", "multipart_upload"}
        allowed_types = {"valid", "border", "invalid"}
        for item in data:
            self.assertIn(item.get("scenario"), allowed_scenarios)
            self.assertIsInstance(item.get("expected_valid"), bool)
            self.assertIn(item.get("sample_type"), allowed_types)
            rel_file = item.get("file")
            self.assertIsInstance(rel_file, str)
            self.assertTrue((MANIFEST.parent / rel_file).is_file(), rel_file)
            if item.get("expected_valid") is False:
                self.assertTrue(item.get("error_type"))

    def test_eval_script_compiles(self) -> None:
        py_compile.compile(
            str(REPO_ROOT / "scripts/run_alfresco_extended_candidate_eval.py"),
            doraise=True,
        )

    def test_optional_extended_eval_summary_header(self) -> None:
        summary = REPO_ROOT / "out/alfresco_extended_candidate_eval/summary.csv"
        if not summary.exists():
            self.skipTest("optional extended candidate eval output is not present")
        header = summary.read_text(encoding="utf-8").splitlines()[0].split(",")
        required = {
            "total_samples",
            "expected_valid",
            "expected_invalid",
            "rule_ae_false_accept",
            "rule_ae_false_reject",
            "rule_fanogan_false_accept",
            "rule_fanogan_false_reject",
            "rule_ae_accuracy",
            "rule_fanogan_accuracy",
            "recommendation",
            "execution_scope",
        }
        self.assertTrue(required.issubset(set(header)), f"missing {required - set(header)}")


if __name__ == "__main__":
    unittest.main()
