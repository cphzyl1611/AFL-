import csv
import json
import py_compile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AlfrescoMultipartOnlineFilterSmokeTest(unittest.TestCase):
    def test_mock_wrapper_and_summarizer_compile(self) -> None:
        py_compile.compile(str(REPO_ROOT / "targets/alfresco_multipart_upload_mock.py"), doraise=True)
        py_compile.compile(
            str(REPO_ROOT / "targets/alfresco_multipart_upload_online_filter_wrapper.py"),
            doraise=True,
        )
        py_compile.compile(
            str(REPO_ROOT / "scripts/summarize_alfresco_afl_multipart_online_filter_smoke.py"),
            doraise=True,
        )

    def test_seed_files_exist(self) -> None:
        seed_dir = REPO_ROOT / "in/alfresco_afl_multipart_upload_smoke"
        expected = {
            "seed_ok_0.multipart",
            "seed_ok_1.multipart",
            "seed_border_0.multipart",
            "seed_bad_0.multipart",
        }
        found = {path.name for path in seed_dir.glob("*.multipart")}
        self.assertTrue(expected.issubset(found), f"missing {expected - found}")
        for name in expected:
            self.assertGreater((seed_dir / name).stat().st_size, 0)

    def test_profile_parses(self) -> None:
        path = REPO_ROOT / "integration/platform_profiles/alfresco_multipart_online_filter_smoke.json"
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data.get("profile"), "alfresco_multipart_online_filter_smoke")
        self.assertEqual(data.get("platform"), "alfresco")
        self.assertEqual(data.get("scenario"), "alfresco_multipart_upload")
        self.assertEqual(data.get("body_type"), "multipart/form-data")
        self.assertTrue(data.get("online_filter"))
        self.assertEqual(data.get("default_mode"), "rule_ae")
        self.assertTrue(data.get("ae_v1_primary"))

    def test_optional_summary_header(self) -> None:
        summary_path = REPO_ROOT / "out/alfresco_afl_multipart_online_filter_smoke_latest/summary.csv"
        if not summary_path.exists():
            self.skipTest("optional multipart online filter summary is not present")
        with summary_path.open("r", encoding="utf-8-sig", newline="") as fh:
            header = set(next(csv.reader(fh)))
        required = {
            "mode",
            "scenario",
            "nv_total_valid_exec",
            "nv_err_exec",
            "nv_err_rate",
            "saved_hangs",
            "saved_crashes",
            "body_rule_pass",
            "body_rule_reject",
            "body_score_pass",
            "body_score_reject",
            "body_score_rpc_ok",
            "body_score_rpc_fail",
            "summary_source",
            "execution_scope",
            "online_filter_mode",
            "sent_to_target",
            "filtered_by_rule",
            "filtered_by_ae",
            "filtered_by_fanogan",
            "filename_detected_count",
            "content_type_detected_count",
        }
        self.assertTrue(required.issubset(header), f"missing {required - header}")


if __name__ == "__main__":
    unittest.main()
