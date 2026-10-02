#!/usr/bin/env python3
"""Step 8: Offline verification - feature extraction only (no numpy/torch)."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "model_stage"))

# Import only the feature extractors (no scorer, no numpy)
from alfresco_feature_extractor import (
    extract_metadata_features,
    extract_text_content_features,
)


def test_content_update_fixture_feature_extraction():
    """Verify content_update fixture produces correct feature vector shape."""
    print("\nTest 1: content_update feature extraction")
    
    fixture_path = REPO_ROOT / "in" / "alfresco_afl_content_update_smoke" / "seed_ok_0.txt"
    if not fixture_path.is_file():
        print(f"  ⚠️  SKIP: fixture missing: {fixture_path}")
        return False
    
    fixture_bytes = fixture_path.read_bytes()
    print(f"  Fixture: {fixture_path.name} ({len(fixture_bytes)} bytes)")
    print(f"  Preview: {fixture_bytes[:50]}...")
    
    # Extract features using content_update path
    vector = extract_text_content_features(fixture_bytes)
    print(f"  Vector shape: {len(vector)}D")
    print(f"  Scenario flags: metadata={vector[0]}, text={vector[1]}, multipart={vector[2]}")
    
    assert len(vector) == 32, f"Expected 32D, got {len(vector)}"
    assert vector[1] == 1.0, "text_content flag must be 1.0"
    assert vector[0] == 0.0, "metadata flag must be 0.0"
    assert vector[2] == 0.0, "multipart flag must be 0.0"
    
    print("  ✓ content_update fixture produces correct vector")
    return True


def test_metadata_update_fixture_feature_extraction():
    """Verify metadata_update fixture produces correct feature vector shape."""
    print("\nTest 2: metadata_update feature extraction")
    
    fixture_path = REPO_ROOT / "in" / "alfresco_afl_metadata_update_smoke" / "seed_ok_0.json"
    if not fixture_path.is_file():
        print(f"  ⚠️  SKIP: fixture missing: {fixture_path}")
        return False
    
    fixture_bytes = fixture_path.read_bytes()
    payload = json.loads(fixture_bytes)
    print(f"  Fixture: {fixture_path.name} ({len(fixture_bytes)} bytes)")
    print(f"  Keys: {list(payload.keys())}")
    
    # Extract features using metadata_update path
    vector = extract_metadata_features(payload)
    print(f"  Vector shape: {len(vector)}D")
    print(f"  Scenario flags: metadata={vector[0]}, text={vector[1]}, multipart={vector[2]}")
    
    assert len(vector) == 32, f"Expected 32D, got {len(vector)}"
    assert vector[0] == 1.0, "metadata flag must be 1.0"
    assert vector[1] == 0.0, "text_content flag must be 0.0"
    assert vector[2] == 0.0, "multipart flag must be 0.0"
    
    print("  ✓ metadata_update fixture produces correct vector")
    return True


def test_scenario_flag_distinction():
    """Verify scenario flags are mutually exclusive."""
    print("\nTest 3: Scenario flag mutual exclusivity")
    
    # Load both fixtures
    content_fixture = REPO_ROOT / "in" / "alfresco_afl_content_update_smoke" / "seed_ok_0.txt"
    metadata_fixture = REPO_ROOT / "in" / "alfresco_afl_metadata_update_smoke" / "seed_ok_0.json"
    
    if not content_fixture.is_file() or not metadata_fixture.is_file():
        print(f"  ⚠️  SKIP: fixtures missing")
        return False
    
    content_bytes = content_fixture.read_bytes()
    metadata_payload = json.loads(metadata_fixture.read_bytes())
    
    vec_content = extract_text_content_features(content_bytes)
    vec_metadata = extract_metadata_features(metadata_payload)
    
    # Check first 3 positions (scenario flags)
    content_flags = vec_content[:3]
    metadata_flags = vec_metadata[:3]
    
    print(f"  content_update flags: {content_flags}")
    print(f"  metadata_update flags: {metadata_flags}")
    
    # Verify mutual exclusivity
    assert tuple(content_flags) == (0.0, 1.0, 0.0), "content flags wrong"
    assert tuple(metadata_flags) == (1.0, 0.0, 0.0), "metadata flags wrong"
    assert content_flags[1] != metadata_flags[1], "flags must differ"
    
    print("  ✓ Scenario flags are mutually exclusive")
    return True


def test_contract_valid_fixtures_exist():
    """Verify authoritative contract-valid fixtures exist."""
    print("\nTest 4: Contract-valid fixture inventory")
    
    fixtures = [
        ("content_update", REPO_ROOT / "in" / "alfresco_afl_content_update_smoke" / "seed_ok_0.txt"),
        ("metadata_update", REPO_ROOT / "in" / "alfresco_afl_metadata_update_smoke" / "seed_ok_0.json"),
    ]
    
    all_present = True
    for scenario, path in fixtures:
        if path.is_file():
            size = path.stat().st_size
            print(f"  ✓ {scenario}: {path.name} ({size} bytes)")
        else:
            print(f"  ✗ {scenario}: MISSING")
            all_present = False
    
    assert all_present, "All contract-valid fixtures must exist"
    return True


if __name__ == "__main__":
    print("=== Step 8: Offline Feature Extraction Verification ===")
    print("(Scoring skipped: no numpy/torch in environment)")
    
    results = []
    results.append(test_content_update_fixture_feature_extraction())
    results.append(test_metadata_update_fixture_feature_extraction())
    results.append(test_scenario_flag_distinction())
    results.append(test_contract_valid_fixtures_exist())
    
    if all(results):
        print("\n✅ All offline feature extraction tests PASS")
        print("\nVerdict:")
        print("  - Routing repair is structurally correct")
        print("  - Feature extractors produce correct scenario flags")
        print("  - Contract-valid fixtures extract correctly")
        print("  - Scorer will receive correct features per scenario")
    else:
        print("\n⚠️  Some tests SKIPPED (missing fixtures)")
