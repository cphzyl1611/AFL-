from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from deep2fuzz_config import config_fingerprint_sha256
from deep2fuzz_provenance import (
    PROVENANCE_SCHEMA_VERSION,
    build_provenance,
    provenance_shape_ok,
    scorer_contract_fingerprint,
    source_identity,
    is_timezone_aware_iso8601,
)


REPO = Path(__file__).resolve().parents[1]


def _git_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    (root / "source.py").write_text("value = 1\n", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "compute_formal_security_score.py").write_text("contract = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    return root


def _snapshot() -> dict:
    return {
        "schema_version": "1",
        "platform": "mock_rest",
        "run": {"max_test_cases": 1, "time_budget_seconds": 2, "timeout_seconds": 3},
        "inputs": {"seed_file": "seed.http"},
        "output": {"evidence_root": "/tmp/new-evidence"},
        "validity": {"enabled": True},
        "cleanup": {"required": True},
        "platform_config": {"mock_rest": {}},
    }


def test_valid_provenance_object_and_exact_identity_fields(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    value = build_provenance(root, config_snapshot=_snapshot(), adapter="mock_rest",
                             run_id="run-1", task_id="task-1", evidence_profile="platform-run",
                             generated_at="2026-01-01T00:00:00Z")
    assert provenance_shape_ok(value)
    assert value["provenance_schema_version"] == PROVENANCE_SCHEMA_VERSION
    assert len(value["source"]["git_commit"]) == 40
    assert len(value["source"]["git_tree"]) == 40
    assert value["run"]["generated_at"].endswith("Z")


def test_provenance_shape_rejects_missing_and_future_schema() -> None:
    value = {"product": {}, "source": {}, "config": {}, "platform": {}, "scoring": {}, "run": {}, "evidence": {}}
    assert not provenance_shape_ok(value)
    value["provenance_schema_version"] = "2"
    assert not provenance_shape_ok(value)


def test_product_version_comes_from_single_source() -> None:
    from deep2fuzz_version import __version__
    value = build_provenance(REPO, config_snapshot=_snapshot(), adapter="mock_rest",
                             run_id="run", task_id="task", evidence_profile="platform-run")
    assert value["product"]["version"] == __version__


def test_clean_fixture_source_is_not_relevant_dirty(tmp_path: Path) -> None:
    value = source_identity(_git_repo(tmp_path))
    assert value["dirty"] is False
    assert value["dirty_fingerprint_sha256"] is None


def test_generated_egg_info_alone_is_not_relevant_dirty(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    (root / "deep2fuzz_es.egg-info").mkdir()
    (root / "deep2fuzz_es.egg-info" / "PKG-INFO").write_text("generated\n", encoding="utf-8")
    value = source_identity(root)
    assert value["dirty"] is False


def test_tracked_relevant_change_is_dirty(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    (root / "source.py").write_text("value = 2\n", encoding="utf-8")
    value = source_identity(root)
    assert value["dirty"] is True
    assert len(value["dirty_fingerprint_sha256"]) == 64


def test_relevant_untracked_source_is_dirty(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    (root / "new_source.py").write_text("value = 2\n", encoding="utf-8")
    value = source_identity(root)
    assert value["dirty"] is True
    assert len(value["dirty_fingerprint_sha256"]) == 64


def test_nested_untracked_source_is_fingerprinted_and_content_sensitive(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    nested = root / "new_package" / "module.py"
    nested.parent.mkdir()
    nested.write_text("value = 2\n", encoding="utf-8")
    first = source_identity(root)["dirty_fingerprint_sha256"]
    nested.write_text("value = 3\n", encoding="utf-8")
    second = source_identity(root)["dirty_fingerprint_sha256"]
    assert first != second


def test_config_fingerprint_is_canonical_for_key_order_and_whitespace() -> None:
    first = _snapshot()
    second = json.loads(json.dumps(first, indent=4, sort_keys=False))
    assert config_fingerprint_sha256(first) == config_fingerprint_sha256(second)


def test_config_semantic_change_changes_fingerprint() -> None:
    first = _snapshot()
    second = copy.deepcopy(first)
    second["run"]["max_test_cases"] = 2
    assert config_fingerprint_sha256(first) != config_fingerprint_sha256(second)


def test_secret_value_is_not_in_provenance() -> None:
    snapshot = _snapshot()
    snapshot["platform_config"]["mock_rest"]["token_env"] = "NV_TOKEN"
    value = build_provenance(REPO, config_snapshot=snapshot, adapter="mock_rest",
                             run_id="run", task_id="task", evidence_profile="platform-run")
    assert "super-secret" not in json.dumps(value)
    assert value["config"]["fingerprint_sha256"]


def test_adapter_and_scorer_identity_are_stable(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    first = scorer_contract_fingerprint(root)
    second = scorer_contract_fingerprint(root)
    assert first == second
    value = build_provenance(root, config_snapshot=_snapshot(), adapter="mock_rest",
                             run_id="run", task_id="task", evidence_profile="platform-run")
    assert value["platform"]["adapter"] == "mock_rest"
    assert value["scoring"]["contract_fingerprint_sha256"] == first


def test_scorer_byte_change_changes_fingerprint(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    first = scorer_contract_fingerprint(root)
    path = root / "scripts" / "compute_formal_security_score.py"
    path.write_text("contract = 2\n", encoding="utf-8")
    assert scorer_contract_fingerprint(root) != first


def test_non_git_source_fails_without_fabricated_identity(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    with pytest.raises(RuntimeError, match="NON_GIT_SOURCE_UNSUPPORTED"):
        source_identity(root)


def test_timestamp_requires_timezone() -> None:
    assert is_timezone_aware_iso8601("2026-01-01T00:00:00Z")
    assert is_timezone_aware_iso8601("2026-01-01T00:00:00+08:00")
    assert not is_timezone_aware_iso8601("2026-01-01T00:00:00")


def _provenance_fixture(tmp_path: Path) -> Path:
    from tests.test_deep2fuzz_evidence_verifier import make_platform_run, _write_json

    root = make_platform_run(tmp_path / "run")
    snapshot = _snapshot()
    value = build_provenance(REPO, config_snapshot=snapshot, adapter="mock_rest",
                             run_id=root.name, task_id="fixture-task", evidence_profile="platform-run",
                             generated_at="2026-01-01T00:00:00Z")
    report = json.loads((root / "eval_report.json").read_text(encoding="utf-8"))
    report.update({"provenance_required": True, "provenance": value, "platform_adapter": "mock_rest"})
    _write_json(root / "eval_report.json", report)
    _write_json(root / "provenance.json", value)
    _write_json(root / "provenance_config.json", snapshot)
    return root


@pytest.mark.parametrize(
    ("field", "bad_value", "check"),
    [
        ("git_commit", "0" * 40, "SOURCE_COMMIT_MISMATCH"),
        ("git_commit", "malformed-commit", "SOURCE_COMMIT_MISMATCH"),
        ("git_tree", "0" * 40, "SOURCE_TREE_MISMATCH"),
        ("fingerprint_sha256", "0" * 64, "CONFIG_FINGERPRINT_MISMATCH"),
    ],
)
def test_provenance_mismatch_fails_closed(tmp_path: Path, field: str, bad_value: str, check: str) -> None:
    root = _provenance_fixture(tmp_path)
    path = root / "provenance.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if field == "fingerprint_sha256":
        value["config"][field] = bad_value
    else:
        value["source"][field] = bad_value
    (root / "eval_report.json").write_text(
        json.dumps({**json.loads((root / "eval_report.json").read_text()), "provenance": value}) + "\n",
        encoding="utf-8",
    )
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    from deep2fuzz_evidence.verifier import verify_evidence

    checks = {item["name"]: item["status"] for item in verify_evidence(root).to_dict()["checks"]}
    assert checks[check] == "FAIL"


def test_missing_new_provenance_fails_but_legacy_fixture_remains_compatible(tmp_path: Path) -> None:
    root = _provenance_fixture(tmp_path)
    report = json.loads((root / "eval_report.json").read_text())
    report.pop("provenance", None)
    (root / "eval_report.json").write_text(json.dumps(report) + "\n", encoding="utf-8")
    (root / "provenance.json").unlink()
    from deep2fuzz_evidence.verifier import verify_evidence

    result = verify_evidence(root).to_dict()
    assert result["verdict"] == "FAIL"
    assert next(item["status"] for item in result["checks"] if item["name"] == "PROVENANCE_MISSING") == "FAIL"


@pytest.mark.parametrize("schema", [None, "99"])
def test_missing_or_future_provenance_schema_fails_closed(tmp_path: Path, schema: str | None) -> None:
    root = _provenance_fixture(tmp_path)
    value = json.loads((root / "provenance.json").read_text())
    if schema is None:
        value.pop("provenance_schema_version")
    else:
        value["provenance_schema_version"] = schema
    (root / "provenance.json").write_text(json.dumps(value) + "\n", encoding="utf-8")
    report = json.loads((root / "eval_report.json").read_text())
    report["provenance"] = value
    (root / "eval_report.json").write_text(json.dumps(report) + "\n", encoding="utf-8")
    from deep2fuzz_evidence.verifier import verify_evidence

    checks = {item["name"]: item for item in verify_evidence(root).to_dict()["checks"]}
    assert checks["PROVENANCE_SCHEMA_UNSUPPORTED"]["status"] == "FAIL"
    assert checks["PROVENANCE_SCHEMA_UNSUPPORTED"]["verification_level"] == "STRUCTURAL"


def test_audit_evidence_provenance_verifies_and_labels_declared_adapter(tmp_path: Path) -> None:
    from deep2fuzz_evidence.verifier import verify_evidence

    root = tmp_path / "audit-evidence"
    root.mkdir()
    snapshot = _snapshot()
    value = build_provenance(REPO, config_snapshot=snapshot, adapter="mock_rest",
                             run_id=root.name, task_id="p1.3-review",
                             evidence_profile="audit-evidence",
                             generated_at="2026-01-01T00:00:00Z")
    final_status = {
        "status": "PASS", "task_id": "p1.3-review", "run_id": root.name,
        "platform_adapter": "mock_rest", "provenance_required": True,
        "provenance": value,
    }
    artifacts = {
        "FINAL_STATUS.json": final_status,
        "provenance.json": value,
        "provenance_config.json": snapshot,
    }
    for name, payload in artifacts.items():
        (root / name).write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    checksums = []
    for name in sorted(artifacts):
        digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
        checksums.append(f"{digest}  {name}")
    (root / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    (root / "EVIDENCE_PATHS.json").write_text(json.dumps({
        "files": sorted(artifacts),
        "file_count_excluding_path_manifest_and_checksum_manifest": len(artifacts),
    }) + "\n", encoding="utf-8")

    result = verify_evidence(root).to_dict()
    assert result["verdict"] == "PASS"
    levels = {item["name"]: item.get("verification_level") for item in result["checks"]}
    assert levels["ADAPTER_IDENTITY_MISMATCH"] == "DECLARED_ONLY"
    assert levels["CONFIG_FINGERPRINT_MISMATCH"] == "RECOMPUTABLE"


@pytest.mark.parametrize(
    ("section", "field", "bad_value", "check"),
    [
        ("product", "version", "0.0.0", "PRODUCT_VERSION_MISMATCH"),
        ("platform", "adapter", "o2oa", "ADAPTER_IDENTITY_MISMATCH"),
        ("scoring", "contract_fingerprint_sha256", "0" * 64, "SCORER_FINGERPRINT_MISMATCH"),
        ("run", "generated_at", "2026-01-01T00:00:00", "TIMESTAMP_INVALID"),
    ],
)
def test_provenance_identity_fields_fail_closed(tmp_path: Path, section: str, field: str,
                                                bad_value: str, check: str) -> None:
    root = _provenance_fixture(tmp_path)
    value = json.loads((root / "provenance.json").read_text())
    value[section][field] = bad_value
    (root / "provenance.json").write_text(json.dumps(value) + "\n", encoding="utf-8")
    report = json.loads((root / "eval_report.json").read_text())
    report["provenance"] = value
    (root / "eval_report.json").write_text(json.dumps(report) + "\n", encoding="utf-8")
    from deep2fuzz_evidence.verifier import verify_evidence

    checks = {item["name"]: item["status"] for item in verify_evidence(root).to_dict()["checks"]}
    assert checks[check] == "FAIL"


def test_dirty_fingerprint_mismatch_fails_closed(tmp_path: Path) -> None:
    root = _provenance_fixture(tmp_path)
    value = json.loads((root / "provenance.json").read_text())
    value["source"]["dirty_fingerprint_sha256"] = "0" * 64
    (root / "provenance.json").write_text(json.dumps(value) + "\n", encoding="utf-8")
    report = json.loads((root / "eval_report.json").read_text())
    report["provenance"] = value
    (root / "eval_report.json").write_text(json.dumps(report) + "\n", encoding="utf-8")
    from deep2fuzz_evidence.verifier import verify_evidence

    checks = {item["name"]: item["status"] for item in verify_evidence(root).to_dict()["checks"]}
    assert checks["SOURCE_DIRTY_FINGERPRINT_MISMATCH"] == "FAIL"


@pytest.mark.parametrize(
    ("section", "field", "bad_value", "check"),
    [
        ("evidence", "profile", "delivery-sample", "EVIDENCE_PROFILE_MISMATCH"),
        ("run", "task_id", "different-task", "RUN_IDENTITY_INVALID"),
    ],
)
def test_report_identity_mismatch_fails_closed(tmp_path: Path, section: str, field: str,
                                              bad_value: str, check: str) -> None:
    root = _provenance_fixture(tmp_path)
    value = json.loads((root / "provenance.json").read_text())
    value[section][field] = bad_value
    (root / "provenance.json").write_text(json.dumps(value) + "\n", encoding="utf-8")
    report = json.loads((root / "eval_report.json").read_text())
    report["provenance"] = value
    (root / "eval_report.json").write_text(json.dumps(report) + "\n", encoding="utf-8")
    from deep2fuzz_evidence.verifier import verify_evidence

    checks = {item["name"]: item["status"] for item in verify_evidence(root).to_dict()["checks"]}
    assert checks[check] == "FAIL"


def test_provenance_artifact_and_report_disagreement_fails_closed(tmp_path: Path) -> None:
    root = _provenance_fixture(tmp_path)
    report = json.loads((root / "eval_report.json").read_text())
    report["provenance"]["run"]["task_id"] = "different-task"
    (root / "eval_report.json").write_text(json.dumps(report) + "\n", encoding="utf-8")
    from deep2fuzz_evidence.verifier import verify_evidence

    checks = {item["name"]: item["status"] for item in verify_evidence(root).to_dict()["checks"]}
    assert checks["REPORT_PROVENANCE_MISMATCH"] == "FAIL"


def test_provenance_collection_is_read_only_and_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _git_repo(tmp_path)
    source_before = (root / "source.py").read_bytes()
    snapshot = _snapshot()
    snapshot_before = copy.deepcopy(snapshot)
    import socket

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("provenance collection attempted network access")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    value = build_provenance(root, config_snapshot=snapshot, adapter="mock_rest",
                             run_id="run", task_id="task", evidence_profile="platform-run")
    assert value["source"]["git_commit"]
    assert (root / "source.py").read_bytes() == source_before
    assert snapshot == snapshot_before
    assert not list(root.glob("*.provenance"))
    assert not any(name in __import__("sys").modules for name in ("requests", "urllib3"))
