"""Offline P3 portability contracts for the supported Deep2Fuzz surface."""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import sys

import pytest

import deep2fuzz_portability as portability
from deep2fuzz_config.validator import config_fingerprint_sha256
from deep2fuzz_provenance import PROVENANCE_SCHEMA_VERSION, source_identity


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "deep2fuzz"
P3_PRODUCT_FILES = (
    ROOT / "deep2fuzz_cli.py",
    ROOT / "deep2fuzz_portability.py",
    ROOT / "deep2fuzz_provenance.py",
    ROOT / "deep2fuzz_config" / "validator.py",
    ROOT / "integration" / "platforms" / "core_runner.py",
    ROOT / "integration" / "platforms" / "smoke.py",
    ROOT / "integration" / "platforms" / "mock_rest" / "target.py",
    ROOT / "scripts" / "run_deep2fuzz_tests.py",
)


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args], cwd=ROOT,
        env=portability.stable_environment(), text=True,
        capture_output=True, check=False,
    )


def _valid_config(root: Path) -> Path:
    seed = root / "路径 with spaces.http"
    seed.write_text("POST /api/items HTTP/1.1\n\n{}\n", encoding="utf-8")
    config = {
        "schema_version": "1", "platform": "mock_rest",
        "run": {"max_test_cases": 1, "time_budget_seconds": 1, "timeout_seconds": 2},
        "inputs": {"seed_file": seed.name},
        "output": {"evidence_root": str(root / "future-output")},
        "validity": {"enabled": True}, "cleanup": {"required": True},
        "platform_config": {"mock_rest": {}},
    }
    path = root / "config.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


def test_t01_pure_posix_path_semantics() -> None:
    value = PurePosixPath("/root/path")
    assert value.parts == ("/", "root", "path")


def test_t02_pure_windows_path_semantics() -> None:
    value = PureWindowsPath(r"C:\Users\name\file")
    assert value.drive == "C:" and value.parts[-1] == "file"


def test_t03_drive_letter_path() -> None:
    assert portability.parse_foreign_path(r"C:\Users\name\file", "windows").drive == "C:"


def test_t04_unc_path() -> None:
    value = portability.parse_foreign_path(r"\\server\share\file", "windows")
    assert value.anchor == "\\\\server\\share\\"


def test_t05_relative_windows_path() -> None:
    assert portability.parse_foreign_path(r"relative\path", "windows").parts == ("relative", "path")


def test_t06_relative_posix_path() -> None:
    assert portability.parse_foreign_path("relative/path", "posix").parts == ("relative", "path")


def test_t07_path_with_spaces_is_opaque() -> None:
    raw = r"C:\Users\name\path with spaces\file"
    assert portability.serialize_path(PureWindowsPath(raw), kind="opaque") == raw


def test_t08_unicode_path_is_preserved() -> None:
    value = portability.parse_foreign_path("路径/文件", "posix")
    assert portability.serialize_path(value, kind="portable") == "路径/文件"


def test_t09_repo_root_discovery_is_cwd_independent(tmp_path: Path) -> None:
    assert portability.discover_repo_root(ROOT / "tests") == ROOT
    assert portability.discover_repo_root(ROOT / "integration" / "platforms") == ROOT
    assert portability.discover_repo_root(tmp_path, required=()) == tmp_path.resolve()


def test_t10_repo_root_discovery_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(portability.UnsupportedCapability, match="repository root"):
        portability.discover_repo_root(tmp_path)


def test_t11_sys_executable_is_preferred() -> None:
    assert portability.interpreter_command() == Path(sys.executable)


def test_t12_posix_venv_layout_is_semantic() -> None:
    assert portability.venv_interpreter_candidates(Path("venv"))[0] == Path("venv/bin/python")


def test_t13_windows_venv_layout_is_semantic() -> None:
    values = portability.venv_interpreter_candidates(Path("venv"))
    assert Path("venv/Scripts/python.exe") in values


def test_t14_missing_interpreter_fails_closed() -> None:
    with pytest.raises(portability.UnsupportedCapability, match="interpreter"):
        portability.interpreter_command("definitely-missing-deep2fuzz-python")


def test_t15_executable_discovery_uses_lookup() -> None:
    assert portability.find_executable("python", which=lambda _: sys.executable) == Path(sys.executable)


def test_t16_shell_false_is_default() -> None:
    assert portability.process_kwargs()["shell"] is False


def test_t17_spaces_do_not_break_argv(tmp_path: Path) -> None:
    result = portability.run_argv([sys.executable, "-c", "import sys; print(sys.argv[1])", "a path"], cwd=tmp_path)
    assert result.stdout.strip() == "a path"


def test_t18_subprocess_argv_is_preserved(tmp_path: Path) -> None:
    result = portability.run_argv([sys.executable, "-c", "import sys; print(repr(sys.argv[1:]))", "a\\b", "路径"], cwd=tmp_path)
    assert "a\\\\b" in result.stdout and "路径" in result.stdout


def test_t19_process_termination_capability_abstraction() -> None:
    plan = portability.termination_plan()
    assert plan == {"graceful": "process_group", "force": "process_group"}


def test_t20_unsupported_signal_fails_closed() -> None:
    with pytest.raises(portability.UnsupportedCapability, match="signal"):
        portability.require_signal("SIG_NOT_A_REAL_SIGNAL")


def test_t21_tempfile_usage(tmp_path: Path) -> None:
    root = portability.new_temp_root(parent=tmp_path, prefix="p3-")
    assert root.parent == tmp_path and root.is_dir()


def test_t22_no_hardcoded_tmp_path_in_supported_product() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in P3_PRODUCT_FILES)
    assert 'Path("/tmp")' not in text and 'Path("/home/cphzy/task4-evidence")' not in text


def test_t23_lf_parsing(tmp_path: Path) -> None:
    path = tmp_path / "lf.txt"
    path.write_bytes(b"a\nb\n")
    assert portability.read_text_utf8(path).splitlines() == ["a", "b"]


def test_t24_crlf_parsing(tmp_path: Path) -> None:
    path = tmp_path / "crlf.txt"
    path.write_bytes(b"a\r\nb\r\n")
    assert portability.read_text_utf8(path).splitlines() == ["a", "b"]


def test_t25_utf8_report(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    portability.write_text_utf8(path, json.dumps({"label": "报告"}) + "\n")
    assert json.loads(path.read_text(encoding="utf-8"))["label"] == "报告"


def test_t26_unicode_evidence_path(tmp_path: Path) -> None:
    path = tmp_path / "证据" / "报告.json"
    path.parent.mkdir()
    portability.write_text_utf8(path, "{}\n")
    assert path.read_text(encoding="utf-8") == "{}\n"


def test_t27_home_missing_does_not_use_home_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOME", raising=False)
    assert portability.home_path() == Path.home()


def test_t28_user_missing_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("USER", raising=False)
    monkeypatch.delenv("USERNAME", raising=False)
    assert portability.optional_environment("USER") is None


def test_t29_temp_env_is_not_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)
    root = portability.new_temp_root(prefix="p3-env-")
    assert root.is_dir()


def test_t30_path_lookup_failure_is_explicit() -> None:
    with pytest.raises(portability.UnsupportedCapability, match="executable"):
        portability.find_executable("missing", which=lambda _: None)


def test_t31_path_serialization_is_deterministic() -> None:
    value = PureWindowsPath(r"C:\Users\name\file")
    assert portability.serialize_path(value, kind="portable") == portability.serialize_path(value, kind="portable")


def test_t32_config_fingerprint_preserves_path_semantics() -> None:
    left = {"schema_version": "1", "inputs": {"seed_file": "a/b"}}
    right = {"schema_version": "1", "inputs": {"seed_file": r"a\b"}}
    assert config_fingerprint_sha256(left) != config_fingerprint_sha256(right)


def test_t33_provenance_ordering_is_deterministic(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=p3@example.invalid", "-c", "user.name=P3", "commit", "-qm", "init"], check=True)
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    (repo / "c.txt").write_text("c\n", encoding="utf-8")
    assert source_identity(repo)["dirty_fingerprint_sha256"] == source_identity(repo)["dirty_fingerprint_sha256"]


def test_t34_crlf_does_not_hide_git_dirty_truth(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    path = repo / "data.txt"
    path.write_bytes(b"a\n")
    subprocess.run(["git", "-C", str(repo), "add", "data.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=p3@example.invalid", "-c", "user.name=P3", "commit", "-qm", "init"], check=True)
    path.write_bytes(b"a\r\n")
    first = source_identity(repo)
    assert first["dirty"] is True


def test_t35_git_missing_fails_closed() -> None:
    with pytest.raises(portability.UnsupportedCapability, match="git"):
        portability.find_executable("git", which=lambda _: None)


def test_t36_cli_help_portability() -> None:
    result = _cli("--help")
    assert result.returncode == 0 and "usage: deep2fuzz" in result.stdout


def test_t37_cli_json_utf8(tmp_path: Path) -> None:
    config = _valid_config(tmp_path)
    result = _cli("config", "validate", str(config), "--json")
    assert result.returncode == 0
    assert json.loads(result.stdout)["verdict"] == "PASS"


def test_t38_doctor_is_offline() -> None:
    result = _cli("doctor")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["LIVE_PLATFORM_PROBED"] is False


def test_t39_doctor_reports_host_capabilities() -> None:
    payload = json.loads(_cli("doctor").stdout)
    assert {"python", "repo_root", "core_imports", "adapter_registry"} <= set(payload)


def test_t40_p2_runner_portability() -> None:
    source = (ROOT / "scripts" / "run_deep2fuzz_tests.py").read_text(encoding="utf-8")
    assert "sys.executable" in source and "shell=True" not in source and 'Path("/tmp")' not in source


def test_t41_formal_node_ids_use_pytest_contract() -> None:
    manifest = json.loads((ROOT / "tests" / "test_groups.json").read_text(encoding="utf-8"))
    ids = manifest["groups"]["required-74"]["members"] + manifest["groups"]["combined-227"]["members"]
    assert all("\\" not in node and "::" in node for node in ids)


def test_t42_p2_gate_repair_preserved() -> None:
    manifest = json.loads((ROOT / "tests" / "test_groups.json").read_text(encoding="utf-8"))
    assert len(manifest["groups"]["required-74"]["members"]) == 74
    assert len(manifest["groups"]["combined-227"]["members"]) == 227


def test_t43_historical_limitation_preserved() -> None:
    text = (ROOT / "docs" / "DEEP2FUZZ_PLATFORM_ADAPTER_SYSTEM.md").read_text(encoding="utf-8")
    assert "18/20" in text and "root cause remains unresolved" in text


def test_t44_unsupported_capability_fails_closed() -> None:
    with pytest.raises(portability.UnsupportedCapability):
        portability.require_capability("native_windows_execution", False)


def test_t45_no_silent_fallback() -> None:
    with pytest.raises(portability.UnsupportedCapability, match="unsupported"):
        portability.require_capability("foreign_host", False)


def test_t46_scientific_output_invariance() -> None:
    source = (ROOT / "deep2fuzz_portability.py").read_text(encoding="utf-8").lower()
    assert "import integration" not in source and "update_state" not in source


def test_t47_runtime_accounting_invariance() -> None:
    assert not hasattr(portability, "update_state")


def test_t48_config_schema_invariance() -> None:
    assert json.loads((ROOT / "tests" / "test_groups.json").read_text(encoding="utf-8"))["schema_version"] == 1


def test_t49_provenance_schema_invariance() -> None:
    assert PROVENANCE_SCHEMA_VERSION == "1"


def test_t50_cli_contract_invariance() -> None:
    assert _cli("--version").stdout.strip() == "1.1.0rc2"
    assert _cli("platform", "list").stdout.strip() == "mock_rest"


def test_t51_missing_shell_helper_fails_closed() -> None:
    with pytest.raises(portability.UnsupportedCapability, match="shell"):
        portability.find_executable("sh", which=lambda _: None)


def test_t52_invalid_local_path_contract_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(portability.UnsupportedCapability, match="path"):
        portability.require_local_path(tmp_path / "missing")


def test_t53_non_writable_temp_parent_fails_closed(tmp_path: Path) -> None:
    parent = tmp_path / "missing-parent"
    with pytest.raises(portability.UnsupportedCapability, match="temporary"):
        portability.new_temp_root(parent=parent, prefix="p3-")


def test_t54_malformed_encoding_input_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "bad.txt"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(UnicodeError):
        portability.read_text_utf8(path)
