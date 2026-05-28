import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class V061DeliveryDocsTest(unittest.TestCase):
    def test_delivery_report_metadata_fields(self) -> None:
        report_path = REPO_ROOT / "out/three_semantics_online_filter_delivery_report.json"
        self.assertTrue(report_path.is_file(), f"{report_path} missing")
        data = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("current_commit"), "55104eb")
        self.assertEqual(data.get("current_tag"), "v0.6.0-three-semantics-online-filter-delivery")
        self.assertEqual(data.get("delivery_tag"), "v0.6.0-three-semantics-online-filter-delivery")
        self.assertEqual(data.get("delivery_tag_commit"), "55104eb")
        self.assertEqual(data.get("evidence_baseline_commit"), "e8a9ece")
        self.assertEqual(data.get("evidence_baseline_tag"), "v0.5.2-multipart-online-filter-stability")
        self.assertIn("metadata_note", data)

    def test_acceptance_docs_exist(self) -> None:
        required = [
            REPO_ROOT / "docs/review/模糊测试模块项目要求-v0.6.1对照表.md",
            REPO_ROOT / "docs/review/v0.6.1验收答辩口径说明.md",
        ]
        missing = [str(path) for path in required if not path.is_file()]
        self.assertFalse(missing, f"missing docs: {missing}")


if __name__ == "__main__":
    unittest.main()
