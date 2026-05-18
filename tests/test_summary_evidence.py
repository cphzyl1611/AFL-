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

    def test_optional_alfresco_content_update_header(self) -> None:
        path = REPO_ROOT / "out/alfresco_content_update_manual_latest/summary.csv"
        if not path.exists():
            self.skipTest("optional Alfresco content update summary is not present")
        header = self.read_header("out/alfresco_content_update_manual_latest/summary.csv")
        required = {
            "mode",
            "nv_total_valid_exec",
            "nv_err_exec",
            "nv_err_rate",
            "body_rule_pass",
            "body_rule_reject",
            "summary_source",
            "execution_scope",
            "metric_semantics",
        }
        self.assertTrue(required.issubset(header), f"missing {required - header}")

    def test_optional_alfresco_multipart_upload_header(self) -> None:
        path = REPO_ROOT / "out/alfresco_multipart_upload_manual_latest/summary.csv"
        if not path.exists():
            self.skipTest("optional Alfresco multipart upload summary is not present")
        header = self.read_header("out/alfresco_multipart_upload_manual_latest/summary.csv")
        required = {
            "mode",
            "nv_total_valid_exec",
            "nv_err_exec",
            "nv_err_rate",
            "body_rule_pass",
            "body_rule_reject",
            "summary_source",
            "execution_scope",
            "metric_semantics",
        }
        self.assertTrue(required.issubset(header), f"missing {required - header}")

    def test_optional_alfresco_ae_v1_score_header(self) -> None:
        path = REPO_ROOT / "out/alfresco_ae_v1_score_compare/summary.csv"
        if not path.exists():
            self.skipTest("optional Alfresco AE v1 score summary is not present")
        header = self.read_header("out/alfresco_ae_v1_score_compare/summary.csv")
        required = {
            "mode",
            "nv_total_valid_exec",
            "nv_err_exec",
            "nv_err_rate",
            "body_rule_pass",
            "body_rule_reject",
            "body_score_pass",
            "body_score_reject",
            "body_score_rpc_ok",
            "body_score_rpc_fail",
            "summary_source",
            "execution_scope",
            "metric_semantics",
        }
        self.assertTrue(required.issubset(header), f"missing {required - header}")


if __name__ == "__main__":
    unittest.main()
