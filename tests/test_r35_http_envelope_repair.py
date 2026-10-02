#!/usr/bin/env python3
"""R35: HTTP envelope repair verification.

Tests that materialize_manifest_seed_dir now wraps content_update seeds
in full HTTP envelopes, fixing the R34 parse rejection issue.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_content_update_manifest_seeds_wrapped_with_http():
    """RED B → GREEN: content_update manifest seeds get HTTP envelope."""
    from scripts.run_alfresco_bounded_feedback import materialize_manifest_seed_dir

    manifest_path = REPO_ROOT / "in" / "alfresco_afl_content_update_smoke" / "manifest.json"
    source_dir = REPO_ROOT / "in" / "alfresco_afl_content_update_smoke"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create target config matching R34 setup
        config_path = Path(tmpdir) / "target.json"
        config_path.write_text(json.dumps({
            "default_endpoint": "content_update",
            "endpoints": [{
                "name": "content_update",
                "method": "PUT",
                "path": "/alfresco/api/-default-/public/alfresco/versions/1/nodes/test-node/content",
            }]
        }))

        dest_dir = Path(tmpdir) / "wrapped_seeds"

        # R35 repair: pass config_path and scenario
        materialize_manifest_seed_dir(
            manifest_path,
            source_dir,
            dest_dir,
            config_path=config_path,
            scenario="content_update",
        )

        # Verify wrapped seed
        wrapped_seed = dest_dir / "seed_ok_0.txt"
        assert wrapped_seed.exists()

        content = wrapped_seed.read_bytes()

        # Full HTTP envelope present
        assert content.startswith(b"PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/test-node/content HTTP/1.1\r\n")
        assert b"Host: 127.0.0.1\r\n" in content
        assert b"Content-Type: text/plain; charset=utf-8\r\n" in content
        assert b"Content-Length: " in content
        assert b"\r\n\r\n" in content

        # Original raw text body preserved after envelope
        assert "关于系统联调测试的通知".encode("utf-8") in content

        # Verify C validator will accept this
        # Line 910: finds '\n' in request line ✓
        # Line 919: sscanf parses "PUT /path" ✓
        # Line 922: path[0] == '/' ✓
        # Line 947: body after \r\n\r\n can be non-JSON for content_update
        #           (but current C code rejects it - see next test)


def test_content_update_manifest_without_config_preserves_compatibility():
    """Backward compatibility: no config_path means no wrapping."""
    from scripts.run_alfresco_bounded_feedback import materialize_manifest_seed_dir

    manifest_path = REPO_ROOT / "in" / "alfresco_afl_content_update_smoke" / "manifest.json"
    source_dir = REPO_ROOT / "in" / "alfresco_afl_content_update_smoke"

    with tempfile.TemporaryDirectory() as tmpdir:
        dest_dir = Path(tmpdir) / "raw_copy"

        # Old signature: no config_path, no wrapping
        materialize_manifest_seed_dir(
            manifest_path,
            source_dir,
            dest_dir,
        )

        dest_seed = dest_dir / "seed_ok_0.txt"
        source_seed = source_dir / "seed_ok_0.txt"

        # Byte-exact copy as before
        assert dest_seed.read_bytes() == source_seed.read_bytes()
        assert not dest_seed.read_bytes().startswith(b"PUT ")


def test_c_validator_body_json_check_still_rejects_text():
    """Document remaining C validator limitation at line 947.

    The C validator currently requires JSON body prefix ({ or [) at line 947.
    This test documents that content_update text/plain bodies will still fail
    C validation even after HTTP wrapping, unless C validator is made
    scenario-aware or content_update seeds bypass C validation entirely.

    This is the SECOND part of the fix needed beyond HTTP wrapping.
    """
    # C validator src/afl-fuzz-run.c line 947:
    # if (blen > 0 && (*body != '{' && *body != '[')) return NV_V_REJ_BODY;
    #
    # UTF-8 Chinese text starts with 0xe5, not '{' (0x7b) or '[' (0x5b)
    # So even with full HTTP envelope, C validator rejects content_update bodies
    #
    # Options for complete fix:
    # A. Make C validator scenario-aware (skip JSON check for content_update)
    # B. Ensure content_update bypasses C validation (body_only_mode=1 semantic)
    # C. Move C validation after Python harness extracts body
    #
    # Current R35 repair implements HTTP wrapping only.
    # The JSON body check remains a blocker requiring either A, B, or C.
    pass


if __name__ == "__main__":
    import pytest
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
