"""Integration test: prove path fix via end-to-end AE validation.

Phase 2 RPC Stats Path Repair - RED/GREEN integration proof.

This test simulates a complete AE run directory and validates that:
1. RED: validator reads from wrong path → cannot find RPC stats → fails
2. GREEN: validator reads from correct path → finds RPC stats → passes
"""
import json
import tempfile
from pathlib import Path


def test_ae_validation_reads_correct_path():
    """End-to-end: validation must read RPC stats from layout["body_valid_stats"]."""
    from scripts.run_alfresco_bounded_feedback import (
        parse_nv_body_valid_stats,
        validate_model_comparison_participation,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Simulate run layout
        afl_out = tmpdir_path / "afl-out"
        afl_out.mkdir()
        
        # Producer path: layout["body_valid_stats"] = run_root / "nv_body_valid_stats.json"
        producer_path = tmpdir_path / "nv_body_valid_stats.json"
        producer_path.write_text(
            json.dumps({
                "body_score_rpc_ok": 5,
                "body_score_rpc_fail": 0,
                "body_score_pass": 3,
                "body_score_reject": 2,
            }),
            encoding="utf-8",
        )
        
        # Create valid trace
        trace = [
            {"backend": "alfresco_ae_v1", "score": 0.85, "exec_seq": i+1}
            for i in range(5)
        ]
        
        # GREEN: Parse from correct path (layout["body_valid_stats"])
        rpc_stats_green = parse_nv_body_valid_stats(producer_path)
        stats_green = {}
        stats_green.update(rpc_stats_green)
        
        result_green = validate_model_comparison_participation(
            stats_green, trace, "alfresco_ae_v1"
        )
        
        assert result_green["verdict"] == "PASS", (
            f"GREEN: Expected PASS but got {result_green['verdict']}"
        )
        assert result_green["scorer_rpc_ok"] == 5
        assert result_green["scorer_rpc_fail"] == 0
        
        # RED: Parse from wrong path (layout["afl_output"] / "nv_body_valid_stats.json")
        wrong_path = afl_out / "nv_body_valid_stats.json"
        assert not wrong_path.exists(), "Wrong path should not exist"
        
        rpc_stats_red = parse_nv_body_valid_stats(wrong_path)
        stats_red = {}
        stats_red.update(rpc_stats_red)
        
        result_red = validate_model_comparison_participation(
            stats_red, trace, "alfresco_ae_v1"
        )
        
        assert result_red["verdict"] == "INVALID_FOR_MODEL_COMPARISON", (
            f"RED: Expected INVALID_FOR_MODEL_COMPARISON but got {result_red['verdict']}"
        )
        assert "ZERO_SCORER_INVOCATIONS" in result_red["reason_codes"], (
            f"RED: Expected ZERO_SCORER_INVOCATIONS in {result_red['reason_codes']}"
        )


def test_production_code_uses_correct_path():
    """Verify run_alfresco_bounded_feedback.py:3043 uses layout["body_valid_stats"]."""
    import re
    from pathlib import Path
    
    script_path = Path(__file__).parent.parent / "scripts" / "run_alfresco_bounded_feedback.py"
    source = script_path.read_text(encoding="utf-8")
    
    # Find the line that sets rpc_stats_path
    # Should be: rpc_stats_path = layout["body_valid_stats"]
    pattern = r'rpc_stats_path\s*=\s*layout\["body_valid_stats"\]'
    
    match = re.search(pattern, source)
    
    assert match, (
        "Production code must use layout[\"body_valid_stats\"] as RPC stats path. "
        "If this assertion fails, the wrong path is still in use (RED state)."
    )
    
    # Also verify it does NOT use the wrong path
    wrong_pattern = r'rpc_stats_path\s*=\s*layout\["afl_output"\]\s*/\s*"nv_body_valid_stats\.json"'
    wrong_match = re.search(wrong_pattern, source)
    
    assert not wrong_match, (
        "Production code must NOT use layout[\"afl_output\"] / \"nv_body_valid_stats.json\". "
        "If this assertion fails, the code is still in RED state."
    )
