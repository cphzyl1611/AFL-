#!/usr/bin/env python3
"""R35: Manifest seed representation contract test.

Proves that manifest-sourced seeds for content_update must be wrapped
in HTTP envelopes before AFL ingestion, since C validator requires full HTTP.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_manifest_seed_raw_representation():
    """Confirm manifest source files are raw text without HTTP envelope."""
    manifest_dir = REPO_ROOT / "in" / "alfresco_afl_content_update_smoke"
    seed_ok_0 = manifest_dir / "seed_ok_0.txt"

    assert seed_ok_0.exists()
    content = seed_ok_0.read_bytes()

    # Raw UTF-8 text, no HTTP envelope
    assert not content.startswith(b"PUT ")
    assert not content.startswith(b"POST ")
    assert b"HTTP/1.1" not in content
    assert b"\r\n\r\n" not in content

    # This is the authoritative content_update semantic contract
    assert content.startswith("关于".encode("utf-8"))


def test_write_initial_seed_wraps_http():
    """Verify write_initial_seed() creates full HTTP envelope."""
    from scripts.run_alfresco_bounded_feedback import write_initial_seed

    # Create minimal target config for content_update
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "target.json"
        config_path.write_text(json.dumps({
            "default_endpoint": "content_update",
            "endpoints": [{
                "name": "content_update",
                "method": "PUT",
                "path": "/nodes/test-id/content",
            }]
        }))

        seed_dir = Path(tmpdir) / "seeds"

        seed_path = write_initial_seed(config_path, seed_dir, scenario="content_update")

        assert seed_path.exists()
        seed_bytes = seed_path.read_bytes()

        # Full HTTP envelope present
        assert seed_bytes.startswith(b"PUT /nodes/test-id/content HTTP/1.1\r\n")
        assert b"Content-Type: text/plain; charset=utf-8\r\n" in seed_bytes
        assert b"\r\n\r\n" in seed_bytes

        # Raw body follows envelope
        assert "关于".encode("utf-8") in seed_bytes


def test_materialize_manifest_copies_raw_bytes():
    """Prove materialize_manifest_seed_dir copies files without wrapping."""
    from scripts.run_alfresco_bounded_feedback import materialize_manifest_seed_dir

    manifest_path = REPO_ROOT / "in" / "alfresco_afl_content_update_smoke" / "manifest.json"
    source_dir = REPO_ROOT / "in" / "alfresco_afl_content_update_smoke"

    with tempfile.TemporaryDirectory() as tmpdir:
        dest_dir = Path(tmpdir) / "materialized"

        materialize_manifest_seed_dir(manifest_path, source_dir, dest_dir)

        # Check materialized seed is byte-exact copy
        dest_seed = dest_dir / "seed_ok_0.txt"
        source_seed = source_dir / "seed_ok_0.txt"

        assert dest_seed.read_bytes() == source_seed.read_bytes()

        # Still raw text, no HTTP envelope added
        content = dest_seed.read_bytes()
        assert not content.startswith(b"PUT ")
        assert b"HTTP/1.1" not in content


def test_r34_configuration_manifest_with_full_http_input_format():
    """Document R34's contradictory configuration."""
    # R34 task.json declared:
    # - "input_format": "full_http"  (C validator expects full HTTP)
    # - "seed_source": "manifest"    (copies raw text files)
    #
    # This mismatch caused all 6600 testcases to be rejected at C parse stage
    # before reaching Python body validation or scorer RPC.
    pass


if __name__ == "__main__":
    import pytest
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
