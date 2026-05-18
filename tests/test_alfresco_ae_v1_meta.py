import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AlfrescoAEV1MetaTest(unittest.TestCase):
    def test_meta_file_is_consistent(self) -> None:
        path = REPO_ROOT / "model_stage/models/alfresco_ae_v1_meta.json"
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("model_name"), "alfresco_ae_v1")
        self.assertEqual(data.get("model_type"), "ae_like_statistical_baseline")
        self.assertGreater(data.get("train_sample_count", 0), 0)
        feature_names = data.get("feature_names")
        mean = data.get("mean")
        std = data.get("std")
        self.assertIsInstance(feature_names, list)
        self.assertEqual(len(feature_names), len(mean))
        self.assertEqual(len(feature_names), len(std))


if __name__ == "__main__":
    unittest.main()
