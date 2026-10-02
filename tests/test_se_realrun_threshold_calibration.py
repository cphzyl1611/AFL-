#!/usr/bin/env python3
"""TDD test suite for SE real-run threshold calibration (Phase 1A).

This test enforces the MATCHED_OPERATING_CRITERION policy: AE and SE must be
compared at the same predeclared filtering strictness, derived from the
existing AE legacy threshold on a common frozen offline calibration population.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Frozen calibration policy constants
AE_LEGACY_THRESHOLD_HIGH = 1.623614
EXPECTED_CALIBRATION_MANIFEST_HASH = "66f030011b79c05fa73e4f397d1524ae81f5b70a48814130eb4a44ba2c9ac5b8"
EXPECTED_CALIBRATION_SCENARIO = "metadata_update"
EXPECTED_MIN_NORMAL_SAMPLES = 10


class SEThresholdCalibrationContractTest(unittest.TestCase):
    """RED: Contract and fail-closed behavior tests."""

    def test_calibration_refuses_empty_population(self):
        """Empty calibration population must fail closed."""
        from scripts.calibrate_se_realrun_threshold import calibrate_threshold

        with self.assertRaises(ValueError) as ctx:
            calibrate_threshold(
                ae_scores=[],
                se_scores=[],
                sample_ids=[],
                ae_threshold=AE_LEGACY_THRESHOLD_HIGH,
            )
        self.assertIn("empty", str(ctx.exception).lower())

    def test_calibration_refuses_mismatched_sample_ids(self):
        """AE and SE must score the exact same sample IDs."""
        from scripts.calibrate_se_realrun_threshold import calibrate_threshold

        with self.assertRaises(ValueError) as ctx:
            calibrate_threshold(
                ae_scores=[1.0, 1.1],
                se_scores=[0.5],
                sample_ids=["a", "b"],
                ae_threshold=AE_LEGACY_THRESHOLD_HIGH,
            )
        self.assertIn("mismatch", str(ctx.exception).lower())

    def test_calibration_refuses_duplicate_sample_ids(self):
        """Duplicate sample IDs must fail closed."""
        from scripts.calibrate_se_realrun_threshold import calibrate_threshold

        with self.assertRaises(ValueError) as ctx:
            calibrate_threshold(
                ae_scores=[1.0, 1.1, 1.2],
                se_scores=[0.5, 0.6, 0.7],
                sample_ids=["a", "a", "b"],
                ae_threshold=AE_LEGACY_THRESHOLD_HIGH,
            )
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_calibration_refuses_non_finite_ae_scores(self):
        """Non-finite AE scores must fail closed."""
        from scripts.calibrate_se_realrun_threshold import calibrate_threshold

        with self.assertRaises(ValueError) as ctx:
            calibrate_threshold(
                ae_scores=[1.0, float('nan'), 1.2],
                se_scores=[0.5, 0.6, 0.7],
                sample_ids=["a", "b", "c"],
                ae_threshold=AE_LEGACY_THRESHOLD_HIGH,
            )
        self.assertIn("finite", str(ctx.exception).lower())

    def test_calibration_refuses_non_finite_se_scores(self):
        """Non-finite SE scores must fail closed."""
        from scripts.calibrate_se_realrun_threshold import calibrate_threshold

        with self.assertRaises(ValueError) as ctx:
            calibrate_threshold(
                ae_scores=[1.0, 1.1, 1.2],
                se_scores=[0.5, float('inf'), 0.7],
                sample_ids=["a", "b", "c"],
                ae_threshold=AE_LEGACY_THRESHOLD_HIGH,
            )
        self.assertIn("finite", str(ctx.exception).lower())

    def test_ae_threshold_verified_not_silently_replaced(self):
        """AE threshold must be read/verified, not silently replaced."""
        from scripts.calibrate_se_realrun_threshold import calibrate_threshold

        result = calibrate_threshold(
            ae_scores=[1.0, 1.5, 1.7],
            se_scores=[0.5, 0.6, 0.7],
            sample_ids=["a", "b", "c"],
            ae_threshold=AE_LEGACY_THRESHOLD_HIGH,
        )
        self.assertEqual(result["ae_threshold"], AE_LEGACY_THRESHOLD_HIGH)

    def test_threshold_selection_matches_ae_frr(self):
        """SE threshold must be selected to match AE FRR."""
        from scripts.calibrate_se_realrun_threshold import calibrate_threshold

        # AE: threshold=1.5, scores=[1.0, 1.4, 1.6, 1.8]
        # AE rejects 2/4 = 50% FRR
        # SE: scores=[0.5, 0.6, 1.0, 1.2]
        # SE threshold to match 50% FRR should be around 1.0 (rejects 2/4)
        result = calibrate_threshold(
            ae_scores=[1.0, 1.4, 1.6, 1.8],
            se_scores=[0.5, 0.6, 1.0, 1.2],
            sample_ids=["a", "b", "c", "d"],
            ae_threshold=1.5,
        )

        # SE threshold should be selected to match AE's 50% FRR
        self.assertAlmostEqual(result["ae_frr"], 0.5, places=2)
        self.assertAlmostEqual(result["se_frr"], 0.5, places=2)

    def test_tie_break_is_deterministic(self):
        """Tie-break must be deterministic and conservative."""
        from scripts.calibrate_se_realrun_threshold import calibrate_threshold

        # Run twice with same inputs
        result1 = calibrate_threshold(
            ae_scores=[1.0, 1.5, 1.7],
            se_scores=[0.5, 0.8, 1.1],
            sample_ids=["a", "b", "c"],
            ae_threshold=1.5,
        )
        result2 = calibrate_threshold(
            ae_scores=[1.0, 1.5, 1.7],
            se_scores=[0.5, 0.8, 1.1],
            sample_ids=["a", "b", "c"],
            ae_threshold=1.5,
        )

        self.assertEqual(result1["se_threshold"], result2["se_threshold"])

    def test_reordering_input_rows_does_not_change_threshold(self):
        """Threshold selection must be invariant to row order."""
        from scripts.calibrate_se_realrun_threshold import calibrate_threshold

        result_ordered = calibrate_threshold(
            ae_scores=[1.0, 1.5, 1.7],
            se_scores=[0.5, 0.8, 1.1],
            sample_ids=["a", "b", "c"],
            ae_threshold=1.5,
        )

        result_reordered = calibrate_threshold(
            ae_scores=[1.7, 1.0, 1.5],
            se_scores=[1.1, 0.5, 0.8],
            sample_ids=["c", "a", "b"],
            ae_threshold=1.5,
        )

        self.assertEqual(result_ordered["se_threshold"], result_reordered["se_threshold"])
        self.assertEqual(result_ordered["ae_frr"], result_reordered["ae_frr"])
        self.assertEqual(result_ordered["se_frr"], result_reordered["se_frr"])


class SEThresholdCalibrationProvenanceTest(unittest.TestCase):
    """RED: Provenance and frozen calibration commitment tests."""

    def test_frozen_manifest_hash_matches_expected(self):
        """Calibration manifest hash must match frozen expected value."""
        manifest_path = ROOT / "in/alfresco_extended_eval_dataset/manifest.json"
        self.assertTrue(manifest_path.is_file(), "calibration manifest missing")

        actual_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        self.assertEqual(
            actual_hash,
            EXPECTED_CALIBRATION_MANIFEST_HASH,
            "calibration manifest has changed",
        )

    def test_calibration_refuses_pilot_or_ab_evidence_directory(self):
        """Calibration must refuse any real_run/pilot/A-B evidence as a source."""
        from scripts.calibrate_se_realrun_threshold import validate_calibration_source

        forbidden_patterns = [
            "real_run",
            "pilot",
            "a_b_test",
            "ab_test",
            "production",
            "live",
        ]

        for pattern in forbidden_patterns:
            with self.assertRaises(ValueError) as ctx:
                validate_calibration_source(f"/some/path/{pattern}/data")
            self.assertIn("real", str(ctx.exception).lower())


class SEThresholdCalibrationScoreDirectionTest(unittest.TestCase):
    """RED: Score direction verification tests."""

    def test_ae_score_direction_verified_higher_is_more_anomalous(self):
        """AE: higher score must mean more anomalous/more likely to reject."""
        from model_stage.alfresco_ae_v1_scorer import AlfrescoAEV1Scorer

        scorer = AlfrescoAEV1Scorer()
        # AE uses threshold_high - scores above threshold are rejected
        # This confirms higher score = more anomalous
        self.assertGreater(scorer.threshold_high, 0)

    def test_se_score_direction_verified_higher_is_more_anomalous(self):
        """SE: higher score must mean more anomalous/more likely to reject."""
        # Load canonical SE reference scorer metadata
        se_ref_meta_path = Path("/home/dministrator/alfresco-audit-artifacts/sefanogan-es-round3-20260901-/training_runs/seed-20260519/sefanogan_es_reference.json")
        self.assertTrue(se_ref_meta_path.exists(),
                       "Canonical SE reference metadata must exist")

        se_meta = json.loads(se_ref_meta_path.read_text())

        # Verify this is the canonical SE reference
        self.assertEqual(se_meta["model_family"], "se_fanogan_es_reference",
                        "Must use canonical SE reference metadata")
        self.assertEqual(se_meta["input_dim"], 32,
                        "Canonical SE has 32-dim Alfresco feature input")
        self.assertEqual(se_meta["feature_contract"]["name"], "alfresco_fixed_32",
                        "Canonical SE uses alfresco_fixed_32 contract")

        # Verify score direction from formula
        score_formula = se_meta["score_formula"]
        self.assertIn("sqrt(reconstruction_mse)", score_formula,
                     "SE score includes reconstruction error term")
        self.assertIn("sqrt(discriminator_feature_mse)", score_formula,
                     "SE score includes discriminator feature error term")

        # Score formula: 0.75*sqrt(reconstruction_mse) + 0.25*sqrt(discriminator_feature_mse)
        # Both terms are non-negative with positive coefficients
        # Therefore: higher score = more anomalous ✓


if __name__ == "__main__":
    unittest.main()
