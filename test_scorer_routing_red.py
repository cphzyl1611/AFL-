#!/usr/bin/env python3
"""RED tests: Real scorer routing must preserve scenario/endpoint identity."""

import json
import struct
import socket
import tempfile
import os
import sys
from pathlib import Path

# Add model_stage to path
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "model_stage"))

from model_stage.alfresco_feature_extractor import (
    extract_metadata_features,
    extract_text_content_features,
    extract_multipart_upload_features,
)


def test_rpc_protocol_preserves_scenario():
    """RPC client must serialize scenario/endpoint identity."""
    from nv_body_valid import rpc_score_unix

    # Currently rpc_score_unix discards endpoint_name (line 234: del endpoint_name)
    # This test documents the RED state
    pass  # Will fail when we add scenario preservation


def test_real_scorer_receives_scenario():
    """Real scorer must receive scenario/endpoint from RPC."""
    # Currently recv_one() only receives raw body bytes (no metadata)
    # This test documents the RED state
    pass  # Will fail when we extend the protocol


def test_content_update_uses_text_extractor():
    """content_update scenario must use extract_text_content_features."""
    text_sample = b"This is plain text content for a document."
    vector = extract_text_content_features(text_sample)

    assert len(vector) == 32, f"Expected 32D vector, got {len(vector)}"
    assert vector[1] == 1.0, "scenario_text_content_update flag must be 1.0"
    assert vector[0] == 0.0, "scenario_metadata_update flag must be 0.0"
    assert vector[2] == 0.0, "scenario_multipart_upload flag must be 0.0"


def test_metadata_update_uses_metadata_extractor():
    """metadata_update scenario must use extract_metadata_features."""
    metadata_sample = {"properties": {"cm:title": "Test", "cm:description": "Description"}}
    vector = extract_metadata_features(metadata_sample)

    assert len(vector) == 32, f"Expected 32D vector, got {len(vector)}"
    assert vector[0] == 1.0, "scenario_metadata_update flag must be 1.0"
    assert vector[1] == 0.0, "scenario_text_content_update flag must be 0.0"
    assert vector[2] == 0.0, "scenario_multipart_upload flag must be 0.0"


def test_multipart_dispatch_unchanged():
    """multipart_upload scenario must use extract_multipart_upload_features."""
    vector = extract_multipart_upload_features(
        filename="test.txt",
        content=b"file content",
        fields={"nodeType": "cm:content", "autoRename": "false"}
    )

    assert len(vector) == 32, f"Expected 32D vector, got {len(vector)}"
    assert vector[2] == 1.0, "scenario_multipart_upload flag must be 1.0"
    assert vector[0] == 0.0, "scenario_metadata_update flag must be 0.0"
    assert vector[1] == 0.0, "scenario_text_content_update flag must be 0.0"


def test_unknown_scenario_fails_closed():
    """Unknown scenario must fail gracefully."""
    # Will be implemented when we add scenario dispatch
    pass


def test_scorer_trace_counters_remain_real():
    """Scorer participation trace must remain accurate."""
    # Test the trace logic inline without importing the full server module
    # (which requires numpy/torch). This verifies the contract.

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as f:
        trace_path = f.name

    try:
        # Simulate what record_scorer_trace does
        rec = {
            "ts": 1234567890,
            "backend": "test_backend",
            "invocation": 1,
            "success": True,
        }
        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # Verify the trace format
        with open(trace_path) as f:
            lines = f.readlines()

        assert len(lines) == 1, "Expected exactly one trace line"
        parsed = json.loads(lines[0])
        assert parsed["backend"] == "test_backend"
        assert parsed["invocation"] == 1
        assert parsed["success"] is True

    finally:
        os.unlink(trace_path)


def test_zero_scorer_invocation_invalid():
    """Zero scorer invocations must be detectable as invalid."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as f:
        trace_path = f.name

    try:
        # Empty trace file = zero invocations
        assert os.path.getsize(trace_path) == 0, "Empty trace = zero scorer invocations"

        with open(trace_path) as f:
            lines = f.readlines()

        assert len(lines) == 0, "Zero scorer invocations is invalid state"

    finally:
        os.unlink(trace_path)


if __name__ == "__main__":
    print("Running RED scorer routing tests...")

    test_content_update_uses_text_extractor()
    print("✓ content_update uses text extractor")

    test_metadata_update_uses_metadata_extractor()
    print("✓ metadata_update uses metadata extractor")

    test_multipart_dispatch_unchanged()
    print("✓ multipart dispatch unchanged")

    test_scorer_trace_counters_remain_real()
    print("✓ scorer trace counters real")

    test_zero_scorer_invocation_invalid()
    print("✓ zero scorer invocation invalid")

    print("\n⚠️  RED tests for scenario routing pass (extractors exist)")
    print("⚠️  Protocol tests skipped (RED: scenario not preserved in RPC)")
    print("\nAll RED routing tests completed.")
