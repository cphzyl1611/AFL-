import csv
import json
import py_compile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AlfrescoAflContentUpdateSmokeTest(unittest.TestCase):
    def test_mock_target_and_summarizer_compile(self) -> None:
        py_compile.compile(str(REPO_ROOT / "targets/alfresco_content_update_mock.py"), doraise=True)
        py_compile.compile(str(REPO_ROOT / "scripts/summarize_alfresco_afl_content_update_smoke.py"), doraise=True)

    def test_smoke_seed_files_exist(self) -> None:
        seed_dir = REPO_ROOT / "in/alfresco_afl_content_update_smoke"
        self.assertTrue(seed_dir.is_dir())
        expected = {
            "seed_ok_0.txt",
            "seed_ok_1.txt",
            "seed_border_0.txt",
            "seed_bad_0.txt",
        }
        actual = {path.name for path in seed_dir.glob("*")}
        self.assertTrue(expected.issubset(actual), f"missing {expected - actual}")

    def test_smoke_profile_parses(self) -> None:
        path = REPO_ROOT / "integration/platform_profiles/alfresco_afl_content_update_smoke.json"
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data.get("profile"), "alfresco_afl_content_update_smoke")
        self.assertEqual(data.get("target_type"), "local_mock")
        self.assertEqual(data.get("scenario"), "alfresco_content_update")

    def test_optional_summary_header(self) -> None:
        summary_path = REPO_ROOT / "out/alfresco_afl_content_update_smoke_latest/summary.csv"
        if not summary_path.exists():
            self.skipTest("optional AFL content update smoke summary is not present")
        with summary_path.open("r", encoding="utf-8-sig", newline="") as fh:
            header = set(next(csv.reader(fh)))
        required = {
            "mode",
            "nv_total_valid_exec",
            "nv_err_exec",
            "nv_err_rate",
            "saved_hangs",
            "saved_crashes",
            "body_rule_pass",
            "body_rule_reject",
            "summary_source",
            "execution_scope",
            "metric_semantics",
        }
        self.assertTrue(required.issubset(header), f"missing {required - header}")


if __name__ == "__main__":
    unittest.main()
