from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _valid_config(root: Path, platform: str = "mock_rest") -> tuple[Path, dict]:
    root.mkdir(parents=True, exist_ok=True)
    seed = root / "seed.http"
    seed.write_text(
        "POST /api/items HTTP/1.1\nContent-Type: application/json\n\n{\"title\":\"fixture\"}\n",
        encoding="utf-8",
    )
    block = {
        "mock_rest": {"timeout_sec": 1.5},
        "o2oa": {"profile": "o2oa_default", "token_env": "NV_TOKEN"},
        "alfresco": {
            "profile": "alfresco_content_update",
            "username_env": "ALFRESCO_USER",
            "password_env": "ALFRESCO_PASS",
        },
    }[platform]
    config = {
        "schema_version": "1",
        "platform": platform,
        "run": {"max_test_cases": 2, "time_budget_seconds": 2, "timeout_seconds": 15},
        "inputs": {"seed_file": "seed.http"},
        "output": {"evidence_root": "future-output/run-1"},
        "validity": {"enabled": True},
        "platform_config": {platform: block},
    }
    if platform == "mock_rest":
        config["cleanup"] = {"required": True}
    path = root / "config.json"
    _write(path, config)
    return path, config


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, allow_nan=False, sort_keys=True) + "\n", encoding="utf-8")


def _validate(path: Path):
    from deep2fuzz_config.validator import validate_config

    return validate_config(path)


def _codes(result) -> list[str]:
    return [item["code"] for item in result.to_dict()["errors"]]


def _error_paths(result) -> list[str]:
    return [item["path"] for item in result.to_dict()["errors"]]


def test_valid_minimal_mock_rest_config_passes(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["platform_config"]["mock_rest"] = {}
    _write(path, config)
    result = _validate(path)
    assert result.to_dict()["verdict"] == "PASS"
    assert result.normalized["platform"] == "mock_rest"


def test_valid_full_mock_rest_config_passes(tmp_path: Path) -> None:
    path, _ = _valid_config(tmp_path)
    assert _validate(path).to_dict()["verdict"] == "PASS"


def test_o2oa_profile_is_structurally_valid_without_authentication(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path, "o2oa")
    result = _validate(path)
    assert result.to_dict()["verdict"] == "PASS"
    assert "NV_TOKEN" not in os.environ or config["platform_config"]["o2oa"]["token_env"] == "NV_TOKEN"


def test_alfresco_profile_is_structurally_valid_without_service_contact(tmp_path: Path) -> None:
    path, _ = _valid_config(tmp_path, "alfresco")
    assert _validate(path).to_dict()["verdict"] == "PASS"


def test_malformed_json_is_config_failure(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"schema_version":', encoding="utf-8")
    result = _validate(path)
    assert result.to_dict()["verdict"] == "FAIL"
    assert "PARSE_ERROR" in _codes(result)


def test_duplicate_json_keys_fail_parse_instead_of_last_value_wins(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"schema_version":"1","schema_version":"1"}', encoding="utf-8")
    assert "PARSE_ERROR" in _codes(_validate(path))


def test_missing_schema_version_fails(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    del config["schema_version"]
    _write(path, config)
    assert "MISSING_REQUIRED" in _codes(_validate(path))


@pytest.mark.parametrize("version", ["0", "2", "future"])
def test_unsupported_schema_version_fails_closed(tmp_path: Path, version: str) -> None:
    path, config = _valid_config(tmp_path)
    config["schema_version"] = version
    _write(path, config)
    result = _validate(path)
    assert result.to_dict()["verdict"] == "FAIL"
    assert "UNSUPPORTED_SCHEMA_VERSION" in _codes(result)


def test_unknown_top_level_field_fails(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["platfrom"] = "mock_rest"
    _write(path, config)
    assert "UNKNOWN_FIELD" in _codes(_validate(path))


def test_unknown_nested_field_fails(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["time_buget_seconds"] = 2
    _write(path, config)
    result = _validate(path)
    assert "UNKNOWN_FIELD" in _codes(result)
    assert "run.time_buget_seconds" in _error_paths(result)


def test_missing_required_run_field_fails(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    del config["run"]["max_test_cases"]
    _write(path, config)
    assert "MISSING_REQUIRED" in _codes(_validate(path))


@pytest.mark.parametrize("value", [True, "2", 2.0, None, []])
def test_max_test_cases_rejects_non_integer_types(tmp_path: Path, value: object) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["max_test_cases"] = value
    _write(path, config)
    assert "INVALID_TYPE" in _codes(_validate(path))


def test_string_to_number_coercion_is_rejected(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["time_budget_seconds"] = "30"
    _write(path, config)
    assert "INVALID_TYPE" in _codes(_validate(path))


def test_fractional_budget_is_a_valid_number(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["time_budget_seconds"] = 2.5
    _write(path, config)
    assert _validate(path).to_dict()["verdict"] == "PASS"


def test_subsecond_budget_fails_when_native_integer_budget_would_be_zero(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["time_budget_seconds"] = 0.5
    _write(path, config)
    assert "OUT_OF_RANGE" in _codes(_validate(path))


def test_unrepresentably_large_number_fails_without_exception(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["timeout_seconds"] = 10 ** 400
    _write(path, config)
    assert "OUT_OF_RANGE" in _codes(_validate(path))


def test_max_cases_above_native_exact_integer_range_fails(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["max_test_cases"] = 2 ** 53
    _write(path, config)
    assert "OUT_OF_RANGE" in _codes(_validate(path))


@pytest.mark.parametrize("value", [-1, 0])
def test_timeout_must_be_positive(tmp_path: Path, value: int) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["timeout_seconds"] = value
    _write(path, config)
    assert "OUT_OF_RANGE" in _codes(_validate(path))


def test_negative_budget_fails(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["time_budget_seconds"] = -1
    _write(path, config)
    assert "OUT_OF_RANGE" in _codes(_validate(path))


def test_zero_execution_budget_fails(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["max_test_cases"] = 0
    _write(path, config)
    assert "OUT_OF_RANGE" in _codes(_validate(path))


def test_non_finite_numeric_constant_fails_parse(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    text = json.dumps(config).replace('"timeout_seconds": 15', '"timeout_seconds": Infinity')
    path.write_text(text, encoding="utf-8")
    assert "PARSE_ERROR" in _codes(_validate(path))


def test_unsupported_platform_fails(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["platform"] = "flowable"
    _write(path, config)
    assert "UNSUPPORTED_PLATFORM" in _codes(_validate(path))


def test_selected_platform_block_is_required(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["platform_config"] = {}
    _write(path, config)
    assert "MISSING_REQUIRED" in _codes(_validate(path))


def test_unrelated_platform_block_fails_deterministically(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["platform_config"]["o2oa"] = {"profile": "o2oa_default", "token_env": "NV_TOKEN"}
    _write(path, config)
    first = _validate(path).to_dict()
    second = _validate(path).to_dict()
    assert first == second
    assert "CROSS_FIELD_CONSTRAINT" in [item["code"] for item in first["errors"]]


def test_seed_file_and_seed_dir_are_mutually_exclusive(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["inputs"]["seed_dir"] = "."
    _write(path, config)
    assert "MUTUALLY_EXCLUSIVE" in _codes(_validate(path))


def test_run_timeout_must_cover_time_budget(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["timeout_seconds"] = 1
    _write(path, config)
    assert "CROSS_FIELD_CONSTRAINT" in _codes(_validate(path))


def test_wrong_path_primitive_type_fails(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["inputs"]["seed_file"] = ["seed.http"]
    _write(path, config)
    assert "INVALID_TYPE" in _codes(_validate(path))


def test_required_seed_path_must_exist(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["inputs"]["seed_file"] = "missing.http"
    _write(path, config)
    assert "PATH_NOT_FOUND" in _codes(_validate(path))


def test_mock_seed_directory_must_match_single_seed_identity_contract(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    (seed_dir / "seed-a.http").write_text("POST /api/items HTTP/1.1\n\n{}\n", encoding="utf-8")
    (seed_dir / "seed-b.http").write_text("POST /api/items HTTP/1.1\n\n{}\n", encoding="utf-8")
    config["inputs"] = {"seed_dir": "seeds"}
    _write(path, config)
    assert "CROSS_FIELD_CONSTRAINT" in _codes(_validate(path))


def test_wrong_seed_path_kind_fails(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["inputs"]["seed_file"] = "."
    _write(path, config)
    assert "PATH_TYPE_MISMATCH" in _codes(_validate(path))


def test_future_output_path_is_not_created_or_config_modified(tmp_path: Path) -> None:
    path, _ = _valid_config(tmp_path)
    output = tmp_path / "future-output/run-1"
    before = (hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns)
    result = _validate(path)
    after = (hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns)
    assert result.to_dict()["verdict"] == "PASS"
    assert not output.exists()
    assert before == after


def test_relative_input_escape_fails(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path / "config")
    config["inputs"]["seed_file"] = "../outside.http"
    (tmp_path / "outside.http").write_text("POST /api/items HTTP/1.1\n\n{}\n", encoding="utf-8")
    _write(path, config)
    assert "PATH_ESCAPE" in _codes(_validate(path))


def test_symlink_escape_fails(tmp_path: Path) -> None:
    root = tmp_path / "config"
    path, config = _valid_config(root)
    outside = tmp_path / "outside.http"
    outside.write_text("POST /api/items HTTP/1.1\n\n{}\n", encoding="utf-8")
    (root / "escape.http").symlink_to(outside)
    config["inputs"]["seed_file"] = "escape.http"
    _write(path, config)
    assert "PATH_ESCAPE" in _codes(_validate(path))


def test_symlink_loop_is_reported_without_exception(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    loop = tmp_path / "loop.http"
    loop.symlink_to(loop)
    config["inputs"]["seed_file"] = "loop.http"
    _write(path, config)
    assert "PATH_ESCAPE" in _codes(_validate(path))


def test_absolute_external_seed_path_is_allowed(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path / "config")
    config["inputs"]["seed_file"] = str(path.parent / "seed.http")
    _write(path, config)
    assert _validate(path).to_dict()["verdict"] == "PASS"


def test_output_under_repository_is_rejected(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["output"]["evidence_root"] = str(REPO / "config-validation-must-not-create")
    _write(path, config)
    assert "PATH_ESCAPE" in _codes(_validate(path))
    assert not (REPO / "config-validation-must-not-create").exists()


def test_mock_rest_object_operation_requires_cleanup(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["cleanup"]["required"] = False
    _write(path, config)
    assert "CROSS_FIELD_CONSTRAINT" in _codes(_validate(path))


def test_null_cleanup_object_is_invalid_type(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["cleanup"] = None
    _write(path, config)
    result = _validate(path)
    assert "INVALID_TYPE" in _codes(result)


def test_valid_environment_reference_is_name_only_and_not_read(tmp_path: Path, monkeypatch) -> None:
    path, config = _valid_config(tmp_path, "o2oa")
    monkeypatch.delenv("NV_TOKEN", raising=False)
    _write(path, config)
    assert _validate(path).to_dict()["verdict"] == "PASS"


def test_invalid_environment_reference_syntax_fails(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path, "o2oa")
    config["platform_config"]["o2oa"]["token_env"] = "not a variable"
    _write(path, config)
    assert "INVALID_VALUE" in _codes(_validate(path))


def test_secret_value_is_never_echoed_in_findings(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path, "o2oa")
    secret = "YOUR_TOKEN_HERE"
    config["platform_config"]["o2oa"]["token"] = secret
    _write(path, config)
    result = _validate(path).to_dict()
    assert result["verdict"] == "FAIL"
    assert "UNKNOWN_FIELD" in [item["code"] for item in result["errors"]]
    assert secret not in json.dumps(result)


def test_invalid_schema_version_value_is_not_echoed(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    secret = "YOUR_TOKEN_HERE"
    config["schema_version"] = {"token": secret}
    _write(path, config)
    result = _validate(path).to_dict()
    assert result["config_schema_version"] is None
    assert secret not in json.dumps(result)


def test_invalid_config_fails_before_runner_and_output_creation(tmp_path: Path, monkeypatch) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["max_test_cases"] = -3
    _write(path, config)
    output = tmp_path / "future-output/run-1"
    from deep2fuzz_cli import main

    called = []
    monkeypatch.setattr("integration.platforms.core_runner.run_core_mock", lambda *a, **kw: called.append(True))
    assert main(["platform", "run", "mock_rest", "--config", str(path)]) == 1
    assert called == []
    assert not output.exists()


def test_cli_json_mode_is_pure_json_and_exit_codes_are_stable(tmp_path: Path, capsys) -> None:
    path, _ = _valid_config(tmp_path)
    from deep2fuzz_cli import main

    assert main(["config", "validate", str(path), "--json"]) == 0
    passed = capsys.readouterr()
    assert passed.err == ""
    assert json.loads(passed.out)["verdict"] == "PASS"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["platform"] = "unknown"
    _write(path, config)
    assert main(["config", "validate", str(path), "--json"]) == 1
    failed = capsys.readouterr()
    assert failed.err == ""
    assert json.loads(failed.out)["errors"][0]["code"] == "UNSUPPORTED_PLATFORM"


def test_cli_input_error_uses_exit_code_two_and_pure_json(tmp_path: Path, capsys) -> None:
    from deep2fuzz_cli import main

    assert main(["config", "validate", str(tmp_path / "missing.json"), "--json"]) == 2
    result = capsys.readouterr()
    assert result.err == ""
    assert json.loads(result.out)["errors"][0]["code"] == "INPUT_ERROR"


def test_error_order_is_stable(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["run"].update({"timeout_seconds": 0, "max_test_cases": "wrong"})
    config["validity"]["enabled"] = "true"
    config["unexpected"] = 1
    _write(path, config)
    first = _validate(path).to_dict()
    second = _validate(path).to_dict()
    assert first == second
    assert first["errors"] == sorted(first["errors"], key=lambda e: (e["path"], e["code"], e["message"]))


def test_failed_validation_does_not_change_config_or_mtime(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path)
    config["run"]["max_test_cases"] = 0
    _write(path, config)
    before = (hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns)
    _validate(path)
    after = (hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns)
    assert before == after


def test_o2oa_profile_enum_is_strict(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path, "o2oa")
    config["platform_config"]["o2oa"]["profile"] = "o2oa_typo"
    _write(path, config)
    assert "INVALID_ENUM" in _codes(_validate(path))


def test_alfresco_profile_enum_is_strict(tmp_path: Path) -> None:
    path, config = _valid_config(tmp_path, "alfresco")
    config["platform_config"]["alfresco"]["profile"] = "alfresco_typo"
    _write(path, config)
    assert "INVALID_ENUM" in _codes(_validate(path))


def test_platform_run_with_valid_config_reaches_existing_mock_core(tmp_path: Path, capsys) -> None:
    path, config = _valid_config(tmp_path)
    config["output"]["evidence_root"] = str(tmp_path / "evidence-run")
    _write(path, config)
    from deep2fuzz_cli import main

    assert main(["platform", "run", "mock_rest", "--config", str(path)]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["passed"] is True
    assert result["evidence_root"] == str(tmp_path / "evidence-run")
    assert (tmp_path / "evidence-run" / "eval_report.json").is_file()


def test_cli_version_and_p1_1_evidence_command_remain_available(tmp_path: Path) -> None:
    path, _ = _valid_config(tmp_path)
    result = __import__("subprocess").run(
        [sys.executable, str(REPO / "deep2fuzz_cli.py"), "--help"],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0
    assert "config" in result.stdout and "evidence" in result.stdout
    assert path.is_file()
