import csv
import py_compile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AlfrescoMultipartOnlineFilterAblationTest(unittest.TestCase):
    def test_run_script_exists(self) -> None:
        path = REPO_ROOT / "scripts/run_alfresco_afl_multipart_online_filter_ablation.sh"
        self.assertTrue(path.is_file())

    def test_summarizer_compiles(self) -> None:
        py_compile.compile(
            str(REPO_ROOT / "scripts/summarize_alfresco_afl_multipart_online_filter_ablation.py"),
            doraise=True,
        )

    def test_optional_ablation_summary_header(self) -> None:
        summary_path = REPO_ROOT / "out/alfresco_afl_multipart_online_filter_ablation/ablation_summary.csv"
        if not summary_path.exists():
            self.skipTest("optional multipart online filter ablation summary is not present")
        with summary_path.open("r", encoding="utf-8-sig", newline="") as fh:
            header = set(next(csv.reader(fh)))
        required = {
            "scenario",
            "modes",
            "total_execs_done",
            "total_valid_exec",
            "total_err_exec",
            "max_nv_err_rate",
            "saved_crashes_total",
            "saved_hangs_total",
            "total_tmout",
            "scoring_error_total",
            "rule_only_sent_to_target",
            "rule_ae_sent_to_target",
            "rule_fanogan_sent_to_target",
            "rule_ae_fanogan_sent_to_target",
            "rule_only_filtered_by_rule",
            "rule_ae_filtered_by_ae",
            "rule_fanogan_filtered_by_fanogan",
            "rule_ae_fanogan_filtered_by_fanogan",
            "rule_only_filename_detected_count",
            "rule_ae_filename_detected_count",
            "rule_fanogan_filename_detected_count",
            "rule_ae_fanogan_filename_detected_count",
            "ae_primary_recommendation",
            "fanogan_online_observation",
            "summary_source",
            "execution_scope",
            "metric_semantics",
        }
        self.assertTrue(required.issubset(header), f"missing {required - header}")


if __name__ == "__main__":
    unittest.main()
