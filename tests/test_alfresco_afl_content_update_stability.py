import csv
import py_compile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AlfrescoAflContentUpdateStabilityTest(unittest.TestCase):
    def test_run_script_exists(self) -> None:
        path = REPO_ROOT / "scripts/run_alfresco_afl_content_update_stability.sh"
        self.assertTrue(path.is_file())

    def test_summarizer_compiles(self) -> None:
        py_compile.compile(
            str(REPO_ROOT / "scripts/summarize_alfresco_afl_content_update_stability.py"),
            doraise=True,
        )

    def test_optional_stability_outputs_have_expected_headers(self) -> None:
        summary_path = REPO_ROOT / "out/alfresco_afl_content_update_stability/stability_summary.csv"
        if not summary_path.exists():
            self.skipTest("optional AFL content update stability output is not present")

        with summary_path.open("r", encoding="utf-8-sig", newline="") as fh:
            summary_header = set(next(csv.reader(fh)))
        summary_required = {
            "runs",
            "total_execs_done",
            "total_valid_exec",
            "total_err_exec",
            "mean_nv_err_rate",
            "max_nv_err_rate",
            "stability_score",
            "summary_source",
            "execution_scope",
            "metric_semantics",
        }
        self.assertTrue(summary_required.issubset(summary_header), f"missing {summary_required - summary_header}")

        details_path = REPO_ROOT / "out/alfresco_afl_content_update_stability/stability_details.csv"
        with details_path.open("r", encoding="utf-8-sig", newline="") as fh:
            details_header = set(next(csv.reader(fh)))
        details_required = {
            "run_id",
            "run_time",
            "execs_done",
            "execs_per_sec",
            "nv_total_valid_exec",
            "nv_err_exec",
            "nv_err_rate",
            "saved_crashes",
            "saved_hangs",
            "summary_source",
            "execution_scope",
        }
        self.assertTrue(details_required.issubset(details_header), f"missing {details_required - details_header}")


if __name__ == "__main__":
    unittest.main()
