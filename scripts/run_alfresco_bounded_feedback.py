#!/usr/bin/env python3
"""Bounded Alfresco metadata feedback orchestration."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
import importlib.util

LEVELC_METADATA_LAUNCHER = (
    Path(__file__).resolve().with_name("run_alfresco_levelc_metadata.py")
)

def _load_levelc_metadata_module():
    """Load the existing verified Level-C metadata launcher without running main()."""

    spec = importlib.util.spec_from_file_location(
        "alfresco_levelc_metadata_reuse",
        LEVELC_METADATA_LAUNCHER,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("LEVELC_METADATA_MODULE_LOAD_FAILED")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def resolve_existing_dedicated_node(client) -> dict:
    """Resolve the existing dedicated Alfresco test node without creating anything."""

    levelc = _load_levelc_metadata_module()

    siblings = client.list_children(levelc.DEDICATED_PARENT)
    
    try:
        folder = levelc._unique_match(
            siblings,
            levelc.DEDICATED_FOLDER_NAME,
            want_folder=True,
            kind="folder",
        )
    except levelc.LevelCAbort as exc:
        raise RuntimeError(
            "BOUNDED_DEDICATED_FOLDER_AMBIGUOUS"
        ) from exc

    if folder is None:
        raise RuntimeError("BOUNDED_DEDICATED_FOLDER_MISSING")

    folder_id = str(folder.get("id", ""))

    children = client.list_children(folder_id)
    node = levelc._unique_match(
        children,
        levelc.DEDICATED_FILE_NAME,
        want_folder=False,
        kind="file",
    )

    if node is None:
        raise RuntimeError("BOUNDED_DEDICATED_FILE_MISSING")

    file_id = str(node.get("id", ""))

    return {
        "folder_id": folder_id,
        "file_id": file_id,
        "aspect_names": list(node.get("aspectNames") or []),
    }

def render_runtime_target_config(
    node_id: str,
    out_path: Path,
) -> Path:
    """Delegate runtime target rendering to the existing Level-C renderer."""

    levelc = _load_levelc_metadata_module()
    return levelc.render_target_config(node_id, Path(out_path))

def build_run_layout(
    run_root: Path,
    repo_root: Path,
) -> dict[str, Path]:
    """Plan all runtime artifacts under one run-scoped directory."""

    run_root = Path(run_root).resolve()
    repo_root = Path(repo_root).resolve()

    if run_root == repo_root or run_root.is_relative_to(repo_root):
        raise ValueError("RUN_ROOT_INSIDE_GIT_WORKTREE")

    return {
        "run_root": run_root,
        "target_config": run_root / "target.json",
        "seed": run_root / "seed.http",
        "status": run_root / "nv_http_status.json",
        "afl_output": run_root / "afl-out",
        "evidence": run_root / "evidence",
    }


_PROXY_ENV_KEYS = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "all_proxy",
    "ALL_PROXY",
)
ALFRESCO_BASE_URL = "http://127.0.0.1:8080"


def validate_base_url(value: str) -> str:
    """Accept only the exact owner-controlled local Alfresco endpoint."""

    if value != ALFRESCO_BASE_URL:
        raise ValueError("INVALID_ALFRESCO_BASE_URL")

    return value


def sanitized_child_env(source_env: dict[str, str]) -> dict[str, str]:
    """Return a copy safe for loopback-only child processes."""

    child = dict(source_env)

    for key in _PROXY_ENV_KEYS:
        child.pop(key, None)

    child["no_proxy"] = "127.0.0.1,localhost"
    child["NO_PROXY"] = "127.0.0.1,localhost"

    return child


def runtime_credentials() -> tuple[str, str]:
    user = os.environ.get("ALFRESCO_USER")
    password = os.environ.get("ALFRESCO_PASS")

    if (
        user is None
        or password is None
        or not user.strip()
        or not password.strip()
    ):
        raise RuntimeError("MISSING_RUNTIME_CREDENTIALS")

    return user, password


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.parse_args()

    try:
        runtime_credentials()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
