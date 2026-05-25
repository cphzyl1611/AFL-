import csv
import py_compile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AlfrescoFanoganCandidateDiagnosisTest(unittest.TestCase):
    def test_diagnosis_script_compiles(self) -> None:
        py_compile.compile(
            str(REPO_ROOT / "scripts/diagnose_alfresco_fanogan_candidate.py"),
            doraise=True,
        )

    def read_header(self, rel_path: str) -> set[str]:
        path = REPO_ROOT / rel_path
        self.assertTrue(path.is_file(), f"missing file: {rel_path}")
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return set(next(csv.reader(fh)))

    def test_optional_diagnosis_outputs_have_headers(self) -> None:
        summary = REPO_ROOT / "out/alfresco_fanogan_candidate_diagnosis/diagnosis_summary.csv"
        if not summary.exists():
            self.skipTest("optional fAnoGAN diagnosis output is not present")

        diagnosis_header = self.read_header("out/alfresco_fanogan_candidate_diagnosis/diagnosis_summary.csv")
        self.assertTrue({"check_item", "status", "detail"}.issubset(diagnosis_header))

        false_reject_header = self.read_header("out/alfresco_fanogan_candidate_diagnosis/false_reject_samples.csv")
        self.assertTrue(
            {
                "scenario",
                "file",
                "expected_valid",
                "rule_pass",
                "ae_score",
                "fanogan_score",
                "difference_type",
            }.issubset(false_reject_header)
        )

        sensitivity_header = self.read_header("out/alfresco_fanogan_candidate_diagnosis/threshold_sensitivity.csv")
        self.assertTrue({"threshold", "false_accept", "false_reject", "accuracy", "notes"}.issubset(sensitivity_header))


if __name__ == "__main__":
    unittest.main()
