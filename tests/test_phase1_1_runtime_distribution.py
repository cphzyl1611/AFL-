from __future__ import annotations

import json
import os
import subprocess
import sys
import venv
from pathlib import Path
import setuptools


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "deep2fuzz"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.pop("HTTP_PROXY", None)
    merged.pop("HTTPS_PROXY", None)
    merged.pop("ALL_PROXY", None)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def test_version_is_single_source_and_help_is_available() -> None:
    help_result = _run("--help")
    version_result = _run("--version")
    assert help_result.returncode == 0, help_result.stderr
    assert "deep2fuzz" in help_result.stdout
    assert version_result.returncode == 0, version_result.stderr
    assert version_result.stdout.strip() == "1.1.0rc2"


def test_fresh_editable_install_and_installed_cli(tmp_path: Path) -> None:
    env_root = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(env_root)
    python = env_root / "bin" / "python"
    env = os.environ.copy()
    env["PIP_NO_INDEX"] = "1"
    env["PYTHONPATH"] = str(Path(setuptools.__file__).resolve().parent.parent)
    installed = subprocess.run(
        [str(python), "-m", "pip", "install", "--no-index", "--no-deps", "--no-build-isolation", "-e", str(ROOT)],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    command = env_root / "bin" / "deep2fuzz"
    # The build helper needs the cached setuptools path above, but the
    # installed CLI must be checked in a clean environment so optional model
    # packages from the host test runner cannot leak into the fresh venv.
    clean_env = env.copy()
    clean_env["PYTHONPATH"] = ""
    for args, expected in ((["--help"], "usage: deep2fuzz"), (["--version"], "1.1.0rc2"), (["platform", "list"], "mock_rest")):
        result = subprocess.run([str(command), *args], env=clean_env, text=True, capture_output=True, check=False)
        assert result.returncode == 0, result.stderr
        assert expected in result.stdout
    doctor = subprocess.run([str(command), "doctor"], env=clean_env, text=True, capture_output=True, check=False)
    payload = json.loads(doctor.stdout)
    assert payload["package_install"] is True
    assert payload["repo_runtime_root"] == str(ROOT)
    assert payload["MODEL_BACKEND_READY"] is False
    assert payload["optional_model_stack_imported"] is False


def test_optional_dependency_errors_name_the_extra(capsys) -> None:
    from deep2fuzz_cli import _check_extra

    assert _check_extra("live", lambda _name: None) == 2
    live_error = capsys.readouterr().err
    assert "MISSING_OPTIONAL_DEPENDENCY" in live_error
    assert "pip install -e '.[live]'" in live_error
    assert _check_extra("model", lambda _name: None) == 2
    model_error = capsys.readouterr().err
    assert "pip install -e '.[model]'" in model_error


def test_mutation_identity_headers_are_opt_in(monkeypatch) -> None:
    from nv_json_mutator import afl_custom_fuzz

    source = b"POST /api/items HTTP/1.1\nContent-Type: application/json\n\n{}"
    monkeypatch.delenv("DEEP2FUZZ_CORE_ADAPTER_BRIDGE", raising=False)
    ordinary = bytes(afl_custom_fuzz(None, source, b"", 4096))
    assert b"X-Deep2Fuzz-" not in ordinary

    monkeypatch.setenv("DEEP2FUZZ_CORE_ADAPTER_BRIDGE", "1")
    monkeypatch.setenv("DEEP2FUZZ_SEED_ID", "seed-0123456789ab")
    monkeypatch.setenv("NV_CUR_ARM", "1")
    bridged = bytes(afl_custom_fuzz(None, source, b"", 4096))
    assert b"X-Deep2Fuzz-Seed-ID: seed-0123456789ab" in bridged
    assert b"X-Deep2Fuzz-Mutation-Arm: arm-1" in bridged


def test_platform_list_and_doctor_are_offline_safe() -> None:
    listed = _run("platform", "list")
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.splitlines() == ["mock_rest"]

    doctor = _run("doctor")
    assert doctor.returncode == 0, doctor.stderr
    payload = json.loads(doctor.stdout)
    assert payload["LIVE_PLATFORM_READY"] is False
    assert payload["LIVE_PLATFORM_PROBED"] is False
    assert payload["optional_model_stack_imported"] is False
    assert payload["PLUGIN_READY"] is True
    assert "repo_root" in payload
    assert "core_imports" in payload


def test_full_core_mock_reconciliation(tmp_path: Path) -> None:
    evidence = tmp_path / "phase1_1"
    result = _run("platform", "run", "mock_rest", "--evidence-root", str(evidence))
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["passed"] is True
    assert summary["real_platform_contacted"] is False
    assert summary["external_network_contacted"] is False
    for key in (
        "EXECUTION_IDENTITY_RECONCILIATION",
        "STATE_ACCOUNTING_RECONCILIATION",
        "MAB_ATTRIBUTION_RECONCILIATION",
        "SEED_ACCOUNTING_RECONCILIATION",
        "REPORT_ACCOUNTING_RECONCILIATION",
        "CLEANUP_RECONCILIATION",
    ):
        assert summary[key] == "PASS"
    assert (evidence / "fuzzer_stats").is_file()
    assert (evidence / "eval_report.json").is_file()
    assert (evidence / "formal_security_score.json").is_file()
    reconciliation = json.loads((evidence / "identity_reconciliation.json").read_text())
    assert reconciliation["join_key"] == "exec_seq"
    assert reconciliation["identity"]["exec_seq"] > 0
    assert all(reconciliation["checks"].values())
    assert summary["security_state_seed_credit"] > 0
    assert reconciliation["identity"]["mutation_arm"] == "arm-1"
    assert (evidence / "evidence" / "mab_updates.jsonl").is_file()
    assert (evidence / "evidence" / "executions.jsonl").is_file()
    assert (evidence / "evidence" / "seed_selection.jsonl").is_file()
    events = [json.loads(line) for line in (evidence / "evidence" / "adapter_events.jsonl").read_text().splitlines() if line]
    assert events
    assert all(row["created_object_id"] == row["cleanup_object_id"] and row["absence_verified"] for row in events)
    assert all(row["identity"]["seed_id"] == reconciliation["identity"]["seed_id"] for row in events)


def test_report_identity_mismatch_fails_core_identity_reconciliation(tmp_path: Path, monkeypatch) -> None:
    from integration.platforms import core_runner

    run = core_runner._run_afl_supervised

    def corrupt_report_identity(command, env, cwd, output_path, abort_path, service):
        result = run(command, env, cwd, output_path, abort_path, service)
        report_path = output_path.parent / "eval_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["security_state_cov"]["security_state_reward_src_seq"] = 999999
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return result

    monkeypatch.setattr(core_runner, "_run_afl_supervised", corrupt_report_identity)
    summary = core_runner.run_core_mock(tmp_path / "identity_mismatch")

    assert summary["EXECUTION_IDENTITY_RECONCILIATION"] == "FAIL"
    assert summary["REPORT_ACCOUNTING_RECONCILIATION"] == "FAIL"
    assert summary["passed"] is False


def _run_scenario(tmp_path: Path, scenario: str) -> tuple[dict, Path]:
    evidence = tmp_path / scenario
    result = _run("platform", "run", "mock_rest", "--scenario", scenario, "--evidence-root", str(evidence))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    return payload, evidence


def test_validity_rejection_has_no_target_execution_or_accounting(tmp_path: Path) -> None:
    summary, evidence = _run_scenario(tmp_path, "validity_rejection")
    assert summary["validity_rejected"] > 0
    assert summary["requests"] == 0
    assert summary["nv_err_exec"] == 0
    assert summary["security_state_seed_credit"] == 0
    assert summary["CLEANUP_RECONCILIATION"] == "PASS"
    assert summary["MAB_ATTRIBUTION_RECONCILIATION"] == "PASS"
    assert summary["REPORT_ACCOUNTING_RECONCILIATION"] == "PASS"
    assert not [line for line in (evidence / "evidence" / "mab_updates.jsonl").read_text().splitlines() if '"event":"mab_update"' in line]
    events = [json.loads(line) for line in (evidence / "evidence" / "adapter_events.jsonl").read_text().splitlines() if line]
    assert events and all(row["created_object_id"] is None for row in events)


def test_expected_http_rejection_is_not_err_and_is_attributed(tmp_path: Path) -> None:
    summary, evidence = _run_scenario(tmp_path, "expected_rejection")
    assert summary["nv_err_exec"] == 0
    assert summary["nv_rec_total"] == 0
    assert summary["EXECUTION_IDENTITY_RECONCILIATION"] == "PASS"
    assert summary["MAB_ATTRIBUTION_RECONCILIATION"] == "PASS"
    assert summary["REPORT_ACCOUNTING_RECONCILIATION"] == "PASS"
    events = [json.loads(line) for line in (evidence / "evidence" / "adapter_events.jsonl").read_text().splitlines() if line]
    assert any(row["result"]["expected_rejection"] and not row["result"]["semantic_failure"] for row in events)


def test_success_status_with_readback_mismatch_is_err_and_cleanup_still_exact(tmp_path: Path) -> None:
    summary, evidence = _run_scenario(tmp_path, "semantic_failure")
    assert summary["nv_err_exec"] > 0
    assert summary["nv_rec_total"] > 0
    assert summary["CLEANUP_RECONCILIATION"] == "PASS"
    assert summary["EXECUTION_IDENTITY_RECONCILIATION"] == "PASS"
    assert summary["MAB_ATTRIBUTION_RECONCILIATION"] == "PASS"
    assert summary["REPORT_ACCOUNTING_RECONCILIATION"] == "PASS"
    statuses = [json.loads(line) for line in (evidence / "evidence" / "status.jsonl").read_text().splitlines() if line]
    assert any(row["is_exception"] and 200 <= row["http_code"] < 300 for row in statuses)
