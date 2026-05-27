import csv
import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ThreeSemanticsOnlineFilterDeliveryTest(unittest.TestCase):
    def test_optional_matrix_header(self) -> None:
        matrix_path = REPO_ROOT / "out/three_semantics_online_filter_delivery_matrix.csv"
        if not matrix_path.exists():
            self.skipTest("optional three semantics delivery matrix is not present")
        with matrix_path.open("r", encoding="utf-8-sig", newline="") as fh:
            header = set(next(csv.reader(fh)))
        required = {
            "scenario",
            "body_type",
            "smoke_done",
            "ablation_done",
            "stability_done",
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
            "overall_stability_score",
            "ae_primary_recommendation",
            "fanogan_observation",
            "boundary",
        }
        self.assertTrue(required.issubset(header), f"missing {required - header}")

    def test_optional_report_json(self) -> None:
        report_path = REPO_ROOT / "out/three_semantics_online_filter_delivery_report.json"
        if not report_path.exists():
            self.skipTest("optional three semantics delivery report is not present")
        data = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertIn("current_commit", data)
        self.assertIn("scenarios", data)
        self.assertIn("boundary", data)
        self.assertEqual(data["current_commit"], "e8a9ece")
        self.assertEqual(len(data["scenarios"]), 3)


if __name__ == "__main__":
    unittest.main()
