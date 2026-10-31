"""PEP 639 license metadata checks for the RC2 distributions."""
from __future__ import annotations

import subprocess
import sys
import tarfile
import re
import tomllib
from email.parser import Parser
from pathlib import Path
import zipfile

import deep2fuzz_build_backend
from deep2fuzz_version import __version__


ROOT = Path(__file__).resolve().parents[1]
LICENSE = ROOT / "LICENSE"
SPDX = "Apache-2.0"
VERSION = "1.1.0rc2"


def test_project_declares_canonical_pep639_license_metadata() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]

    build_requirement = config["build-system"]["requires"][0]
    minimum = re.search(r"setuptools\s*>=\s*(\d+(?:\.\d+)*)", build_requirement)
    assert minimum and tuple(map(int, minimum.group(1).split("."))) >= (77,)
    assert project["license"] == SPDX
    assert "LICENSE" in project["license-files"]
    assert LICENSE.is_file()
    assert not [item for item in project.get("classifiers", []) if item.startswith("License ::")]
    assert __version__ == VERSION


def test_fresh_wheel_and_sdist_emit_pep639_license_metadata(tmp_path: Path) -> None:
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
    sdist = Path(deep2fuzz_build_backend.build_sdist(str(sdist_dir)))

    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        wheel_metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
    wheel_license = next(
        name for name in names
        if name.endswith(".dist-info/licenses/LICENSE") or name.endswith(".dist-info/LICENSE")
    )
    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_license_bytes = archive.read(wheel_license)

    with tarfile.open(sdist) as archive:
        members = {member.name: member for member in archive.getmembers()}
        pkg_info_name = next(name for name in members if name.endswith("/PKG-INFO"))
        sdist_metadata = Parser().parsestr(archive.extractfile(members[pkg_info_name]).read().decode("utf-8"))
        license_name = next(name for name in members if name.endswith("/LICENSE"))
        sdist_license_bytes = archive.extractfile(members[license_name]).read()

    for metadata in (wheel_metadata, sdist_metadata):
        assert metadata["Name"] == "deep2fuzz-es"
        assert metadata["Version"] == VERSION
        assert metadata.get("License-Expression") == SPDX
        assert metadata.get_all("License-File") == ["LICENSE"]
        assert not any(value.startswith("License ::") for value in metadata.get_all("Classifier", []))

    assert wheel_license in names
    assert wheel_license_bytes == LICENSE.read_bytes()
    assert license_name in members
    assert sdist_license_bytes == LICENSE.read_bytes()
