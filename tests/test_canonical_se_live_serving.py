from __future__ import annotations

import json
import unittest

from tests.test_sefanogan_backend_wiring import (
    ROOT,
    load_server_from,
    production_environment,
    reference_artifacts,
)

from model_stage.alfresco_feature_extractor import extract_metadata_features, feature_names
from scripts.run_alfresco_ae_v1_threshold_sweep import seed_samples


def _first_valid_metadata_seed():
    for sample in seed_samples():
        if sample.scenario == "metadata_update" and sample.sample_origin == "seed" and sample.expected_valid:
            return sample
    raise unittest.SkipTest("no valid Alfresco metadata_update seed sample available")


class CanonicalSELiveServingTest(unittest.TestCase):
    """Characterizes the canonical Alfresco SE-fAnoGAN-ES live-serving path.

    metadata_update is the only scenario the production runner
    (scripts/run_alfresco_bounded_feedback.py) ever routes to the SE
    reference score RPC: it forces enable_validity=0 for multipart_upload,
    and it does not support content_update as a scenario at all. So the
    live serving fix only needs to reproduce the metadata_update
    training-time contract exactly; there is no live RPC path for the
    other two scenarios to characterize here.
    """

    def _load_reference_backend_server(self):
        reference_artifacts()  # skips the test outright if the frozen checkpoint is unavailable
        env = production_environment("sefanogan_es_reference")
        return load_server_from(ROOT / "model_stage/nv_valid_server_real.py", env)

    def test_se_reference_backend_is_real_reference_scorer(self):
        server = self._load_reference_backend_server()
        self.assertEqual(type(server.PREDICTOR).__module__, "model_stage.sefanogan_es_reference")
        self.assertEqual(type(server.PREDICTOR).__name__, "ReferenceScorer")

    def test_canonical_metadata_body_reaches_32dim_training_contract(self):
        sample = _first_valid_metadata_seed()
        body = json.dumps(sample.payload, ensure_ascii=False).encode("utf-8")

        expected_vector = extract_metadata_features(sample.payload)
        self.assertEqual(len(expected_vector), 32)
        self.assertEqual(feature_names()[0], "scenario_metadata_update")

        server = self._load_reference_backend_server()
        result = server.predict_score_from_body(body)

        expected_score = server.PREDICTOR.score(expected_vector)
        self.assertAlmostEqual(float(result["score"]), float(expected_score), places=9)


if __name__ == "__main__":
    unittest.main()
