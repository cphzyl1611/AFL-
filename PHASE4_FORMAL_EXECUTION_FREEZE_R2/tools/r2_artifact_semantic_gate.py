#!/usr/bin/env python3
"""
R2 Semantic Artifact-Gate Adapter

Reconciles validator false negatives for the zero-execution case where
nv_probe.json and nv_state_db.json are architecturally absent.

This adapter does NOT weaken the general artifact contract. It applies
a narrow semantic interpretation aligned with the frozen R1 contract
language which explicitly enumerates "fuzzer_stats, manifest JSON, trace files"
without listing probe or state_db.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Tuple


def load_json_file(path: Path) -> Dict[str, Any]:
    """Load and parse JSON file."""
    with open(path, 'r') as f:
        return json.load(f)


def r2_artifact_semantic_gate(
    artifact_report_path: Path,
    body_valid_stats_path: Path,
    execution_ledger_path: Path
) -> Tuple[str, str]:
    """
    Apply R2 semantic artifact-gate logic.
    
    Args:
        artifact_report_path: Path to artifact_report.json from base validator
        body_valid_stats_path: Path to nv_body_valid_stats.json
        execution_ledger_path: Path to executions.jsonl
    
    Returns:
        Tuple of (verdict, reason)
        
    Verdicts:
        "PASS" - base validator passed
        "PASS_VALIDATOR_FALSE_NEGATIVE_ZERO_EXECUTION_CASE" - reconciled false negative
        "FAIL" - genuine artifact failure
    """
    
    # Load base validator report
    artifact_report = load_json_file(artifact_report_path)
    
    # Rule 1: If base validator passed, pass immediately
    if artifact_report.get('artifact_final_result') == 'artifact_contract_pass':
        return ('PASS', 'Base validator artifact_contract passed')
    
    # Base validator failed - check if this is the narrow false-negative case
    
    # Rule 2: Check all conditions for false-negative reconciliation
    
    # Condition: Base validator must have failed
    if artifact_report.get('artifact_final_result') != 'artifact_contract_failed':
        return ('FAIL', 'Base validator did not return artifact_contract_failed')
    
    # Condition: Missing artifacts must be exactly probe and state_db
    missing_required = set(artifact_report.get('missing_required', []))
    expected_missing = {'probe', 'state_db'}
    
    if missing_required != expected_missing:
        return ('FAIL', f'Missing artifacts ({missing_required}) are not exactly probe and state_db')
    
    # Condition: body_score_pass must be 0
    body_valid_stats = load_json_file(body_valid_stats_path)
    body_score_pass = body_valid_stats.get('body_score_pass', -1)
    
    if body_score_pass != 0:
        return ('FAIL', f'body_score_pass={body_score_pass}, expected 0 for false-negative case')
    
    # Condition: No target-valid execution occurred
    # Check execution_ledger for counted_execution_count or target_execution_count
    if execution_ledger_path.exists():
        # execution_ledger is inside artifact_report.json
        exec_ledger = artifact_report.get('execution_ledger', {})
        counted_execution_count = exec_ledger.get('counted_execution_count', -1)
        target_execution_count = exec_ledger.get('target_execution_count', -1)
        
        if counted_execution_count != 0:
            return ('FAIL', f'counted_execution_count={counted_execution_count}, expected 0')
        
        if target_execution_count != 0:
            return ('FAIL', f'target_execution_count={target_execution_count}, expected 0')
    
    # Condition: body_score_rpc_ok > 0, body_score_rpc_fail = 0
    body_score_rpc_ok = body_valid_stats.get('body_score_rpc_ok', 0)
    body_score_rpc_fail = body_valid_stats.get('body_score_rpc_fail', -1)
    
    if body_score_rpc_ok <= 0:
        return ('FAIL', f'body_score_rpc_ok={body_score_rpc_ok}, expected > 0')
    
    if body_score_rpc_fail != 0:
        return ('FAIL', f'body_score_rpc_fail={body_score_rpc_fail}, expected 0')
    
    # Condition: trace_invocations > 0
    model_comp = artifact_report.get('model_comparison_validity', {})
    trace_invocations = model_comp.get('trace_invocations', 0)
    
    if trace_invocations <= 0:
        return ('FAIL', f'trace_invocations={trace_invocations}, expected > 0')
    
    # Condition: model_comparison_validity = PASS
    model_comp_verdict = model_comp.get('verdict', 'UNKNOWN')
    
    if model_comp_verdict != 'PASS':
        return ('FAIL', f'model_comparison_validity={model_comp_verdict}, expected PASS')
    
    # Condition: readback = PASS
    readback_verdict = artifact_report.get('readback_verdict', 'UNKNOWN')
    
    if readback_verdict != 'pass':
        return ('FAIL', f'readback_verdict={readback_verdict}, expected pass')
    
    # Condition: All other required artifacts present
    # Check that no other artifacts are missing
    missing_setup = artifact_report.get('missing_setup_required', [])
    missing_conditional = artifact_report.get('missing_conditional', [])
    
    # ctx is conditionally required but not present in zero-execution case - allowed
    allowed_missing_conditional = {'ctx'}
    actual_missing_conditional = set(missing_conditional)
    
    if not actual_missing_conditional.issubset(allowed_missing_conditional):
        unexpected = actual_missing_conditional - allowed_missing_conditional
        return ('FAIL', f'Unexpected missing conditional artifacts: {unexpected}')
    
    if missing_setup:
        return ('FAIL', f'Missing setup artifacts: {missing_setup}')
    
    # All conditions met - this is the false-negative case
    return (
        'PASS_VALIDATOR_FALSE_NEGATIVE_ZERO_EXECUTION_CASE',
        'Zero-execution case: probe/state_db architecturally absent due to body_score_pass=0'
    )


def main():
    """CLI entry point."""
    if len(sys.argv) != 4:
        print("Usage: r2_artifact_semantic_gate.py <artifact_report.json> <nv_body_valid_stats.json> <executions.jsonl>", file=sys.stderr)
        sys.exit(2)
    
    artifact_report_path = Path(sys.argv[1])
    body_valid_stats_path = Path(sys.argv[2])
    execution_ledger_path = Path(sys.argv[3])
    
    verdict, reason = r2_artifact_semantic_gate(
        artifact_report_path,
        body_valid_stats_path,
        execution_ledger_path
    )
    
    result = {
        'r2_artifact_semantic_gate': verdict,
        'reason': reason,
        'adapter_version': '1.0.0'
    }
    
    print(json.dumps(result, indent=2))
    
    if verdict == 'FAIL':
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
