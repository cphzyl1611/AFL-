"""Run the existing bounded delivery sample from an installed distribution.

The source-tree runner remains authoritative.  An installed wheel has no
repository root, so its small, explicitly packaged sample assets are copied
to a fresh temporary runtime root and the same runner is invoked there.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from importlib.resources import files
from pathlib import Path

_REQUIRED_ASSETS = (
    "afl-fuzz",
    "distribution_provenance.py",
    "nv_json_mutator.py",
    "nv_url_query.py",
    "in/p0_o2oa_cms_doc_list/seed_all.txt",
    "in/p0_o2oa_cms_doc_list/seed_bad_missing_key.txt",
    "in/p0_o2oa_cms_doc_list/seed_search.txt",
    "in/p0_o2oa_cms_doc_list/seed_status.txt",
    "scripts/compute_formal_security_score.py",
    "scripts/run_task4_sample.py",
    "scripts/summarize_p0_mab_feedback.py",
    "targets/nv_p0_deterministic_target.py",
)


def _copy_assets(destination: Path) -> None:
    source = files("deep2fuzz_runtime").joinpath("assets")
    destination.mkdir(parents=True, exist_ok=True)

    def copy_tree(source_node, relative: Path = Path(".")) -> None:
        for item in source_node.iterdir():
            child_relative = relative / item.name
            target = destination / child_relative
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                copy_tree(item, child_relative)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with item.open("rb") as input_stream, target.open("wb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream)
            if child_relative.name == "afl-fuzz":
                target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    copy_tree(source)
    missing = [name for name in _REQUIRED_ASSETS if not (destination / name).is_file()]
    if missing:
        raise FileNotFoundError("packaged delivery runtime is incomplete")
    if not ((destination / "afl-fuzz").stat().st_mode & 0o111):
        raise PermissionError("packaged AFL runtime is not executable")


def run_delivery_sample(output: str | Path) -> int:
    """Run the packaged offline sample and return its first-attempt exit code."""
    output_path = Path(output).resolve()
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite evidence root: {output_path}")
    with tempfile.TemporaryDirectory(prefix="deep2fuzz-distribution-") as temporary:
        runtime_root = Path(temporary) / "runtime"
        _copy_assets(runtime_root)
        environment = os.environ.copy()
        for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
            environment.pop(name, None)
        environment.update({
            "ROOT": str(runtime_root),
            "OUT_DIR": str(output_path),
            "PYTHON_BIN": sys.executable,
            "MAX_TEST_CASES": "8",
            "TIME_BUDGET": "5",
            "HARD_TIMEOUT": "20",
            "AFL_RAND_SEED": "20261026",
            "PYTHONPATH": os.pathsep.join((str(runtime_root), str(runtime_root / "scripts"))),
        })
        result = subprocess.run(
            [sys.executable, "-m", "deep2fuzz_runtime.sample_runner"],
            cwd=runtime_root,
            env=environment,
            check=False,
        )
        return int(result.returncode)
