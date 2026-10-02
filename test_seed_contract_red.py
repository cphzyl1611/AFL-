#!/usr/bin/env python3
"""RED tests: Seed contract must be scenario-aware."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_alfresco_bounded_feedback import write_initial_seed, REPO_ROOT as SCRIPT_REPO_ROOT


def test_content_update_seed_is_plain_text():
    """content_update seed must be plain text/file-content bytes, not JSON."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_dir = Path(tmpdir) / "seed_dir"
        config_path = SCRIPT_REPO_ROOT / "targets" / "alfresco_content_update.json"

        seed_path = write_initial_seed(config_path, seed_dir, scenario="content_update")

        content = seed_path.read_bytes()

        # Must contain HTTP envelope + plain text body
        assert b"HTTP/1.1" in content, "Must be full HTTP request"
        assert b"Content-Type: text/plain" in content, "Must be text/plain"

        # Extract body after \r\n\r\n
        parts = content.split(b"\r\n\r\n", 1)
        assert len(parts) == 2, "Must have header and body"
        body = parts[1]

        # Body must NOT be valid JSON
        try:
            json.loads(body)
            raise AssertionError("content_update seed body must NOT be JSON metadata")
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass  # Expected: plain text, not JSON

        # Body must be non-empty plain text
        assert len(body) > 0, "Body must be non-empty"
        assert body != b'{"properties":', "Must not be JSON metadata structure"


def test_metadata_update_seed_is_json():
    """metadata_update seed must be JSON metadata, not plain text."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_dir = Path(tmpdir) / "seed_dir"
        config_path = SCRIPT_REPO_ROOT / "targets" / "alfresco_metadata_update.json"

        seed_path = write_initial_seed(config_path, seed_dir, scenario="metadata_update")

        content = seed_path.read_bytes()

        # Must contain HTTP envelope + JSON body
        assert b"HTTP/1.1" in content, "Must be full HTTP request"
        assert b"Content-Type: application/json" in content, "Must be application/json"

        # Extract body after \r\n\r\n
        parts = content.split(b"\r\n\r\n", 1)
        assert len(parts) == 2, "Must have header and body"
        body = parts[1]

        # Body must be valid JSON
        parsed = json.loads(body)
        assert isinstance(parsed, dict), "metadata_update seed must be JSON object"


def test_json_metadata_fixture_cannot_become_content_update_seed():
    """JSON metadata fixtures must never silently become content_update seeds."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_dir = Path(tmpdir) / "seed_dir"
        config_path = SCRIPT_REPO_ROOT / "targets" / "alfresco_content_update.json"

        seed_path = write_initial_seed(config_path, seed_dir, scenario="content_update")
        content = seed_path.read_bytes()

        # Extract body
        parts = content.split(b"\r\n\r\n", 1)
        body = parts[1]

        # Negative control: the wrong preserved JSON seed from Phase 2
        wrong_json_seed = b'{"properties":{"cm:title":"seed title","cm:description":"seed description"}}'

        assert body != wrong_json_seed, "content_update must never use JSON metadata fixture"


def test_content_update_fixture_is_authoritative():
    """content_update seed must come from an authoritative project fixture."""
    fixture_path = SCRIPT_REPO_ROOT / "in" / "alfresco_afl_content_update_smoke" / "seed_ok_0.txt"

    assert fixture_path.is_file(), f"Authoritative fixture must exist: {fixture_path}"

    content = fixture_path.read_bytes()
    assert len(content) > 0, "Fixture must be non-empty"

    # Must be plain text, not JSON
    try:
        json.loads(content)
        raise AssertionError("content_update fixture must be plain text, not JSON")
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass  # Expected


def test_metadata_update_keeps_json_seed_contract():
    """metadata_update must keep its JSON metadata seed contract."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_dir = Path(tmpdir) / "seed_dir"
        config_path = SCRIPT_REPO_ROOT / "targets" / "alfresco_metadata_update.json"

        seed_path = write_initial_seed(config_path, seed_dir, scenario="metadata_update")
        content = seed_path.read_bytes()

        parts = content.split(b"\r\n\r\n", 1)
        body = parts[1]

        parsed = json.loads(body)
        assert isinstance(parsed, dict), "metadata_update seed must be JSON object"


def test_unknown_scenario_fails_closed():
    """Unknown scenario must fail rather than selecting wrong seed type."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_dir = Path(tmpdir) / "seed_dir"
        config_path = SCRIPT_REPO_ROOT / "targets" / "alfresco_metadata_update.json"

        try:
            write_initial_seed(config_path, seed_dir, scenario="unknown_scenario")
            raise AssertionError("Unknown scenario must raise ValueError")
        except ValueError as e:
            assert "UNKNOWN_SCENARIO" in str(e)


if __name__ == "__main__":
    print("Running RED seed contract tests...")

    test_content_update_seed_is_plain_text()
    print("✓ content_update seed is plain text")

    test_metadata_update_seed_is_json()
    print("✓ metadata_update seed is JSON")

    test_json_metadata_fixture_cannot_become_content_update_seed()
    print("✓ JSON metadata fixture cannot become content_update seed")

    test_content_update_fixture_is_authoritative()
    print("✓ content_update fixture is authoritative")

    test_metadata_update_keeps_json_seed_contract()
    print("✓ metadata_update keeps JSON seed contract")

    test_unknown_scenario_fails_closed()
    print("✓ unknown scenario fails closed")

    print("\nAll RED seed contract tests PASS (seed contract already repaired).")
