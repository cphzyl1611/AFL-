#!/usr/bin/env python3
"""Integration test for query parameter support in mutator and harness."""

import unittest
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nv_json_mutator import afl_custom_fuzz
from nv_url_query import parse_seed, serialize_seed


class TestQueryIntegration(unittest.TestCase):
    """Test query support across mutator and harness."""

    def setUp(self):
        """Set body_only_mode for mutator tests."""
        os.environ["NV_BODY_ONLY_MODE"] = "1"

    def tearDown(self):
        """Clean up environment."""
        os.environ.pop("NV_BODY_ONLY_MODE", None)

    def test_mutator_preserves_query_structure(self):
        """Mutator preserves query+body structure."""
        seed = serialize_seed({"q": "test"}, {"data": "value"})

        # Mutate multiple times
        for _ in range(5):
            mutated = afl_custom_fuzz(None, seed, b"", 4096)
            query, body = parse_seed(bytes(mutated))

            # Both should still be present
            self.assertIsNotNone(query)
            self.assertIsNotNone(body)

    def test_mutator_handles_body_only(self):
        """Mutator handles body-only seeds (backward compat)."""
        seed = b'{"key": "value"}'

        mutated = afl_custom_fuzz(None, seed, b"", 4096)

        # Should still parse
        self.assertIsNotNone(mutated)
        self.assertGreater(len(mutated), 0)

    def test_mutator_handles_query_only(self):
        """Mutator handles query-only seeds."""
        seed = serialize_seed({"q": "search", "limit": "10"}, None)

        mutated = afl_custom_fuzz(None, seed, b"", 4096)
        query, body = parse_seed(bytes(mutated))

        # Query should be present
        self.assertIsNotNone(query)

    def test_seed_roundtrip_through_mutator(self):
        """Seed structure survives mutation roundtrip."""
        original_query = {"key": "value"}
        original_body = {"data": [1, 2, 3]}

        seed = serialize_seed(original_query, original_body)
        mutated = afl_custom_fuzz(None, seed, b"", 4096)

        query, body = parse_seed(bytes(mutated))

        # Structure preserved (content may change)
        self.assertIsInstance(query, dict)
        self.assertIsInstance(body, dict)


if __name__ == '__main__':
    unittest.main()
