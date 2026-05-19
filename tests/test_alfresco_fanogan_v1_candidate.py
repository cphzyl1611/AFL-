import json
import unittest
from pathlib import Path

from model_stage.alfresco_fanogan_v1_candidate import torch_available
from model_stage.alfresco_fanogan_v1_candidate_scorer import AlfrescoFanoganV1CandidateScorer


REPO_ROOT = Path(__file__).resolve().parents[1]


class AlfrescoFanoganV1CandidateTest(unittest.TestCase):
    def test_torch_availability_probe_returns_bool(self) -> None:
        self.assertIsInstance(torch_available(), bool)

    def test_meta_file_is_parseable(self) -> None:
        path = REPO_ROOT / "model_stage/models/alfresco_fanogan_v1_candidate_meta.json"
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("model_name"), "alfresco_fanogan_v1_candidate")
        self.assertIn(data.get("model_type"), {"torch_fanogan_style_candidate", "gan_style_statistical_candidate"})
        self.assertGreater(data.get("train_sample_count", 0), 0)
        self.assertGreater(data.get("threshold_high", 0), 0)

    def test_scorer_returns_decision_for_content_update(self) -> None:
        scorer = AlfrescoFanoganV1CandidateScorer()
        result = scorer.score_text_content("会议纪要\n补充责任人和完成时限")
        self.assertIn("score", result)
        self.assertIn(result["decision"], {"pass", "reject"})
        self.assertIn(result["model_type"], {"torch_fanogan_style_candidate", "gan_style_statistical_candidate"})


if __name__ == "__main__":
    unittest.main()
