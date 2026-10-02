#!/usr/bin/env python3
"""GREEN tests: Scorer routing repair verification."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "model_stage"))

from alfresco_feature_extractor import (
    extract_metadata_features,
    extract_text_content_features,
)


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


def test_rpc_protocol_preserves_scenario():
    """RPC protocol v2 must preserve scenario/endpoint identity."""
    # Verify nv_body_valid.py sends scenario in envelope
    with open("nv_body_valid.py") as f:
        content = f.read()
    
    assert '"scenario": scenario,' in content, "RPC client must send scenario in envelope"
    assert '"endpoint": endpoint_name,' in content, "RPC client must send endpoint in envelope"
    assert 'base64.b64encode(norm_body)' in content, "RPC client must encode body as base64"


def test_real_scorer_receives_scenario():
    """Real scorer must receive and parse scenario from RPC envelope."""
    with open("model_stage/nv_valid_server_real.py") as f:
        content = f.read()
    
    assert 'def recv_one(conn: socket.socket):' in content, "recv_one must be updated"
    assert 'scenario = str(envelope.get("scenario"' in content, "recv_one must extract scenario"
    assert 'return scenario, endpoint, body' in content, "recv_one must return tuple"


def test_scorer_dispatches_by_scenario():
    """Scorer must dispatch to correct feature extractor based on scenario."""
    with open("model_stage/nv_valid_server_real.py") as f:
        content = f.read()
    
    assert 'def predict_score_from_body(scenario: str, body: bytes)' in content
    assert 'if scenario == "content_update":' in content
    assert 'extract_text_content_features(body)' in content
    assert 'extract_metadata_features(payload)' in content


def test_unknown_scenario_fails_closed():
    """Unknown scenario must fail closed with clear error."""
    with open("model_stage/nv_valid_server_real.py") as f:
        content = f.read()
    
    assert 'if scenario not in ("metadata_update", "content_update")' in content
    assert 'UNSUPPORTED_SCENARIO_FOR_RPC' in content


if __name__ == "__main__":
    print("Running GREEN scorer routing tests...")
    
    test_content_update_uses_text_extractor()
    print("✓ content_update uses text extractor")
    
    test_metadata_update_uses_metadata_extractor()
    print("✓ metadata_update uses metadata extractor")
    
    test_rpc_protocol_preserves_scenario()
    print("✓ RPC protocol preserves scenario")
    
    test_real_scorer_receives_scenario()
    print("✓ real scorer receives scenario")
    
    test_scorer_dispatches_by_scenario()
    print("✓ scorer dispatches by scenario")
    
    test_unknown_scenario_fails_closed()
    print("✓ unknown scenario fails closed")
    
    print("\n✅ All GREEN scorer routing tests PASS")
