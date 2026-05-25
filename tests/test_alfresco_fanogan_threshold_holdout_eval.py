import py_compile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AlfrescoFanoganThresholdHoldoutEvalTest(unittest.TestCase):
    def read_header(self, rel_path: str) -> list[str]:
        path = REPO_ROOT / rel_path
        self.assertTrue(path.is_file(), rel_path)
        return path.read_text(encoding="utf-8").splitlines()[0].split(",")

    def test_script_compiles(self) -> None:
        py_compile.compile(
            str(REPO_ROOT / "scripts/run_alfresco_fanogan_threshold_holdout_eval.py"),
            doraise=True,
        )

    def test_optional_holdout_outputs_have_expected_headers(self) -> None:
        summary = REPO_ROOT / "out/alfresco_fanogan_threshold_holdout_eval/holdout_summary.csv"
        if not summary.exists():
            self.skipTest("optional fAnoGAN threshold holdout output is not present")

        calibration_header = self.read_header("out/alfresco_fanogan_threshold_holdout_eval/calibration_summary.csv")
        self.assertTrue(
            {
                "threshold",
                "false_accept",
                "false_reject",
                "accuracy",
                "selected",
                "reason",
            }.issubset(set(calibration_header))
        )

        holdout_header = self.read_header("out/alfresco_fanogan_threshold_holdout_eval/holdout_summary.csv")
        self.assertTrue(
            {
                "total_samples",
                "expected_valid",
                "expected_invalid",
                "rule_ae_false_accept",
                "rule_ae_false_reject",
                "rule_fanogan_default_false_accept",
                "rule_fanogan_default_false_reject",
                "rule_fanogan_calibrated_false_accept",
                "rule_fanogan_calibrated_false_reject",
                "chosen_threshold",
                "recommendation",
                "execution_scope",
            }.issubset(set(holdout_header))
        )

        details_header = self.read_header("out/alfresco_fanogan_threshold_holdout_eval/holdout_details.csv")
        self.assertTrue(
            {
                "split",
                "scenario",
                "file",
                "expected_valid",
                "rule_pass",
                "ae_score",
                "fanogan_score",
                "rule_ae_decision",
                "rule_fanogan_default_decision",
                "rule_fanogan_calibrated_decision",
            }.issubset(set(details_header))
        )


if __name__ == "__main__":
    unittest.main()
