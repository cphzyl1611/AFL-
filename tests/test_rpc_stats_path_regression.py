"""Focused regression test: RPC stats path must match producer.

Phase 2 RPC Stats Path Repair - RED/GREEN proof.

The harness writes nv_body_valid_stats.json to layout["body_valid_stats"].
The validator MUST read from the same path, not from layout["afl_output"].

This test proves:
1. RED: wrong path → parse returns empty dict → ZERO_SCORER_INVOCATIONS
2. GREEN: correct path → parse returns RPC stats → PASS
"""
import json
import tempfile
from pathlib import Path


def test_parse_reads_from_layout_body_valid_stats():
    """parse_nv_body_valid_stats must read from layout["body_valid_stats"]."""
    from scripts.run_alfresco_bounded_feedback import parse_nv_body_valid_stats

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Simulate layout["body_valid_stats"] = run_root / "nv_body_valid_stats.json"
        correct_path = tmpdir_path / "nv_body_valid_stats.json"
        correct_path.write_text(
            json.dumps({
                "body_score_rpc_ok": 5,
                "body_score_rpc_fail": 0,
                "body_score_pass": 3,
                "body_score_reject": 2,
            }),
            encoding="utf-8",
        )
        
        # Parse from correct path
        result = parse_nv_body_valid_stats(correct_path)
        
        assert result["body_score_rpc_ok"] == 5
        assert result["body_score_rpc_fail"] == 0
        assert result["body_score_pass"] == 3
        assert result["body_score_reject"] == 2


def test_parse_returns_empty_when_path_wrong():
    """parse_nv_body_valid_stats returns {} when file doesn't exist."""
    from scripts.run_alfresco_bounded_feedback import parse_nv_body_valid_stats

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Simulate the WRONG path: layout["afl_output"] / "nv_body_valid_stats.json"
        wrong_path = tmpdir_path / "afl-out" / "nv_body_valid_stats.json"
        
        # File doesn't exist at wrong path
        assert not wrong_path.exists()
        
        # Parse returns empty dict (fail-closed)
        result = parse_nv_body_valid_stats(wrong_path)
        
        assert result == {}


def test_validation_fails_when_rpc_stats_missing():
    """Validation reports ZERO_SCORER_INVOCATIONS when RPC stats are missing."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )

    # Empty stats dict (as if parse returned {})
    stats = {}
    
    # Valid trace with 5 records
    trace = [
        {"backend": "alfresco_ae_v1", "score": 0.85, "exec_seq": i+1}
        for i in range(5)
    ]
    
    result = validate_model_comparison_participation(
        stats, trace, "alfresco_ae_v1"
    )
    
    # Validation should fail with ZERO_SCORER_INVOCATIONS
    assert result["verdict"] == "INVALID_FOR_MODEL_COMPARISON"
    assert "ZERO_SCORER_INVOCATIONS" in result["reason_codes"]


def test_validation_passes_when_rpc_stats_present():
    """Validation passes when RPC stats show rpc_ok>0, rpc_fail=0."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )

    # Stats dict with RPC counters (as if parse succeeded)
    stats = {
        "body_score_rpc_ok": 5,
        "body_score_rpc_fail": 0,
    }
    
    # Valid trace with 5 records
    trace = [
        {"backend": "alfresco_ae_v1", "score": 0.85, "exec_seq": i+1}
        for i in range(5)
    ]
    
    result = validate_model_comparison_participation(
        stats, trace, "alfresco_ae_v1"
    )
    
    # Validation should pass
    assert result["verdict"] == "PASS"
    assert result["reason_codes"] == []
    assert result["scorer_rpc_ok"] == 5
    assert result["scorer_rpc_fail"] == 0


def test_parse_fail_closed_on_malformed_json():
    """parse_nv_body_valid_stats returns {} when JSON is malformed."""
    from scripts.run_alfresco_bounded_feedback import parse_nv_body_valid_stats

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        stats_path = tmpdir_path / "nv_body_valid_stats.json"
        stats_path.write_text("{ broken json", encoding="utf-8")
        
        result = parse_nv_body_valid_stats(stats_path)
        
        assert result == {}


def test_parse_fail_closed_on_missing_rpc_fields():
    """parse_nv_body_valid_stats defaults to 0 when RPC fields missing."""
    from scripts.run_alfresco_bounded_feedback import parse_nv_body_valid_stats

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        stats_path = tmpdir_path / "nv_body_valid_stats.json"
        stats_path.write_text(
            json.dumps({
                "body_rule_pass": 10,
                # Missing body_score_rpc_ok and body_score_rpc_fail
            }),
            encoding="utf-8",
        )
        
        result = parse_nv_body_valid_stats(stats_path)
        
        assert result["body_score_rpc_ok"] == 0
        assert result["body_score_rpc_fail"] == 0


def test_validation_fails_when_rpc_fail_nonzero():
    """Validation reports SCORER_RPC_FAILURE when rpc_fail > 0."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )

    stats = {
        "body_score_rpc_ok": 3,
        "body_score_rpc_fail": 2,  # Non-zero failures
    }
    
    trace = [
        {"backend": "alfresco_ae_v1", "score": 0.85, "exec_seq": i+1}
        for i in range(3)
    ]
    
    result = validate_model_comparison_participation(
        stats, trace, "alfresco_ae_v1"
    )
    
    assert result["verdict"] == "INVALID_FOR_MODEL_COMPARISON"
    assert "SCORER_RPC_FAILURE" in result["reason_codes"]
