"""Release metadata closure checks for the 1.1.0rc2 candidate."""
from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

from deep2fuzz_version import __version__
import deep2fuzz_build_backend


ROOT = Path(__file__).resolve().parents[1]
RELEASE_NOTES = ROOT / "docs" / "releases" / "Deep2Fuzz-ES-1.1.0rc2.md"
REQUIRED_LIMITATIONS = (
    "18/20",
    "native Windows execution",
    "UNSUPPORTED_FAIL_CLOSED",
    "byte-reproducible",
    "cross-host",
    "32D",
    "SE-fAnoGAN-ES",
    "scenario-dependent",
    "Cov/Err/Rec/overall",
    "papers",
    "patents",
)


def test_version_and_product_documents_are_rc2_ready() -> None:
    assert __version__ == "1.1.0rc2"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = RELEASE_NOTES.read_text(encoding="utf-8")
    assert "# Deep2Fuzz-ES" in readme
    assert "## Known limitations" in readme
    assert "1.1.0rc2" in changelog
    assert "Release Candidate" in notes
    combined = readme + changelog + notes
    for limitation in REQUIRED_LIMITATIONS:
        assert limitation in combined
    assert "universal security score" in combined
    assert "exact external equivalence" in combined


def test_pyproject_binds_existing_license_and_readme() -> None:
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'readme = "README.md"' in config
    assert 'license = { file = "LICENSE" }' in config
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("                                 Apache License")


def test_fresh_wheel_metadata_has_rc2_readme_and_license(tmp_path: Path) -> None:
    output = tmp_path / "wheel"
    output.mkdir()
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
         "--no-index", str(ROOT), "-w", str(output)],
        cwd=ROOT, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    wheels = list(output.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
        names = set(archive.namelist())
    assert metadata["Version"] == "1.1.0rc2"
    assert metadata["Description-Content-Type"] == "text/markdown"
    assert metadata.get_payload().startswith("# Deep2Fuzz-ES")
    assert metadata.get("License-File") == "LICENSE"
    assert "tests/" not in "\n".join(sorted(names))
    assert not any("egg-info" in name for name in names)


def test_fresh_sdist_contains_product_docs_and_excludes_generated_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "sdist"
    output.mkdir()
    archive_path = Path(deep2fuzz_build_backend.build_sdist(str(output)))
    archives = list(output.glob("*.tar.gz"))
    assert len(archives) == 1
    assert archive_path == archives[0]
    with tarfile.open(archives[0]) as archive:
        names = set(archive.getnames())
        payload = {name: archive.extractfile(name).read() for name in names if name.endswith(("README.md", "CHANGELOG.md"))}
    assert any(name.endswith("/README.md") for name in payload)
    assert any(name.endswith("/CHANGELOG.md") for name in payload)
    assert not any("egg-info" in name or "/tests/" in name for name in names)


def test_release_scope_preserves_contract_boundaries() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    notes = RELEASE_NOTES.read_text(encoding="utf-8")
    for text in (readme, notes):
        assert "Cov" in text and "Err" in text and "Rec" in text and "overall" in text
        assert "P1.1B" in text
        assert "native Windows" in text
        assert "SE-fAnoGAN-ES" in text
    assert json.loads('{"schema_version": "1"}') == {"schema_version": "1"}
