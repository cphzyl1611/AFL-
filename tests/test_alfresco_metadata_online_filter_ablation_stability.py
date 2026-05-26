import csv
import py_compile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AlfrescoMetadataOnlineFilterAblationStabilityTest(unittest.TestCase):
    def test_run_script_exists(self) -> None:
        path = REPO_ROOT / "scripts/run_alfresco_afl_metadata_online_filter_ablation_stability.sh"
        self.assertTrue(path.is_file())

    def test_summarizer_compiles(self) -> None:
        py_compile.compile(
            str(REPO_ROOT / "scripts/summarize_alfresco_afl_metadata_online_filter_ablation_stability.py"),
            doraise=True,
        )

    def test_optional_stability_summary_header(self) -> None:
        summary_path = REPO_ROOT / "out/alfresco_afl_metadata_online_filter_ablation_stability/stability_summary.csv"
        if not summary_path.exists():
            self.skipTest("optional metadata online filter ablation stability summary is not present")
        with summary_path.open("r", encoding="utf-8-sig", newline="") as fh:
            header = set(next(csv.reader(fh)))
        required = {
            "scenario",
            "modes",
            "runs_per_mode",
            "total_runs",
            "total_execs_done",
            "total_valid_exec",
            "total_err_exec",
            "max_nv_err_rate",
            "saved_crashes_total",
            "saved_hangs_total",
            "scoring_error_total",
            "rule_only_stability_score",
            "rule_ae_stability_score",
            "rule_fanogan_stability_score",
            "rule_ae_fanogan_stability_score",
            "overall_stability_score",
            "rule_only_total_sent_to_target",
            "rule_ae_total_sent_to_target",
            "rule_fanogan_total_sent_to_target",
            "rule_ae_fanogan_total_sent_to_target",
            "ae_primary_recommendation",
            "fanogan_online_stability_observation",
            "summary_source",
            "execution_scope",
            "metric_semantics",
        }
        self.assertTrue(required.issubset(header), f"missing {required - header}")


if __name__ == "__main__":
    unittest.main()
