#!/usr/bin/env python3
"""Tests for authoritative formal security score computation."""

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from compute_formal_security_score import (
    FormalScoreConfig,
    compute_coverage_ratio,
    compute_recovery_rate,
    compute_formal_score,
    extract_metrics_from_stats,
    compute_from_stats
)


class TestFormalScoreConfig(unittest.TestCase):
    """Test weight configuration and validation."""

    def test_valid_weights_equal(self):
        """Valid weights with equal distribution."""
        config = FormalScoreConfig(0.333, 0.333, 0.334)
        self.assertAlmostEqual(config.beta1, 0.333)
        self.assertAlmostEqual(config.beta2, 0.333)
        self.assertAlmostEqual(config.beta3, 0.334)

    def test_valid_weights_e_government(self):
        """Valid weights emphasizing recovery for e-government."""
        config = FormalScoreConfig(0.25, 0.25, 0.50)
        self.assertEqual(config.beta3, 0.50)

    def test_weights_sum_validation(self):
        """Reject weights that don't sum to 1."""
        with self.assertRaises(ValueError) as ctx:
            FormalScoreConfig(0.3, 0.3, 0.3)
        self.assertIn("sum to 1.0", str(ctx.exception))

    def test_weights_range_validation(self):
        """Reject weights outside [0, 1]."""
        with self.assertRaises(ValueError) as ctx:
            FormalScoreConfig(-0.1, 0.6, 0.5)
        self.assertIn("[0, 1]", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            FormalScoreConfig(0.3, 1.2, -0.5)
        self.assertIn("[0, 1]", str(ctx.exception))

    def test_from_dict(self):
        """Load configuration from dictionary."""
        config = FormalScoreConfig.from_dict({
            'beta1': 0.4,
            'beta2': 0.3,
            'beta3': 0.3
        })
        self.assertEqual(config.beta1, 0.4)

    def test_to_dict(self):
        """Export configuration to dictionary."""
        config = FormalScoreConfig(0.25, 0.25, 0.50)
        d = config.to_dict()
        self.assertEqual(d['beta1'], 0.25)
        self.assertEqual(d['beta3'], 0.50)
        self.assertAlmostEqual(d['sum'], 1.0)


class TestMetricNormalization(unittest.TestCase):
    """Test normalization of raw metrics to [0, 1] scale."""

    def test_compute_coverage_ratio_zero_capacity(self):
        """Coverage is 0 when capacity is 0."""
        cov = compute_coverage_ratio(0, 0)
        self.assertEqual(cov, 0.0)

    def test_compute_coverage_ratio_partial(self):
        """Coverage as fraction of capacity."""
        cov = compute_coverage_ratio(100, 65536)
        self.assertAlmostEqual(cov, 100.0 / 65536.0)

    def test_compute_coverage_ratio_caps_at_one(self):
        """Coverage capped at 1.0."""
        cov = compute_coverage_ratio(70000, 65536)
        self.assertEqual(cov, 1.0)

    def test_compute_recovery_rate_zero_total(self):
        """Recovery is 0 when no recovery attempts."""
        r_rec = compute_recovery_rate(0, 0)
        self.assertEqual(r_rec, 0.0)

    def test_compute_recovery_rate_fraction(self):
        """Recovery rate as successful/total."""
        r_rec = compute_recovery_rate(8, 10)
        self.assertAlmostEqual(r_rec, 0.8)

    def test_compute_recovery_rate_caps_at_one(self):
        """Recovery rate capped at 1.0."""
        r_rec = compute_recovery_rate(15, 10)
        self.assertEqual(r_rec, 1.0)


class TestFormalScoreComputation(unittest.TestCase):
    """Test authoritative formula computation."""

    def test_formula_structure(self):
        """Verify formula: P_sec = β1*Cov + β2*(1/(1+Err)) + β3*R_rec."""
        config = FormalScoreConfig(0.333, 0.333, 0.334)

        # Perfect scenario: max coverage, no errors, max recovery
        score = compute_formal_score(config, cov=1.0, err=0.0, r_rec=1.0)
        # 0.333*1 + 0.333*1 + 0.334*1 = 1.0
        self.assertAlmostEqual(score, 1.0, places=3)

    def test_formula_with_errors(self):
        """Error term: 1/(1+Err) decreases with higher error rate."""
        config = FormalScoreConfig(0.0, 1.0, 0.0)  # Only error term

        score_no_err = compute_formal_score(config, 0, 0.0, 0)
        score_low_err = compute_formal_score(config, 0, 0.1, 0)
        score_high_err = compute_formal_score(config, 0, 1.0, 0)

        # Error term should decrease: 1/(1+0) > 1/(1+0.1) > 1/(1+1.0)
        self.assertEqual(score_no_err, 1.0)
        self.assertAlmostEqual(score_low_err, 1.0/1.1, places=5)
        self.assertAlmostEqual(score_high_err, 0.5, places=5)
        self.assertGreater(score_no_err, score_low_err)
        self.assertGreater(score_low_err, score_high_err)

    def test_e_government_emphasis(self):
        """E-government weights emphasize recovery (β3 increased)."""
        config_balanced = FormalScoreConfig(0.333, 0.333, 0.334)
        config_egov = FormalScoreConfig(0.25, 0.25, 0.50)

        # Scenario with strong recovery but weak coverage
        metrics = {'cov': 0.2, 'err': 0.0, 'r_rec': 0.9}

        score_balanced = compute_formal_score(config_balanced, **metrics)
        score_egov = compute_formal_score(config_egov, **metrics)

        # E-gov config should score higher due to β3=0.50
        self.assertGreater(score_egov, score_balanced)


class TestStatsExtraction(unittest.TestCase):
    """Test extraction from fuzzer_stats file."""

    def setUp(self):
        """Create temporary stats file."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.stats_path = Path(self.temp_dir.name) / "fuzzer_stats"

    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def write_stats(self, content: str):
        """Write stats file content."""
        with open(self.stats_path, 'w') as f:
            f.write(content)

    def test_extract_all_required_metrics(self):
        """Extract all required metrics successfully."""
        self.write_stats("""
nv_err_rate       : 0.05
nv_rec_total      : 20
nv_rec_success    : 15
security_state_new_total : 10
security_state_capacity : 65536
other_field       : ignored
""")

        metrics = extract_metrics_from_stats(self.stats_path)
        self.assertIsNotNone(metrics)
        self.assertAlmostEqual(metrics['nv_err_rate'], 0.05)
        self.assertEqual(metrics['nv_rec_total'], 20)
        self.assertEqual(metrics['nv_rec_success'], 15)
        self.assertEqual(metrics['security_state_new_total'], 10)
        self.assertEqual(metrics['security_state_capacity'], 65536)

    def test_extract_missing_metrics(self):
        """Return None when required metrics missing."""
        self.write_stats("""
nv_err_rate       : 0.05
nv_rec_total      : 20
""")

        metrics = extract_metrics_from_stats(self.stats_path)
        self.assertIsNone(metrics)

    def test_extract_nonexistent_file(self):
        """Return None for nonexistent file."""
        metrics = extract_metrics_from_stats(Path("/nonexistent/stats"))
        self.assertIsNone(metrics)


class TestEndToEndComputation(unittest.TestCase):
    """Test complete score computation from stats file."""

    def setUp(self):
        """Create temporary stats file."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.stats_path = Path(self.temp_dir.name) / "fuzzer_stats"

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def write_stats(self, content: str):
        """Write stats file."""
        with open(self.stats_path, 'w') as f:
            f.write(content)

    def test_compute_from_valid_stats(self):
        """Compute score from valid stats file."""
        self.write_stats("""
nv_err_rate       : 0.1
nv_rec_total      : 10
nv_rec_success    : 8
security_state_new_total : 2
security_state_capacity : 65536
""")

        config = FormalScoreConfig(0.333, 0.333, 0.334)
        score, prov = compute_from_stats(self.stats_path, config)

        self.assertIsNotNone(score)
        self.assertEqual(prov['status'], 'computed')
        self.assertIn('P_sec', prov)
        self.assertIn('weights', prov)
        self.assertIn('raw_metrics', prov)
        self.assertIn('normalized_metrics', prov)
        self.assertIn('cov_source', prov)
        self.assertIn('recovery_source', prov)
        self.assertIn('error_source', prov)

    def test_compute_from_missing_stats(self):
        """Return unavailable when stats missing."""
        config = FormalScoreConfig(0.333, 0.333, 0.334)
        score, prov = compute_from_stats(Path("/nonexistent"), config)

        self.assertIsNone(score)
        self.assertEqual(prov['status'], 'unavailable')
        self.assertIn('reason', prov)

    def test_provenance_includes_formula(self):
        """Provenance documents the authoritative formula."""
        self.write_stats("""
nv_err_rate       : 0.0
nv_rec_total      : 5
nv_rec_success    : 5
security_state_new_total : 1
security_state_capacity : 65536
""")

        config = FormalScoreConfig(0.333, 0.333, 0.334)
        score, prov = compute_from_stats(self.stats_path, config)

        self.assertIn('formula', prov)
        self.assertIn('β1 * Cov', prov['formula'])
        self.assertIn('1/(1+Err)', prov['formula'])
        self.assertIn('R_rec', prov['formula'])


class TestRegressionCompatibility(unittest.TestCase):
    """Test that implementation matches expected behavior."""

    def test_no_invented_weights(self):
        """Configuration requires explicit weights, no defaults."""
        # This should require explicit parameters
        with self.assertRaises(TypeError):
            FormalScoreConfig()  # No default weights

    def test_score_range(self):
        """Score should be in reasonable range [0, ~1]."""
        config = FormalScoreConfig(0.333, 0.333, 0.334)

        # Worst case: no coverage, high error, no recovery
        score_min = compute_formal_score(config, 0.0, 10.0, 0.0)
        # Best case: max coverage, no error, max recovery
        score_max = compute_formal_score(config, 1.0, 0.0, 1.0)

        self.assertGreaterEqual(score_min, 0.0)
        self.assertLessEqual(score_max, 1.1)  # Small tolerance
        self.assertGreater(score_max, score_min)


if __name__ == '__main__':
    unittest.main()
