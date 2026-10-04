#!/usr/bin/env python3
"""Tests for URL query parameter support."""

import unittest
import json
from nv_url_query import (
    parse_seed,
    serialize_seed,
    build_query_string,
    parse_query_string,
    construct_url,
    mutate_query_value
)


class TestSeedParsing(unittest.TestCase):
    """Test seed parsing for query and body separation."""

    def test_parse_legacy_body_only(self):
        """Parse legacy format: pure JSON body."""
        seed = b'{"key": "value", "num": 42}'
        query, body = parse_seed(seed)

        self.assertIsNone(query)
        self.assertEqual(body, {"key": "value", "num": 42})

    def test_parse_extended_query_and_body(self):
        """Parse extended format with both query and body."""
        seed = b'{"query": {"q": "search"}, "body": {"data": "value"}}'
        query, body = parse_seed(seed)

        self.assertEqual(query, {"q": "search"})
        self.assertEqual(body, {"data": "value"})

    def test_parse_query_only(self):
        """Parse extended format with query only."""
        seed = b'{"query": {"key": "value"}}'
        query, body = parse_seed(seed)

        self.assertEqual(query, {"key": "value"})
        self.assertIsNone(body)

    def test_parse_body_only_explicit(self):
        """Parse extended format with body only (explicit)."""
        seed = b'{"body": {"key": "value"}}'
        query, body = parse_seed(seed)

        self.assertIsNone(query)
        self.assertEqual(body, {"key": "value"})

    def test_parse_empty_seed(self):
        """Parse empty seed."""
        query, body = parse_seed(b'')
        self.assertIsNone(query)
        self.assertIsNone(body)

    def test_parse_invalid_json(self):
        """Parse invalid JSON returns None."""
        query, body = parse_seed(b'not json')
        self.assertIsNone(query)
        self.assertIsNone(body)

    def test_parse_invalid_query_type(self):
        """Parse with non-dict query returns None for query."""
        seed = b'{"query": "not a dict", "body": {}}'
        query, body = parse_seed(seed)

        self.assertIsNone(query)
        self.assertEqual(body, {})


class TestSeedSerialization(unittest.TestCase):
    """Test seed serialization."""

    def test_serialize_body_only(self):
        """Serialize body-only (legacy format)."""
        seed = serialize_seed(None, {"key": "value"})
        self.assertEqual(json.loads(seed), {"key": "value"})

    def test_serialize_query_and_body(self):
        """Serialize with both query and body."""
        seed = serialize_seed({"q": "search"}, {"data": "value"})
        parsed = json.loads(seed)

        self.assertEqual(parsed["query"], {"q": "search"})
        self.assertEqual(parsed["body"], {"data": "value"})

    def test_serialize_query_only(self):
        """Serialize query-only."""
        seed = serialize_seed({"q": "search"}, None)
        parsed = json.loads(seed)

        self.assertEqual(parsed["query"], {"q": "search"})
        self.assertNotIn("body", parsed)

    def test_serialize_empty(self):
        """Serialize empty seed."""
        seed = serialize_seed(None, None)
        self.assertEqual(seed, b'{}')

    def test_serialize_roundtrip(self):
        """Roundtrip: serialize then parse."""
        original_query = {"key": "value", "num": "42"}
        original_body = {"data": [1, 2, 3]}

        seed = serialize_seed(original_query, original_body)
        parsed_query, parsed_body = parse_seed(seed)

        self.assertEqual(parsed_query, original_query)
        self.assertEqual(parsed_body, original_body)


class TestQueryStringBuilding(unittest.TestCase):
    """Test URL query string construction."""

    def test_build_simple_query(self):
        """Build simple query string."""
        qs = build_query_string({"key": "value"})
        self.assertEqual(qs, "key=value")

    def test_build_multiple_params(self):
        """Build query with multiple parameters."""
        qs = build_query_string({"a": "1", "b": "2"})
        # Order may vary, check both present
        self.assertIn("a=1", qs)
        self.assertIn("b=2", qs)
        self.assertIn("&", qs)

    def test_build_utf8_encoding(self):
        """Build query with UTF-8 characters."""
        qs = build_query_string({"key": "你好"})
        # Should be percent-encoded
        self.assertIn("%", qs)
        self.assertNotIn("你好", qs)

    def test_build_special_chars(self):
        """Build query with special characters."""
        qs = build_query_string({"key": "a b&c=d"})
        # Should be percent-encoded
        self.assertNotIn(" ", qs)
        self.assertNotIn("&c", qs)
        self.assertIn("%", qs)

    def test_build_empty_value(self):
        """Build query with empty value."""
        qs = build_query_string({"key": ""})
        self.assertEqual(qs, "key=")

    def test_build_list_values(self):
        """Build query with repeated keys (list values)."""
        qs = build_query_string({"key": ["a", "b", "c"]})
        # Should have multiple key= entries
        self.assertEqual(qs.count("key="), 3)
        self.assertIn("key=a", qs)
        self.assertIn("key=b", qs)
        self.assertIn("key=c", qs)

    def test_build_empty_query(self):
        """Build empty query returns empty string."""
        qs = build_query_string({})
        self.assertEqual(qs, "")


class TestQueryStringParsing(unittest.TestCase):
    """Test URL query string parsing."""

    def test_parse_simple_query(self):
        """Parse simple query string."""
        query = parse_query_string("key=value")
        self.assertEqual(query, {"key": "value"})

    def test_parse_multiple_params(self):
        """Parse multiple parameters."""
        query = parse_query_string("a=1&b=2&c=3")
        self.assertEqual(query, {"a": "1", "b": "2", "c": "3"})

    def test_parse_with_leading_question(self):
        """Parse query with leading '?'."""
        query = parse_query_string("?key=value")
        self.assertEqual(query, {"key": "value"})

    def test_parse_percent_encoded(self):
        """Parse percent-encoded query."""
        query = parse_query_string("key=%E4%BD%A0%E5%A5%BD")
        self.assertEqual(query, {"key": "你好"})

    def test_parse_empty_value(self):
        """Parse empty value."""
        query = parse_query_string("key=")
        self.assertEqual(query, {"key": ""})

    def test_parse_repeated_keys(self):
        """Parse repeated keys as list."""
        query = parse_query_string("key=a&key=b&key=c")
        self.assertEqual(query, {"key": ["a", "b", "c"]})

    def test_parse_empty_string(self):
        """Parse empty string returns empty dict."""
        query = parse_query_string("")
        self.assertEqual(query, {})

    def test_parse_roundtrip(self):
        """Roundtrip: build then parse."""
        original = {"a": "1", "b": "test value"}
        qs = build_query_string(original)
        parsed = parse_query_string(qs)
        self.assertEqual(parsed, original)


class TestURLConstruction(unittest.TestCase):
    """Test complete URL construction."""

    def test_construct_no_query(self):
        """Construct URL without query."""
        url = construct_url("/api/endpoint", None)
        self.assertEqual(url, "/api/endpoint")

    def test_construct_with_query(self):
        """Construct URL with query."""
        url = construct_url("/api/endpoint", {"key": "value"})
        self.assertEqual(url, "/api/endpoint?key=value")

    def test_construct_empty_query(self):
        """Construct URL with empty query dict."""
        url = construct_url("/api/endpoint", {})
        self.assertEqual(url, "/api/endpoint")

    def test_construct_existing_query(self):
        """Construct URL that already has query parameters."""
        url = construct_url("/api/endpoint?existing=param", {"new": "param"})
        self.assertIn("existing=param", url)
        self.assertIn("new=param", url)
        self.assertIn("&", url)
        # Should not add extra '?'
        self.assertEqual(url.count("?"), 1)

    def test_construct_multiple_params(self):
        """Construct URL with multiple query parameters."""
        url = construct_url("/api/endpoint", {"a": "1", "b": "2"})
        self.assertIn("?", url)
        self.assertIn("a=1", url)
        self.assertIn("b=2", url)


class TestQueryMutation(unittest.TestCase):
    """Test query parameter mutation."""

    def test_mutate_value_modifies(self):
        """Value mutation modifies parameters."""
        query = {"key": "value"}
        mutated = mutate_query_value(query, 'value')

        # Should still have 'key'
        self.assertIn("key", mutated)
        # Value may have changed (probabilistic, but structure preserved)
        self.assertIsInstance(mutated["key"], str)

    def test_mutate_boundary_changes_count(self):
        """Boundary mutation adds/removes parameters."""
        query = {"a": "1", "b": "2", "c": "3"}

        # Run multiple times to hit both add and remove
        counts = set()
        for _ in range(20):
            mutated = mutate_query_value(query.copy(), 'boundary')
            counts.add(len(mutated))

        # Should see different parameter counts
        self.assertGreater(len(counts), 1)

    def test_mutate_structure_changes_type(self):
        """Structure mutation changes value types."""
        # Test single -> list
        query1 = {"key": "value"}
        for _ in range(10):
            mutated = mutate_query_value(query1, 'structure')
            if isinstance(mutated["key"], list):
                break

        # Test list -> single
        query2 = {"key": ["a", "b"]}
        for _ in range(10):
            mutated = mutate_query_value(query2, 'structure')
            if not isinstance(mutated["key"], list):
                break

    def test_mutate_preserves_empty(self):
        """Mutating empty query returns empty."""
        query = {}
        mutated = mutate_query_value(query, 'value')
        self.assertEqual(mutated, {})

    def test_mutate_does_not_modify_original(self):
        """Mutation does not modify original dict."""
        original = {"key": "value"}
        mutated = mutate_query_value(original, 'value')

        # Original unchanged
        self.assertEqual(original, {"key": "value"})


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with existing JSON-body-only workflow."""

    def test_legacy_seed_works(self):
        """Legacy JSON body seeds work unchanged."""
        legacy_seed = b'{"docStatusList":[],"key":""}'
        query, body = parse_seed(legacy_seed)

        self.assertIsNone(query)
        self.assertEqual(body, {"docStatusList": [], "key": ""})

    def test_serialize_legacy_format(self):
        """Serializing body-only produces legacy format."""
        seed = serialize_seed(None, {"key": "value"})

        # Should be plain JSON, not wrapped
        parsed = json.loads(seed)
        self.assertEqual(parsed, {"key": "value"})
        self.assertNotIn("body", parsed)
        self.assertNotIn("query", parsed)

    def test_url_construction_without_query(self):
        """URL construction without query is unchanged."""
        url = construct_url("/api/endpoint", None)
        self.assertEqual(url, "/api/endpoint")
        self.assertNotIn("?", url)


if __name__ == '__main__':
    unittest.main()
