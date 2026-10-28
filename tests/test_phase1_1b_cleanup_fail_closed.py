from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

from integration.platforms.abort import write_abort_marker
from integration.platforms.base import CleanupResult
from integration.platforms.mock_rest.service import MockRestService
from integration.platforms.mock_rest import target


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "deep2fuzz"


def _run(root: Path, scenario: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env.pop(name, None)
    return subprocess.run(
        [sys.executable, str(CLI), "platform", "run", "mock_rest", "--scenario", scenario,
         "--evidence-root", str(root)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )


def test_abort_marker_is_atomic_sanitized_and_identity_bound(tmp_path: Path, monkeypatch) -> None:
    marker_path = tmp_path / "control" / "abort.json"
    identity = {"task_id": "task-a", "run_id": "run-a", "exec_seq": 7,
                "seed_id": "seed-0123456789ab", "mutation_arm": "arm-1"}
    original_replace = os.replace
    replace_observations: list[tuple[bool, bool]] = []

    def observe_replace(source, destination):
        staged = json.loads(Path(source).read_text(encoding="utf-8"))
        replace_observations.append((not Path(destination).exists(), staged["terminal"] is True))
        return original_replace(source, destination)

    monkeypatch.setattr("integration.platforms.abort.os.replace", observe_replace)
    result = write_abort_marker(marker_path, identity, object_id="item-sensitive")

    assert replace_observations == [(True, True)]
    assert json.loads(marker_path.read_text(encoding="utf-8")) == result
    assert result["reason"] == "CLEANUP_FAILED"
    assert {key: result[key] for key in identity} == identity
    assert "item-sensitive" not in marker_path.read_text(encoding="utf-8")
    assert "object_id_sha256" in result
    assert not {"password", "token", "cookie", "authorization", "response_body"} & set(result)


def test_next_target_invocation_observes_abort_before_adapter_or_http(tmp_path: Path, monkeypatch) -> None:
    marker_path = tmp_path / "control" / "abort.json"
    write_abort_marker(marker_path, {
        "task_id": "task-race", "run_id": "run-race", "exec_seq": 1,
        "seed_id": "seed-0123456789ab", "mutation_arm": "arm-0",
    })
    observations = tmp_path / "abort_observations.jsonl"
    monkeypatch.setenv("DEEP2FUZZ_ABORT_MARKER", str(marker_path))
    monkeypatch.setenv("DEEP2FUZZ_ABORT_OBSERVATIONS", str(observations))
    monkeypatch.setattr(target, "_read_input", mock.Mock(side_effect=AssertionError("input read after abort")))
    monkeypatch.setattr(target, "MockRestAdapter", mock.Mock(side_effect=AssertionError("adapter created after abort")))
    monkeypatch.setattr(sys, "argv", [str(ROOT / "integration/platforms/mock_rest/target.py"), "/missing"])

    with MockRestService() as service:
        assert target.main() == 0
        assert service.request_count == 0
        assert service.object_creation_count == 0

    rows = [json.loads(line) for line in observations.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"terminal": True, "reason": "CLEANUP_FAILED", "action": "platform_contact_skipped"}]


def test_race_window_after_cleanup_failure_has_zero_platform_contact(tmp_path: Path, monkeypatch) -> None:
    marker_path = tmp_path / "control" / "abort.json"
    monkeypatch.setenv("DEEP2FUZZ_ABORT_MARKER", str(marker_path))
    monkeypatch.delenv("DEEP2FUZZ_SUPERVISOR_PID", raising=False)
    monkeypatch.setenv("DEEP2FUZZ_TASK_ID", "task-race")
    monkeypatch.setenv("DEEP2FUZZ_RUN_ID", "run-race")
    monkeypatch.setenv("DEEP2FUZZ_SEED_ID", "seed-0123456789ab")
    monkeypatch.setenv("NV_CUR_ARM", "1")
    monkeypatch.setenv("NV_STATUS_PATH", str(tmp_path / "status.json"))
    monkeypatch.setenv("NV_STATUS_LEDGER_PATH", str(tmp_path / "status.jsonl"))
    monkeypatch.setenv("NV_PROBE_PATH", str(tmp_path / "probe.json"))
    monkeypatch.setenv("NV_STATE_DB", str(tmp_path / "state.json"))
    monkeypatch.setenv("DEEP2FUZZ_ADAPTER_EVENTS", str(tmp_path / "adapter_events.jsonl"))
    raw = b"POST /api/items HTTP/1.1\nContent-Type: application/json\n\n{\"title\":\"race\"}"
    monkeypatch.setattr(target, "_read_input", lambda: raw)
    monkeypatch.setattr(sys, "argv", [str(ROOT / "integration/platforms/mock_rest/target.py"), "seed.http"])

    original_adapter = target.MockRestAdapter

    class CleanupFailureAdapter:
        def __init__(self, config):
            self.delegate = original_adapter(config)

        def __getattr__(self, name):
            return getattr(self.delegate, name)

        def cleanup(self, object_id, identity):
            return CleanupResult(identity, False, object_id=object_id, error_kind="delete_failed", safe_message="cleanup failed")

    monkeypatch.setattr(target, "MockRestAdapter", CleanupFailureAdapter)
    with MockRestService() as service:
        monkeypatch.setenv("DEEP2FUZZ_MOCK_URL", service.base_url)
        assert target.main() == 1
        marker_after_failure = marker_path.read_bytes()
        requests_after_failure = service.request_count
        creations_after_failure = service.object_creation_count
        # This is the race window: the supervisor has not acted yet.
        assert target.main() == 0
        assert service.request_count == requests_after_failure
        assert service.object_creation_count == creations_after_failure
    assert marker_path.read_bytes() == marker_after_failure
    events = [json.loads(line) for line in (tmp_path / "adapter_events.jsonl").read_text().splitlines()]
    assert len(events) == 1
    assert events[0]["cleanup"] is False


def test_cleanup_failure_stops_campaign_preserves_evidence_and_exits_nonzero(tmp_path: Path) -> None:
    evidence = tmp_path / "cleanup_failure"
    result = _run(evidence, "cleanup_failure")
    assert result.returncode != 0
    summary = json.loads(result.stdout)
    assert summary["passed"] is False
    assert summary["terminal_reason"] == "CLEANUP_FAILED"
    assert summary["CLEANUP_FAILURE_DETECTED"] == "PASS"
    assert summary["ABORT_MARKER_WRITTEN"] == "PASS"
    assert summary["ABORT_MARKER_ATOMIC"] == "PASS"
    assert summary["POST_CLEANUP_FAILURE_PLATFORM_EXECUTIONS"] == 0
    assert summary["POST_CLEANUP_FAILURE_OBJECT_CREATIONS"] == 0
    assert summary["POST_ABORT_FALSE_MAB_PULLS"] == 0
    assert summary["POST_ABORT_FALSE_MAB_COMMITS"] == 0
    assert summary["POST_ABORT_FALSE_SEED_CREDIT"] == 0
    assert summary["POST_ABORT_FALSE_STATE_UPDATES"] == 0
    assert summary["AFL_CAMPAIGN_TERMINATED"] == "PASS"
    assert summary["AFL_SAVED_CRASHES"] == 0
    assert summary["PARTIAL_EVIDENCE_PRESERVED"] == "PASS"
    assert summary["termination_escalation_used"] is False

    marker = json.loads((evidence / "control" / "abort.json").read_text(encoding="utf-8"))
    run_status = json.loads((evidence / "run_status.json").read_text(encoding="utf-8"))
    termination = json.loads((evidence / "supervisor_termination.json").read_text(encoding="utf-8"))
    assert marker["terminal"] is True and marker["reason"] == "CLEANUP_FAILED"
    assert marker["task_id"] == "phase1-1-mock" and marker["run_id"] == evidence.name
    assert marker["exec_seq"] > 0
    assert run_status["run_complete"] is False
    assert run_status["terminal"] is True
    assert run_status["terminal_reason"] == "CLEANUP_FAILED"
    assert termination["abort_detected_at"]
    assert termination["termination_requested_at"]
    assert termination["process_exited_at"]
    assert termination["termination_escalation_used"] is False

    for rel in (
        "afl_console.log", "fuzzer_stats", "eval_report.json",
        "evidence/adapter_events.jsonl", "evidence/status.jsonl",
        "evidence/executions.jsonl", "evidence/mab_updates.jsonl",
        "evidence/seed_selection.jsonl", "evidence/state.jsonl",
    ):
        assert (evidence / rel).is_file(), rel
    events = [json.loads(line) for line in (evidence / "evidence/adapter_events.jsonl").read_text().splitlines() if line]
    assert events and events[-1]["cleanup"] is False
    assert events[-1]["identity"]["exec_seq"] == marker["exec_seq"]
    for rel in (
        "eval_report.json", "identity_reconciliation.json", "formal_security_score.json",
        "core_mock_summary.json", "run_status.json", "supervisor_termination.json",
    ):
        json.loads((evidence / rel).read_text(encoding="utf-8"))
    for rel in (
        "evidence/adapter_events.jsonl", "evidence/status.jsonl",
        "evidence/executions.jsonl", "evidence/mab_updates.jsonl",
        "evidence/seed_selection.jsonl", "evidence/state.jsonl",
    ):
        rows = [line for line in (evidence / rel).read_text(encoding="utf-8").splitlines() if line]
        assert rows, rel
        for line in rows:
            json.loads(line)


def test_success_path_still_completes_with_exact_seed_credit(tmp_path: Path) -> None:
    evidence = tmp_path / "success"
    result = _run(evidence, "success")
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["passed"] is True
    assert summary["security_state_seed_credit"] == 1
    assert summary["EXECUTION_IDENTITY_RECONCILIATION"] == "PASS"
    assert summary["MAB_ATTRIBUTION_RECONCILIATION"] == "PASS"
    assert summary["REPORT_ACCOUNTING_RECONCILIATION"] == "PASS"
    assert summary["CLEANUP_RECONCILIATION"] == "PASS"
    assert not (evidence / "control" / "abort.json").exists()


def test_existing_negative_paths_remain_nonterminal_business_outcomes(tmp_path: Path) -> None:
    for scenario in ("validity_rejection", "expected_rejection", "semantic_failure"):
        evidence = tmp_path / scenario
        result = _run(evidence, scenario)
        assert result.returncode == 0, (scenario, result.stderr)
        summary = json.loads(result.stdout)
        assert summary["passed"] is True, scenario
        assert not (evidence / "control" / "abort.json").exists(), scenario


def test_post_abort_mab_pull_count_comes_from_mab_journal(tmp_path: Path, monkeypatch) -> None:
    from integration.platforms import core_runner

    run = core_runner._run_afl_supervised

    def inject_post_abort_update(command, env, cwd, output_path, abort_path, service):
        result = run(command, env, cwd, output_path, abort_path, service)
        assert result[1] is not None
        marker_seq = int(result[1]["marker"]["exec_seq"])
        journal = output_path.parent / "evidence" / "mab_updates.jsonl"
        with journal.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "mab_update", "exec_seq": marker_seq + 1}) + "\n")
        return result

    monkeypatch.setattr(core_runner, "_run_afl_supervised", inject_post_abort_update)
    summary = core_runner.run_core_mock(tmp_path / "post_abort_mab", scenario="cleanup_failure")

    assert summary["POST_ABORT_FALSE_MAB_PULLS"] == 1
    assert summary["POST_ABORT_FALSE_MAB_COMMITS"] == 1
