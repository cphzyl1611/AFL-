import csv
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class SummaryEvidenceTest(unittest.TestCase):
    def read_header(self, rel_path: str) -> set[str]:
        path = REPO_ROOT / rel_path
        self.assertTrue(path.is_file(), f"missing summary: {rel_path}")
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            return set(next(reader))

    def test_nv_mab_smoke_header(self) -> None:
        header = self.read_header("out/nv_mab_smoke_summary.csv")
        required = {"case_name", "nv_mab_total_pulls", "arm0_pulls", "arm1_pulls", "arm2_pulls", "expected_pass"}
        self.assertTrue(required.issubset(header), f"missing {required - header}")

    def test_nv_mab_stability_header(self) -> None:
        header = self.read_header("out/nv_mab_stability_summary.csv")
        required = {
            "run_id",
            "nv_mab_total_pulls",
            "nv_mab_arm0_pulls",
            "nv_mab_arm1_pulls",
            "nv_mab_arm2_pulls",
            "expected_pass",
        }
        self.assertTrue(required.issubset(header), f"missing {required - header}")

    def test_nv_mab_ablation_header(self) -> None:
        header = self.read_header("out/nv_mab_ablation_summary.csv")
        required = {"group", "nv_mab_total_pulls", "arm0_pulls", "arm1_pulls", "arm2_pulls", "expected_pass"}
        self.assertTrue(required.issubset(header), f"missing {required - header}")


if __name__ == "__main__":
    unittest.main()
