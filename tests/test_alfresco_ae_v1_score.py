import unittest

from model_stage.alfresco_ae_v1_scorer import AlfrescoAEV1Scorer


class AlfrescoAEV1ScoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scorer = AlfrescoAEV1Scorer()

    def test_valid_metadata_scores_pass(self) -> None:
        result = self.scorer.score_metadata_payload(
            {
                "name": "official_doc_metadata_ok.txt",
                "properties": {
                    "cm:title": "关于系统联调测试的通知",
                    "cm:description": "用于验证文档元数据更新",
                },
            }
        )
        self.assertIn("score", result)
        self.assertTrue(result["pass"])

    def test_valid_text_scores(self) -> None:
        result = self.scorer.score_text_content("会议纪要\n补充责任人和完成时限")
        self.assertIn(result["decision"], {"pass", "reject"})
        self.assertIn("feature_vector", result)

    def test_valid_upload_scores(self) -> None:
        result = self.scorer.score_multipart_upload(
            "official_doc.txt",
            "关于系统联调测试的通知".encode("utf-8"),
            {"nodeType": "cm:content", "autoRename": "true"},
        )
        self.assertIn(result["decision"], {"pass", "reject"})
        self.assertIn("feature_vector", result)


if __name__ == "__main__":
    unittest.main()
