"""Offline regressions for multipart validity and execution identity."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import nv_http_harness


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py"
MULTIPART_MANIFEST = REPO_ROOT / "in" / "alfresco_multipart_upload_bounded" / "manifest.txt"
MULTIPART_SEED = REPO_ROOT / "in" / "alfresco_multipart_upload_bounded" / "seed_0.http"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "multipart_upload_contract_repair_runner", RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _task(runner, scenario: str) -> dict:
    common = {
        "seed_dir": Path("/tmp/offline-multipart-contract-seeds"),
        "max_test_cases": 3,
        "time_budget": 30,
        "scenario": scenario,
    }
    if scenario == "multipart_upload":
        common.update({
            "seed_source": "manifest",
            "seed_manifest": MULTIPART_MANIFEST,
            "input_format": "full_http_multipart",
            "parent_node_id": "parent-1",
        })
    return runner.build_task_payload(**common)


def _upload_record(*, exec_seq=7) -> dict:
    content = b"alpha"
    return {
        "validation_reject": False,
        "target_invoked": True,
        "status_observed": True,
        "http_status": 201,
        "exec_seq": exec_seq,
        "response_node_id": "node-7",
        "parent_node_id": "parent-1",
        "uploaded_name": "sample.txt",
        "file_size": len(content),
        "file_sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
    }


def _ledger_record(
    *, exec_seq=7, target_invoked: bool = True, iteration_id: int = 1
) -> dict:
    return {
        "schema_version": 1,
        "event": "execution",
        "iteration_id": iteration_id,
        "selected_arm": 0,
        "actual_used_arm": 0,
        "arm_match": True,
        "counted_execution": True,
        "harness_invoked": True,
        "target_invoked": target_invoked,
        "body_validated": True,
        "status_observed": True,
        "exec_seq": exec_seq,
        "http_status": 201,
        "mab_outcome": "committed_update" if target_invoked else "target_execution_no_mab",
    }


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _artifact_report(tmp_path: Path, uploads: list[dict], ledger: list[dict]):
    runner = _load_runner()
    layout = runner.build_run_layout(tmp_path / "run", REPO_ROOT)
    _write_jsonl(Path(layout["multipart_uploads"]), uploads)
    _write_jsonl(runner.execution_ledger_path(layout), ledger)
    return runner, layout, runner.inspect_multipart_artifacts(
        layout, launch_returncode=0
    )


def _passing_readback() -> dict:
    return {
        "status": "PASS",
        "verified_count": 1,
        "total_count": 1,
        "records": [{
            "exec_seq": 7,
            "identity_match": True,
            "content_size_match": True,
            "content_hash_match": True,
            "status": "PASS",
        }],
    }


def _passing_campaign_report() -> dict:
    return {
        "final_result": "pass",
        "campaign_execution_proved": True,
        "target_execution_proved": True,
        "target_invocation_count": 1,
        "missing_required": [],
    }


def test_multipart_task_bypasses_only_the_incompatible_generic_validity_gate():
    runner = _load_runner()

    assert _task(runner, "metadata_update")["enable_validity"] == 1
    assert _task(runner, "content_update")["enable_validity"] == 1
    assert _task(runner, "multipart_upload")["enable_validity"] == 0


def test_canonical_multipart_reaches_production_harness_path(tmp_path, monkeypatch):
    runner = _load_runner()
    assert _task(runner, "multipart_upload")["enable_validity"] == 0
    monkeypatch.setenv(
        "NV_MULTIPART_UPLOADS_PATH", str(tmp_path / "multipart_uploads.jsonl")
    )

    class FakeClient:
        parent_node_id = "parent-1"

        def __init__(self):
            self.called = False

        def upload_multipart(self, *, fields, filename, file_bytes):
            self.called = True
            assert fields["nodeType"] == "cm:content"
            assert filename
            assert file_bytes
            return {"status": 201, "body": {"entry": {"id": "node-7", "name": filename}}}

    client = FakeClient()
    result = nv_http_harness.run_multipart_seed(
        MULTIPART_SEED.read_bytes(),
        client=client,
        status_writer=lambda **kwargs: {"exec_seq": 7},
    )
    assert client.called is True
    assert result["validation_reject"] is False
    assert result["http_status"] == 201


def test_identity_case_a_matching_upload_and_authoritative_execution_passes(tmp_path):
    runner, _layout, report = _artifact_report(
        tmp_path, [_upload_record()], [_ledger_record()]
    )
    assert report["multipart_execution_identity_proved"] is True
    assert report["successful_uploads"] == 1
    assert report["ok"] is True
    assert runner.multipart_real_service_reproduction_proved(
        _passing_campaign_report(), report, _passing_readback(), True
    ) is True


def test_uncorrelated_startup_upload_is_retained_but_cannot_supply_proof(tmp_path):
    startup = _upload_record(exec_seq=2)
    campaign = _upload_record(exec_seq=7)
    campaign["response_node_id"] = "node-campaign-7"
    _runner, _layout, report = _artifact_report(
        tmp_path, [startup, campaign], [_ledger_record(exec_seq=7)]
    )
    assert report["successful_upload_candidates"] == 2
    assert report["successful_uploads"] == 1
    assert report["successful_records"] == [campaign]
    assert report["multipart_execution_identity_proved"] is True


def test_identity_case_b_upload_exec_seq_absent_from_ledger_fails_closed(tmp_path):
    _runner, _layout, report = _artifact_report(
        tmp_path, [_upload_record(exec_seq=7)], [_ledger_record(exec_seq=8)]
    )
    assert report["multipart_execution_identity_proved"] is False
    assert report["ok"] is False
    assert "multipart_execution_identity" in report["missing_required"]


def test_identity_case_c_target_not_invoked_fails_closed(tmp_path):
    _runner, _layout, report = _artifact_report(
        tmp_path, [_upload_record()], [_ledger_record(target_invoked=False)]
    )
    assert report["multipart_execution_identity_proved"] is False
    assert report["ok"] is False


def test_identity_case_d_missing_upload_exec_seq_fails_closed(tmp_path):
    _runner, _layout, report = _artifact_report(
        tmp_path, [_upload_record(exec_seq=None)], [_ledger_record()]
    )
    assert report["multipart_execution_identity_proved"] is False
    assert report["ok"] is False


def test_identity_case_e_successful_readback_cannot_replace_ledger_correlation(tmp_path):
    runner, _layout, report = _artifact_report(
        tmp_path, [_upload_record(exec_seq=7)], [_ledger_record(exec_seq=8)]
    )
    assert runner.multipart_real_service_reproduction_proved(
        _passing_campaign_report(), report, _passing_readback(), True
    ) is False


def test_identity_case_f_duplicate_ledger_exec_seq_is_ambiguous(tmp_path):
    _runner, _layout, report = _artifact_report(
        tmp_path,
        [_upload_record()],
        [_ledger_record(iteration_id=1), _ledger_record(iteration_id=2)],
    )
    assert report["multipart_execution_identity_proved"] is False
    assert report["ok"] is False
    assert "ambiguous_exec_seq:7" in report["execution_identity_diagnostics"]
