"""GREEN test: verify complete trace-writing integration.

Phase 2 Model-Comparison Evidence Contract TDD Repair - Integration Test.

This test verifies the complete end-to-end flow:
1. ScorerLifecycleManager propagates NV_SCORER_TRACE_PATH to scorer subprocess
2. Scorer implementation writes JSONL trace records on each invocation
3. Validator reads and reconciles trace with RPC counters from nv_body_valid_stats.json

Defects A and B are both repaired, so this should pass.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def test_complete_trace_writing_flow():
    """Complete integration: manager → scorer → trace file → validator."""
    from scripts.run_alfresco_bounded_feedback import (
        ScorerLifecycleManager,
        parse_scorer_trace,
        parse_nv_body_valid_stats,
        validate_model_comparison_participation,
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Use the real patched scorer
        scorer_script = Path("nv_valid_server_mock.py").resolve()
        socket_path = tmpdir_path / "test.sock"
        trace_path = tmpdir_path / "trace.jsonl"
        
        # Start scorer with trace path
        manager = ScorerLifecycleManager(
            scorer_python=sys.executable,
            scorer_script=scorer_script,
            socket_path=socket_path,
            backend="alfresco_ae_v1",
            timeout=5.0,
            trace_path=trace_path,
        )
        
        try:
            manager.start()
            
            # Send 5 scoring requests
            import socket as sock_module
            import struct
            
            for i in range(5):
                test_body = json.dumps({"key": f"value_{i}"}).encode("utf-8")
                
                sock = sock_module.socket(sock_module.AF_UNIX, sock_module.SOCK_STREAM)
                sock.settimeout(2.0)
                sock.connect(str(socket_path))
                
                sock.sendall(struct.pack("<I", len(test_body)))
                sock.sendall(test_body)
                
                score_bytes = sock.recv(8)
                score = struct.unpack("<d", score_bytes)[0]
                
                sock.close()
                time.sleep(0.05)
            
            # Wait for trace writes to flush
            time.sleep(0.2)
            
            # Verify trace file exists and has 5 records
            assert trace_path.exists(), "Trace file not created"
            
            trace = parse_scorer_trace(trace_path)
            assert len(trace) == 5, f"Expected 5 trace records, got {len(trace)}"
            
            for record in trace:
                assert record["backend"] == "alfresco_ae_v1"
                assert "score" in record
                assert "timestamp_ms" in record
            
            # Create nv_body_valid_stats.json
            stats_json = tmpdir_path / "nv_body_valid_stats.json"
            stats_json.write_text(
                json.dumps({
                    "body_score_rpc_ok": 5,
                    "body_score_rpc_fail": 0,
                    "body_score_pass": 5,
                    "body_score_reject": 0,
                }),
                encoding="utf-8",
            )
            
            # Simulate production validation flow
            stats = parse_nv_body_valid_stats(stats_json)
            result = validate_model_comparison_participation(
                stats, trace, "alfresco_ae_v1"
            )
            
            # Should pass validation
            assert result["verdict"] == "PASS", (
                f"Expected PASS verdict but got {result['verdict']} "
                f"with reason codes: {result['reason_codes']}"
            )
            assert not result["reason_codes"]
            assert result["scorer_rpc_ok"] == 5
            assert result["scorer_rpc_fail"] == 0
            assert result["trace_invocations"] == 5
            
        finally:
            manager.stop()


def test_trace_reconciliation_with_mismatch():
    """Validator correctly detects trace/RPC counter mismatches."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # RPC counters say 5 invocations
        stats = {
            "body_score_rpc_ok": 5,
            "body_score_rpc_fail": 0,
        }
        
        # But trace only has 3 records (mismatch)
        trace = [
            {"backend": "alfresco_ae_v1", "score": 0.85}
            for _ in range(3)
        ]
        
        result = validate_model_comparison_participation(
            stats, trace, "alfresco_ae_v1"
        )
        
        # Should detect mismatch
        assert result["verdict"] == "INVALID_FOR_MODEL_COMPARISON"
        assert "TRACE_COUNT_MISMATCH" in result["reason_codes"]


def test_backend_mismatch_detection():
    """Validator correctly detects backend mismatches in trace."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )
    
    stats = {
        "body_score_rpc_ok": 5,
        "body_score_rpc_fail": 0,
    }
    
    # Trace has wrong backend
    trace = [
        {"backend": "wrong_backend", "score": 0.85}
        for _ in range(5)
    ]
    
    result = validate_model_comparison_participation(
        stats, trace, "alfresco_ae_v1"
    )
    
    assert result["verdict"] == "INVALID_FOR_MODEL_COMPARISON"
    assert "TRACE_BACKEND_MISMATCH" in result["reason_codes"]
