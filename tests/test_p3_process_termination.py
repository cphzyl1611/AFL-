"""Behavior-level repair tests; all real processes are harmless local fixtures."""
from __future__ import annotations

import ast
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

import deep2fuzz_cli
import deep2fuzz_portability as portability
from integration.platforms import core_runner

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests' / 'helpers' / 'p3_process_tree_fixture.py'


def _tree(case, tmp_path):
    path = tmp_path / (case + '.json')
    run = subprocess.run([sys.executable, str(FIXTURE), case, str(path)],
                         text=True, encoding='utf-8', capture_output=True, timeout=12,
                         env=portability.stable_environment(), check=False)
    assert run.returncode == 0, run.stderr
    result = json.loads(path.read_text(encoding='utf-8'))
    assert result['orphan_count'] == 0, result
    assert all(not Path(f'/proc/{node["pid"]}').exists() for node in result['nodes']), result
    return result


def test_t01_actual_parent_child_forced_termination(tmp_path):
    result = _tree('forced', tmp_path)
    assert result['returned_success'] and result['escalated'], result
    assert result['live_after_api'] == [], result


def test_t02_actual_grandchild_termination(tmp_path):
    result = _tree('grandchild', tmp_path)
    assert len(result['nodes']) == 3
    assert result['returned_success'] and result['live_after_api'] == [], result


def test_t03_graceful_group_without_force(tmp_path):
    result = _tree('graceful', tmp_path)
    assert result['returned_success'] and result['escalated'] is False, result
    assert result['live_after_api'] == [], result


def test_t04_parent_exit_does_not_hide_resistant_child(tmp_path):
    result = _tree('leader_exits', tmp_path)
    assert result['returned_success'] and result['escalated'], result
    assert result['live_after_api'] == [], result


def test_t05_parent_only_kill_cannot_report_success(tmp_path):
    result = _tree('parent_only_bug', tmp_path)
    assert result['returned_success'] is False and result['caller_verdict'] == 'FAIL', result
    assert result['error_type'] == 'TerminationError', result
    assert result['live_after_api'], result


def test_t06_live_descendant_forces_bounded_error(tmp_path):
    result = _tree('force_ineffective', tmp_path)
    assert result['returned_success'] is False and result['error_type'] == 'TerminationError', result
    assert result['elapsed_seconds'] < 1.5, result


def test_t07_windows_resolver_to_termination_to_failure(tmp_path):
    result = _tree('windows', tmp_path)
    assert not result['returned_success'] and result['error_type'] == 'UnsupportedCapability', result
    assert len(result['live_after_api']) == 2, result


def test_t08_missing_signal_cannot_fallback_to_parent(tmp_path):
    result = _tree('missing_signal', tmp_path)
    assert not result['returned_success'] and result['error_type'] == 'UnsupportedCapability', result
    assert len(result['live_after_api']) == 2, result


def test_t09_cli_unsupported_before_process_or_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(portability.platform_module, 'system', lambda: 'Windows')
    output = tmp_path / 'not-created'
    def forbidden(*args, **kwargs):
        pytest.fail('unsupported termination capability entered execution')
    monkeypatch.setattr(core_runner, '_run_afl_supervised', forbidden)
    assert deep2fuzz_cli.main(['platform', 'run', 'mock_rest', '--evidence-root', str(output)]) == 1
    assert not output.exists()
    captured = capsys.readouterr()
    assert 'RUNTIME_FAILURE' in captured.err and not captured.out


def test_t10_assertion_failure_still_reaps_fixture(tmp_path):
    result = _tree('cleanup_assertion', tmp_path)
    assert result['error_type'] == 'AssertionError'
    assert result['orphan_count'] == 0


def test_t11_forced_wait_has_observed_bound(tmp_path):
    result = _tree('forced', tmp_path)
    assert result['returned_success'] and result['elapsed_seconds'] < 1.5, result


def test_t12_no_unbounded_wait_in_termination():
    source = ast.parse((ROOT / 'deep2fuzz_portability.py').read_text(encoding='utf-8'))
    calls = [node for node in ast.walk(source) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == 'wait']
    assert all(any(kw.arg == 'timeout' for kw in call.keywords) for call in calls)


def test_t13_polling_uses_monotonic_deadline():
    import inspect
    source = inspect.getsource(portability._wait_scope_quiescent)
    assert 'time.monotonic()' in source and 'deadline' in source
    assert 'min(' in source and 'time.sleep(' in source


def test_t14_detached_descendant_session_is_still_managed(tmp_path):
    result = _tree('detached', tmp_path)
    assert result['nodes'][1]['sid'] != result['nodes'][0]['sid']
    assert result['returned_success'] and not result['live_after_api'], result


def test_t15_missing_group_capability_runtime_chain(tmp_path, monkeypatch, capsys):
    monkeypatch.delattr(portability.os, 'killpg')
    output = tmp_path / 'missing-group'
    assert deep2fuzz_cli.main(['platform', 'run', 'mock_rest', '--evidence-root', str(output)]) == 1
    assert not output.exists()
    assert 'RUNTIME_FAILURE' in capsys.readouterr().err


def test_t16_windows_native_claim_remains_absent():
    text = (ROOT / 'docs' / 'DEEP2FUZZ_PLATFORM_ADAPTER_SYSTEM.md').read_text(encoding='utf-8')
    assert 'Native Windows' in text and 'unverified' in text


def test_t17_formal_gate_membership_matches_baseline():
    baseline = json.loads(subprocess.check_output(['git', '-C', str(ROOT), 'show',
        '0b82f1168ff04359424dee9fec1a2bd399362d04:tests/test_groups.json']))
    current = json.loads((ROOT / 'tests' / 'test_groups.json').read_text(encoding='utf-8'))
    for name, spec in baseline['groups'].items():
        assert current['groups'][name] == spec


def test_t18_historical_limitation_remains():
    text = (ROOT / 'docs' / 'DEEP2FUZZ_PLATFORM_ADAPTER_SYSTEM.md').read_text(encoding='utf-8')
    assert '18/20' in text and 'root cause remains unresolved' in text


def test_t19_scientific_contract_files_unchanged():
    for name in ('scripts/compute_formal_security_score.py', 'nv_json_mutator.py',
                 'deep2fuzz_config/validator.py', 'deep2fuzz_provenance.py'):
        baseline = subprocess.check_output(['git', '-C', str(ROOT), 'show',
            '0b82f1168ff04359424dee9fec1a2bd399362d04:' + name])
        assert (ROOT / name).read_bytes() == baseline


def test_t20_success_summary_needs_entire_tree_quiescent(tmp_path):
    result = _tree('grandchild', tmp_path)
    assert result['returned_success']
    assert len(result['states_after_api']) == 3 and not result['live_after_api']


def test_t21_shared_caller_group_is_never_signalled(tmp_path):
    result = _tree('unisolated', tmp_path)
    assert not result['returned_success'] and result['error_type'] == 'UnsupportedCapability', result
    assert len(result['live_after_api']) == 2, result


@pytest.mark.parametrize('value', [-1, math.inf, math.nan])
def test_t22_invalid_wait_budget_fails_before_signalling(value):
    class NoSignalProcess:
        pid = os.getpid()
        def poll(self):
            return None
    with pytest.raises(ValueError):
        portability.terminate_process(NoSignalProcess(), grace_seconds=value)


def test_t23_no_external_helper_required_with_empty_path(tmp_path, monkeypatch):
    monkeypatch.setenv('PATH', str(tmp_path / 'no-tools'))
    result = _tree('forced', tmp_path)
    assert result['returned_success'] and not result['live_after_api'], result


def test_t24_unreadable_scope_fails_before_execution(tmp_path, monkeypatch, capsys):
    def denied(path):
        raise PermissionError('fixture cannot inspect processes')
    monkeypatch.setattr(portability, '_read_process_record', denied)
    output = tmp_path / 'no-inspection'
    assert deep2fuzz_cli.main(['platform', 'run', 'mock_rest', '--evidence-root', str(output)]) == 1
    assert not output.exists()
    assert 'RUNTIME_FAILURE' in capsys.readouterr().err


def test_t25_missing_sigterm_fails_before_execution(tmp_path, monkeypatch, capsys):
    monkeypatch.delattr(portability.signal, 'SIGTERM')
    output = tmp_path / 'no-sigterm'
    assert deep2fuzz_cli.main(['platform', 'run', 'mock_rest', '--evidence-root', str(output)]) == 1
    assert not output.exists()
    assert 'RUNTIME_FAILURE' in capsys.readouterr().err


def test_t26_denied_group_signal_cannot_report_success(tmp_path):
    result = _tree('signal_denied', tmp_path)
    assert not result['returned_success'] and result['error_type'] == 'TerminationError', result
    assert len(result['live_after_api']) == 2, result


def test_t27_scan_deadline_is_not_a_success_or_inspection_error(monkeypatch):
    def deadline(*args):
        raise portability._InspectionDeadline('phase budget exhausted')
    class Running:
        def poll(self):
            return None
    monkeypatch.setattr(portability, '_refresh_scope', deadline)
    import time
    assert portability._wait_scope_quiescent(
        Running(), {}, set(), set(), time.monotonic() + 1, signal.SIGTERM) is False
