"""Small offline build wrapper used to keep generated egg-info out of sdists."""
from __future__ import annotations

import os
import tarfile
from pathlib import Path

from setuptools.build_meta import *  # noqa: F401,F403 - PEP 517 hook surface
from setuptools.build_meta import build_sdist as _setuptools_build_sdist


def build_sdist(sdist_directory: str, config_settings=None) -> str:
    generated = Path(_setuptools_build_sdist(sdist_directory, config_settings))
    if not generated.is_absolute():
        generated = Path(sdist_directory) / generated
    cleaned = generated.with_name(generated.name + ".cleaned")
    with tarfile.open(generated, "r:gz") as source, tarfile.open(cleaned, "w:gz") as target:
        for member in source:
            if any(part.endswith(".egg-info") for part in Path(member.name).parts):
                continue
            fileobj = source.extractfile(member) if member.isfile() else None
            target.addfile(member, fileobj)
            if fileobj is not None:
                fileobj.close()
    os.replace(cleaned, generated)
    return str(generated)
