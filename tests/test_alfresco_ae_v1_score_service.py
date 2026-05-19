import py_compile
import unittest
from pathlib import Path

from model_stage.alfresco_ae_v1_scorer import AlfrescoAEV1Scorer
import model_stage.alfresco_ae_v1_score_service as score_service


REPO_ROOT = Path(__file__).resolve().parents[1]


class AlfrescoAEV1ScoreServiceTest(unittest.TestCase):
    def test_score_service_py_compile(self) -> None:
        py_compile.compile(str(REPO_ROOT / "model_stage/alfresco_ae_v1_score_service.py"), doraise=True)

    def test_score_service_imports(self) -> None:
        self.assertEqual(score_service.DEFAULT_HOST, "127.0.0.1")
        self.assertEqual(score_service.DEFAULT_PORT, 18181)

    def test_score_service_reuses_scorer(self) -> None:
        scorer = AlfrescoAEV1Scorer()
        result = scorer.score_sample(
            {
                "scenario": "metadata_update",
                "payload": {
                    "name": "official_doc.txt",
                    "properties": {
                        "cm:title": "标题",
                        "cm:description": "说明",
                    },
                },
            }
        )
        self.assertIn("score", result)
        self.assertIn(result["decision"], {"pass", "reject"})


if __name__ == "__main__":
    unittest.main()
