"""Offline P2 blocker-repair contracts for deterministic test infrastructure."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "run_deep2fuzz_tests.py"
SPEC = importlib.util.spec_from_file_location("deep2fuzz_test_runner", RUNNER_PATH)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _manifest(members: list[str]) -> dict:
    return {"schema_version": 1, "groups": {"mini": {"members": sorted(members)}}}


def _result(node: str, status: str, attempt: int = 1) -> dict:
    return {
        "node_id": node,
        "terminal_status": status,
        "duration": 0.001,
        "attempt": attempt,
    }


def test_t01_timing_report_schema() -> None:
    report = runner.build_timing_report("unit", 2, 2, 0, 1.25, ["a", "b"])
    assert set(("group", "tests", "passed", "failed", "duration_seconds", "slowest")) <= set(report)
    assert report["duration_seconds"] == 1.25


def test_t02_group_manifest_deterministic() -> None:
    assert runner.load_manifest() == runner.load_manifest()


def test_t03_logical_gate_projection_deterministic() -> None:
    members = runner.load_manifest()["groups"]["combined-227"]["members"]
    results = [_result(node, "PASS") for node in members]
    first = runner.project_gates(runner.load_manifest(), "combined-227", results, collection_status="PASS")
    second = runner.project_gates(runner.load_manifest(), "combined-227", results, collection_status="PASS")
    assert first == second
    assert first["verdict"] == "PASS"


def test_t04_duplicate_physical_execution_detection() -> None:
    manifest = runner.load_manifest()
    phase1 = set(manifest["groups"]["phase1"]["members"])
    required = set(manifest["groups"]["required-74"]["members"])
    combined = set(manifest["groups"]["combined-227"]["members"])
    assert phase1 <= required
    assert phase1 <= combined
    assert phase1 & required
    assert all(node in combined for node in phase1 & combined)


def test_t05_generated_artifact_excluded_from_source_identity() -> None:
    manifest = runner.load_manifest()
    assert all("egg-info" not in path for path in manifest["source_excludes"])
    assert "deep2fuzz_es.egg-info" in manifest["generated_excludes"]


def test_t06_temp_roots_isolated(tmp_path: Path) -> None:
    a = runner.new_temp_root(tmp_path, "a")
    b = runner.new_temp_root(tmp_path, "b")
    assert a != b and a.parent == b.parent


def test_t07_filesystem_ordering_stable(tmp_path: Path) -> None:
    for name in ("z", "a", "m"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    assert runner.sorted_entries(tmp_path) == ["a", "m", "z"]


def test_t08_seeded_randomness_deterministic() -> None:
    assert runner.seeded_sequence(7, 5) == runner.seeded_sequence(7, 5)
    assert runner.seeded_sequence(7, 5) != runner.seeded_sequence(8, 5)


def test_t09_timezone_independent_result() -> None:
    assert runner.utc_timestamp(0) == "1970-01-01T00:00:00Z"


def test_t10_locale_independent_result() -> None:
    assert runner.stable_sort(["b", "A", "a"]) == ["A", "a", "b"]


def test_t11_timeout_uses_monotonic_clock() -> None:
    assert runner.deadline_clock_name() == "monotonic"


def test_t12_timeout_diagnostic_contains_elapsed_deadline() -> None:
    data = runner.timeout_diagnostic("case", 1.2, 1.0, "exited", "Authorization: hidden")
    assert data["test_id"] == "case"
    assert data["elapsed_seconds"] == 1.2
    assert data["deadline_seconds"] == 1.0
    assert "hidden" not in data["stderr"]


def test_t13_no_unbounded_polling() -> None:
    assert runner.poll_until(lambda: True, deadline_seconds=0.1, interval_seconds=0.001)


def test_t14_cleanup_leaves_no_orphan_process() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    assert runner.finish_process(proc, deadline_seconds=2) == "exited"
    assert proc.poll() == 0


def test_t15_ephemeral_port_allocation_works() -> None:
    with runner.ephemeral_listener() as sock:
        assert sock.getsockname()[1] > 0


def test_t16_retry_disabled_by_default() -> None:
    assert runner.DEFAULT_RETRY == 0


def test_t17_first_pass_is_acceptance_verdict() -> None:
    report = runner.record_attempts([{"attempt": 1, "result": "PASS"}])
    assert report["acceptance"]["status"] == "PASS"
    assert report["final_acceptance_status"] == "PASS"


def test_t18_first_failure_is_preserved_without_rerun() -> None:
    report = runner.record_attempts([{"attempt": 1, "result": "FAIL"}])
    assert report["acceptance"]["status"] == "FAIL"
    assert report["final_acceptance_status"] == "FAIL"


def test_t19_first_failure_cannot_be_erased_by_diagnostic_pass() -> None:
    report = runner.record_attempts([
        {"attempt": 1, "result": "FAIL"},
        {"attempt": 2, "result": "PASS"},
    ])
    assert report["acceptance"]["status"] == "FAIL"
    assert report["diagnostic_reruns"] == [{"attempt": 2, "status": "PASS"}]
    assert report["final_acceptance_status"] == "FAIL"
    assert report["flaky_observed"] is True


def test_t20_first_failure_stays_failed_after_failed_diagnostic() -> None:
    report = runner.record_attempts([
        {"attempt": 1, "result": "FAIL"},
        {"attempt": 2, "result": "FAIL"},
    ])
    assert report["final_acceptance_status"] == "FAIL"
    assert report["flaky_observed"] is False


def test_t21_error_is_not_erased_by_diagnostic_pass() -> None:
    report = runner.record_attempts([
        {"attempt": 1, "result": "ERROR"},
        {"attempt": 2, "result": "PASS"},
    ])
    assert report["final_acceptance_status"] == "ERROR"
    assert report["flaky_observed"] is True


def test_t22_missing_diagnostic_result_preserves_original() -> None:
    report = runner.record_attempts([{"attempt": 1, "result": "FAIL"}, {}])
    assert report["final_acceptance_status"] == "FAIL"
    assert report["diagnostic_reruns"][0]["status"] == "ERROR"


def test_t23_retry_never_masks_failure() -> None:
    assert runner.retry_masks_failure(["FAIL", "PASS"]) is False
    assert runner.retry_masks_failure(["ERROR", "PASS"]) is False
    assert runner.retry_masks_failure(["PASS"]) is False


def test_t24_repeat_stability_surfaces_late_failure() -> None:
    stability = runner.repeat_stability([
        {"acceptance_status": "PASS"},
        {"acceptance_status": "FAIL"},
        {"acceptance_status": "PASS"},
    ])
    assert stability["repeat_stable"] is False
    assert stability["repeat_failed_attempts"] == [2]


def test_t25_fast_gate_is_not_acceptance_authority() -> None:
    assert runner.load_manifest()["fast_gate_acceptance_authority"] is False


def test_t26_required_gate_exact_membership() -> None:
    group = runner.load_manifest()["groups"]["required-74"]
    assert len(group["members"]) == 74
    assert group["members"] == sorted(group["members"])
    assert len(set(group["members"])) == 74


def test_t27_combined_gate_exact_membership() -> None:
    group = runner.load_manifest()["groups"]["combined-227"]
    assert len(group["members"]) == 227
    assert group["members"] == sorted(group["members"])
    assert len(set(group["members"])) == 227


def test_t28_frozen_offline_gate_authority_is_unchanged() -> None:
    group = runner.load_manifest()["groups"]["frozen-offline"]
    assert group["files"]
    assert group["pytest_args"] == ["-k", "not test_filter_by_task_name"]
    assert group["expected_tests"] == 235


def test_t29_repeat_runner_produces_stable_summary() -> None:
    summary = runner.repeat_summary([{"duration_seconds": 1.0, "result": "PASS"}] * 2)
    assert summary["runs"] == 2
    assert summary["durations"] == [1.0, 1.0]
    assert summary["final_acceptance_status"] == "PASS"
    assert summary["repeat_stable"] is True


def test_t30_critical_repeat_targets_are_explicit() -> None:
    targets = runner.critical_repeat_groups()
    assert targets["p1_1b_cleanup"].endswith("tests/test_phase1_1b_cleanup_fail_closed.py")
    assert targets["p1_3_provenance"].endswith("tests/test_deep2fuzz_provenance.py")
    assert targets["p1_4_cli"].endswith("tests/test_phase2_p1_4_cli_consistency.py")


def test_t31_source_config_evidence_semantics_unchanged() -> None:
    invariance = runner.load_manifest()["invariance"]
    assert all(invariance.values())


def test_t31_projection_missing_member_fails_closed() -> None:
    node_a, node_b = "tests/mini.py::test_a", "tests/mini.py::test_b"
    projection = runner.project_gates(
        _manifest([node_a, node_b]), "mini", [_result(node_a, "PASS")],
        collection_status="PASS",
    )
    assert projection["verdict"] == "FAIL"
    assert projection["missing_members"] == [node_b]


def test_t32_projection_failed_member_fails_closed() -> None:
    node = "tests/mini.py::test_a"
    projection = runner.project_gates(_manifest([node]), "mini", [_result(node, "FAIL")], collection_status="PASS")
    assert projection["verdict"] == "FAIL"
    assert projection["failed_members"] == [node]


def test_t33_projection_error_member_fails_closed() -> None:
    node = "tests/mini.py::test_a"
    projection = runner.project_gates(_manifest([node]), "mini", [_result(node, "ERROR")], collection_status="PASS")
    assert projection["verdict"] == "FAIL"
    assert projection["error_members"] == [node]


def test_t34_projection_deselection_fails_closed() -> None:
    node = "tests/mini.py::test_a"
    projection = runner.project_gates(_manifest([node]), "mini", [_result(node, "PASS")], collection_status="PASS", deselected=[node])
    assert projection["verdict"] == "FAIL"
    assert projection["deselected_members"] == [node]


def test_t35_projection_unknown_member_fails_closed() -> None:
    node, unknown = "tests/mini.py::test_a", "tests/mini.py::test_unknown"
    projection = runner.project_gates(_manifest([node]), "mini", [_result(unknown, "PASS")], collection_status="PASS")
    assert projection["verdict"] == "FAIL"
    assert projection["unexpected_members"] == [unknown]
    assert projection["missing_members"] == [node]


def test_t36_projection_same_status_duplicate_fails_closed() -> None:
    node = "tests/mini.py::test_a"
    projection = runner.project_gates(_manifest([node]), "mini", [_result(node, "PASS"), _result(node, "PASS")], collection_status="PASS")
    assert projection["verdict"] == "FAIL"
    assert projection["duplicate_members"] == [node]


def test_t37_projection_conflicting_duplicate_fails_closed() -> None:
    node = "tests/mini.py::test_a"
    projection = runner.project_gates(_manifest([node]), "mini", [_result(node, "PASS"), _result(node, "FAIL")], collection_status="PASS")
    assert projection["verdict"] == "FAIL"
    assert projection["conflicting_duplicate_members"] == [node]


def test_t38_projection_collection_failure_fails_closed() -> None:
    node = "tests/mini.py::test_a"
    projection = runner.project_gates(_manifest([node]), "mini", [_result(node, "PASS")], collection_status="ERROR", collection_errors=["mini.py"])
    assert projection["verdict"] == "FAIL"
    assert projection["collection_errors"] == ["mini.py"]


def test_t39_projection_malformed_physical_result_fails_closed() -> None:
    node = "tests/mini.py::test_a"
    projection = runner.project_gates(_manifest([node]), "mini", [None, _result(node, "PASS")], collection_status="PASS")
    assert projection["verdict"] == "FAIL"
    assert projection["malformed_result_indexes"] == [0]


def test_t40_malformed_node_membership_is_rejected() -> None:
    with pytest.raises(runner.ManifestError):
        runner._validate_members("mini", ["tests/mini.py"])


def test_t41_duplicate_manifest_node_id_is_rejected() -> None:
    node = "tests/mini.py::test_a"
    with pytest.raises(runner.ManifestError):
        runner._validate_members("mini", [node, node])


def test_t42_uncollectable_node_id_is_rejected_by_real_pytest(tmp_path: Path) -> None:
    with pytest.raises(runner.ManifestError):
        runner._collect_declared_nodes([str(tmp_path / "missing_test.py") + "::test_missing"])


def test_t43_same_count_different_membership_fails() -> None:
    expected = ["tests/mini.py::test_a", "tests/mini.py::test_b"]
    actual = [_result(expected[0], "PASS"), _result("tests/mini.py::test_replaced", "PASS")]
    projection = runner.project_gates(_manifest(expected), "mini", actual, collection_status="PASS")
    assert projection["verdict"] == "FAIL"
    assert projection["missing_members"] == [expected[1]]
    assert projection["unexpected_members"] == ["tests/mini.py::test_replaced"]


@pytest.mark.parametrize(
    ("body", "expected_status"),
    [
        ("def test_pass(): pass\n", "PASS"),
        ("def test_fail(): assert False\n", "FAIL"),
        ("import pytest\n@pytest.fixture\ndef broken(): raise RuntimeError('boom')\ndef test_error(broken): pass\n", "ERROR"),
    ],
)
def test_t44_real_pytest_capture_statuses(tmp_path: Path, body: str, expected_status: str) -> None:
    path = tmp_path / "test_mini.py"
    path.write_text(body, encoding="utf-8")
    payload = runner._capture_pytest([str(path)], cwd=tmp_path)
    assert payload["results"][0]["terminal_status"] == expected_status
    assert payload["returncode"] != 0 if expected_status != "PASS" else payload["returncode"] == 0


def test_t45_collection_failure_is_reported_by_real_capture(tmp_path: Path) -> None:
    path = tmp_path / "test_mini.py"
    path.write_text("def test_broken(:\n    pass\n", encoding="utf-8")
    payload = runner._capture_pytest([str(path)], cwd=tmp_path)
    assert payload["collection_status"] == "ERROR"
    assert payload["returncode"] != 0


def test_t46_projection_does_not_synthesize_results() -> None:
    node = "tests/mini.py::test_a"
    projection = runner.project_gates(_manifest([node]), "mini", [], collection_status="PASS")
    assert projection["logical_projection_synthesizes_test_result"] is False
    assert projection["verdict"] == "FAIL"


def test_t47_runner_reports_independent_repeats_and_fails_on_late_failure(monkeypatch, capsys) -> None:
    manifest = {"schema_version": 1, "groups": {"mini": {"members": ["tests/mini.py::test_case"]}}}
    reports = iter([
        {"acceptance_status": "PASS", "duration_seconds": 0.1, "tests": 1, "passed": 1, "failed": 0},
        {"acceptance_status": "FAIL", "duration_seconds": 0.2, "tests": 1, "passed": 0, "failed": 1},
    ])
    monkeypatch.setattr(runner, "load_manifest", lambda **_kwargs: manifest)
    monkeypatch.setattr(runner, "run_group", lambda *_args, **_kwargs: next(reports))

    result = runner.main(["--group", "mini", "--repeat", "2", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert result == 1
    assert payload["first_attempt_acceptance"]["acceptance_status"] == "PASS"
    assert payload["retry_semantics"]["final_acceptance_status"] == "PASS"
    assert payload["diagnostic_reruns"] == []
    assert len(payload["independent_repeats"]) == 1
    assert payload["repeat_stability"]["repeat_failed_attempts"] == [2]


@pytest.mark.parametrize(
    ("body", "expected_status", "expected_returncode"),
    [
        ("def test_case(): pass\n", "PASS", 0),
        ("def test_case(): assert False\n", "FAIL", 1),
    ],
)
def test_t48_runner_executes_exact_temp_suite_fail_closed(
    tmp_path: Path, monkeypatch, capsys, body: str, expected_status: str, expected_returncode: int
) -> None:
    root = tmp_path
    test_file = root / "test_mini.py"
    test_file.write_text(body, encoding="utf-8")
    node = "test_mini.py::test_case"
    manifest_path = root / "groups.json"
    manifest_path.write_text(json.dumps({"schema_version": 1, "groups": {"mini": {"members": [node], "expected_tests": 1}}}), encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(runner, "FORMAL_GROUPS", frozenset({"mini"}))

    result = runner.main(["--group", "mini", "--json", "--timeout", "30"])
    payload = json.loads(capsys.readouterr().out)
    first = payload["first_attempt_acceptance"]
    assert result == expected_returncode
    assert first["acceptance_status"] == expected_status
    assert first["logical_gate_projection"]["executed_members"] == [node]
    assert first["logical_gate_projection"]["verdict"] == expected_status


def test_t49_runner_collection_error_returns_input_error(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path
    test_file = root / "test_mini.py"
    test_file.write_text("def test_broken(:\n pass\n", encoding="utf-8")
    node = "test_mini.py::test_case"
    manifest_path = root / "groups.json"
    manifest_path.write_text(json.dumps({"schema_version": 1, "groups": {"mini": {"members": [node], "expected_tests": 1}}}), encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(runner, "FORMAL_GROUPS", frozenset({"mini"}))

    result = runner.main(["--group", "mini", "--json", "--timeout", "30"])
    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["runner_status"] == "ERROR"
    assert "pytest collection failed" in payload["error"]


def test_t50_historical_timeout_target_is_explicit() -> None:
    target = runner.critical_repeat_groups()["historical_timeout"]
    assert "::test_full_core_mock_reconciliation" in target
