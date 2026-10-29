"""Read-only, offline provenance collection for P1.3 evidence.

This module records source/config/adapter/scorer identity. It does not import
or reproduce any scientific scoring, MAB, validity, or accounting logic.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from deep2fuzz_config.validator import config_fingerprint_sha256
from deep2fuzz_version import __version__


PROVENANCE_SCHEMA_VERSION = "1"
PRODUCT_NAME = "Deep2Fuzz-ES"
EVIDENCE_SCHEMA_VERSION = "1"
ADAPTER_CONTRACT_VERSIONS = {
    "mock_rest": "1",
    "o2oa": "existing-platform-runner-v1",
    "alfresco": "existing-platform-runner-v1",
    "o2oa-shaped-local-deterministic-target": "delivery-sample-v1",
}
SCORER_CONTRACT_ID = "formal-security-score-v1"
SCORER_CONTRACT_FILES = ("scripts/compute_formal_security_score.py",)
_EXCLUDED_DIRS = {
    ".git", ".pytest_cache", "__pycache__", ".venv", "venv", "build", "dist",
    "deep2fuzz_es.egg-info", "evidence", "logs", "tmp", "output",
    "reproduce-results",
}
_MAX_DIRTY_FILE_BYTES = 64 * 1024 * 1024
_MAX_DIRTY_ENTRIES = 100_000


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _run_git(repo_root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), *args],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("git source identity is unavailable") from exc


def _excluded(path: str) -> bool:
    parts = Path(path).parts
    if any(part in _EXCLUDED_DIRS for part in parts):
        return True
    if parts and parts[0] == "out":
        return True
    return path.endswith(".pyc")


def _status_entries(repo_root: Path) -> list[tuple[str, str]]:
    raw = subprocess.check_output(
        ["git", "-C", str(repo_root), "status", "--porcelain=v1", "-z",
         "--untracked-files=all", "--no-renames"],
        stderr=subprocess.DEVNULL,
    )
    entries: list[tuple[str, str]] = []
    for item in raw.decode("utf-8", "surrogateescape").split("\0"):
        if not item:
            continue
        status, path = item[:2], item[3:]
        entries.append((status, path))
    return sorted(entries)


def _path_fingerprint(path: Path) -> str:
    try:
        path.lstat()
    except OSError:
        return "missing"
    if path.is_symlink():
        return _sha256_bytes(os.readlink(path).encode("utf-8", "surrogateescape"))
    if not path.is_file():
        raise RuntimeError("relevant dirty source entry is not a regular file")
    if path.stat().st_size > _MAX_DIRTY_FILE_BYTES:
        raise RuntimeError("relevant dirty source file exceeds the fingerprint size limit")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dirty_fingerprint(repo_root: Path, relevant: list[tuple[str, str]]) -> str | None:
    if not relevant:
        return None
    records: list[dict[str, str]] = []
    tracked_paths = [path for _, path in relevant if not path.startswith("?")]
    index_entries = subprocess.check_output(
        ["git", "-C", str(repo_root), "ls-files", "--stage", "-z", "--", *tracked_paths],
        stderr=subprocess.DEVNULL,
    ) if tracked_paths else b""
    if index_entries:
        records.append({"kind": "index-entries", "sha256": _sha256_bytes(index_entries)})
    if len(relevant) > _MAX_DIRTY_ENTRIES:
        raise RuntimeError("relevant dirty source entry count exceeds the fingerprint limit")
    for status, rel in relevant:
        path = repo_root / rel
        try:
            mode = stat.S_IMODE(path.lstat().st_mode)
        except OSError:
            mode = 0
        records.append({"kind": "path", "status": status, "path": rel,
                        "mode": str(mode), "sha256": _path_fingerprint(path)})
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return _sha256_bytes(canonical)


def source_identity(repo_root: str | Path) -> dict[str, Any]:
    """Collect deterministic git identity using only local read-only commands."""
    root = Path(repo_root).resolve()
    if not (root / ".git").exists():
        raise RuntimeError("NON_GIT_SOURCE_UNSUPPORTED: source tree has no .git metadata")
    entries = _status_entries(root)
    relevant = [(status, path) for status, path in entries if not _excluded(path)]
    dirty = bool(relevant)
    return {
        "git_commit": _run_git(root, "rev-parse", "HEAD"),
        "git_tree": _run_git(root, "rev-parse", "HEAD^{tree}"),
        "dirty": dirty,
        "dirty_fingerprint_sha256": _dirty_fingerprint(root, relevant) if dirty else None,
    }


def scorer_contract_fingerprint(repo_root: str | Path) -> str:
    root = Path(repo_root).resolve()
    records: list[dict[str, str]] = []
    for rel in SCORER_CONTRACT_FILES:
        path = root / rel
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"scorer contract file is unavailable: {rel}")
        records.append({"path": rel, "sha256": _path_fingerprint(path)})
    return _sha256_bytes(json.dumps(records, sort_keys=True, separators=(",", ":")).encode())


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_provenance(
    repo_root: str | Path,
    *,
    config_snapshot: Mapping[str, Any],
    adapter: str,
    run_id: str,
    task_id: str,
    evidence_profile: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if adapter not in ADAPTER_CONTRACT_VERSIONS:
        raise ValueError(f"unsupported adapter identity: {adapter}")
    source = source_identity(repo_root)
    return {
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "product": {"name": PRODUCT_NAME, "version": __version__},
        "source": source,
        "config": {
            "schema_version": str(config_snapshot.get("schema_version", "")),
            "fingerprint_sha256": config_fingerprint_sha256(config_snapshot),
        },
        "platform": {
            "adapter": adapter,
            "adapter_contract_version": ADAPTER_CONTRACT_VERSIONS[adapter],
        },
        "scoring": {
            "contract_id": SCORER_CONTRACT_ID,
            "contract_files": list(SCORER_CONTRACT_FILES),
            "contract_fingerprint_sha256": scorer_contract_fingerprint(repo_root),
        },
        "run": {
            "run_id": run_id,
            "task_id": task_id,
            "generated_at": generated_at or utc_timestamp(),
        },
        "evidence": {
            "profile": evidence_profile,
            "schema_version": EVIDENCE_SCHEMA_VERSION,
        },
    }


def provenance_shape_ok(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("provenance_schema_version") != PROVENANCE_SCHEMA_VERSION:
        return False
    required = ("product", "source", "config", "platform", "scoring", "run", "evidence")
    return all(isinstance(value.get(name), dict) for name in required)


def is_timezone_aware_iso8601(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None
