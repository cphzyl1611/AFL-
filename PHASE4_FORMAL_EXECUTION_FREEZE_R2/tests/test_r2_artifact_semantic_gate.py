#!/usr/bin/env python3
"""
Offline TDD tests for R2 semantic artifact-gate adapter.

Tests all required cases using offline fixtures.
No network. No real experiment runs.
"""

import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))

from r2_artifact_semantic_gate import r2_artifact_semantic_gate


def create_fixture_files(tmpdir: Path, artifact_report: dict, body_valid_stats: dict) -> tuple:
    """Create fixture files for testing."""
    artifact_path = tmpdir / 'artifact_report.json'
    body_valid_path = tmpdir / 'nv_body_valid_stats.json'
    exec_ledger_path = tmpdir / 'executions.jsonl'
    
    with open(artifact_path, 'w') as f:
        json.dump(artifact_report, f)
    
    with open(body_valid_path, 'w') as f:
        json.dump(body_valid_stats, f)
    
    # Create empty executions.jsonl (path must exist)
    exec_ledger_path.touch()
    
    return artifact_path, body_valid_path, exec_ledger_path


def test_t1_base_validator_pass():
    """T1: Base validator PASS => semantic PASS"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        artifact_report = {
            'artifact_final_result': 'artifact_contract_pass',
            'ok': True,
            'missing_required': []
        }
        
        body_valid_stats = {
            'body_score_pass': 5,
            'body_score_rpc_ok': 5,
            'body_score_rpc_fail': 0
        }
        
        paths = create_fixture_files(tmpdir, artifact_report, body_valid_stats)
        verdict, reason = r2_artifact_semantic_gate(*paths)
        
        assert verdict == 'PASS', f"T1 failed: expected PASS, got {verdict}"
        assert 'Base validator' in reason
        
        return 'PASS'


def test_t2_false_negative_zero_exec_case():
    """T2: False-negative case (missing probe/state_db, body_score_pass=0, zero exec) => PASS_VALIDATOR_FALSE_NEGATIVE"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        artifact_report = {
            'artifact_final_result': 'artifact_contract_failed',
            'ok': False,
            'missing_required': ['probe', 'state_db'],
            'missing_setup_required': [],
            'missing_conditional': ['ctx'],
            'execution_ledger': {
                'counted_execution_count': 0,
                'target_execution_count': 0
            },
            'model_comparison_validity': {
                'verdict': 'PASS',
                'trace_invocations': 5,
                'scorer_rpc_ok': 5,
                'scorer_rpc_fail': 0
            },
            'readback_verdict': 'pass'
        }
        
        body_valid_stats = {
            'body_score_pass': 0,
            'body_score_reject': 5,
            'body_score_rpc_ok': 5,
            'body_score_rpc_fail': 0
        }
        
        paths = create_fixture_files(tmpdir, artifact_report, body_valid_stats)
        verdict, reason = r2_artifact_semantic_gate(*paths)
        
        assert verdict == 'PASS_VALIDATOR_FALSE_NEGATIVE_ZERO_EXECUTION_CASE', \
            f"T2 failed: expected PASS_VALIDATOR_FALSE_NEGATIVE_ZERO_EXECUTION_CASE, got {verdict}"
        assert 'Zero-execution' in reason
        
        return 'PASS'


def test_t3_missing_files_but_body_score_pass_gt_0():
    """T3: Same missing files but body_score_pass > 0 => FAIL"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        artifact_report = {
            'artifact_final_result': 'artifact_contract_failed',
            'ok': False,
            'missing_required': ['probe', 'state_db'],
            'missing_setup_required': [],
            'missing_conditional': [],
            'execution_ledger': {
                'counted_execution_count': 0,
                'target_execution_count': 0
            },
            'model_comparison_validity': {
                'verdict': 'PASS',
                'trace_invocations': 5
            },
            'readback_verdict': 'pass'
        }
        
        body_valid_stats = {
            'body_score_pass': 3,  # > 0
            'body_score_reject': 2,
            'body_score_rpc_ok': 5,
            'body_score_rpc_fail': 0
        }
        
        paths = create_fixture_files(tmpdir, artifact_report, body_valid_stats)
        verdict, reason = r2_artifact_semantic_gate(*paths)
        
        assert verdict == 'FAIL', f"T3 failed: expected FAIL, got {verdict}"
        assert 'body_score_pass' in reason
        
        return 'PASS'


def test_t4_missing_files_but_target_exec_gt_0():
    """T4: Same missing files but target execution count > 0 => FAIL"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        artifact_report = {
            'artifact_final_result': 'artifact_contract_failed',
            'ok': False,
            'missing_required': ['probe', 'state_db'],
            'missing_setup_required': [],
            'missing_conditional': [],
            'execution_ledger': {
                'counted_execution_count': 2,  # > 0
                'target_execution_count': 2
            },
            'model_comparison_validity': {
                'verdict': 'PASS',
                'trace_invocations': 5
            },
            'readback_verdict': 'pass'
        }
        
        body_valid_stats = {
            'body_score_pass': 0,
            'body_score_reject': 5,
            'body_score_rpc_ok': 5,
            'body_score_rpc_fail': 0
        }
        
        paths = create_fixture_files(tmpdir, artifact_report, body_valid_stats)
        verdict, reason = r2_artifact_semantic_gate(*paths)
        
        assert verdict == 'FAIL', f"T4 failed: expected FAIL, got {verdict}"
        assert 'counted_execution_count' in reason or 'target_execution_count' in reason
        
        return 'PASS'


def test_t5_missing_files_plus_other_artifact_failure():
    """T5: Missing probe/state_db plus other required artifact failure => FAIL"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        artifact_report = {
            'artifact_final_result': 'artifact_contract_failed',
            'ok': False,
            'missing_required': ['probe', 'state_db', 'afl_stats'],  # Additional missing
            'missing_setup_required': [],
            'missing_conditional': [],
            'execution_ledger': {
                'counted_execution_count': 0,
                'target_execution_count': 0
            },
            'model_comparison_validity': {
                'verdict': 'PASS',
                'trace_invocations': 5
            },
            'readback_verdict': 'pass'
        }
        
        body_valid_stats = {
            'body_score_pass': 0,
            'body_score_reject': 5,
            'body_score_rpc_ok': 5,
            'body_score_rpc_fail': 0
        }
        
        paths = create_fixture_files(tmpdir, artifact_report, body_valid_stats)
        verdict, reason = r2_artifact_semantic_gate(*paths)
        
        assert verdict == 'FAIL', f"T5 failed: expected FAIL, got {verdict}"
        assert 'not exactly probe and state_db' in reason
        
        return 'PASS'


def test_t6_rpc_failure_or_provenance_failure():
    """T6: RPC failure or provenance failure => FAIL"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        artifact_report = {
            'artifact_final_result': 'artifact_contract_failed',
            'ok': False,
            'missing_required': ['probe', 'state_db'],
            'missing_setup_required': [],
            'missing_conditional': [],
            'execution_ledger': {
                'counted_execution_count': 0,
                'target_execution_count': 0
            },
            'model_comparison_validity': {
                'verdict': 'FAIL',  # Model comparison failed
                'trace_invocations': 5
            },
            'readback_verdict': 'pass'
        }
        
        body_valid_stats = {
            'body_score_pass': 0,
            'body_score_reject': 5,
            'body_score_rpc_ok': 5,
            'body_score_rpc_fail': 0
        }
        
        paths = create_fixture_files(tmpdir, artifact_report, body_valid_stats)
        verdict, reason = r2_artifact_semantic_gate(*paths)
        
        assert verdict == 'FAIL', f"T6 failed: expected FAIL, got {verdict}"
        assert 'model_comparison_validity' in reason
        
        return 'PASS'


def main():
    """Run all tests."""
    tests = [
        ('T1_BASE_VALIDATOR_PASS', test_t1_base_validator_pass),
        ('T2_FALSE_NEGATIVE_ZERO_EXEC', test_t2_false_negative_zero_exec_case),
        ('T3_BODY_SCORE_PASS_GT_0', test_t3_missing_files_but_body_score_pass_gt_0),
        ('T4_TARGET_EXEC_GT_0', test_t4_missing_files_but_target_exec_gt_0),
        ('T5_OTHER_ARTIFACT_FAILURE', test_t5_missing_files_plus_other_artifact_failure),
        ('T6_RPC_OR_PROVENANCE_FAILURE', test_t6_rpc_failure_or_provenance_failure)
    ]
    
    results = {}
    all_pass = True
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results[test_name] = result
            print(f"{test_name}: {result}")
        except AssertionError as e:
            results[test_name] = f"FAIL ({e})"
            all_pass = False
            print(f"{test_name}: FAIL - {e}")
        except Exception as e:
            results[test_name] = f"ERROR ({e})"
            all_pass = False
            print(f"{test_name}: ERROR - {e}")
    
    print()
    print("=" * 60)
    if all_pass:
        print("R2_SEMANTIC_GATE_TDD = PASS")
        print("All 6 required test cases passed")
        return 0
    else:
        print("R2_SEMANTIC_GATE_TDD = FAIL")
        print("Some tests failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
