"""Offline regressions for Task 4 clean-room execution evidence."""

from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import types
from pathlib import Path
from unittest import mock

import nv_http_harness as harness
import nv_state_probe
from nv_body_valid import body_validate
from nv_http_body_adapter import extract_http_body


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py"
RULES_PATH = REPO_ROOT / "validity" / "alfresco_metadata_update_rules.json"


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "task4_clean_room_runner_test", RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_target_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "base": "http://offline.invalid",
                "health": "/health",
                "auth": {"type": "none"},
                "body_only_mode": 1,
                "default_endpoint": "metadata_update",
                "endpoints": [
                    {
                        "name": "metadata_update",
                        "method": "PUT",
                        "path": "/alfresco/node/offline-only",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def execution_record(*, target_invoked: bool, exec_seq: int | None) -> dict:
    status_observed = target_invoked and exec_seq is not None
    return {
        "schema_version": 1,
        "event": "execution",
        "iteration_id": 1,
        "input_id": "offline",
        "stage": "fuzz",
        "selected_arm": 0,
        "actual_used_arm": 0,
        "arm_match": True,
        "counted_execution": target_invoked,
        "harness_invoked": True,
        "target_invoked": target_invoked,
        "body_validated": target_invoked,
        "status_observed": status_observed,
        "exec_seq": exec_seq if status_observed else None,
        "http_status": 200 if status_observed else 0,
        "mab_outcome": (
            "target_execution_no_mab" if target_invoked else "body_validation_reject"
        ),
        "pending_cleanup_reason": None,
    }


def materialize_common_artifacts(layout: dict[str, Path], *, target_invoked: bool) -> None:
    layout["run_root"].mkdir(parents=True, exist_ok=True)
    layout["evidence"].mkdir(parents=True, exist_ok=True)
    layout["afl_output"].mkdir(parents=True, exist_ok=True)
    layout["seed_dir"].mkdir(parents=True, exist_ok=True)
    layout["err_dir"].mkdir(parents=True, exist_ok=True)
    write_target_config(layout["target_config"])
    layout["task"].write_text(
        json.dumps(
            {
                "scenario": "metadata_update",
                "seed_source": "seed_file",
                "mutation_scope": ["field_value"],
            }
        ),
        encoding="utf-8",
    )
    layout["mab_journal"].touch()
    layout["seed_selection_audit"].touch()
    (layout["afl_output"] / "fuzzer_stats").write_text(
        "execs_done : 1\n"
        f"nv_total_valid_exec : {1 if target_invoked else 0}\n"
        "nv_mab_total_pulls : 0\n"
        "nv_mab_arm0_pulls : 0\n"
        "nv_mab_arm1_pulls : 0\n"
        "nv_mab_arm2_pulls : 0\n"
        "nv_mab_arm0_sum : 0\n"
        "nv_mab_arm1_sum : 0\n"
        "nv_mab_arm2_sum : 0\n"
        "nv_mab_arm0_pos : 0\n"
        "nv_mab_arm1_pos : 0\n"
        "nv_mab_arm2_pos : 0\n"
        "security_state_reward_src_seq : 0\n"
        "nv_mab_journal_error_count : 0\n"
        "nv_mab_journal_audit_invalid : 0\n"
        "ss_selected_sum : 0\n"
        "seed_audit_enabled : 1\n"
        "seed_audit_error_count : 0\n"
        "seed_audit_invalid : 0\n"
        "seed_audit_record_count : 0\n"
        "seed_audit_expected_selection_count : 0\n",
        encoding="utf-8",
    )
    layout["state_trace"].write_text('{"event":"state"}\n', encoding="utf-8")


class Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def getcode(self) -> int:
        return 200

    def read(self, limit: int) -> bytes:
        del limit
        return b'{"status":"ok"}'


def test_runner_metadata_seed_passes_production_extraction_and_validation() -> None:
    runner = load_runner()
    with tempfile.TemporaryDirectory(prefix="task4-seed-contract-") as tmp:
        root = Path(tmp)
        config = root / "target.json"
        write_target_config(config)

        seed = runner.write_initial_seed(config, root / "seed", "metadata_update")
        body = extract_http_body(seed.read_bytes())
        result = body_validate(
            scenario="metadata_update",
            endpoint_name="metadata_update",
            raw_body=body,
            rules_path=str(RULES_PATH),
        )

    assert result["ok"], result["reason"]
    assert set(json.loads(body)) == {"properties"}

    malformed = body_validate(
        scenario="metadata_update",
        endpoint_name="metadata_update",
        raw_body=b'{"properties":"not-an-object"}',
        rules_path=str(RULES_PATH),
    )
    assert not malformed["ok"]
    assert malformed["reason"] == "field_type_mismatch"


def test_validation_only_campaign_does_not_require_state_artifacts() -> None:
    runner = load_runner()
    with tempfile.TemporaryDirectory(prefix="task4-zero-target-") as tmp:
        layout = runner.build_run_layout(Path(tmp) / "run", REPO_ROOT)
        materialize_common_artifacts(layout, target_invoked=False)
        layout["seed"].write_bytes(b"not-json")
        layout["status"].write_text(
            json.dumps({"exec_seq": 1, "http_code": 0, "validation_reject": 1}),
            encoding="utf-8",
        )
        layout["status_seq"].write_text("1", encoding="utf-8")
        layout["body_valid_stats"].write_text(
            json.dumps({"body_rule_pass": 0, "body_rule_reject": 1}),
            encoding="utf-8",
        )
        runner.execution_ledger_path(layout).write_text(
            json.dumps(execution_record(target_invoked=False, exec_seq=None)) + "\n",
            encoding="utf-8",
        )

        report = runner.inspect_artifacts(layout, launch_returncode=0)

        assert not layout["probe"].exists()
        assert not layout["state_db"].exists()
        assert "probe" not in report["missing_required"]
        assert "state_db" not in report["missing_required"]
        assert report["campaign_execution_proved"] is True
        assert report["execution_proved"] is True
        assert report["target_execution_proved"] is False
        assert report["target_invocation_count"] == 0
        assert report["real_service_reproduction_proved"] is False


def test_target_invocation_requires_real_state_artifacts() -> None:
    runner = load_runner()
    with tempfile.TemporaryDirectory(prefix="task4-target-artifacts-") as tmp:
        layout = runner.build_run_layout(Path(tmp) / "run", REPO_ROOT)
        materialize_common_artifacts(layout, target_invoked=True)
        seed = runner.write_initial_seed(
            layout["target_config"], layout["seed_dir"], "metadata_update"
        )
        env = {
            "NV_TARGET_CONFIG": str(layout["target_config"]),
            "NV_BODY_RULES": str(RULES_PATH),
            "NV_BODY_VALID_STATS": str(layout["body_valid_stats"]),
            "NV_STATUS_PATH": str(layout["status"]),
            "NV_PROBE_PATH": str(layout["probe"]),
            "NV_STATE_DB": str(layout["state_db"]),
        }
        stdin = types.SimpleNamespace(buffer=io.BytesIO(seed.read_bytes()))
        with (
            mock.patch.dict(harness.os.environ, env, clear=True),
            mock.patch.object(harness, "STATUS_PATH", str(layout["status"])),
            mock.patch.object(harness.sys, "stdin", stdin),
            mock.patch.object(nv_state_probe, "PROBE_PATH", str(layout["probe"])),
            mock.patch.object(nv_state_probe, "STATE_DB_PATH", str(layout["state_db"])),
            mock.patch.object(
                harness.urllib.request, "urlopen", return_value=Response()
            ) as urlopen,
        ):
            return_code = harness.main()

        assert return_code == 0
        urlopen.assert_called_once()
        assert layout["probe"].is_file()
        assert layout["state_db"].is_file()
        status = json.loads(layout["status"].read_text(encoding="utf-8"))
        runner.execution_ledger_path(layout).write_text(
            json.dumps(
                execution_record(target_invoked=True, exec_seq=status["exec_seq"])
            )
            + "\n",
            encoding="utf-8",
        )

        layout["probe"].unlink()
        layout["state_db"].unlink()
        report = runner.inspect_artifacts(layout, launch_returncode=0)

        assert report["campaign_execution_proved"] is True
        assert report["target_execution_proved"] is True
        assert report["target_invocation_count"] == 1
        assert report["real_service_reproduction_proved"] is False
        assert {"probe", "state_db"}.issubset(report["missing_required"])
        assert report["final_result"] == "artifact_contract_failed"
