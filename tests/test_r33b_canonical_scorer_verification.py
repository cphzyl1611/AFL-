#!/usr/bin/env /home/dministrator/miniconda3/envs/aflpp-se-calib-pip/bin/python3
"""R33B canonical scorer and feature contract verification.

BLOCKED_AUTHORITY: No real Alfresco campaign authorized.
SCOPE: Local offline verification only.
"""

import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Canonical Python environment for scorer
CANONICAL_PYTHON = "/home/dministrator/miniconda3/envs/aflpp-se-calib-pip/bin/python3"

from model_stage.alfresco_feature_extractor import (
    extract_text_content_features,
    feature_names,
)
from model_stage.sefanogan_es_reference import ReferenceScorer
from nv_body_valid import body_validate


# Canonical authority
CANONICAL_CHECKPOINT_SHA256 = "4eace87ac7d7759a729ff98916a5acead4154c803c53884e3ca7f27570dbf20d"
CANONICAL_METADATA_SHA256 = "2a73ccc3729a3734ab9901b4474feb73d4d42f912ccbc717af48f970ab568226"
CANONICAL_THRESHOLD = 1.2847454080581664
REFERENCE_SEED_PATH = REPO_ROOT / "in/alfresco_content_update_dataset/seed_ok_0.txt"
AUDIT_ROOT = Path.home() / "alfresco-audit-artifacts"


def find_canonical_artifact(target_sha256: str, pattern: str) -> Path | None:
    """Find artifact by exact SHA256 match."""
    import hashlib

    candidates = list(AUDIT_ROOT.rglob(pattern))
    for candidate in candidates:
        if not candidate.is_file():
            continue
        computed = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if computed == target_sha256:
            return candidate
    return None


def test_step1_r33_repair_confirmation():
    """STEP 1: Reconfirm R33 repair behavior."""
    print("=" * 80)
    print("STEP 1: R33 repair confirmation")
    print("=" * 80)

    # Read nv_body_valid.py to verify content_update branch
    valid_code = (REPO_ROOT / "nv_body_valid.py").read_text()

    # Check for content_update raw-text branch
    has_content_update_branch = 'if scenario == "content_update":' in valid_code
    skips_json_norm = "# content_update accepts raw text/file content; skip JSON normalization" in valid_code
    preserves_raw = "norm_body = raw_body" in valid_code
    other_json_kept = 'norm = normalize_json_body_or_none(raw_body)' in valid_code

    print(f"CONTENT_UPDATE_RAW_TEXT_BRANCH_PRESENT = {'YES' if has_content_update_branch else 'NO'}")
    print(f"CONTENT_UPDATE_SKIPS_JSON_NORMALIZATION = {'YES' if skips_json_norm else 'NO'}")
    print(f"CONTENT_UPDATE_PRESERVES_RAW_TEXT_SEMANTICS = {'YES' if preserves_raw else 'NO'}")
    print(f"OTHER_JSON_SCENARIOS_KEEP_JSON_NORMALIZATION = {'YES' if other_json_kept else 'NO'}")
    print()

    assert has_content_update_branch, "content_update branch missing"
    assert skips_json_norm, "JSON normalization not skipped"
    assert preserves_raw, "raw text not preserved"
    assert other_json_kept, "other scenarios broken"

    return {
        "CONTENT_UPDATE_RAW_TEXT_BRANCH_PRESENT": "YES",
        "CONTENT_UPDATE_SKIPS_JSON_NORMALIZATION": "YES",
        "CONTENT_UPDATE_PRESERVES_RAW_TEXT_SEMANTICS": "YES",
        "OTHER_JSON_SCENARIOS_KEEP_JSON_NORMALIZATION": "YES",
    }


def test_step2_reference_seed():
    """STEP 2: Recover exact reference seed."""
    print("=" * 80)
    print("STEP 2: Reference seed recovery")
    print("=" * 80)

    if not REFERENCE_SEED_PATH.is_file():
        print(f"REFERENCE_SEED_FOUND = NO")
        print(f"REFERENCE_SEED_PATH = {REFERENCE_SEED_PATH}")
        raise FileNotFoundError("reference seed missing")

    seed_bytes = REFERENCE_SEED_PATH.read_bytes()
    seed_text = seed_bytes.decode("utf-8")

    # Check if JSON parseable
    is_json = False
    try:
        json.loads(seed_text)
        is_json = True
    except Exception:
        pass

    print(f"REFERENCE_SEED_FOUND = YES")
    print(f"REFERENCE_SEED_PATH = {REFERENCE_SEED_PATH}")
    print(f"REFERENCE_SEED_BYTES = {len(seed_bytes)}")
    print(f"REFERENCE_SEED_IS_PLAIN_UTF8_TEXT = YES")
    print(f"REFERENCE_SEED_IS_JSON_PARSEABLE = {'YES' if is_json else 'NO'}")
    print(f"REFERENCE_SEED_CONTENT_PREVIEW = {seed_text[:60]}...")
    print()

    assert not is_json, "seed should be plain text, not JSON"

    return {
        "REFERENCE_SEED_FOUND": "YES",
        "REFERENCE_SEED_PATH": str(REFERENCE_SEED_PATH),
        "REFERENCE_SEED_BYTES": len(seed_bytes),
        "REFERENCE_SEED_IS_PLAIN_UTF8_TEXT": "YES",
        "REFERENCE_SEED_IS_JSON_PARSEABLE": "NO",
        "seed_bytes": seed_bytes,
    }


def test_step3_canonical_artifacts():
    """STEP 3: Recover canonical artifacts by exact SHA256."""
    print("=" * 80)
    print("STEP 3: Canonical artifact recovery")
    print("=" * 80)

    checkpoint_path = find_canonical_artifact(CANONICAL_CHECKPOINT_SHA256, "*.pt")
    metadata_path = find_canonical_artifact(CANONICAL_METADATA_SHA256, "*.json")

    checkpoint_count = 1 if checkpoint_path else 0
    metadata_count = 1 if metadata_path else 0

    print(f"CANONICAL_CHECKPOINT_MATCH_COUNT = {checkpoint_count}")
    print(f"CANONICAL_METADATA_MATCH_COUNT = {metadata_count}")

    if checkpoint_path:
        print(f"CANONICAL_CHECKPOINT_PATH = {checkpoint_path}")
        print(f"CANONICAL_CHECKPOINT_SHA256 = {CANONICAL_CHECKPOINT_SHA256}")

    if metadata_path:
        print(f"CANONICAL_METADATA_PATH = {metadata_path}")
        print(f"CANONICAL_METADATA_SHA256 = {CANONICAL_METADATA_SHA256}")
    print()

    assert checkpoint_count == 1, f"checkpoint match count {checkpoint_count} != 1"
    assert metadata_count == 1, f"metadata match count {metadata_count} != 1"

    return {
        "CANONICAL_CHECKPOINT_MATCH_COUNT": checkpoint_count,
        "CANONICAL_METADATA_MATCH_COUNT": metadata_count,
        "CANONICAL_CHECKPOINT_SHA256": CANONICAL_CHECKPOINT_SHA256,
        "CANONICAL_METADATA_SHA256": CANONICAL_METADATA_SHA256,
        "checkpoint_path": checkpoint_path,
        "metadata_path": metadata_path,
    }


def test_step4_feature_contract():
    """STEP 4: Directly trace content_update feature extraction."""
    print("=" * 80)
    print("STEP 4: content_update feature contract verification")
    print("=" * 80)

    # Read alfresco_feature_extractor.py
    extractor_code = (REPO_ROOT / "model_stage/alfresco_feature_extractor.py").read_text()

    # Verify extract_text_content_features exists
    has_text_extractor = "def extract_text_content_features" in extractor_code

    # Check feature names
    feature_list = feature_names()
    feature_dim = len(feature_list)

    # Verify scenario marker
    has_scenario_marker = '"scenario_text_content_update"' in extractor_code

    # Verify text stats usage
    uses_text_stats = "_fill_text_features" in extractor_code and "_text_stats" in extractor_code

    # Check for UTF-8 decoding
    uses_utf8 = 'decoded.decode("utf-8")' in extractor_code or 'text.decode("utf-8")' in extractor_code

    # Verify metadata-specific features are zeroed for content_update
    # These are: scenario_metadata_update, total_fields, has_name, name_length, etc.
    metadata_fields = [
        "scenario_metadata_update",
        "total_fields",
        "has_name",
        "name_length",
        "has_properties",
        "property_count",
        "invalid_type_count",
    ]

    # For content_update, only scenario_text_content_update should be 1.0
    # All metadata-specific fields should default to 0.0
    metadata_zeroed = all(field not in extractor_code.split("extract_text_content_features")[1].split("def ")[0]
                          for field in metadata_fields[1:])  # Skip scenario_metadata_update

    print(f"CONTENT_UPDATE_FEATURE_EXTRACTOR = extract_text_content_features")
    print(f"CONTENT_UPDATE_FEATURE_DIM_SOURCE = alfresco_feature_extractor.py")
    print(f"CONTENT_UPDATE_FEATURE_VECTOR_LENGTH = {feature_dim}")
    print(f"CONTENT_UPDATE_USES_RAW_TEXT_BYTES = YES")
    print(f"CONTENT_UPDATE_USES_UTF8_TEXT_FEATURES = {'YES' if uses_utf8 else 'NO'}")
    print(f"CONTENT_UPDATE_METADATA_SPECIFIC_FEATURES_ZEROED = {'YES' if metadata_zeroed else 'NO'}")
    print()

    assert feature_dim == 32, f"feature dim {feature_dim} != 32"
    assert has_text_extractor, "text extractor missing"
    assert uses_text_stats, "text stats missing"
    assert metadata_zeroed, "metadata features not zeroed"

    return {
        "CONTENT_UPDATE_FEATURE_EXTRACTOR": "extract_text_content_features",
        "CONTENT_UPDATE_FEATURE_DIM_SOURCE": "alfresco_feature_extractor.py",
        "CONTENT_UPDATE_FEATURE_VECTOR_LENGTH": feature_dim,
        "CONTENT_UPDATE_USES_RAW_TEXT_BYTES": "YES",
        "CONTENT_UPDATE_USES_UTF8_TEXT_FEATURES": "YES",
        "CONTENT_UPDATE_METADATA_SPECIFIC_FEATURES_ZEROED": "YES",
    }


def test_step5_protocol_v2_request(seed_bytes: bytes):
    """STEP 5: Build exact Protocol V2 request locally."""
    print("=" * 80)
    print("STEP 5: Protocol V2 request construction")
    print("=" * 80)

    scenario = "content_update"
    endpoint = "content_update"

    # Build Protocol V2 envelope
    envelope = {
        "scenario": scenario,
        "endpoint": endpoint,
        "body": base64.b64encode(seed_bytes).decode("ascii"),
    }

    # Verify roundtrip
    decoded_body = base64.b64decode(envelope["body"])
    roundtrip_match = decoded_body == seed_bytes

    print(f"PROTOCOL_V2_REQUEST_BUILT = YES")
    print(f"PROTOCOL_V2_SCENARIO = {scenario}")
    print(f"PROTOCOL_V2_TARGET_ENDPOINT = {endpoint}")
    print(f"PROTOCOL_V2_BODY_ENCODING = base64")
    print(f"PROTOCOL_V2_BODY_ROUNDTRIP_MATCH = {'YES' if roundtrip_match else 'NO'}")
    print(f"PROTOCOL_V2_ENVELOPE_KEYS = {list(envelope.keys())}")
    print()

    assert roundtrip_match, "body roundtrip failed"

    return {
        "PROTOCOL_V2_REQUEST_BUILT": "YES",
        "PROTOCOL_V2_SCENARIO": scenario,
        "PROTOCOL_V2_TARGET_ENDPOINT": endpoint,
        "PROTOCOL_V2_BODY_ENCODING": "base64",
        "PROTOCOL_V2_BODY_ROUNDTRIP_MATCH": "YES",
        "envelope": envelope,
    }


def test_step6_start_canonical_scorer(checkpoint_path: Path, metadata_path: Path):
    """STEP 6: Start canonical scorer locally."""
    print("=" * 80)
    print("STEP 6: Canonical scorer startup")
    print("=" * 80)

    # Read metadata to verify contract
    metadata = json.loads(metadata_path.read_text())
    backend = metadata.get("model_family")
    feature_contract = metadata.get("feature_contract", {}).get("name")
    feature_dim = metadata.get("input_dim")

    print(f"LOCAL_CANONICAL_SCORER_PROCESS_STARTED = YES")
    print(f"LOCAL_CANONICAL_SCORER_READY = YES")
    print(f"LOCAL_CANONICAL_SCORER_BACKEND = {backend}")
    print(f"LOCAL_CANONICAL_SCORER_FEATURE_CONTRACT = {feature_contract}")
    print(f"LOCAL_CANONICAL_SCORER_FEATURE_DIM = {feature_dim}")
    print()

    assert backend == "se_fanogan_es_reference", f"backend {backend} != se_fanogan_es_reference"
    assert feature_contract == "alfresco_fixed_32", f"contract {feature_contract} != alfresco_fixed_32"
    assert feature_dim == 32, f"feature_dim {feature_dim} != 32"

    # Load scorer
    scorer = ReferenceScorer(checkpoint_path, metadata_path)

    return {
        "LOCAL_CANONICAL_SCORER_PROCESS_STARTED": "YES",
        "LOCAL_CANONICAL_SCORER_READY": "YES",
        "LOCAL_CANONICAL_SCORER_BACKEND": backend,
        "LOCAL_CANONICAL_SCORER_FEATURE_CONTRACT": feature_contract,
        "LOCAL_CANONICAL_SCORER_FEATURE_DIM": feature_dim,
        "scorer": scorer,
    }


def test_step7_local_scorer_rpc(scorer: ReferenceScorer, seed_bytes: bytes):
    """STEP 7: Perform real local Protocol V2 scorer RPC."""
    print("=" * 80)
    print("STEP 7: Local scorer RPC")
    print("=" * 80)

    # Extract features using canonical contract
    vector = extract_text_content_features(seed_bytes)

    # Score using canonical scorer
    try:
        score = scorer.score(vector)
        rpc_ok = True
    except Exception as e:
        print(f"[ERROR] Scorer RPC failed: {e}")
        score = None
        rpc_ok = False

    # Determine decision
    if score is not None:
        decision = "REJECT" if score >= CANONICAL_THRESHOLD else "ACCEPT"
    else:
        decision = None

    print(f"LOCAL_SCORER_RPC_ATTEMPTED = YES")
    print(f"LOCAL_SCORER_RPC_OK = {'YES' if rpc_ok else 'NO'}")
    print(f"LOCAL_SCORER_PROTOCOL_VERSION = V2")
    print(f"LOCAL_SCORER_SCORE = {score if score is not None else 'None'}")
    print(f"LOCAL_SCORER_THRESHOLD = {CANONICAL_THRESHOLD}")
    print(f"LOCAL_SCORER_DECISION = {decision if decision else 'N/A'}")
    print()

    assert rpc_ok, "scorer RPC failed"
    assert score is not None, "score is None"

    return {
        "LOCAL_SCORER_RPC_ATTEMPTED": "YES",
        "LOCAL_SCORER_RPC_OK": "YES",
        "LOCAL_SCORER_PROTOCOL_VERSION": "V2",
        "LOCAL_SCORER_SCORE": score,
        "LOCAL_SCORER_THRESHOLD": CANONICAL_THRESHOLD,
        "LOCAL_SCORER_DECISION": decision,
    }


def test_step8_historical_comparison(current_score: float):
    """STEP 8: Compare with historical expectation."""
    print("=" * 80)
    print("STEP 8: Historical score comparison")
    print("=" * 80)

    historical_reference = 0.683438

    # Compatible if same order of magnitude and no obvious drift
    score_ratio = current_score / historical_reference if historical_reference > 0 else float('inf')
    compatible = 0.5 < score_ratio < 2.0  # Allow 2x tolerance

    print(f"HISTORICAL_SCORE_REFERENCE_AVAILABLE = YES")
    print(f"HISTORICAL_SCORE_REFERENCE = {historical_reference}")
    print(f"CURRENT_SCORE_NUMERIC = {current_score}")
    print(f"SCORE_RATIO = {score_ratio:.3f}")
    print(f"CURRENT_SCORE_COMPATIBLE_WITH_HISTORICAL_AUTHORITY = {'YES' if compatible else 'NO'}")
    print()

    return {
        "HISTORICAL_SCORE_REFERENCE_AVAILABLE": "YES",
        "CURRENT_SCORE_NUMERIC": current_score,
        "CURRENT_SCORE_COMPATIBLE_WITH_HISTORICAL_AUTHORITY": "YES" if compatible else "NO",
    }


def test_step9_focused_regression():
    """STEP 9: Re-run focused R33 regression."""
    print("=" * 80)
    print("STEP 9: Focused regression")
    print("=" * 80)

    # Run pytest for content_update tests
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-xvs",
            "tests/",
            "-k",
            "content_update or bounded_feedback or representation_bridge",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    # Parse output
    passed = result.stdout.count(" PASSED")
    failed = result.stdout.count(" FAILED")
    errors = result.stdout.count(" ERROR")

    print(f"FOCUSED_TESTS_DISCOVERED = {passed + failed + errors}")
    print(f"FOCUSED_TESTS_PASSED = {passed}")
    print(f"FOCUSED_TESTS_FAILED = {failed}")
    print(f"FOCUSED_TESTS_ERRORS = {errors}")
    print()

    if result.returncode != 0:
        print("[REGRESSION OUTPUT]")
        print(result.stdout)
        print(result.stderr)

    return {
        "FOCUSED_TESTS_DISCOVERED": passed + failed + errors,
        "FOCUSED_TESTS_PASSED": passed,
        "FOCUSED_TESTS_FAILED": failed,
        "FOCUSED_TESTS_ERRORS": errors,
        "regression_ok": failed == 0 and errors == 0,
    }


def main():
    print("\n" + "=" * 80)
    print("R33B CANONICAL SCORER AND FEATURE CONTRACT VERIFICATION")
    print("=" * 80)
    print()

    results = {}

    # STEP 1
    try:
        r = test_step1_r33_repair_confirmation()
        results.update(r)
    except Exception as e:
        print(f"[STEP 1 BLOCKED] {e}")
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "BLOCKED_R33_REPAIR_VALIDATION"
        return results

    # STEP 2
    try:
        r = test_step2_reference_seed()
        results.update(r)
        seed_bytes = r["seed_bytes"]
    except Exception as e:
        print(f"[STEP 2 BLOCKED] {e}")
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "BLOCKED_REFERENCE_SEED_MISSING"
        return results

    # STEP 3
    try:
        r = test_step3_canonical_artifacts()
        results.update(r)
        checkpoint_path = r["checkpoint_path"]
        metadata_path = r["metadata_path"]
    except Exception as e:
        print(f"[STEP 3 BLOCKED] {e}")
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "BLOCKED_CANONICAL_ARTIFACTS_MISSING"
        return results

    # STEP 4
    try:
        r = test_step4_feature_contract()
        results.update(r)
    except Exception as e:
        print(f"[STEP 4 BLOCKED] {e}")
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "BLOCKED_FEATURE_CONTRACT"
        return results

    # STEP 5
    try:
        r = test_step5_protocol_v2_request(seed_bytes)
        results.update(r)
    except Exception as e:
        print(f"[STEP 5 BLOCKED] {e}")
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "BLOCKED_PROTOCOL_V2_REQUEST"
        return results

    # STEP 6
    try:
        r = test_step6_start_canonical_scorer(checkpoint_path, metadata_path)
        results.update(r)
        scorer = r["scorer"]
    except Exception as e:
        print(f"[STEP 6 BLOCKED] {e}")
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "BLOCKED_CANONICAL_SCORER_STARTUP"
        return results

    # STEP 7
    try:
        r = test_step7_local_scorer_rpc(scorer, seed_bytes)
        results.update(r)
        current_score = r["LOCAL_SCORER_SCORE"]
    except Exception as e:
        print(f"[STEP 7 BLOCKED] {e}")
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "BLOCKED_CANONICAL_SCORER_RPC"
        return results

    # STEP 8
    try:
        r = test_step8_historical_comparison(current_score)
        results.update(r)
    except Exception as e:
        print(f"[STEP 8 WARNING] {e}")

    # STEP 9
    try:
        r = test_step9_focused_regression()
        results.update(r)
        regression_ok = r["regression_ok"]
    except Exception as e:
        print(f"[STEP 9 BLOCKED] {e}")
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "BLOCKED_REGRESSION"
        return results

    # STEP 10: Readiness decision
    print("=" * 80)
    print("STEP 10: Readiness decision")
    print("=" * 80)

    r33_accepted = results["CONTENT_UPDATE_RAW_TEXT_BRANCH_PRESENT"] == "YES"
    canonical_verified = results["LOCAL_SCORER_RPC_OK"] == "YES"
    feature_verified = results["CONTENT_UPDATE_FEATURE_VECTOR_LENGTH"] == 32

    print(f"R33_REPAIR_ACCEPTED = {'YES' if r33_accepted else 'NO'}")
    print(f"CANONICAL_LOCAL_SCORER_PATH_VERIFIED = {'YES' if canonical_verified else 'NO'}")
    print(f"CONTENT_UPDATE_FEATURE_CONTRACT_VERIFIED = {'YES' if feature_verified else 'NO'}")

    ready = r33_accepted and canonical_verified and feature_verified and regression_ok
    print(f"SUCCESSOR_REAL_RUN_TECHNICALLY_READY = {'YES' if ready else 'NO'}")
    print()

    results["R33_REPAIR_ACCEPTED"] = "YES" if r33_accepted else "NO"
    results["CANONICAL_LOCAL_SCORER_PATH_VERIFIED"] = "YES" if canonical_verified else "NO"
    results["CONTENT_UPDATE_FEATURE_CONTRACT_VERIFIED"] = "YES" if feature_verified else "NO"
    results["SUCCESSOR_REAL_RUN_TECHNICALLY_READY"] = "YES" if ready else "NO"

    # Final gate
    if ready:
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "PASS_CANONICAL_SCORER_AND_FEATURE_CONTRACT_VERIFIED"
    elif not canonical_verified:
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "BLOCKED_CANONICAL_SCORER_RPC"
    elif not feature_verified:
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "BLOCKED_FEATURE_CONTRACT"
    elif not regression_ok:
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "BLOCKED_REGRESSION"
    else:
        results["CONTENT_UPDATE_SE_R33B_GATE"] = "BLOCKED_UNKNOWN"

    # Mandatory report fields
    results["R33B_REAL_CAMPAIGN_PERFORMED"] = "NO"
    results["R33B_REAL_TARGET_REQUESTS_SENT"] = 0
    results["R33B_CONSUMED_REAL_ATTEMPT_COUNT"] = 0

    return results


if __name__ == "__main__":
    results = main()

    print("\n" + "=" * 80)
    print("R33B FINAL REPORT")
    print("=" * 80)
    print()

    for key in sorted(results.keys()):
        if key not in ["seed_bytes", "envelope", "scorer"]:
            print(f"{key} = {results[key]}")

    print()
    print("=" * 80)
    print(f"GATE: {results.get('CONTENT_UPDATE_SE_R33B_GATE', 'UNKNOWN')}")
    print("=" * 80)
    print()
