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

    def test_optional_alfresco_ae_v1_threshold_sweep_headers(self) -> None:
        summary_path = REPO_ROOT / "out/alfresco_ae_v1_threshold_sweep/summary.csv"
        if not summary_path.exists():
            self.skipTest("optional Alfresco AE v1 threshold sweep output is not present")

        summary_header = self.read_header("out/alfresco_ae_v1_threshold_sweep/summary.csv")
        summary_required = {
            "threshold",
            "total_samples",
            "expected_valid",
            "expected_invalid",
            "rule_only_pass",
            "rule_only_reject",
            "ae_only_pass",
            "ae_only_reject",
            "rule_ae_pass",
            "rule_ae_reject",
            "false_accept",
            "false_reject",
            "accuracy",
        }
        self.assertTrue(summary_required.issubset(summary_header), f"missing {summary_required - summary_header}")

        details_header = self.read_header("out/alfresco_ae_v1_threshold_sweep/details.csv")
        details_required = {
            "scenario",
            "sample_name",
            "sample_origin",
            "expected_valid",
            "rule_pass",
            "ae_score",
            "threshold",
            "ae_pass",
            "rule_ae_decision",
            "error_type",
            "feature_vector",
        }
        self.assertTrue(details_required.issubset(details_header), f"missing {details_required - details_header}")

        distribution_header = self.read_header("out/alfresco_ae_v1_threshold_sweep/score_distribution.csv")
        distribution_required = {
            "scenario",
            "sample_origin",
            "expected_valid",
            "min_score",
            "median_score",
            "max_score",
            "count",
        }
        self.assertTrue(distribution_required.issubset(distribution_header), f"missing {distribution_required - distribution_header}")

    def test_optional_alfresco_ae_v1_service_compare_headers(self) -> None:
        summary_path = REPO_ROOT / "out/alfresco_ae_v1_service_compare/summary.csv"
        if not summary_path.exists():
            self.skipTest("optional Alfresco AE v1 service compare output is not present")

        summary_header = self.read_header("out/alfresco_ae_v1_service_compare/summary.csv")
        summary_required = {
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
        }
        self.assertTrue(summary_required.issubset(summary_header), f"missing {summary_required - summary_header}")

        details_header = self.read_header("out/alfresco_ae_v1_service_compare/details.csv")
        details_required = {
            "scenario",
            "seed_file",
            "expected_negative",
            "rule_pass",
            "http_code",
            "score",
            "score_pass",
            "decision",
            "reason",
            "service_latency_ms",
        }
        self.assertTrue(details_required.issubset(details_header), f"missing {details_required - details_header}")

    def test_optional_alfresco_fanogan_candidate_headers(self) -> None:
        summary_path = REPO_ROOT / "out/alfresco_fanogan_v1_candidate_compare/summary.csv"
        if not summary_path.exists():
            self.skipTest("optional Alfresco fAnoGAN candidate output is not present")

        summary_header = self.read_header("out/alfresco_fanogan_v1_candidate_compare/summary.csv")
        summary_required = {
            "mode",
            "total_samples",
            "expected_valid",
            "expected_invalid",
            "rule_only_pass",
            "rule_only_reject",
            "ae_v1_pass",
            "ae_v1_reject",
            "fanogan_pass",
            "fanogan_reject",
            "rule_fanogan_pass",
            "rule_fanogan_reject",
            "false_accept",
            "false_reject",
            "accuracy",
            "model_type",
            "summary_source",
            "execution_scope",
        }
        self.assertTrue(summary_required.issubset(summary_header), f"missing {summary_required - summary_header}")

        details_header = self.read_header("out/alfresco_fanogan_v1_candidate_compare/details.csv")
        details_required = {
            "scenario",
            "sample_name",
            "sample_origin",
            "expected_valid",
            "rule_pass",
            "ae_score",
            "ae_decision",
            "fanogan_score",
            "fanogan_decision",
            "rule_fanogan_decision",
            "model_type",
        }
        self.assertTrue(details_required.issubset(details_header), f"missing {details_required - details_header}")

        compare_header = self.read_header("out/alfresco_fanogan_v1_candidate_compare/compare_with_ae.csv")
        compare_required = {"strategy", "false_accept", "false_reject", "accuracy", "notes"}
        self.assertTrue(compare_required.issubset(compare_header), f"missing {compare_required - compare_header}")


if __name__ == "__main__":
    unittest.main()
