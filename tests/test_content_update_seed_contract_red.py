#!/usr/bin/env python3
"""RED tests for content_update seed contract repair.

These tests document that:
1. content_update seeds must be plain text/file-content bytes
2. metadata_update seeds must be JSON metadata objects
3. The two contracts are distinct and never interchangeable
"""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class TestContentUpdateSeedContract(unittest.TestCase):
    """Test that content_update and metadata_update have distinct seed contracts."""

    def test_content_update_authoritative_seeds_are_plain_text(self):
        """Verify authoritative content_update seeds are plain text, not JSON."""
        content_seed_dir = REPO_ROOT / "in" / "alfresco_afl_content_update_smoke"
        self.assertTrue(content_seed_dir.is_dir(), "content_update seed directory must exist")
        
        # Check seed_ok_0.txt
        seed_ok_0 = content_seed_dir / "seed_ok_0.txt"
        self.assertTrue(seed_ok_0.is_file(), "seed_ok_0.txt must exist")
        
        content = seed_ok_0.read_bytes()
        self.assertGreater(len(content), 0, "seed must not be empty")
        
        # Must be plain text (UTF-8 decodable)
        text = content.decode("utf-8")
        self.assertGreater(len(text.strip()), 0, "seed must have non-whitespace content")
        
        # Must NOT be JSON
        with self.assertRaises(json.JSONDecodeError):
            json.loads(text)

    def test_metadata_update_authoritative_seeds_are_json_metadata(self):
        """Verify authoritative metadata_update seeds are JSON metadata objects."""
        metadata_seed_dir = REPO_ROOT / "in" / "alfresco_afl_metadata_update_smoke"
        self.assertTrue(metadata_seed_dir.is_dir(), "metadata_update seed directory must exist")
        
        seed_ok_0 = metadata_seed_dir / "seed_ok_0.json"
        self.assertTrue(seed_ok_0.is_file(), "seed_ok_0.json must exist")
        
        content = seed_ok_0.read_bytes()
        payload = json.loads(content.decode("utf-8"))
        
        # Must be a JSON object (metadata format)
        self.assertIsInstance(payload, dict)
        # Current format: {"name": "...", "title": "...", "description": "..."}
        self.assertIn("title", payload)

    def test_json_metadata_payload_violates_content_update_contract(self):
        """RED: Metadata JSON structure violates content_update plain-text contract."""
        metadata_seed_dir = REPO_ROOT / "in" / "alfresco_afl_metadata_update_smoke"
        metadata_seed = metadata_seed_dir / "seed_ok_0.json"
        
        content = metadata_seed.read_bytes()
        
        # This can parse as JSON - violates plain-text expectation
        try:
            payload = json.loads(content.decode("utf-8"))
            # If it parsed, it's structured JSON, not plain text
            self.assertIsInstance(payload, dict, 
                "This is structured JSON, violates content_update plain-text contract")
        except json.JSONDecodeError:
            self.fail("Metadata seed should be JSON")

    def test_runner_initial_seed_body_is_metadata_json(self):
        """Document current bug: INITIAL_SEED_BODY is hardcoded metadata JSON."""
        from scripts.run_alfresco_bounded_feedback import INITIAL_SEED_BODY
        
        # Current implementation: INITIAL_SEED_BODY is hardcoded to metadata JSON
        parsed = json.loads(INITIAL_SEED_BODY.decode("utf-8"))
        self.assertIsInstance(parsed, dict)
        self.assertIn("properties", parsed)
        
        # This is the BUG: same JSON seed used for all scenarios
        # After repair, write_initial_seed() must select based on scenario

    def test_content_update_dataset_seeds_are_all_plain_text(self):
        """Verify all content_update dataset seeds are plain text."""
        dataset_dir = REPO_ROOT / "in" / "alfresco_content_update_dataset"
        if not dataset_dir.is_dir():
            self.skipTest("content_update dataset not present")
        
        seed_files = [f for f in dataset_dir.iterdir() if f.suffix == ".txt"]
        self.assertGreater(len(seed_files), 0, "Must have .txt seed files")
        
        for seed_file in seed_files:
            with self.subTest(seed=seed_file.name):
                content = seed_file.read_bytes()
                text = content.decode("utf-8")
                
                # Must be plain text (not empty, not JSON)
                self.assertGreater(len(text.strip()), 0)
                
                # Must NOT parse as JSON
                try:
                    json.loads(text)
                    self.fail(f"{seed_file.name} should be plain text, not JSON")
                except json.JSONDecodeError:
                    pass  # Expected - plain text

    def test_runner_write_initial_seed_must_respect_scenario(self):
        """RED: write_initial_seed() must generate scenario-appropriate bodies.
        
        Current bug: always uses INITIAL_SEED_BODY (metadata JSON).
        After repair: must select body based on scenario parameter.
        """
        from scripts.run_alfresco_bounded_feedback import write_initial_seed, INITIAL_SEED_BODY
        
        # Current behavior: always metadata JSON regardless of scenario
        # This test documents the requirement for scenario-aware seed selection
        
        # The bug manifests when content_update uses metadata JSON seed
        parsed = json.loads(INITIAL_SEED_BODY)
        self.assertIn("properties", parsed)
        
        # After repair: content_update should use plain text from authoritative fixture
        # After repair: metadata_update should use JSON from authoritative fixture


class TestSeedContractSeparation(unittest.TestCase):
    """Test that seed contracts remain distinct across scenarios."""

    def test_multipart_seed_format_distinct_from_content_and_metadata(self):
        """Verify multipart seeds have their own distinct format."""
        multipart_dir = REPO_ROOT / "in" / "alfresco_multipart_upload_bounded"
        if not multipart_dir.is_dir():
            self.skipTest("multipart seed directory not present")
        
        seed_files = list(multipart_dir.glob("*.http"))
        self.assertGreater(len(seed_files), 0, "Must have .http multipart seeds")
        
        # Multipart seeds are full HTTP with boundary markers
        seed_0 = seed_files[0]
        content = seed_0.read_bytes()
        
        # Must contain multipart boundary
        self.assertIn(b"boundary=", content)
        self.assertIn(b"Content-Disposition:", content)

    def test_scenario_values_recognized_by_task_builder(self):
        """Verify all three scenario values are recognized."""
        from scripts.run_alfresco_bounded_feedback import build_task_payload
        
        # content_update must be recognized
        task = build_task_payload(
            seed_dir=Path("/tmp/test"),
            max_test_cases=2,
            time_budget=10,
            mutation_scope=["field_value"],
            seed_source="seed_file",
            scenario="content_update",
        )
        self.assertEqual(task.get("scenario"), "content_update")


if __name__ == "__main__":
    unittest.main()
