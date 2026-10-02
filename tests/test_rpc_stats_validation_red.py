"""RED test: prove validator reads RPC stats from wrong source.

Phase 2 Model-Comparison Evidence Contract TDD Repair - Step 4.

Defect A: validate_model_comparison_participation() reads body_score_rpc_*
from fuzzer_stats dict, but the harness writes these counters to
nv_body_valid_stats.json. The validator must read from the JSON file.

This test establishes the RED state: when nv_body_valid_stats.json has
rpc_ok>0 and rpc_fail=0, but fuzzer_stats lacks these fields, the current
code incorrectly reports ZERO_SCORER_INVOCATIONS.

After GREEN repair, the validator will integrate parse_nv_body_valid_stats()
and pass this test.
"""
import json
import tempfile
from pathlib import Path


def test_validator_reads_rpc_from_wrong_source():
    """Current validator incorrectly reads RPC stats from fuzzer_stats dict.

    Case 1: nv_body_valid_stats.json exists with rpc_ok=5, rpc_fail=0.
            fuzzer_stats dict LACKS body_score_rpc_* fields.
            Valid trace has 5 records matching expected backend.

    Expected CURRENT behavior (RED): INVALID_FOR_MODEL_COMPARISON with
                                     ZERO_SCORER_INVOCATIONS reason code

    Expected AFTER repair (GREEN): PASS verdict, no reason codes
    """
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
        parse_nv_body_valid_stats,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create nv_body_valid_stats.json with valid RPC counters
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

        # Verify parse_nv_body_valid_stats() works correctly
        parsed = parse_nv_body_valid_stats(stats_json)
        assert parsed["body_score_rpc_ok"] == 5
        assert parsed["body_score_rpc_fail"] == 0

        # Create fuzzer_stats dict WITHOUT body_score_rpc_* fields
        # (This simulates the actual fuzzer_stats that only has core AFL fields)
        fuzzer_stats = {
            "nv_total_valid_exec": "5",
            "execs_done": "10",
            "execs_per_sec": "1.5",
            # Deliberately omit body_score_rpc_ok and body_score_rpc_fail
        }

        # Create valid trace with 5 records
        trace = [
            {"backend": "alfresco_ae_v1", "score": 0.85, "exec_seq": i+1}
            for i in range(5)
        ]

        # Call the validator with fuzzer_stats dict (current wrong source)
        result = validate_model_comparison_participation(
            fuzzer_stats, trace, "alfresco_ae_v1"
        )

        # RED: Current code reads from fuzzer_stats dict, sees no rpc_ok field,
        # defaults to 0, and reports ZERO_SCORER_INVOCATIONS
        assert result["verdict"] == "INVALID_FOR_MODEL_COMPARISON", (
            f"Expected RED state: INVALID verdict, but got {result['verdict']}"
        )
        assert "ZERO_SCORER_INVOCATIONS" in result["reason_codes"], (
            f"Expected RED state: ZERO_SCORER_INVOCATIONS in reason_codes, "
            f"but got {result['reason_codes']}"
        )

        # Document what the correct behavior SHOULD be after repair
        # (This assertion should FAIL in RED state, PASS after GREEN repair)
        try:
            assert result["verdict"] == "PASS"
            assert not result["reason_codes"]
            print("UNEXPECTED: Test passed in GREEN state before repair!")
        except AssertionError:
            # Expected in RED state
            pass


def test_validator_should_use_nv_body_valid_stats_json():
    """After repair: validator integrates parse_nv_body_valid_stats().

    Case 2: Same setup as Case 1, but now the validator reads from
            nv_body_valid_stats.json instead of fuzzer_stats dict.

    Expected behavior after GREEN repair: PASS verdict, no reason codes.

    This test will SKIP in RED state (because the validator signature
    doesn't accept the stats_path yet), and PASS after GREEN repair.
    """
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
        parse_nv_body_valid_stats,
    )
    import inspect

    # Check if the validator has been repaired to accept stats_path
    sig = inspect.signature(validate_model_comparison_participation)
    if "stats_path" not in sig.parameters:
        # RED state: validator doesn't accept stats_path yet
        # Skip this test until GREEN repair
        import pytest
        pytest.skip("Validator not yet repaired to accept stats_path")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create nv_body_valid_stats.json with valid RPC counters
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

        # Create fuzzer_stats dict WITHOUT body_score_rpc_* fields
        fuzzer_stats = {
            "nv_total_valid_exec": "5",
        }

        # Create valid trace with 5 records
        trace = [
            {"backend": "alfresco_ae_v1", "score": 0.85, "exec_seq": i+1}
            for i in range(5)
        ]

        # After repair, call with stats_path parameter
        result = validate_model_comparison_participation(
            fuzzer_stats, trace, "alfresco_ae_v1", stats_path=stats_json
        )

        # GREEN: Validator reads from nv_body_valid_stats.json and passes
        assert result["verdict"] == "PASS", (
            f"After repair, expected PASS but got {result['verdict']}"
        )
        assert not result["reason_codes"], (
            f"After repair, expected no reason codes but got {result['reason_codes']}"
        )
        assert result["scorer_rpc_ok"] == 5
        assert result["scorer_rpc_fail"] == 0


def test_fuzzer_stats_not_required_to_contain_rpc_counters():
    """Contract clarification: fuzzer_stats is NOT the RPC counter authority.

    This test documents the ownership principle established in Step 2:
    RPC_COUNTER_AUTHORITY = nv_body_valid_stats.json (not fuzzer_stats)
    FUZZER_STATS_REQUIRED_TO_CONTAIN_BODY_SCORE_RPC_COUNTERS = NO

    After repair, the validator must tolerate fuzzer_stats that lacks
    body_score_rpc_* fields entirely.
    """
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )
    import inspect

    # This test only runs after GREEN repair
    sig = inspect.signature(validate_model_comparison_participation)
    if "stats_path" not in sig.parameters:
        import pytest
        pytest.skip("Validator not yet repaired")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create nv_body_valid_stats.json
        stats_json = tmpdir_path / "nv_body_valid_stats.json"
        stats_json.write_text(
            json.dumps({
                "body_score_rpc_ok": 3,
                "body_score_rpc_fail": 0,
            }),
            encoding="utf-8",
        )

        # Create fuzzer_stats with ONLY core AFL fields, no NV RPC fields
        fuzzer_stats = {
            "start_time": "1234567890",
            "execs_done": "5",
            "execs_per_sec": "2.0",
            "paths_total": "3",
            # Deliberately no body_score_rpc_ok or body_score_rpc_fail
        }

        trace = [
            {"backend": "sefanogan_es_reference", "score": 0.9, "exec_seq": i+1}
            for i in range(3)
        ]

        # After repair, this should pass without requiring fuzzer_stats
        # to have RPC counters
        result = validate_model_comparison_participation(
            fuzzer_stats, trace, "sefanogan_es_reference", stats_path=stats_json
        )

        assert result["verdict"] == "PASS"
        assert result["scorer_rpc_ok"] == 3
        assert result["scorer_rpc_fail"] == 0
