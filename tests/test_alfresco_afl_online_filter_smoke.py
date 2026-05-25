import csv
import json
import py_compile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AlfrescoAflOnlineFilterSmokeTest(unittest.TestCase):
    def test_wrapper_and_summarizer_compile(self) -> None:
        py_compile.compile(
            str(REPO_ROOT / "targets/alfresco_content_update_online_filter_wrapper.py"),
            doraise=True,
        )
        py_compile.compile(
            str(REPO_ROOT / "scripts/summarize_alfresco_afl_online_filter_smoke.py"),
            doraise=True,
        )

    def test_profile_parses(self) -> None:
        path = REPO_ROOT / "integration/platform_profiles/alfresco_afl_online_filter_smoke.json"
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data.get("profile"), "alfresco_afl_online_filter_smoke")
        self.assertEqual(data.get("scenario"), "alfresco_content_update")
        self.assertTrue(data.get("online_filter"))
        self.assertEqual(data.get("default_mode"), "rule_ae")
        self.assertTrue(data.get("ae_v1_primary"))

    def test_optional_summary_header(self) -> None:
        summary_path = REPO_ROOT / "out/alfresco_afl_online_filter_smoke_latest/summary.csv"
        if not summary_path.exists():
            self.skipTest("optional AFL online filter summary is not present")
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
            "body_score_pass",
            "body_score_reject",
            "summary_source",
            "execution_scope",
            "online_filter_mode",
            "sent_to_target",
            "filtered_by_rule",
            "filtered_by_ae",
            "filtered_by_fanogan",
        }
        self.assertTrue(required.issubset(header), f"missing {required - header}")


if __name__ == "__main__":
    unittest.main()
