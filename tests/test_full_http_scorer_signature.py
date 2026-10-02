"""
RED test for content_update full-HTTP scorer signature mismatch.

Before fix: rpc_score_unix is called with 3 args, should be 4.
Expected failure: TypeError when body_only_mode=0 and scorer is enabled.
"""
import os
import sys
import tempfile
import json
import pytest
from unittest.mock import patch, MagicMock, call

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_full_http_scorer_signature_red():
    """
    RED test: Verify that full-HTTP path calls rpc_score_unix with correct signature.
    
    Before fix: This should FAIL with TypeError (missing 'scenario' argument).
    After fix: This should PASS.
    """
    # Setup: content_update scenario config
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config = {
            "scenario": "content_update",
            "base": "http://localhost:8080",
            "default_endpoint": "content_update_endpoint",
            "target_type": "http_json",
            "endpoints": []
        }
        json.dump(config, f)
        config_path = f.name
    
    # Create temp status file
    status_fd, status_path = tempfile.mkstemp(suffix='.json')
    os.close(status_fd)
    
    try:
        # Environment setup for full-HTTP mode (body_only_mode=0)
        env_vars = {
            "NV_TARGET_CONFIG": config_path,
            "NV_ENDPOINT_NAME": "content_update_endpoint",
            "NV_BODY_SCORE_ENDPOINT": "unix:///tmp/test_scorer.sock",
            "NV_BODY_SCORE_THRESHOLD": "0.5",
            "NV_STATUS_PATH": status_path,
            "NV_BODY_ONLY_MODE": "0",  # Full-HTTP mode
        }
        
        # Mock stdin with simple JSON body
        test_body = b'{"nodeId": "test-node-123", "properties": {"cm:title": "Test"}}'
        
        # Create a mock stdin object
        mock_stdin = MagicMock()
        mock_stdin.buffer.read.return_value = test_body
        
        with patch.dict(os.environ, env_vars, clear=False):
            with patch('sys.stdin', mock_stdin):
                # Mock urllib.request.build_opener for HTTP calls
                with patch('urllib.request.build_opener') as mock_opener:
                    mock_response = MagicMock()
                    mock_response.getcode.return_value = 200
                    mock_response.read.return_value = b'{"success": true}'
                    mock_response.headers = {}
                    mock_opener.return_value.open.return_value = mock_response
                    
                    # Mock rpc_score_unix at the module level BEFORE importing nv_http_harness
                    with patch('nv_body_valid.rpc_score_unix') as mock_rpc:
                        mock_rpc.return_value = (True, 0.3)
                        
                        # Now import main - it will pick up the mocked rpc_score_unix
                        import nv_http_harness
                        # Force reload to pick up the mock
                        import importlib
                        importlib.reload(nv_http_harness)
                        
                        try:
                            result = nv_http_harness.main()
                            
                            # Verify rpc_score_unix was called
                            assert mock_rpc.called, f"rpc_score_unix should have been called. Call count: {mock_rpc.call_count}"
                            
                            # Extract actual call arguments
                            call_args = mock_rpc.call_args
                            actual_arg_count = len(call_args[0]) if call_args[0] else 0
                            
                            print(f"\nActual call: {call_args}")
                            print(f"Argument count: {actual_arg_count}")
                            
                            # BEFORE FIX: Should have 3 args (missing scenario)
                            # AFTER FIX: Should have 4 args (endpoint, scenario, endpoint_name, body)
                            if actual_arg_count == 3:
                                # RED state - missing scenario argument
                                args = call_args[0]
                                pytest.fail(
                                    f"RED CONFIRMED: rpc_score_unix called with {actual_arg_count} args "
                                    f"(missing scenario). Expected 4 args: (endpoint, scenario, endpoint_name, body). "
                                    f"Actual args: endpoint={args[0]!r}, arg2={args[1]!r}, arg3={args[2]!r}"
                                )
                            elif actual_arg_count == 4:
                                # GREEN state - correct signature
                                endpoint, scenario, endpoint_name, body = call_args[0]
                                assert scenario == "content_update", \
                                    f"Scenario should be 'content_update', got '{scenario}'"
                                assert endpoint_name == "content_update_endpoint"
                                assert body == test_body
                                print("GREEN: Test PASSED - correct signature with scenario='content_update'")
                            else:
                                pytest.fail(f"Unexpected argument count: {actual_arg_count}")
                                
                        except TypeError as e:
                            # Also acceptable RED failure mode
                            if "rpc_score_unix" in str(e):
                                pytest.fail(f"RED CONFIRMED: TypeError in rpc_score_unix call: {e}")
                            else:
                                raise
                    
    finally:
        if os.path.exists(config_path):
            os.unlink(config_path)
        if os.path.exists(status_path):
            os.unlink(status_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
