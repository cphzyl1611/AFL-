"""RC2 clean-source portability regressions for the smoke evidence parent."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import deep2fuzz_portability as portability
from integration.platforms.smoke import default_evidence_root


ROOT = Path(__file__).resolve().parents[1]
T22 = "tests/test_p3_portability.py::test_t22_no_hardcoded_tmp_path_in_supported_product"


def _offline_env(**extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"PYTHONHASHSEED": "0", "LC_ALL": "C", "LANG": "C", "TZ": "UTC", "TASK4_OFFLINE": "1"})
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(name, None)
    env.update(extra)
    return env


def _clean_checkout(parent: Path, name: str = "clean-checkout") -> Path:
    checkout = parent / name
    checkout.mkdir()
    if (ROOT / ".git").exists():
        archive = parent / f"{name}.tar"
        with archive.open("wb") as stream:
            subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, stdout=stream, check=True)
        with tarfile.open(archive, mode="r:") as bundle:
            bundle.extractall(checkout, filter="data")
    else:
        shutil.copytree(
            ROOT,
            checkout,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "deep2fuzz_es.egg-info", "build", "dist"),
        )
    # Build the candidate from the committed tree plus only the reviewed smoke
    # portability hunk; unrelated dirty files never enter the candidate.
    shutil.copy2(ROOT / "integration" / "platforms" / "smoke.py", checkout / "integration" / "platforms" / "smoke.py")
    return checkout


def _smoke_parent(checkout: Path, env: dict[str, str]) -> Path:
    result = subprocess.run(
        [sys.executable, "-c", "from integration.platforms.smoke import default_evidence_root; print(default_evidence_root().parent)"],
        cwd=checkout,
        env={**env, "PYTHONPATH": str(checkout)},
        text=True,
        capture_output=True,
        check=True,
    )
    return Path(result.stdout.strip())


def test_t01_committed_smoke_has_no_developer_absolute_evidence_path() -> None:
    text = (ROOT / "integration" / "platforms" / "smoke.py").read_text(encoding="utf-8")
    assert "/home/" not in text
    assert "C:\\Users\\" not in text
    assert "Path(\"/tmp\")" not in text


def test_t02_explicit_evidence_parent_override_is_used(tmp_path: Path, monkeypatch) -> None:
    explicit = tmp_path / "explicit evidence parent"
    monkeypatch.setenv("DEEP2FUZZ_EVIDENCE_PARENT", str(explicit))
    assert default_evidence_root().parent == explicit


def test_t03_unset_evidence_parent_uses_home_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEEP2FUZZ_EVIDENCE_PARENT", raising=False)
    monkeypatch.setattr(portability, "home_path", lambda: tmp_path / "synthetic-home")
    assert default_evidence_root().parent == tmp_path / "synthetic-home" / "task4-evidence"


def test_t04_clean_checkout_from_temp_path_resolves_explicit_parent(tmp_path: Path) -> None:
    checkout = _clean_checkout(tmp_path)
    explicit = tmp_path / "explicit"
    assert _smoke_parent(checkout, _offline_env(DEEP2FUZZ_EVIDENCE_PARENT=str(explicit))) == explicit


def test_t05_moved_repository_uses_home_fallback(tmp_path: Path) -> None:
    checkout = _clean_checkout(tmp_path, "renamed deep2fuzz checkout")
    synthetic_home = tmp_path / "isolated-home"
    assert _smoke_parent(checkout, _offline_env(HOME=str(synthetic_home))) == synthetic_home / "task4-evidence"


def test_t06_clean_candidate_does_not_need_unrelated_dirty_target(tmp_path: Path) -> None:
    checkout = _clean_checkout(tmp_path)
    target = checkout / "integration" / "platforms" / "mock_rest" / "target.py"
    explicit = tmp_path / "without-target"
    assert target.is_file()
    assert _smoke_parent(checkout, _offline_env(DEEP2FUZZ_EVIDENCE_PARENT=str(explicit))) == explicit


def test_t07_target_dirty_diff_is_not_part_of_smoke_resolution(tmp_path: Path) -> None:
    checkout = _clean_checkout(tmp_path)
    smoke = checkout / "integration" / "platforms" / "smoke.py"
    target = checkout / "integration" / "platforms" / "mock_rest" / "target.py"
    committed_target = subprocess.check_output(
        ["git", "show", "HEAD:integration/platforms/mock_rest/target.py"], cwd=ROOT
    )
    assert "default_evidence_parent" in smoke.read_text(encoding="utf-8")
    assert target.read_bytes() == committed_target


def test_t08_exact_clean_checkout_passes_t22(tmp_path: Path) -> None:
    checkout = _clean_checkout(tmp_path, "exact clean checkout")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", T22],
        cwd=checkout,
        env=_offline_env(PYTHONPATH=str(checkout)),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
