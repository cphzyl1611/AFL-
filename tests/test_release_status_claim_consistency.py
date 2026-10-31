"""Keep current release-status wording consistent across source and packages."""
from __future__ import annotations

import re
import subprocess
import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

from deep2fuzz_version import __version__
import deep2fuzz_build_backend


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
RC2_NOTES = ROOT / "docs" / "releases" / "Deep2Fuzz-ES-1.1.0rc2.md"
REQUIRED_LIMITATIONS = tuple(f"KL{i:02d}" for i in range(1, 12))
FORBIDDEN_CLAIMS = (
    "deep2fuzz-es-v1.1.0-rc.1 has not been created",
    "deep2fuzz-es-v1.1.0-rc.2 has not been created",
    "1.1.0rc1 has not been released",
    "1.1.0rc2 has not been released",
)
CURRENT_CANDIDATE_ABSENCE = re.compile(
    r"(?:rc2|rc\.2)[^\n.]{0,100}(?:has not been created|does not exist|has not been published|has not been released)",
    re.IGNORECASE,
)
CANONICAL_VERSION = "1.1.0rc2"
CANONICAL_CHANNEL = "Release Candidate"
CANONICAL_STABLE_STATUS = "Stable version `1.1.0` has not yet\nbeen released."


def _current_status_text() -> str:
    readme = README.read_text(encoding="utf-8")
    section = readme.split("## Version and release status\n", 1)[1].split("\n## ", 1)[0]
    return section


def _assert_current_claim_is_lifecycle_safe(text: str) -> None:
    assert f"Version `{CANONICAL_VERSION}` is a {CANONICAL_CHANNEL}." in text
    assert "Stable version `1.1.0` has not yet\nbeen released." in text
    for claim in FORBIDDEN_CLAIMS:
        assert claim.casefold() not in text.casefold()
    assert CURRENT_CANDIDATE_ABSENCE.search(text) is None

    states = (
        ("before_rc2_tag", CANONICAL_VERSION, CANONICAL_CHANNEL, False, True),
        ("after_rc2_tag", CANONICAL_VERSION, CANONICAL_CHANNEL, False, True),
        ("after_rc2_prerelease", CANONICAL_VERSION, CANONICAL_CHANNEL, False, True),
        ("before_stable", CANONICAL_VERSION, CANONICAL_CHANNEL, False, True),
        ("after_stable", "1.1.0", "Stable", True, False),
    )
    for _state, version, channel, stable_released, expected in states:
        claim_is_true = version == CANONICAL_VERSION and channel == CANONICAL_CHANNEL and not stable_released
        assert claim_is_true is expected


def _fresh_build(tmp_path: Path) -> tuple[Path, Path]:
    wheel_dir = tmp_path / "wheel"
    sdist_dir = tmp_path / "sdist"
    wheel_dir.mkdir()
    sdist_dir.mkdir()
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
         "--no-index", str(ROOT), "-w", str(wheel_dir)],
        cwd=ROOT, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    wheels = list(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1
    sdist_path = Path(deep2fuzz_build_backend.build_sdist(str(sdist_dir)))
    archives = list(sdist_dir.glob("*.tar.gz"))
    assert len(archives) == 1 and sdist_path == archives[0]
    return wheels[0], archives[0]


def test_release_status_claim_is_current_and_lifecycle_safe() -> None:
    assert __version__ == CANONICAL_VERSION
    cli = subprocess.run(
        [sys.executable, str(ROOT / "deep2fuzz"), "--version"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert cli.returncode == 0 and cli.stdout.strip() == CANONICAL_VERSION
    readme = README.read_text(encoding="utf-8")
    status = _current_status_text()
    assert f"Version `{__version__}`" in readme
    _assert_current_claim_is_lifecycle_safe(status)
    assert CHANGELOG.read_text(encoding="utf-8").startswith(
        "# Deep2Fuzz-ES Changelog\n\n## 1.1.0rc2 -"
    )
    changelog = " ".join(CHANGELOG.read_text(encoding="utf-8").split("## 1.1.0rc1", 1)[0].split())
    assert "false RC1 release-status statement" in changelog
    assert "Runtime and scientific behavior are unchanged" in changelog
    assert "RC1" in changelog and "immutable" in changelog
    notes = " ".join(RC2_NOTES.read_text(encoding="utf-8").split())
    assert "Release Candidate" in notes
    assert "false release-status statement" in notes
    assert "Runtime behavior" in notes and "scientific behavior" in notes
    assert "RC1 remains immutable" in notes
    assert all(limitation in notes for limitation in REQUIRED_LIMITATIONS)


def test_current_release_documents_have_no_self_negating_claim() -> None:
    current_docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (README, CHANGELOG, RC2_NOTES)
    )
    for claim in FORBIDDEN_CLAIMS:
        assert claim.casefold() not in current_docs.casefold()
    assert CURRENT_CANDIDATE_ABSENCE.search(current_docs) is None


def test_fresh_wheel_and_sdist_carry_correct_release_status(tmp_path: Path) -> None:
    wheel, sdist = _fresh_build(tmp_path)
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
    wheel_long_description = metadata.get_payload()
    assert metadata["Version"] == CANONICAL_VERSION
    _assert_current_claim_is_lifecycle_safe(wheel_long_description)

    with tarfile.open(sdist) as archive:
        files = {
            name.rsplit("/", 1)[-1]: archive.extractfile(name).read().decode("utf-8")
            for name in archive.getnames()
            if name.endswith(("/README.md", "/PKG-INFO"))
        }
    readme_payload = files["README.md"]
    pkg_info = files["PKG-INFO"]
    pkg_metadata = Parser().parsestr(pkg_info)
    assert pkg_metadata["Version"] == CANONICAL_VERSION
    for text in (readme_payload, pkg_info):
        _assert_current_claim_is_lifecycle_safe(text)
    assert pkg_metadata.get_payload().startswith("# Deep2Fuzz-ES")
