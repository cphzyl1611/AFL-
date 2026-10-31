from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path
import sys
from unittest import mock
import venv
import zipfile

import pytest

import deep2fuzz_cli
from deep2fuzz_provenance import (
    PROVENANCE_SCHEMA_VERSION,
    provenance_shape_ok,
    source_identity,
)
from deep2fuzz_runtime import sample as distribution_sample
from deep2fuzz_runtime.sample import _copy_assets
import deep2fuzz_build_backend


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "deep2fuzz_runtime" / "assets"


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env.pop(name, None)
    env["TASK4_OFFLINE"] = "1"
    return env


def _run(command: list[str], *, cwd: Path, timeout: float = 180.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=_clean_env(), text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=timeout, check=True)


def _build_wheel(output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    _run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
          "--no-index", str(ROOT), "-w", str(output)], cwd=ROOT)
    wheels = sorted(output.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def _install_wheel(wheel: Path, destination: Path) -> Path:
    venv.create(destination, with_pip=True, clear=False)
    pip = destination / "bin" / "pip"
    _run([str(pip), "install", "--no-index", "--no-deps", str(wheel)], cwd=destination.parent)
    return destination / "bin" / "deep2fuzz"


@pytest.fixture(scope="module")
def distribution_artifacts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    work = tmp_path_factory.mktemp("p4-real-distribution")
    wheel_a = _build_wheel(work / "wheel-a")
    wheel_b = _build_wheel(work / "wheel-b")
    sdist_dir = work / "sdist"
    sdist_dir.mkdir()
    sdist = Path(deep2fuzz_build_backend.build_sdist(str(sdist_dir)))

    extraction = work / "sdist-extracted"
    extraction.mkdir()
    with tarfile.open(sdist) as archive:
        archive.extractall(extraction)
    source = next(extraction.iterdir())
    clean_wheel = _build_wheel(work / "sdist-clean-wheel") if source == ROOT else None
    if clean_wheel is None:
        output = work / "sdist-clean-wheel"
        output.mkdir()
        _run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
              "--no-index", str(source), "-w", str(output)], cwd=work)
        clean_wheel = next(output.glob("*.whl"))

    wheel_venv_1 = work / "wheel-venv-1"
    wheel_venv_2 = work / "wheel-venv-2"
    sdist_venv = work / "sdist-venv"
    command_1 = _install_wheel(wheel_a, wheel_venv_1)
    command_2 = _install_wheel(wheel_b, wheel_venv_2)
    command_sdist = _install_wheel(clean_wheel, sdist_venv)
    return {
        "wheel_a": wheel_a,
        "wheel_b": wheel_b,
        "sdist": sdist,
        "clean_wheel": clean_wheel,
        "command_1": command_1,
        "command_2": command_2,
        "command_sdist": command_sdist,
        "venv_1": wheel_venv_1,
        "venv_2": wheel_venv_2,
        "sdist_venv": sdist_venv,
    }


def _snapshot() -> dict:
    return {
        "schema_version": "1",
        "platform": "o2oa",
        "run": {"max_test_cases": 8, "time_budget_seconds": 5, "timeout_seconds": 20},
        "inputs": {"seed_dir": "in/p0_o2oa_cms_doc_list"},
        "output": {"evidence_root": "new-output"},
        "validity": {"enabled": True},
        "platform_config": {"o2oa": {"profile": "o2oa_default", "token_env": "NV_TOKEN"}},
    }


def test_p4_sample_assets_are_explicit_and_complete(distribution_artifacts: dict[str, Path]) -> None:
    required = (
        "afl-fuzz",
        "distribution_provenance.py",
        "nv_json_mutator.py",
        "nv_url_query.py",
        "scripts/run_task4_sample.py",
        "scripts/summarize_p0_mab_feedback.py",
        "scripts/compute_formal_security_score.py",
        "targets/nv_p0_deterministic_target.py",
        "in/p0_o2oa_cms_doc_list/seed_all.txt",
        "in/p0_o2oa_cms_doc_list/seed_bad_missing_key.txt",
        "in/p0_o2oa_cms_doc_list/seed_search.txt",
        "in/p0_o2oa_cms_doc_list/seed_status.txt",
    )
    assert all((ASSETS / item).is_file() for item in required)
    assert sorted(
        path.relative_to(ASSETS).as_posix()
        for path in ASSETS.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    ) == sorted(
        item for item in required if (ASSETS / item).is_file()
    )
    for wheel in (distribution_artifacts["wheel_a"], distribution_artifacts["wheel_b"],
                  distribution_artifacts["clean_wheel"]):
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
        assert not any(name.startswith("tests/") or ".egg-info/" in name for name in names)
        assert not any(name.endswith((".env", ".token")) for name in names)
        assert "deep2fuzz_runtime/assets/nv_json_mutator.py" in names
        assert "deep2fuzz_runtime/assets/nv_url_query.py" in names


def test_distribution_asset_copy_is_exact_and_executable(
    tmp_path: Path, distribution_artifacts: dict[str, Path]
) -> None:
    destination = tmp_path / "runtime"
    _copy_assets(destination)
    source_files = {p.relative_to(ASSETS).as_posix(): p.read_bytes() for p in ASSETS.rglob("*") if p.is_file()}
    copied_files = {p.relative_to(destination).as_posix(): p.read_bytes() for p in destination.rglob("*") if p.is_file()}
    assert copied_files == source_files
    assert (destination / "afl-fuzz").stat().st_mode & 0o111
    external_cwd = tmp_path / "cwd with spaces" / "unicode"
    external_cwd.mkdir(parents=True)
    for name in ("command_1", "command_2"):
        command = distribution_artifacts[name]
        result = _run([str(command), "--version"], cwd=external_cwd)
        assert result.stdout.strip() == "1.1.0rc1"
    import_check = _run(
        [str(distribution_artifacts["venv_2"] / "bin" / "python"), "-c",
         "import deep2fuzz_cli,deep2fuzz_config.validator,deep2fuzz_evidence.verifier,deep2fuzz_provenance,deep2fuzz_portability, integration.platforms.registry; print(deep2fuzz_cli.__file__)"] ,
        cwd=external_cwd,
    )
    assert "site-packages" in import_check.stdout
    assert str(ROOT) not in import_check.stdout


def test_missing_distribution_asset_fails_before_runner_or_output(tmp_path: Path, monkeypatch) -> None:
    package = tmp_path / "package"
    for relative in distribution_sample._REQUIRED_ASSETS:
        if relative == "nv_json_mutator.py":
            continue
        asset = package / "assets" / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text("", encoding="utf-8")
        if relative == "afl-fuzz":
            asset.chmod(0o755)
    monkeypatch.setattr(distribution_sample, "files", lambda _name: package)
    monkeypatch.setattr(distribution_sample.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("runner started"))
    output = tmp_path / "output"
    with pytest.raises(FileNotFoundError, match="runtime is incomplete"):
        distribution_sample.run_delivery_sample(output)
    assert not output.exists()


def test_sdist_backend_excludes_generated_egg_info(
    tmp_path: Path, monkeypatch, distribution_artifacts: dict[str, Path]
) -> None:
    archive = tmp_path / "fixture.tar.gz"

    def build_sdist(output: str, _settings=None) -> str:
        path = Path(output) / archive.name
        with tarfile.open(path, "w:gz") as bundle:
            for name, payload in (
                ("dist/package/module.py", b"value = 1\n"),
                ("dist/package.egg-info/SOURCES.txt", b"generated\n"),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                bundle.addfile(info, __import__("io").BytesIO(payload))
        return str(path)

    monkeypatch.setattr(deep2fuzz_build_backend, "_setuptools_build_sdist", build_sdist)
    result = Path(deep2fuzz_build_backend.build_sdist(str(tmp_path)))
    with tarfile.open(result) as bundle:
        names = bundle.getnames()
    assert names == ["dist/package/module.py"]
    assert distribution_artifacts["clean_wheel"].is_file()
    sdist_smoke = _run(
        [str(distribution_artifacts["command_sdist"]), "--version"],
        cwd=tmp_path,
    )
    assert sdist_smoke.stdout.strip() == "1.1.0rc1"


def test_distribution_provenance_has_no_fabricated_git_identity(
    tmp_path: Path, distribution_artifacts: dict[str, Path]
) -> None:
    root = tmp_path / "runtime"
    _copy_assets(root)
    from deep2fuzz_runtime.provenance import build_provenance

    source = {"git_commit": None, "git_tree": None, "dirty": False, "dirty_fingerprint_sha256": None}
    assert source == {
        "git_commit": None,
        "git_tree": None,
        "dirty": False,
        "dirty_fingerprint_sha256": None,
    }
    value = build_provenance(
        root,
        config_snapshot=_snapshot(),
        adapter="o2oa-shaped-local-deterministic-target",
        run_id="run-1",
        task_id="task-1",
        evidence_profile="delivery-sample",
    )
    assert provenance_shape_ok(value)
    assert value["provenance_schema_version"] == PROVENANCE_SCHEMA_VERSION
    assert value["source"] == source
    assert "git_commit" not in json.dumps(value) or '"git_commit": null' in json.dumps(value)
    external_cwd = tmp_path / "provenance-cwd"
    external_cwd.mkdir()
    result = _run(
        [str(distribution_artifacts["venv_1"] / "bin" / "python"), "-c",
         "import pathlib,tempfile; from importlib.metadata import version; import deep2fuzz_version; from deep2fuzz_provenance import source_identity; assert version('deep2fuzz-es') == deep2fuzz_version.__version__; p=pathlib.Path(tempfile.mkdtemp()); "
         "exec(\"try:\\n source_identity(p)\\nexcept RuntimeError as e:\\n assert 'NON_GIT_SOURCE_UNSUPPORTED' in str(e)\\nelse:\\n raise AssertionError('Git identity must fail closed')\")"],
        cwd=external_cwd,
    )
    assert result.returncode == 0


def test_ordinary_non_git_source_identity_still_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="NON_GIT_SOURCE_UNSUPPORTED"):
        source_identity(tmp_path)


def test_installed_sample_cli_dispatches_to_packaged_runtime(
    tmp_path: Path, distribution_artifacts: dict[str, Path]
) -> None:
    external_cwd = tmp_path / "sample cwd"
    external_cwd.mkdir()
    command = distribution_artifacts["command_1"]
    explicit = tmp_path / "explicit-sample"
    env = _clean_env()
    env["DEEP2FUZZ_EVIDENCE_PARENT"] = str(explicit)
    completed = subprocess.run([str(command), "sample"], cwd=external_cwd, env=env,
                               text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=45, check=True)
    assert '"valid_exec": 9' in completed.stdout
    sample_roots = sorted(explicit.glob("DEEP2FUZZ_DELIVERY_SAMPLE-*"))
    assert len(sample_roots) == 1
    verify = subprocess.run(
        [str(command), "evidence", "verify", str(sample_roots[0]), "--json"],
        cwd=external_cwd, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=True,
    )
    assert json.loads(verify.stdout)["verdict"] == "PASS"
    seed = tmp_path / "seed.json"
    seed.write_text("{}\n", encoding="utf-8")

    def config_fixture(name: str, mutate) -> Path:
        config = json.loads(json.dumps(_snapshot()))
        config["inputs"] = {"seed_file": str(seed)}
        config["output"] = {"evidence_root": str(tmp_path / f"output-{name}")}
        mutate(config)
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    valid = subprocess.run(
        [str(command), "config", "validate", str(config_fixture("valid", lambda _c: None)), "--json"],
        cwd=external_cwd, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    assert valid.returncode == 0
    assert json.loads(valid.stdout)["verdict"] == "PASS"
    cases = (
        ("unknown", lambda c: c.update({"typo_field": "synthetic-secret-value"}), "UNKNOWN_FIELD"),
        ("future", lambda c: c.update({"schema_version": "999"}), "UNSUPPORTED_SCHEMA_VERSION"),
        ("coercion", lambda c: c["run"].update({"max_test_cases": "8"}), "INVALID_TYPE"),
        ("traversal", lambda c: c["inputs"].update({"seed_file": "../../outside-seed"}), "PATH_ESCAPE"),
    )
    for name, mutate, expected_code in cases:
        invalid = subprocess.run(
            [str(command), "config", "validate", str(config_fixture(name, mutate)), "--json"],
            cwd=external_cwd, env=env, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        )
        assert invalid.returncode == 1
        assert json.loads(invalid.stdout)["errors"][0]["code"] == expected_code
        assert "synthetic-secret-value" not in invalid.stdout + invalid.stderr

    invalid_root = tmp_path / "invalid-evidence"
    shutil.copytree(sample_roots[0], invalid_root)
    (invalid_root / "sample_eval_report.json").write_text("{malformed", encoding="utf-8")
    invalid_evidence = subprocess.run(
        [str(command), "evidence", "verify", str(invalid_root), "--json"],
        cwd=external_cwd, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    assert invalid_evidence.returncode == 1
    assert json.loads(invalid_evidence.stdout)["verdict"] == "FAIL"
    input_error = subprocess.run(
        [str(command), "evidence", "verify", str(tmp_path / "missing-root"), "--json"],
        cwd=external_cwd, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    assert input_error.returncode == 2
    assert json.loads(input_error.stdout)["verdict"] == "FAIL"
