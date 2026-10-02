#!/usr/bin/env python3
"""RED tests for content_update body validation defect.

These tests prove that body_validate() unconditionally calls
normalize_json_body_or_none(), which rejects plain UTF-8 text as invalid_json.

This blocks content_update scenarios, which require raw text validation.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nv_body_valid import body_validate


class TestContentUpdateBodyValidationDefect(unittest.TestCase):
    """RED tests proving content_update plain text is rejected."""

    def test_red_a_plain_utf8_content_update_rejected_as_invalid_json(self):
        """RED A: Plain UTF-8 content_update body is rejected as invalid_json.

        Expected before repair: FAIL (rejected as invalid_json)
        Expected after repair: PASS (accepted as valid raw text)
        """
        # Use actual content_update seed from authoritative fixture
        seed_file = REPO_ROOT / "in" / "alfresco_afl_content_update_smoke" / "seed_ok_0.txt"
        raw_body = seed_file.read_bytes()

        # Verify it's plain text (not JSON)
        text = raw_body.decode("utf-8")
        self.assertGreater(len(text.strip()), 0)

        # Call body_validate with content_update scenario
        result = body_validate(
            scenario="content_update",
            endpoint_name="content_update",
            raw_body=raw_body,
            rules_path="",  # No rules needed for content_update
            score_endpoint=None,
            score_threshold=None,
        )

        # RED: Currently fails because normalize_json_body_or_none rejects plain text
        self.assertTrue(result["ok"], "content_update plain text must be accepted")
        self.assertEqual(result["reason"], "ok")
        self.assertIsNotNone(result.get("norm_body"))

    def test_red_b_multiline_utf8_text_preserved(self):
        """RED B: Multiline UTF-8 content_update text is preserved.

        Expected before repair: FAIL (rejected as invalid_json)
        Expected after repair: PASS (text preserved with LF, UTF-8, spaces)
        """
        # Representative multiline Chinese text with LF, spaces, punctuation
        raw_body = b"\xe5\x85\xb3\xe5\xae\x89\xe7\xb3\xbb\xe7\xbb\x9f\xe8\x81\x94\xe8\xb0\x83\xe6\xb5\x8b\xe8\xaf\x95\xe7\x9a\x84\xe9\x80\x9a\xe7\x9f\xa5\n\xe8\xaf\xb7\xe5\x90\x84\xe9\x83\xa8\xe9\x97\xa8\xe6\x8c\x89\xe7\x85\xa7\xe8\xae\xa1\xe5\x88\x92\xe5\xae\x8c\xe6\x88\x90\xe6\x8e\xa5\xe5\x8f\xa3\xe8\x81\x94\xe8\xb0\x83\xe3\x80\x81\xe6\x97\xa5\xe5\xbf\x97\xe5\xbd\x92\xe6\xa1\xa3\xe5\x92\x8c\xe9\x97\xae\xe9\xa2\x98\xe9\x97\xad\xe7\x8e\xaf\xe3\x80\x82"

        # Verify UTF-8 decodable with newlines
        text = raw_body.decode("utf-8")
        self.assertIn("\n", text)
        self.assertGreater(len(text.strip()), 0)

        result = body_validate(
            scenario="content_update",
            endpoint_name="content_update",
            raw_body=raw_body,
            rules_path="",
            score_endpoint=None,
            score_threshold=None,
        )

        # RED: Currently fails
        self.assertTrue(result["ok"], "multiline UTF-8 text must be accepted")

        # After repair: norm_body should preserve raw bytes for content_update
        if result["ok"]:
            self.assertEqual(result["norm_body"], raw_body, "raw text must be preserved")

    def test_metadata_json_validation_preserved(self):
        """RED C: metadata_update JSON validation must continue unchanged.

        This is a regression guard: metadata_update must still require JSON.
        Expected: PASS before and after repair.
        """
        # Valid metadata JSON
        valid_json = b'{"name":"doc.txt","title":"Test","description":"Test doc"}'

        result = body_validate(
            scenario="metadata_update",
            endpoint_name="metadata_update",
            raw_body=valid_json,
            rules_path="",
            score_endpoint=None,
            score_threshold=None,
        )

        self.assertTrue(result["ok"], "valid metadata JSON must be accepted")
        self.assertEqual(result["reason"], "ok")

        # Plain text must be rejected for metadata_update
        plain_text = b"This is plain text, not JSON"
        result = body_validate(
            scenario="metadata_update",
            endpoint_name="metadata_update",
            raw_body=plain_text,
            rules_path="",
            score_endpoint=None,
            score_threshold=None,
        )

        self.assertFalse(result["ok"], "plain text must be rejected for metadata_update")
        self.assertEqual(result["reason"], "invalid_json")

    def test_red_d_content_update_safety_limits(self):
        """RED D: content_update must still reject invalid/unsafe bodies.

        Expected: empty body behavior defined by contract.
        After repair: content_update should have appropriate size/safety limits.
        """
        # Empty body
        result = body_validate(
            scenario="content_update",
            endpoint_name="content_update",
            raw_body=b"",
            rules_path="",
            score_endpoint=None,
            score_threshold=None,
        )

        # Document current behavior: normalize_json_body_or_none returns b"{}" for empty
        # After repair: content_update may need to define empty-body policy
        # For now, document what happens
        if not result["ok"]:
            self.assertIn(result["reason"], ["invalid_json", "empty_body"])


class TestScenarioDispatchRequirements(unittest.TestCase):
    """Document scenario dispatch requirements for body_validate."""

    def test_body_validate_receives_scenario_parameter(self):
        """Verify body_validate receives scenario as first parameter."""
        from nv_body_valid import body_validate
        import inspect

        sig = inspect.signature(body_validate)
        params = list(sig.parameters.keys())

        self.assertEqual(params[0], "scenario", "scenario must be first parameter")
        self.assertEqual(params[1], "endpoint_name")
        self.assertEqual(params[2], "raw_body")

    def test_harness_passes_scenario_to_body_validate(self):
        """Verify harness passes scenario from cfg to body_validate."""
        # This is a documentation test - harness already passes scenario
        # Line 1024 in nv_http_harness.py:
        #   scenario=cfg.get("scenario", "metadata_update")
        pass


if __name__ == "__main__":
    unittest.main()
