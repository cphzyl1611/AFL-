from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows), encoding="utf-8")


def _stats(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "execs_done": 1,
        "nv_execution_iteration": 1,
        "nv_enable_validity": 1,
        "nv_valid_cnt": 1,
        "nv_invalid_cnt": 0,
        "nv_invalid_rate": 0.0,
        "nv_total_valid_exec": 1,
        "nv_err_exec": 0,
        "nv_err_rate": 0.0,
        "nv_rec_total": 0,
        "nv_rec_success": 0,
        "nv_mab_total_pulls": 1,
        "nv_mab_arm0_pulls": 1,
        "nv_mab_arm1_pulls": 0,
        "nv_mab_arm2_pulls": 0,
        "nv_mab_journal_record_count": 1,
        "security_state_total": 1,
        "security_state_new_total": 1,
        "security_state_capacity": 16,
        "security_state_observations": 1,
        "security_state_seed_credit": 1,
        "security_state_reward_src_seq": 1,
        "ss_cov_cnt": 1,
        "ss_selected_cnt": 1,
        "ss_cov_sum": 1,
        "ss_selected_sum": 1,
    }
    values.update(overrides)
    return values


def _write_stats(path: Path, values: dict[str, object]) -> None:
    path.write_text("".join(f"{key} : {value}\n" for key, value in values.items()), encoding="utf-8")


def make_platform_run(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    seed = b"POST /api/items HTTP/1.1\n\n{}\n"
    (root / "seeds").mkdir()
    (root / "seeds" / "seed_0.http").write_bytes(seed)
    seed_id = "seed-" + hashlib.sha256(seed).hexdigest()[:12]
    task_id, run_id, seq, arm = "fixture-task", root.name, 1, "arm-0"

    stats = _stats()
    _write_stats(root / "fuzzer_stats", stats)
    score_stats = dict(stats, recovery_opportunity_count=0, recovery_success_count=0)
    _write_stats(root / "formal_score_stats.txt", score_stats)

    status = {
        "task_id": task_id, "run_id": run_id, "exec_seq": seq, "seed_id": seed_id,
        "mutation_arm": arm, "method": "POST", "path": "/api/items", "class": "2xx",
        "http_code": 201, "is_exception": False,
    }
    execution = {
        "event": "execution", "exec_seq": seq, "selected_arm": 0, "actual_used_arm": 0,
        "arm_match": True, "target_invoked": True, "status_observed": True,
        "mab_outcome": "committed_update",
    }
    state = {"exec_seq": seq, "state": "POST /api/items|2xx", "new": 1, "state_id": "state-1"}
    mab = {"event": "mab_update", "exec_seq": seq, "selected_arm": 0, "actual_used_arm": 0,
           "arm_match": True, "reward": 1.0, "reward_components": {"security_state_new": 1}}
    identity = {"task_id": task_id, "run_id": run_id, "exec_seq": seq,
                "seed_id": seed_id, "mutation_arm": arm}
    adapter = {"identity": identity, "created_object_id": "fixture-object-1",
               "cleanup_object_id": "fixture-object-1", "cleanup": True, "absence_verified": True,
               "result": {"http_code": 201, "expected_rejection": False,
                          "semantic_failure": False, "business_success": True}}
    evidence = root / "evidence"
    _write_jsonl(evidence / "status.jsonl", [status])
    _write_jsonl(evidence / "executions.jsonl", [execution])
    _write_jsonl(evidence / "state.jsonl", [state])
    _write_jsonl(evidence / "mab_updates.jsonl", [mab])
    _write_jsonl(evidence / "seed_selection.jsonl", [{"queue_id": 0, "ss_cov_cnt": 1, "ss_selected_cnt": 1}])
    _write_jsonl(evidence / "adapter_events.jsonl", [adapter])

    from scripts.compute_formal_security_score import FormalScoreConfig, compute_from_stats

    score, provenance = compute_from_stats(root / "formal_score_stats.txt", FormalScoreConfig(1 / 3, 1 / 3, 1 / 3))
    report = {
        "task": {"enable_validity": 1},
        "validity": {"valid_cnt": 1, "invalid_cnt": 0, "invalid_rate": 0.0},
        "exec": {"total_execs": 1, "valid_exec": 1},
        "security_state_cov": {
            "security_state_total": 1, "security_state_new_total": 1,
            "security_state_capacity": 16, "security_state_observations": 1,
            "security_state_seed_credit": 1, "security_state_reward_src_seq": seq,
        },
        "err": {"err_exec": 0, "err_rate": 0.0},
        "rec": {"rec_total": 0, "rec_success": 0, "recovery_opportunity_count": 0,
                "recovery_success_count": 0, "rec_rate": None, "rec_avg_ms": 0.0},
        "mab": {"total_pulls": 1, "arms": [{"arm": 0, "pulls": 1},
                                                {"arm": 1, "pulls": 0}, {"arm": 2, "pulls": 0}]},
        "mab_journal": {"record_count": 1, "audit_invalid": 0, "error_count": 0},
        "formal_security_score": score,
        "formal_score_provenance": provenance,
    }
    _write_json(root / "eval_report.json", report)
    _write_json(root / "formal_security_score.json", {"formal_security_score": score, "provenance": provenance})
    checks = {name: True for name in (
        "status_identity", "adapter_to_status", "execution_ledger_to_status", "state_to_status",
        "mab_arm_to_status", "seed_accounting", "report_to_reward_source",
    )}
    _write_json(root / "identity_reconciliation.json", {
        "schema_version": 1, "join_key": "exec_seq", "checks": checks,
        "status_rows": 1, "adapter_events": 1, "execution_rows": 1,
        "state_rows": 1, "mab_updates": 1, "report_reward_source_exec_seq": seq,
        "identity": identity,
    })
    _write_json(root / "core_mock_summary.json", {
        "passed": True, "scenario": "success", "validity_enabled": True,
        "validity_rejected": 0, "security_state_seed_credit": 1,
        "EXECUTION_IDENTITY_RECONCILIATION": "PASS",
        "STATE_ACCOUNTING_RECONCILIATION": "PASS", "MAB_ATTRIBUTION_RECONCILIATION": "PASS",
        "SEED_ACCOUNTING_RECONCILIATION": "PASS", "REPORT_ACCOUNTING_RECONCILIATION": "PASS",
        "CLEANUP_RECONCILIATION": "PASS",
    })
    return root


def make_validity_rejection_run(root: Path) -> Path:
    root = make_platform_run(root)
    from scripts.compute_formal_security_score import FormalScoreConfig, compute_from_stats

    values = _stats(
        nv_valid_cnt=0, nv_invalid_cnt=1, nv_total_valid_exec=0,
        nv_execution_iteration=1, nv_invalid_rate=1.0,
        nv_err_exec=0, nv_err_rate=0.0, nv_mab_total_pulls=0,
        nv_mab_arm0_pulls=0, nv_mab_arm1_pulls=0, nv_mab_arm2_pulls=0,
        nv_mab_journal_record_count=0, security_state_total=0,
        security_state_new_total=0, security_state_observations=0,
        security_state_seed_credit=0, security_state_reward_src_seq=0,
        ss_cov_cnt=0, ss_selected_cnt=0, ss_cov_sum=0, ss_selected_sum=1,
    )
    _write_stats(root / "fuzzer_stats", values)
    _write_stats(root / "formal_score_stats.txt", dict(
        values, recovery_opportunity_count=0, recovery_success_count=0
    ))
    for name in ("status.jsonl", "state.jsonl", "adapter_events.jsonl", "mab_updates.jsonl"):
        _write_jsonl(root / "evidence" / name, [])
    _write_jsonl(root / "evidence/executions.jsonl", [{
        "event": "execution", "exec_seq": None, "selected_arm": 0,
        "actual_used_arm": 0, "arm_match": True, "target_invoked": False,
        "status_observed": False, "mab_outcome": "body_validation_reject",
    }])
    report = json.loads((root / "eval_report.json").read_text())
    report["validity"].update({"valid_cnt": 0, "invalid_cnt": 1, "invalid_rate": 1.0})
    report["exec"]["valid_exec"] = 0
    report["security_state_cov"].update({
        "security_state_total": 0, "security_state_new_total": 0,
        "security_state_observations": 0, "security_state_seed_credit": 0,
        "security_state_reward_src_seq": 0,
    })
    report["err"].update({"err_exec": 0, "err_rate": 0.0})
    report["mab"].update({"total_pulls": 0, "arms": [
        {"arm": 0, "pulls": 0}, {"arm": 1, "pulls": 0}, {"arm": 2, "pulls": 0},
    ]})
    report["mab_journal"]["record_count"] = 0
    score, provenance = compute_from_stats(
        root / "formal_score_stats.txt", FormalScoreConfig(1 / 3, 1 / 3, 1 / 3)
    )
    report["formal_security_score"] = score
    report["formal_score_provenance"] = provenance
    _write_json(root / "eval_report.json", report)
    _write_json(root / "formal_security_score.json", {
        "formal_security_score": score, "provenance": provenance,
    })
    _write_json(root / "identity_reconciliation.json", {
        "checks": {
            "status_identity": "NOT_APPLICABLE", "adapter_to_status": "NOT_APPLICABLE",
            "execution_ledger_to_status": "NOT_APPLICABLE", "state_to_status": "NOT_APPLICABLE",
            "mab_arm_to_status": "NOT_APPLICABLE", "seed_accounting": True,
            "report_to_reward_source": True,
        },
        "report_reward_source_exec_seq": 0,
    })
    summary = json.loads((root / "core_mock_summary.json").read_text())
    summary.update({"passed": True, "scenario": "validity_rejection", "requests": 0,
                    "validity_enabled": True, "validity_rejected": 1,
                    "security_state_seed_credit": 0})
    _write_json(root / "core_mock_summary.json", summary)
    return root


def _verify(root: Path):
    from deep2fuzz_evidence.verifier import verify_evidence

    return verify_evidence(root)


def _check(result, name: str) -> str:
    return next(item["status"] for item in result.to_dict()["checks"] if item["name"] == name)


def test_valid_platform_run_passes_without_mutation(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    before = {p.relative_to(root): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}

    result = _verify(root)

    after = {p.relative_to(root): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    assert result.to_dict()["verdict"] == "PASS"
    assert result.to_dict()["profile"] == "platform-run"
    assert before == after
    for check in ("EXECUTION_IDENTITY_RECONCILIATION", "VALIDITY_ACCOUNTING_RECONCILIATION",
                  "MAB_ATTRIBUTION_RECONCILIATION", "SEED_ACCOUNTING_RECONCILIATION",
                  "COV_ACCOUNTING_RECONCILIATION", "ERR_ACCOUNTING_RECONCILIATION",
                  "REC_NULL_POLICY", "OVERALL_SCORE_RECONCILIATION", "CLEANUP_RECONCILIATION"):
        assert _check(result, check) == "PASS"


def test_missing_contract_artifact_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    (root / "eval_report.json").unlink()
    result = _verify(root).to_dict()
    assert result["verdict"] == "FAIL"
    assert result["profile"] == "platform-run"
    required = next(check for check in result["checks"] if check["name"] == "REQUIRED_ARTIFACTS")
    assert required["status"] == "FAIL"


def test_malformed_json_fails_without_crash(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    (root / "eval_report.json").write_text("{broken", encoding="utf-8")
    result = _verify(root).to_dict()
    assert result["verdict"] == "FAIL"
    assert _check(_verify(root), "JSON_PARSE_VALIDATION") == "FAIL"


def test_contract_json_requires_object_top_level(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    _write_json(root / "eval_report.json", [])
    result = _verify(root)
    assert result.to_dict()["verdict"] == "FAIL"
    assert _check(result, "JSON_PARSE_VALIDATION") == "FAIL"


def test_nested_shape_errors_fail_without_crashing(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    report = json.loads((root / "eval_report.json").read_text())
    report.update({"task": [], "validity": "invalid", "exec": None,
                   "security_state_cov": [], "formal_score_provenance": "invalid"})
    _write_json(root / "eval_report.json", report)
    result = _verify(root)
    assert result.to_dict()["verdict"] == "FAIL"


def test_nested_identity_shape_errors_fail_without_crashing(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    identity = json.loads((root / "identity_reconciliation.json").read_text())
    identity["checks"] = []
    _write_json(root / "identity_reconciliation.json", identity)
    result = _verify(root)
    assert result.to_dict()["verdict"] == "FAIL"
    assert _check(result, "JSON_SCHEMA_VALIDATION") == "FAIL"


def test_unhashable_seed_identity_fails_without_crashing(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    status_path = root / "evidence/status.jsonl"
    status = json.loads(status_path.read_text())
    status["seed_id"] = {"unexpected": "object"}
    _write_jsonl(status_path, [status])
    result = _verify(root)
    assert result.to_dict()["verdict"] == "FAIL"
    assert _check(result, "SEED_ACCOUNTING_RECONCILIATION") == "FAIL"


def test_unhashable_state_identity_fails_without_crashing(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    state_path = root / "evidence/state.jsonl"
    state = json.loads(state_path.read_text())
    state["state_id"] = {"unexpected": "object"}
    _write_jsonl(state_path, [state])
    result = _verify(root)
    assert result.to_dict()["verdict"] == "FAIL"


def test_sha256_mismatch_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    (root / "SHA256SUMS.txt").write_text("0" * 64 + "  eval_report.json\n", encoding="utf-8")
    assert _check(_verify(root), "SHA256_MANIFEST") == "FAIL"


def test_malformed_sha256_manifest_row_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    (root / "SHA256SUMS.txt").write_text("not-a-hash  eval_report.json\n", encoding="utf-8")
    assert _check(_verify(root), "SHA256_MANIFEST") == "FAIL"


def test_conflicting_duplicate_sha256_entries_fail(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    (root / "SHA256SUMS.txt").write_text(
        "0" * 64 + "  eval_report.json\n" + "1" * 64 + "  eval_report.json\n",
        encoding="utf-8",
    )
    assert _check(_verify(root), "SHA256_MANIFEST") == "FAIL"


def test_execution_identity_mismatch_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    status_path = root / "evidence/status.jsonl"
    row = json.loads(status_path.read_text())
    row["run_id"] = "other-run"
    _write_jsonl(status_path, [row])
    assert _check(_verify(root), "EXECUTION_IDENTITY_RECONCILIATION") == "FAIL"


def test_duplicate_status_exec_seq_fails_identity_reconciliation(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    status_path = root / "evidence/status.jsonl"
    row = json.loads(status_path.read_text())
    _write_jsonl(status_path, [row, row])
    assert _check(_verify(root), "EXECUTION_IDENTITY_RECONCILIATION") == "FAIL"


def test_orphan_mab_commit_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    row = json.loads((root / "evidence/mab_updates.jsonl").read_text())
    row["exec_seq"] = 99
    _write_jsonl(root / "evidence/mab_updates.jsonl", [row])
    assert _check(_verify(root), "MAB_ATTRIBUTION_RECONCILIATION") == "FAIL"


def test_duplicate_mab_commit_for_execution_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    mab_path = root / "evidence/mab_updates.jsonl"
    row = json.loads(mab_path.read_text())
    _write_jsonl(mab_path, [row, row])
    assert _check(_verify(root), "MAB_ATTRIBUTION_RECONCILIATION") == "FAIL"


def test_mab_pull_counts_must_match_attributed_journal_commits(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    _write_stats(root / "fuzzer_stats", _stats(nv_mab_arm0_pulls=0))
    assert _check(_verify(root), "MAB_ATTRIBUTION_RECONCILIATION") == "FAIL"


def test_execution_identity_allows_multiple_selected_seeds(tmp_path: Path) -> None:
    from deep2fuzz_evidence.verifier import VerificationResult, _platform_identity

    root = tmp_path / "run"
    task_id, run_id = "fixture-task", root.name
    identities = [
        {"task_id": task_id, "run_id": run_id, "exec_seq": seq,
         "seed_id": f"seed-{seq}", "mutation_arm": f"arm-{seq - 1}"}
        for seq in (1, 2)
    ]
    statuses = [dict(identity, method="POST", path=f"/items/{seq}", **{"class": "2xx"})
                for seq, identity in enumerate(identities, 1)]
    rows = {
        "evidence/status.jsonl": statuses,
        "evidence/executions.jsonl": [
            {"event": "execution", "exec_seq": seq, "selected_arm": seq - 1,
             "actual_used_arm": seq - 1, "arm_match": True, "target_invoked": True,
             "status_observed": True}
            for seq in (1, 2)
        ],
        "evidence/state.jsonl": [
            {"exec_seq": seq, "state": f"POST /items/{seq}|2xx", "new": 0}
            for seq in (1, 2)
        ],
        "evidence/adapter_events.jsonl": [{"identity": identity} for identity in identities],
        "evidence/mab_updates.jsonl": [
            {"event": "mab_update", "exec_seq": seq, "selected_arm": seq - 1,
             "actual_used_arm": seq - 1, "arm_match": True}
            for seq in (1, 2)
        ],
    }
    checks = {name: True for name in (
        "status_identity", "adapter_to_status", "execution_ledger_to_status", "state_to_status",
        "mab_arm_to_status", "seed_accounting", "report_to_reward_source",
    )}
    parsed = {
        "identity_reconciliation.json": {"checks": checks, "identity": identities[0]},
        "eval_report.json": {"security_state_cov": {"security_state_reward_src_seq": 1}},
        "core_mock_summary.json": {"scenario": "success"},
    }
    stats = {"fuzzer_stats": {
        "nv_mab_total_pulls": "2", "nv_mab_arm0_pulls": "1",
        "nv_mab_arm1_pulls": "1", "nv_mab_arm2_pulls": "0",
    }}
    result = VerificationResult("platform-run")

    _platform_identity(result, parsed, stats, rows, root)

    assert _check(result, "EXECUTION_IDENTITY_RECONCILIATION") == "PASS"
    assert _check(result, "MAB_ATTRIBUTION_RECONCILIATION") == "PASS"


def test_state_identity_mismatch_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    row = json.loads((root / "evidence/state.jsonl").read_text())
    row["state"] = "GET /wrong|2xx"
    _write_jsonl(root / "evidence/state.jsonl", [row])
    assert _check(_verify(root), "EXECUTION_IDENTITY_RECONCILIATION") == "FAIL"


def test_false_seed_credit_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    stats = _stats(security_state_seed_credit=2)
    _write_stats(root / "fuzzer_stats", stats)
    assert _check(_verify(root), "SEED_ACCOUNTING_RECONCILIATION") == "FAIL"


def test_candidate_counts_must_match_validity_accounting(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    _write_stats(root / "fuzzer_stats", _stats(nv_execution_iteration=2))
    assert _check(_verify(root), "VALIDITY_ACCOUNTING_RECONCILIATION") == "FAIL"


def test_seed_credit_without_execution_attribution_fails(tmp_path: Path) -> None:
    from deep2fuzz_evidence.verifier import VerificationResult, _platform_seed

    root = make_platform_run(tmp_path / "run")
    from deep2fuzz_evidence.verifier import _jsonl_load

    rows = {
        "evidence/status.jsonl": [],
        "evidence/adapter_events.jsonl": [],
        "evidence/seed_selection.jsonl": _jsonl_load(root / "evidence/seed_selection.jsonl"),
    }
    parsed = {"eval_report.json": {"security_state_cov": {"security_state_seed_credit": 1}}}
    stats = {"fuzzer_stats": _stats()}
    result = VerificationResult("platform-run")

    _platform_seed(result, root, parsed, stats, rows)

    assert _check(result, "SEED_ACCOUNTING_RECONCILIATION") == "FAIL"


def test_seed_accounting_accepts_multiple_selected_seed_identities(tmp_path: Path) -> None:
    from deep2fuzz_evidence.verifier import VerificationResult, _jsonl_load, _platform_seed

    root = make_platform_run(tmp_path / "run")
    second_seed = b"PUT /api/items/2 HTTP/1.1\n\n{}\n"
    (root / "seeds/seed_1.http").write_bytes(second_seed)
    second_seed_id = "seed-" + hashlib.sha256(second_seed).hexdigest()[:12]
    status = _jsonl_load(root / "evidence/status.jsonl")
    status.append(dict(status[0], exec_seq=2, seed_id=second_seed_id))
    events = _jsonl_load(root / "evidence/adapter_events.jsonl")
    events.append(dict(events[0], identity=dict(events[0]["identity"], exec_seq=2, seed_id=second_seed_id)))
    rows = {
        "evidence/status.jsonl": status,
        "evidence/adapter_events.jsonl": events,
        "evidence/seed_selection.jsonl": _jsonl_load(root / "evidence/seed_selection.jsonl") + [{
            "queue_id": 1, "ss_cov_cnt": 1, "ss_selected_cnt": 1,
        }],
    }
    parsed = {"eval_report.json": {"security_state_cov": {"security_state_seed_credit": 1}}}
    stats = {"fuzzer_stats": _stats(ss_selected_sum=2)}
    result = VerificationResult("platform-run")

    _platform_seed(result, root, parsed, stats, rows)

    assert _check(result, "SEED_ACCOUNTING_RECONCILIATION") == "PASS"


def test_cov_counter_inconsistency_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    _write_stats(root / "fuzzer_stats", _stats(security_state_new_total=17))
    assert _check(_verify(root), "COV_ACCOUNTING_RECONCILIATION") == "FAIL"


def test_duplicate_new_state_identity_fails_cov_accounting(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    state = json.loads((root / "evidence/state.jsonl").read_text())
    duplicate = dict(state, exec_seq=2)
    _write_jsonl(root / "evidence/state.jsonl", [state, duplicate])
    assert _check(_verify(root), "STATE_ACCOUNTING_RECONCILIATION") == "FAIL"


def test_err_counter_inconsistency_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    _write_stats(root / "fuzzer_stats", _stats(nv_err_exec=1, nv_err_rate=0.0))
    assert _check(_verify(root), "ERR_ACCOUNTING_RECONCILIATION") == "FAIL"


def test_expected_rejection_and_semantic_failure_are_classified_by_existing_status(tmp_path: Path) -> None:
    from integration.platforms.core_runner import run_core_mock

    expected_root = Path(run_core_mock(tmp_path / "expected", scenario="expected_rejection")["evidence_root"])
    semantic_root = Path(run_core_mock(tmp_path / "semantic", scenario="semantic_failure")["evidence_root"])
    assert _verify(expected_root).to_dict()["verdict"] == "PASS"
    assert _verify(semantic_root).to_dict()["verdict"] == "PASS"


def test_expected_rejection_is_not_counted_as_err(tmp_path: Path) -> None:
    from deep2fuzz_evidence.verifier import _stats_load
    from integration.platforms.core_runner import run_core_mock

    root = Path(run_core_mock(tmp_path / "expected", scenario="expected_rejection")["evidence_root"])
    values = _stats_load(root / "fuzzer_stats")
    denominator = int(values["nv_total_valid_exec"])
    values["nv_err_exec"] = "1"
    values["nv_err_rate"] = str(1 / denominator)
    _write_stats(root / "fuzzer_stats", values)
    report = json.loads((root / "eval_report.json").read_text())
    report["err"].update({"err_exec": 1, "err_rate": 1 / denominator})
    _write_json(root / "eval_report.json", report)

    assert _check(_verify(root), "ERR_ACCOUNTING_RECONCILIATION") == "FAIL"


def test_validity_rejection_cannot_have_state_observation_ledger(tmp_path: Path) -> None:
    from integration.platforms.core_runner import run_core_mock

    root = Path(run_core_mock(tmp_path / "validity", scenario="validity_rejection")["evidence_root"])
    _write_jsonl(root / "evidence/state.jsonl", [
        {"exec_seq": 1, "state": "POST /api/items|2xx", "state_id": "state-1", "new": 0}
    ])
    assert _check(_verify(root), "VALIDITY_ACCOUNTING_RECONCILIATION") == "FAIL"


def test_validity_rejection_without_target_or_state_activity_passes(tmp_path: Path) -> None:
    root = make_validity_rejection_run(tmp_path / "run")
    result = _verify(root)
    assert result.to_dict()["verdict"] == "PASS"
    assert _check(result, "VALIDITY_ACCOUNTING_RECONCILIATION") == "PASS"


def test_no_recovery_opportunity_requires_null_rec_and_overall(tmp_path: Path) -> None:
    result = _verify(make_platform_run(tmp_path / "run"))
    assert _check(result, "REC_NULL_POLICY") == "PASS"
    assert _check(result, "OVERALL_SCORE_RECONCILIATION") == "PASS"


def test_zero_recovery_opportunities_with_zero_rec_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    report = json.loads((root / "eval_report.json").read_text())
    report["rec"]["rec_rate"] = 0.0
    _write_json(root / "eval_report.json", report)
    assert _check(_verify(root), "REC_NULL_POLICY") == "FAIL"


@pytest.mark.parametrize("value", ["missing", "null", "NaN"])
def test_rec_null_policy_rejects_missing_string_null_and_nan(tmp_path: Path, value: str) -> None:
    root = make_platform_run(tmp_path / "run")
    report = json.loads((root / "eval_report.json").read_text())
    if value == "missing":
        del report["rec"]["rec_rate"]
    elif value == "null":
        report["rec"]["rec_rate"] = "null"
    else:
        (root / "eval_report.json").write_text(
            json.dumps(report).replace('"rec_rate": null', '"rec_rate": NaN'), encoding="utf-8"
        )
        assert _check(_verify(root), "JSON_PARSE_VALIDATION") == "FAIL"
        return
    _write_json(root / "eval_report.json", report)
    assert _check(_verify(root), "REC_NULL_POLICY") == "FAIL"


def test_real_recovery_opportunity_with_no_success_has_zero_rec(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    stats = _stats()
    _write_stats(root / "fuzzer_stats", stats)
    _write_stats(root / "formal_score_stats.txt", dict(stats, recovery_opportunity_count=1,
                                                        recovery_success_count=0))
    from scripts.compute_formal_security_score import FormalScoreConfig, compute_from_stats

    score, provenance = compute_from_stats(root / "formal_score_stats.txt", FormalScoreConfig(1 / 3, 1 / 3, 1 / 3))
    report = json.loads((root / "eval_report.json").read_text())
    report["rec"].update({"recovery_opportunity_count": 1, "recovery_success_count": 0, "rec_rate": 0.0})
    report["formal_security_score"] = score
    report["formal_score_provenance"] = provenance
    _write_json(root / "eval_report.json", report)
    _write_json(root / "formal_security_score.json", {"formal_security_score": score, "provenance": provenance})
    assert _check(_verify(root), "REC_NULL_POLICY") == "PASS"


def test_delivery_sample_with_real_recovery_opportunity_recomputes_overall(tmp_path: Path) -> None:
    from scripts.compute_formal_security_score import FormalScoreConfig, compute_from_stats

    test_delivery_sample_profile_is_distinct(tmp_path)
    root = tmp_path / "sample"
    for name in ("fuzzer_stats", "sample_fuzzer_stats.txt"):
        path = root / name
        path.write_text(path.read_text().replace("nv_rec_total : 0", "nv_rec_total : 1"), encoding="utf-8")
    sample = json.loads((root / "sample_eval_report.json").read_text())
    report = json.loads((root / "eval_report.json").read_text())
    report["rec"] = {}
    score, provenance = compute_from_stats(root / "sample_fuzzer_stats.txt", FormalScoreConfig(1 / 3, 1 / 3, 1 / 3))
    sample.update({"recovery_opportunity_count": 1, "recovery_success_count": 0,
                   "recovery_rate": 0.0, "overall_score": score, "formal_score_provenance": provenance})
    report["rec"].update({"recovery_opportunity_count": 1, "recovery_success_count": 0, "rec_rate": 0.0})
    report["formal_security_score"] = score
    report["formal_score_provenance"] = provenance
    _write_json(root / "sample_eval_report.json", sample)
    _write_json(root / "eval_report.json", report)

    result = _verify(root)
    assert result.to_dict()["verdict"] == "PASS"
    assert _check(result, "OVERALL_SCORE_RECONCILIATION") == "PASS"


def test_overall_score_mismatch_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    report = json.loads((root / "eval_report.json").read_text())
    report["formal_security_score"] = 0.25
    _write_json(root / "eval_report.json", report)
    assert _check(_verify(root), "OVERALL_SCORE_RECONCILIATION") == "FAIL"


def test_required_cleanup_evidence_missing_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    _write_jsonl(root / "evidence/adapter_events.jsonl", [])
    assert _check(_verify(root), "CLEANUP_RECONCILIATION") == "FAIL"


def test_cleanup_requires_same_exact_object_id(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    events_path = root / "evidence/adapter_events.jsonl"
    event = json.loads(events_path.read_text())
    event["cleanup_object_id"] = "different-object"
    _write_jsonl(events_path, [event])
    assert _check(_verify(root), "CLEANUP_RECONCILIATION") == "FAIL"


def test_post_abort_accounting_fails_closed_check(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    _write_json(root / "control/abort.json", {
        "terminal": True, "reason": "CLEANUP_FAILED", "task_id": "fixture-task",
        "run_id": root.name, "exec_seq": 1, "seed_id": "seed-x", "mutation_arm": "arm-0",
    })
    _write_json(root / "run_status.json", {
        "terminal": True, "run_complete": False, "terminal_reason": "CLEANUP_FAILED",
        "task_id": "fixture-task", "run_id": root.name, "abort_exec_seq": 1,
    })
    _write_json(root / "supervisor_termination.json", {"requests_after_abort": 0, "creations_after_abort": 0})
    summary = json.loads((root / "core_mock_summary.json").read_text())
    summary.update({"terminal": True, "terminal_reason": "CLEANUP_FAILED", "POST_ABORT_FALSE_MAB_COMMITS": 1})
    _write_json(root / "core_mock_summary.json", summary)
    assert _check(_verify(root), "FAIL_CLOSED_RECONCILIATION") == "FAIL"


def test_secret_finding_is_redacted(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    secret = "fake-secret-value-do-not-echo-7319"
    (root / "runtime.env").write_text(f"O2OA_PASSWORD={secret}\n", encoding="utf-8")
    result = _verify(root).to_dict()
    rendered = json.dumps(result)
    assert result["verdict"] == "FAIL"
    assert secret not in rendered
    assert _check(_verify(root), "SECRET_SCAN") == "FAIL"


def test_symlink_escape_fails(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (root / "escape.txt").symlink_to(outside)
    assert _check(_verify(root), "PATH_SAFETY") == "FAIL"


@pytest.mark.parametrize("relative", ["eval_report.json", "evidence/status.jsonl"])
def test_contract_symlink_escape_is_rejected_without_reading_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    from deep2fuzz_evidence import verifier

    root = make_platform_run(tmp_path / "run")
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    target = root / relative
    if relative.startswith("evidence/"):
        shutil.copytree(root / "evidence", outside_dir / "evidence")
        shutil.rmtree(root / "evidence")
        (root / "evidence").symlink_to(outside_dir / "evidence", target_is_directory=True)
        outside_file = outside_dir / relative
    else:
        outside_file = outside_dir / "eval_report.json"
        shutil.copy2(target, outside_file)
        target.unlink()
        target.symlink_to(outside_file)

    original = verifier._json_load

    def guarded_json_load(path: Path):
        if path.resolve(strict=False).is_relative_to(outside_dir.resolve()):
            pytest.fail("validator followed an evidence symlink outside the selected root")
        return original(path)

    monkeypatch.setattr(verifier, "_json_load", guarded_json_load)
    result = _verify(root)
    assert _check(result, "PATH_SAFETY") == "FAIL"
    assert result.to_dict()["verdict"] == "FAIL"


def test_json_cli_is_pure_json_with_contract_exit_codes(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    installed_value = os.environ.get("DEEP2FUZZ_TEST_CLI")
    installed = Path(installed_value) if installed_value else None
    command = ([str(installed), "evidence", "verify", str(root), "--json"] if installed
               else [sys.executable, str(REPO / "deep2fuzz_cli.py"), "evidence", "verify", str(root), "--json"])
    passed = subprocess.run(command, cwd=REPO, text=True, capture_output=True, check=False)
    assert passed.returncode == 0
    assert json.loads(passed.stdout)["verdict"] == "PASS"
    (root / "eval_report.json").unlink()
    failed = subprocess.run(command, cwd=REPO, text=True, capture_output=True, check=False)
    assert failed.returncode == 1
    assert json.loads(failed.stdout)["verdict"] == "FAIL"


def test_audit_profile_checks_checksum_and_path_manifest(tmp_path: Path) -> None:
    root = tmp_path / "audit"
    root.mkdir()
    _write_json(root / "FINAL_STATUS.json", {"status": "PASS"})
    _write_json(root / "EVIDENCE_PATHS.json", {
        "root": str(root), "files": ["FINAL_STATUS.json"],
        "file_count_excluding_path_manifest_and_checksum_manifest": 1,
    })
    digest = hashlib.sha256((root / "FINAL_STATUS.json").read_bytes()).hexdigest()
    (root / "SHA256SUMS.txt").write_text(f"{digest}  FINAL_STATUS.json\n", encoding="utf-8")
    result = _verify(root).to_dict()
    assert result["profile"] == "audit-evidence"
    assert result["verdict"] == "PASS"


def test_audit_profile_accepts_legacy_self_listed_path_manifest(tmp_path: Path) -> None:
    root = tmp_path / "audit"
    root.mkdir()
    _write_json(root / "FINAL_STATUS.json", {"status": "PASS"})
    _write_json(root / "EVIDENCE_PATHS.json", {
        "files": ["FINAL_STATUS.json", "EVIDENCE_PATHS.json"],
        "file_count_before_manifest": 2,
    })
    digest = hashlib.sha256((root / "FINAL_STATUS.json").read_bytes()).hexdigest()
    (root / "SHA256SUMS.txt").write_text(f"{digest}  FINAL_STATUS.json\n", encoding="utf-8")
    result = _verify(root).to_dict()
    assert result["profile"] == "audit-evidence"
    assert result["verdict"] == "PASS"


def test_audit_profile_requires_a_terminal_status_field(tmp_path: Path) -> None:
    root = tmp_path / "audit"
    root.mkdir()
    _write_json(root / "FINAL_STATUS.json", {"task": "audit"})
    _write_json(root / "EVIDENCE_PATHS.json", {"files": ["FINAL_STATUS.json"]})
    digest = hashlib.sha256((root / "FINAL_STATUS.json").read_bytes()).hexdigest()
    (root / "SHA256SUMS.txt").write_text(f"{digest}  FINAL_STATUS.json\n", encoding="utf-8")
    result = _verify(root)
    assert _check(result, "AUDIT_FINAL_STATUS") == "FAIL"


def test_delivery_sample_profile_is_distinct(tmp_path: Path) -> None:
    root = tmp_path / "sample"
    root.mkdir()
    _write_json(root / "sample_eval_report.json", {
        "task_id": "sample", "run_id": root.name, "validity_enabled": True,
        "valid_exec": 1, "overall_score": None, "recovery_opportunity_count": 0,
        "recovery_success_count": 0, "recovery_rate": None, "coverage_rate": 1 / 16,
        "anomaly_rate": 0.0, "security_state_new_total": 1,
        "security_state_capacity": 16, "mab_total_pulls": 1,
        "formal_score_provenance": {"weights": {"beta1": 1 / 3, "beta2": 1 / 3, "beta3": 1 / 3}},
    })
    stats_text = ("execs_done : 1\nnv_enable_validity : 1\nnv_total_valid_exec : 1\nnv_rec_total : 0\n"
                  "nv_rec_success : 0\nnv_err_exec : 0\nnv_err_rate : 0\n"
                  "security_state_total : 1\nsecurity_state_new_total : 1\nsecurity_state_observations : 1\n"
                  "security_state_capacity : 16\nsecurity_state_seed_credit : 1\n"
                  "nv_mab_total_pulls : 1\nnv_mab_arm0_pulls : 1\nnv_mab_arm1_pulls : 0\nnv_mab_arm2_pulls : 0\n"
                  "ss_cov_sum : 1\nss_selected_sum : 1\n")
    (root / "sample_fuzzer_stats.txt").write_text(stats_text, encoding="utf-8")
    (root / "fuzzer_stats").write_text(stats_text, encoding="utf-8")
    _write_json(root / "eval_report.json", {
        "rec": {"recovery_opportunity_count": 0, "recovery_success_count": 0, "rec_rate": None},
        "formal_security_score": None,
    })
    csv_fields = (
        "execs_done", "nv_total_valid_exec", "nv_err_exec", "nv_mab_total_pulls",
        "arm0_pulls", "arm1_pulls", "arm2_pulls", "security_state_total",
        "security_state_new_total", "security_state_observations", "security_state_seed_credit",
        "security_state_capacity", "ss_cov_sum", "ss_selected_sum",
    )
    csv_values = {
        "execs_done": "1", "nv_total_valid_exec": "1", "nv_err_exec": "0",
        "nv_mab_total_pulls": "1", "arm0_pulls": "1", "arm1_pulls": "0", "arm2_pulls": "0",
        "security_state_total": "1", "security_state_new_total": "1",
        "security_state_observations": "1", "security_state_seed_credit": "1",
        "security_state_capacity": "16", "ss_cov_sum": "1", "ss_selected_sum": "1",
    }
    (root / "summary.csv").write_text(",".join(csv_fields) + "\n" +
                                       ",".join(csv_values[field] for field in csv_fields) + "\n", encoding="utf-8")
    (root / "security_states.jsonl").write_text("{}\n", encoding="utf-8")
    result = _verify(root).to_dict()
    assert result["profile"] == "delivery-sample"
    assert "REC_NULL_POLICY" in {check["name"] for check in result["checks"]}
    assert _check(_verify(root), "SUMMARY_CSV_RECONCILIATION") == "PASS"


def test_delivery_summary_csv_counter_mismatch_fails(tmp_path: Path) -> None:
    test_delivery_sample_profile_is_distinct(tmp_path)
    root = tmp_path / "sample"
    csv_path = root / "summary.csv"
    csv_path.write_text(csv_path.read_text().replace("1,1,0,1,1,0,0,1,1,1,1,16,1,1\n",
                                                    "1,1,0,1,1,0,0,1,9,1,1,16,1,1\n"), encoding="utf-8")
    assert _check(_verify(root), "SUMMARY_CSV_RECONCILIATION") == "FAIL"


def test_delivery_sample_zero_recovery_opportunities_requires_null_overall(tmp_path: Path) -> None:
    test_delivery_sample_profile_is_distinct(tmp_path)
    root = tmp_path / "sample"
    sample = json.loads((root / "sample_eval_report.json").read_text())
    sample["overall_score"] = 0.0
    _write_json(root / "sample_eval_report.json", sample)
    assert _check(_verify(root), "OVERALL_SCORE_RECONCILIATION") == "FAIL"


def test_delivery_sample_report_overall_must_match_recomputed_score(tmp_path: Path) -> None:
    from scripts.compute_formal_security_score import FormalScoreConfig, compute_from_stats

    test_delivery_sample_profile_is_distinct(tmp_path)
    root = tmp_path / "sample"
    for name in ("fuzzer_stats", "sample_fuzzer_stats.txt"):
        path = root / name
        path.write_text(path.read_text().replace("nv_rec_total : 0", "nv_rec_total : 1"), encoding="utf-8")
    sample = json.loads((root / "sample_eval_report.json").read_text())
    report = json.loads((root / "eval_report.json").read_text())
    report["rec"] = {"recovery_opportunity_count": 1, "recovery_success_count": 0}
    score, provenance = compute_from_stats(
        root / "sample_fuzzer_stats.txt", FormalScoreConfig(1 / 3, 1 / 3, 1 / 3)
    )
    sample.update({"recovery_opportunity_count": 1, "recovery_success_count": 0,
                   "recovery_rate": 0.0, "overall_score": score, "formal_score_provenance": provenance})
    report["formal_security_score"] = score + 0.1
    _write_json(root / "sample_eval_report.json", sample)
    _write_json(root / "eval_report.json", report)
    assert _check(_verify(root), "OVERALL_SCORE_RECONCILIATION") == "FAIL"


def test_delivery_sample_bad_nested_shape_fails_without_crashing(tmp_path: Path) -> None:
    test_delivery_sample_profile_is_distinct(tmp_path)
    root = tmp_path / "sample"
    _write_json(root / "sample_eval_report.json", [])
    result = _verify(root)
    assert result.to_dict()["verdict"] == "FAIL"
    assert _check(result, "JSON_SCHEMA_VALIDATION") == "FAIL"


def test_platform_nested_score_shape_fails_without_crashing(tmp_path: Path) -> None:
    root = make_platform_run(tmp_path / "run")
    report = json.loads((root / "eval_report.json").read_text())
    report["formal_score_provenance"]["normalized_metrics"] = []
    _write_json(root / "eval_report.json", report)
    result = _verify(root)
    assert result.to_dict()["verdict"] == "FAIL"
    assert _check(result, "JSON_SCHEMA_VALIDATION") == "FAIL"


def test_delivery_sample_nested_rec_shape_fails_without_crashing(tmp_path: Path) -> None:
    test_delivery_sample_profile_is_distinct(tmp_path)
    root = tmp_path / "sample"
    _write_json(root / "eval_report.json", {"rec": [], "formal_security_score": None})
    result = _verify(root)
    assert result.to_dict()["verdict"] == "FAIL"
    assert _check(result, "JSON_SCHEMA_VALIDATION") == "FAIL"


def test_delivery_sample_mirrored_raw_stats_must_agree(tmp_path: Path) -> None:
    test_delivery_sample_profile_is_distinct(tmp_path)
    root = tmp_path / "sample"
    path = root / "sample_fuzzer_stats.txt"
    path.write_text(path.read_text().replace("nv_err_exec : 0", "nv_err_exec : 1"), encoding="utf-8")
    assert _check(_verify(root), "REPORT_STATS_RECONCILIATION") == "FAIL"


def test_json_cli_input_error_uses_exit_code_two_and_pure_json(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    result = subprocess.run(
        [sys.executable, str(REPO / "deep2fuzz_cli.py"), "evidence", "verify", str(missing), "--json"],
        cwd=REPO, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout)["checks"][0]["name"] == "INPUT"


def test_unknown_profile_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "unknown"
    root.mkdir()
    result = _verify(root).to_dict()
    assert result["profile"] == "unknown"
    assert result["verdict"] == "FAIL"
    assert next(item for item in result["checks"] if item["name"] == "PROFILE_DETECTION")["status"] == "FAIL"


def test_evidence_root_symlink_is_input_error(tmp_path: Path) -> None:
    from deep2fuzz_evidence.verifier import EvidenceInputError, verify_evidence

    target = tmp_path / "directory"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(EvidenceInputError):
        verify_evidence(link)
