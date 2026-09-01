#!/usr/bin/env python3
"""Bounded Alfresco metadata feedback orchestration."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import sysconfig
import tempfile
import shutil
import time
import uuid
from pathlib import Path
from typing import Sequence

LEVELC_METADATA_LAUNCHER = (
    Path(__file__).resolve().with_name("run_alfresco_levelc_metadata.py")
)

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = REPO_ROOT / "nv_http_harness.py"
BODY_RULES_PATH = REPO_ROOT / "validity" / "alfresco_metadata_update_rules.json"
ENDPOINT_NAME = "metadata_update"

# One small, valid metadata seed body.  In body-only mode the production
# harness accepts a bare JSON body; this is the minimum that satisfies both
# the C-side structural check and the rule-based validity gate.
INITIAL_SEED_BODY = (
    b'{"properties":{"cm:title":"seed title",'
    b'"cm:description":"seed description"}}'
)

# Bounded real-gate budget.  max_test_cases is authoritative (small,
# single-digit); time_budget is only a safety fuse.
DEFAULT_MAX_TEST_CASES = 3
DEFAULT_TIME_BUDGET = 30

# Source-authoritative arm names/order.  This mirrors the bit assignment in
# nv_parse_scope_one_text() (src/afl-fuzz.c): field_value=0x1, boundary=0x2,
# structure=0x4.  Canonicalizing to this order keeps task.json, audit trails
# and tests deterministic regardless of the order a caller requests arms in.
MUTATION_SCOPE_ALLOWED = ("field_value", "boundary", "structure")
DEFAULT_MUTATION_SCOPE = ("field_value",)
AFL_BINARY = REPO_ROOT / "afl-fuzz"
DEFAULT_VALIDITY_BACKEND = "alfresco_ae_v1"
VALIDITY_BACKENDS = ("alfresco_ae_v1", "sefanogan_es_reference")


def build_harness_command_for_scenario(task_payload: dict) -> list[str]:
    """Build the stdin harness command for a validated task scenario."""
    scenario = str(task_payload.get("scenario", "metadata_update"))
    input_format = str(task_payload.get("input_format", "full_http"))
    if scenario == "multipart_upload" and input_format == "full_http_multipart":
        return [sys.executable, str(HARNESS_PATH)]
    if scenario == "metadata_update" and input_format == "full_http":
        return [sys.executable, str(HARNESS_PATH)]
    raise ValueError("TASK_SCENARIO_CONTRACT_INVALID")


def validate_target_file_name(value: str | None) -> str:
    """Accept one logical existing filename, never a filesystem path."""

    levelc = _load_levelc_metadata_module()
    name = levelc.DEDICATED_FILE_NAME if value is None else str(value)
    if (
        not name
        or not name.strip()
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in name)
    ):
        raise ValueError("INVALID_TARGET_FILE_NAME")
    return name


def _canonical_mutation_scope(items: Sequence[str]) -> list[str]:
    """Validate and canonicalize an already-split sequence of arm names.

    Pure: no environment, filesystem, or network access.  Rejects unknown
    arms and duplicates; never invents an "all"/"auto" alias.
    """

    if not items:
        raise ValueError("INVALID_MUTATION_SCOPE")

    seen: set[str] = set()
    for item in items:
        if item not in MUTATION_SCOPE_ALLOWED or item in seen:
            raise ValueError("INVALID_MUTATION_SCOPE")
        seen.add(item)

    return [name for name in MUTATION_SCOPE_ALLOWED if name in seen]


def parse_mutation_scope(raw: str | None) -> list[str]:
    """Parse a ``--mutation-scope`` CLI value into a canonical arm list.

    ``raw is None`` (the flag was not given) returns the default single-arm
    scope.  Otherwise ``raw`` is a comma-separated list of
    ``field_value``/``boundary``/``structure`` names; surrounding and
    per-element whitespace is trimmed, but empty elements, unknown names,
    and duplicates are all rejected fail-closed.  Pure function: no
    environment, filesystem, or network access.
    """

    if raw is None:
        return list(DEFAULT_MUTATION_SCOPE)

    elements = [item.strip() for item in raw.split(",")]
    if any(not item for item in elements):
        raise ValueError("INVALID_MUTATION_SCOPE")

    return _canonical_mutation_scope(elements)

# Stable runner-level status for a contract violation.  This is intentionally
# distinct from the child AFL return code and from the credential/service
# gates (2/3).
ARTIFACT_CONTRACT_FAILURE = 4
ARTIFACT_CONTRACT_FAILED = "ARTIFACT_CONTRACT_FAILED"
READBACK_CONTRACT_FAILURE = 5
RUNNER_EXCEPTION_FAILURE = 6
ALFRESCO_API_BASE = "/alfresco/api/-default-/public/alfresco/versions/1"
READBACK_SCHEMA_VERSION = 1
READBACK_EVENT = "post_execution_readback"
READBACK_METADATA_FIELDS = ("cm:title", "cm:description")

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

def _parent_alias_matches(client, parent_id: str, alias: str) -> bool:
    """Accept an alias or its canonical Alfresco node id as the parent."""

    if not parent_id or parent_id == alias:
        return True

    getter = getattr(client, "get_node", None)
    if not callable(getter):
        return False

    try:
        canonical = getter(alias)
    except Exception:
        return False

    return str(canonical.get("id", "")) == parent_id


def resolve_existing_dedicated_parent(client) -> dict:
    """Resolve the existing dedicated folder for creating-upload scenarios."""

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
        raise RuntimeError("BOUNDED_DEDICATED_FOLDER_AMBIGUOUS") from exc
    if folder is None:
        raise RuntimeError("BOUNDED_DEDICATED_FOLDER_MISSING")
    folder_id = str(folder.get("id", ""))
    if not folder_id:
        raise RuntimeError("BOUNDED_DEDICATED_FOLDER_INVALID")
    parent_id = str(folder.get("parentId", "") or "")
    if not _parent_alias_matches(client, parent_id, levelc.DEDICATED_PARENT):
        raise RuntimeError("BOUNDED_DEDICATED_FOLDER_WRONG_PARENT")
    return {"folder_id": folder_id, "parent_id": parent_id or levelc.DEDICATED_PARENT}


def resolve_existing_dedicated_node(
    client, target_file_name: str | None = None
) -> dict:
    """Resolve the existing dedicated Alfresco test node without creating anything."""

    levelc = _load_levelc_metadata_module()
    target_file_name = validate_target_file_name(target_file_name)

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

    if not folder_id:
        raise RuntimeError("BOUNDED_DEDICATED_FOLDER_INVALID")

    folder_parent_id = str(folder.get("parentId", "") or "")
    if not _parent_alias_matches(
        client, folder_parent_id, levelc.DEDICATED_PARENT
    ):
        raise RuntimeError("BOUNDED_DEDICATED_FOLDER_WRONG_PARENT")

    children = client.list_children(folder_id)
    try:
        node = levelc._unique_match(
            children,
            target_file_name,
            want_folder=False,
            kind="file",
        )
    except levelc.LevelCAbort as exc:
        raise RuntimeError("BOUNDED_DEDICATED_FILE_AMBIGUOUS") from exc

    if node is None:
        raise RuntimeError("BOUNDED_DEDICATED_FILE_MISSING")

    file_id = str(node.get("id", ""))
    if not file_id:
        raise RuntimeError("BOUNDED_DEDICATED_FILE_INVALID")

    parent_id = str(node.get("parentId", "") or "")
    if parent_id and parent_id != folder_id:
        raise RuntimeError("BOUNDED_DEDICATED_FILE_WRONG_PARENT")

    return {
        "folder_id": folder_id,
        "file_id": file_id,
        "parent_id": parent_id or folder_id,
        "target_name": str(node.get("name", "")),
        "aspect_names": list(node.get("aspectNames") or []),
    }

def render_runtime_target_config(
    node_id: str,
    out_path: Path,
) -> Path:
    """Delegate runtime target rendering to the existing Level-C renderer."""

    levelc = _load_levelc_metadata_module()
    return levelc.render_target_config(node_id, Path(out_path))


def render_multipart_runtime_config(parent_id: str, out_path: Path) -> Path:
    """Render an upload profile bound to the existing dedicated parent."""

    parent = str(parent_id).strip()
    if not parent or any(char in parent for char in ("/", "\\", "?", "#")):
        raise ValueError("INVALID_MULTIPART_PARENT_ID")
    profile_path = REPO_ROOT / "targets" / "alfresco_multipart_upload.json"
    try:
        config = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("MULTIPART_PROFILE_INVALID") from exc
    if not isinstance(config, dict):
        raise RuntimeError("MULTIPART_PROFILE_INVALID")
    endpoint = f"{ALFRESCO_API_BASE}/nodes/{parent}/children"
    config.update({
        "platform": "alfresco",
        "target_type": "http_api",
        "base": ALFRESCO_BASE_URL,
        "health": "/alfresco/service/api/server",
        "auth": {
            "type": "basic",
            "username_env": "ALFRESCO_USER",
            "password_env": "ALFRESCO_PASS",
        },
        "body_only_mode": 0,
        "parent_node_id": parent,
        "endpoints": [{
            "name": "multipart_upload",
            "method": "POST",
            "path": endpoint,
        }],
        "biz_fields": ["statusCode", "errorKey", "code", "message"],
    })
    destination = Path(out_path).resolve()
    if destination.is_relative_to(REPO_ROOT):
        raise ValueError("MULTIPART_RUNTIME_CONFIG_IN_WORKTREE")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(config, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return destination

def build_run_layout(
    run_root: Path,
    repo_root: Path,
) -> dict[str, Path]:
    """Plan all runtime artifacts under one run-scoped directory."""

    run_root = Path(run_root).resolve()
    repo_root = Path(repo_root).resolve()

    if run_root == repo_root or run_root.is_relative_to(repo_root):
        raise ValueError("RUN_ROOT_INSIDE_GIT_WORKTREE")

    status = run_root / "nv_http_status.json"
    seed_dir = run_root / "seed_input"
    return {
        "run_root": run_root,
        "target_config": run_root / "target.json",
        "task": run_root / "task.json",
        "seed_dir": seed_dir,
        "seed": seed_dir / "seed.http",
        "status": status,
        "status_seq": Path(str(status) + ".seq"),
        "probe": run_root / "nv_probe.json",
        "state_db": run_root / "nv_state_db.json",
        "ctx": run_root / "nv_ctx.json",
        "err_dir": run_root / "err_cases",
        "state_trace": run_root / "nv_state_trace.jsonl",
        "body_valid_stats": run_root / "nv_body_valid_stats.json",
        "afl_output": run_root / "afl-out",
        "evidence": run_root / "evidence",
        "readback": run_root / "evidence" / "readback.json",
        "multipart_readback": run_root / "evidence" / "multipart_readback.json",
        "multipart_uploads": run_root / "evidence" / "multipart_uploads.jsonl",
        "mab_journal": run_root / "evidence" / "mab_updates.jsonl",
        "seed_selection_audit": run_root / "evidence" / "seed_selection.jsonl",
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


def default_run_root() -> Path:
    """Return a fresh run root under /tmp, never inside the Git worktree."""

    return Path("/tmp") / f"nv-alfresco-bounded-{os.getpid()}-{uuid.uuid4().hex}"


def seed_request_metadata(config_path: Path) -> tuple[str, str]:
    """Read the method/path that the rendered target config allows."""

    try:
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("TARGET_CONFIG_INVALID") from exc

    endpoints = cfg.get("endpoints")
    if not isinstance(endpoints, list):
        raise RuntimeError("TARGET_CONFIG_ENDPOINTS_INVALID")

    selected = None
    for endpoint in endpoints:
        if isinstance(endpoint, dict) and str(endpoint.get("name", "")) == ENDPOINT_NAME:
            selected = endpoint
            break
    if not selected:
        raise RuntimeError("TARGET_CONFIG_ENDPOINT_MISSING")

    method = str(selected.get("method", "")).upper().strip()
    path = str(selected.get("path", "")).strip()
    if (
        not method
        or not path.startswith("/")
        or any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in method)
        or any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in path)
        or any(ord(ch) > 0x7F for ch in method + path)
    ):
        raise RuntimeError("TARGET_CONFIG_ENDPOINT_INVALID")
    return method, path


def write_initial_seed(config_path: Path, seed_dir: Path) -> Path:
    """Write one full HTTP seed consumed through harness stdin."""

    method, path = seed_request_metadata(config_path)
    body = INITIAL_SEED_BODY
    envelope = (
        f"{method} {path} HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "\r\n"
    ).encode("ascii")
    seed_dir = Path(seed_dir)
    seed_dir.mkdir(parents=True, exist_ok=True)
    seed_path = seed_dir / "seed.http"
    seed_path.write_bytes(envelope + body)
    return seed_path


def _validate_manifest_seed_name(value: str) -> str:
    name = str(value)
    if (
        not name
        or not name.strip()
        or name in {".", ".."}
        or "/" in name
        or "\\\\" in name
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in name)
    ):
        raise ValueError("INVALID_MANIFEST_SEED_NAME")
    return name


def load_manifest_seed_names(manifest_path: Path) -> list[str]:
    """Load the manifest's filename-only, ordered seed authority."""

    manifest = Path(manifest_path).expanduser().resolve()
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("MANIFEST_NOT_REGULAR")
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError("MANIFEST_UNREADABLE") from exc

    names: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        name = _validate_manifest_seed_name(raw.strip())
        if name in seen:
            raise ValueError("MANIFEST_DUPLICATE_SEED")
        seen.add(name)
        names.append(name)
    if len(names) < 3:
        raise ValueError("MANIFEST_TOO_FEW_SEEDS")
    return names


def materialize_manifest_seed_dir(
    manifest_path: Path, source_dir: Path, destination_dir: Path
) -> Path:
    """Copy only manifest-listed regular files into a fresh run-scoped view."""

    names = load_manifest_seed_names(manifest_path)
    source = Path(source_dir).expanduser().resolve()
    destination = Path(destination_dir).expanduser().resolve()
    if source.is_symlink() or not source.is_dir():
        raise ValueError("MANIFEST_SOURCE_NOT_DIRECTORY")
    if destination.exists():
        raise ValueError("MANIFEST_DESTINATION_NOT_FRESH")

    destination.mkdir(parents=True)
    try:
        for name in names:
            source_path = source / name
            source_stat = source_path.lstat()
            if source_path.is_symlink() or not source_path.is_file():
                raise ValueError("MANIFEST_SEED_NOT_REGULAR")
            target_path = destination / name
            shutil.copyfile(source_path, target_path, follow_symlinks=False)
            if target_path.is_symlink() or not target_path.is_file():
                raise ValueError("MANIFEST_MATERIALIZED_NOT_REGULAR")
            if target_path.read_bytes() != source_path.read_bytes():
                raise ValueError("MANIFEST_SEED_BYTES_CHANGED")
            if target_path.stat().st_size != source_stat.st_size:
                raise ValueError("MANIFEST_SEED_SIZE_CHANGED")
    except (OSError, ValueError):
        raise
    return destination


def build_task_payload(
    seed_dir: Path,
    *,
    max_test_cases: int,
    time_budget: int,
    mutation_scope: Sequence[str] = DEFAULT_MUTATION_SCOPE,
    target_file_name: str | None = None,
    seed_source: str = "seed_file",
    seed_manifest: Path | None = None,
    scenario: str = "metadata_update",
    input_format: str = "full_http",
    parent_node_id: str | None = None,
    validity_backend: str = DEFAULT_VALIDITY_BACKEND,
) -> dict:
    """Build exactly the fields loaded by the current C-side task parser."""

    if isinstance(max_test_cases, bool) or int(max_test_cases) <= 0:
        raise ValueError("INVALID_MAX_TEST_CASES")
    if isinstance(time_budget, bool) or int(time_budget) <= 0:
        raise ValueError("INVALID_TIME_BUDGET")
    canonical_scope = _canonical_mutation_scope(list(mutation_scope))
    if validity_backend not in VALIDITY_BACKENDS:
        raise ValueError("INVALID_VALIDITY_BACKEND")
    selected_target = validate_target_file_name(target_file_name)
    if seed_source not in {"seed_file", "manifest"}:
        raise ValueError("INVALID_SEED_SOURCE")
    if seed_source == "manifest" and seed_manifest is None:
        raise ValueError("MANIFEST_AUTHORITY_MISSING")
    if seed_source == "seed_file" and seed_manifest is not None:
        raise ValueError("UNEXPECTED_MANIFEST_AUTHORITY")
    if scenario not in {"metadata_update", "multipart_upload"}:
        raise ValueError("INVALID_SCENARIO")
    if input_format not in {"full_http", "full_http_multipart"}:
        raise ValueError("INVALID_INPUT_FORMAT")
    if scenario == "multipart_upload" and input_format != "full_http_multipart":
        raise ValueError("MULTIPART_INPUT_FORMAT_REQUIRED")
    if scenario == "metadata_update" and input_format != "full_http":
        raise ValueError("METADATA_INPUT_FORMAT_REQUIRED")
    if scenario == "multipart_upload":
        parent = str(parent_node_id or "").strip()
        if not parent or any(char in parent for char in ("/", "\\", "?", "#")):
            raise ValueError("MULTIPART_PARENT_REQUIRED")
    else:
        parent = None

    target_endpoint = "multipart_upload" if scenario == "multipart_upload" else ENDPOINT_NAME
    payload = {
        "target_type": "http_api",
        "target_endpoint": target_endpoint,
        "seed_source": seed_source,
        "seed_location": str(Path(seed_dir).resolve()),
        "mutation_scope": canonical_scope,
        "max_test_cases": int(max_test_cases),
        "time_budget": int(time_budget),
        "enable_validity": 0 if scenario == "multipart_upload" else 1,
    }
    if scenario == "multipart_upload":
        payload.update({
            "scenario": "multipart_upload",
            "input_format": "full_http_multipart",
            "target_kind": "creating_upload",
            "readback": "created_node_content",
            "parent_node_id": parent,
        })
    if seed_manifest is not None:
        payload["seed_manifest"] = str(Path(seed_manifest).expanduser().resolve())
    if scenario == "multipart_upload":
        payload["parent_node_id"] = parent
    # Preserve the historical default task schema; explicit binding is
    # recorded for runs that opted into a non-canonical target.
    if target_file_name is not None:
        payload["target_file_name"] = selected_target
    return payload


def parse_multipart_upload_records(path: Path) -> list[dict]:
    records: list[dict] = []
    if not Path(path).is_file():
        return records
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("MULTIPART_UPLOAD_RECORD_INVALID")
        records.append(value)
    return records


def inspect_multipart_artifacts(layout: dict[str, Path], *, launch_returncode: int | None = None) -> dict[str, object]:
    """Check multipart-specific upload evidence independently of fixed targets."""
    try:
        records = parse_multipart_upload_records(layout["multipart_uploads"])
    except (OSError, UnicodeDecodeError, ValueError):
        records = []
    successful = [
        record for record in records
        if record.get("target_invoked") is True
        and record.get("status_observed") is True
        and int(record.get("http_status", 0)) == 201
        and isinstance(record.get("response_node_id"), str)
        and bool(record["response_node_id"])
        and isinstance(record.get("exec_seq"), int)
        and int(record["exec_seq"]) > 0
    ]
    invalid_target_records = [
        record for record in records
        if record.get("target_invoked") is True
        and not (record.get("status_observed") is True and int(record.get("exec_seq", 0)) > 0)
    ]
    missing_required: list[str] = []
    if launch_returncode == 0 and not successful:
        missing_required.append("multipart_successful_upload")
    if invalid_target_records:
        missing_required.append("multipart_execution_identity")
    return {
        "ok": not missing_required,
        "records": len(records),
        "successful_uploads": len(successful),
        "validation_rejects": sum(1 for record in records if record.get("validation_reject") is True),
        "invalid_target_records": len(invalid_target_records),
        "missing_required": missing_required,
        "successful_records": successful,
    }


def write_multipart_readback_artifact(layout: dict[str, Path], result: dict[str, object]) -> Path:
    """Publish the sanitized created-upload read-back result."""
    destination = Path(layout["multipart_readback"]).resolve()
    run_root = Path(layout["run_root"]).resolve()
    if not destination.is_relative_to(run_root) or destination.parent != Path(layout["evidence"]).resolve():
        raise OSError("MULTIPART_READBACK_PATH_INVALID")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sanitized = json.loads(json.dumps(result, ensure_ascii=False))
    for record in sanitized.get("records", []):
        record.pop("node_id", None)
    destination.write_text(json.dumps(sanitized, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return destination


def multipart_readback_is_complete(layout: dict[str, Path], upload_report: dict[str, object]) -> bool:
    """Require one successful read-back for every successful upload."""
    path = Path(layout["multipart_readback"])
    if not path.is_file():
        return False
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    return (
        isinstance(result, dict)
        and result.get("status") == "PASS"
        and int(result.get("verified_count", -1)) == int(upload_report.get("successful_uploads", -2))
        and int(result.get("total_count", -1)) == int(upload_report.get("successful_uploads", -2))
    )


def read_multipart_content_bytes(client, node_id: str) -> bytes:
    """Read binary content through the bounded client without changing Level-C."""

    delegated = getattr(client, "get_content_bytes", None)
    if callable(delegated):
        content = delegated(node_id)
        if not isinstance(content, bytes):
            raise RuntimeError("MULTIPART_READBACK_CONTENT_INVALID")
        return content

    request = urllib.request.Request(
        client.base + f"/alfresco/api/-default-/public/alfresco/versions/1/nodes/{node_id}/content",
        method="GET",
        headers={"Authorization": client._auth, "Accept": "application/octet-stream"},
    )
    try:
        with client.opener.open(request, timeout=client.timeout) as response:
            if int(response.getcode()) != 200:
                raise RuntimeError("MULTIPART_READBACK_CONTENT_FAILED")
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError("MULTIPART_READBACK_CONTENT_FAILED") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("MULTIPART_READBACK_CONTENT_FAILED") from exc


def verify_multipart_readback(client, records: list[dict]) -> dict[str, object]:
    """Verify created upload identities and content against sent-byte digests."""

    results: list[dict[str, object]] = []
    for record in records:
        node_id = str(record.get("response_node_id", ""))
        parent_id = str(record.get("parent_node_id", ""))
        name = str(record.get("uploaded_name", ""))
        expected_size = int(record.get("file_size", -1))
        expected_hash = str(record.get("file_sha256", ""))
        result: dict[str, object] = {
            "exec_seq": record.get("exec_seq"),
            "node_id_present": bool(node_id),
            "identity_match": False,
            "content_size_match": False,
            "content_hash_match": False,
            "status": "FAIL",
        }
        if not node_id or expected_size < 0 or not expected_hash.startswith("sha256:"):
            results.append(result)
            continue
        try:
            node = client.get_node(node_id)
            content = read_multipart_content_bytes(client, node_id)
        except Exception as exc:
            result["error"] = exc.__class__.__name__
            results.append(result)
            continue
        if not isinstance(node, dict) or not isinstance(content, bytes):
            results.append(result)
            continue
        result["metadata_status"] = 200
        result["content_status"] = 200
        result["identity_match"] = (
            str(node.get("id", "")) == node_id
            and str(node.get("parentId", "")) == parent_id
            and str(node.get("name", "")) == name
        )
        result["content_size_match"] = len(content) == expected_size
        result["content_hash_match"] = (
            "sha256:" + hashlib.sha256(content).hexdigest() == expected_hash
        )
        result["status"] = "PASS" if all(
            result[key] for key in (
                "identity_match", "content_size_match", "content_hash_match"
            )
        ) else "FAIL"
        results.append(result)
    verified_count = sum(item["status"] == "PASS" for item in results)
    return {
        "status": "PASS" if verified_count == len(records) else "FAIL",
        "verified_count": verified_count,
        "total_count": len(records),
        "records": results,
    }


def read_only_target_identity(client, node_id: str) -> dict:
    """Perform the independent read-only GET for the resolved target."""

    getter = getattr(client, "get_node", None)
    if not callable(getter):
        raise RuntimeError("DEDICATED_TARGET_IDENTITY_GET_UNAVAILABLE")
    try:
        identity = getter(node_id)
    except Exception as exc:
        raise RuntimeError("DEDICATED_TARGET_IDENTITY_GET_FAILED") from exc
    if not isinstance(identity, dict) or any(
        not isinstance(identity.get(field), str) or not identity[field]
        for field in ("id", "parentId", "name")
    ):
        raise RuntimeError("DEDICATED_TARGET_IDENTITY_INCOMPLETE")
    if identity["id"] != str(node_id):
        raise RuntimeError("DEDICATED_TARGET_IDENTITY_MISMATCH")
    return identity


def _identity_digest(domain: str, value: str) -> str:
    """Keep Alfresco identifiers out of evidence while preserving correlation."""

    digest = hashlib.sha256(f"alfresco:{domain}:{value}".encode("utf-8")).hexdigest()
    return f"sha256:{domain}:{digest}"


def _readback_base(*, applicable: bool, valid_count: int = 0) -> dict[str, object]:
    return {
        "enabled": True,
        "applicable": applicable,
        "attempted": False,
        "present": False,
        "correlation": "moderate",
        "status": None,
        "identity_match": False,
        "parent_match": False,
        "verdict": "not_applicable" if not applicable else "snapshot_unavailable",
        "reconciled": False,
        "valid_execution_count": valid_count,
    }


def _read_json_object(path: Path, error: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError(error) from exc
    if not isinstance(value, dict):
        raise RuntimeError(error)
    return value


def parse_final_execution_snapshot(layout: dict[str, Path]) -> dict[str, object]:
    """Require one consistent C-side final execution snapshot."""

    stats_path = layout["afl_output"] / "fuzzer_stats"
    try:
        stats = parse_fuzzer_stats(stats_path)
        valid_count = int(stats["nv_total_valid_exec"])
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("FINAL_EXECUTION_SNAPSHOT_INVALID") from exc
    if valid_count < 0:
        raise RuntimeError("FINAL_EXECUTION_SNAPSHOT_INVALID")
    if valid_count == 0:
        raise RuntimeError("FINAL_EXECUTION_SNAPSHOT_ZERO_VALID_EXEC")

    status = _read_json_object(layout["status"], "FINAL_STATUS_INVALID")
    try:
        last_exec_seq = int(status["exec_seq"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("FINAL_STATUS_EXEC_SEQ_INVALID") from exc
    if last_exec_seq <= 0:
        raise RuntimeError("FINAL_STATUS_EXEC_SEQ_INVALID")

    try:
        trace_lines = Path(layout["state_trace"]).read_text(
            encoding="utf-8", errors="strict"
        ).splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError("FINAL_STATE_TRACE_UNAVAILABLE") from exc

    valid_trace: list[dict[str, object]] = []
    for raw in trace_lines:
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except ValueError as exc:
            raise RuntimeError("FINAL_STATE_TRACE_INVALID") from exc
        if not isinstance(record, dict):
            raise RuntimeError("FINAL_STATE_TRACE_INVALID")
        try:
            sequence = int(record["exec_seq"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("FINAL_STATE_TRACE_EXEC_SEQ_INVALID") from exc
        if sequence > 0:
            valid_trace.append(record)
    if not valid_trace:
        raise RuntimeError("FINAL_STATE_TRACE_NO_VALID_EXECUTION")
    trace_last = valid_trace[-1]
    if int(trace_last["exec_seq"]) != last_exec_seq:
        raise RuntimeError("FINAL_EXECUTION_SEQ_MISMATCH")
    return {
        "stats": stats,
        "status": status,
        "trace_last": trace_last,
        "last_exec_seq": last_exec_seq,
        "valid_execution_count": valid_count,
    }


def _readback_field_presence(properties: dict) -> list[dict[str, str]]:
    fields = []
    for name in READBACK_METADATA_FIELDS:
        if name in properties:
            value = properties[name]
            if value is None:
                field_type = "null"
            elif isinstance(value, bool):
                field_type = "boolean"
            elif isinstance(value, (int, float)):
                field_type = "number"
            elif isinstance(value, str):
                field_type = "string"
            elif isinstance(value, list):
                field_type = "array"
            elif isinstance(value, dict):
                field_type = "object"
            else:
                field_type = "other"
            fields.append({"name": name, "type": field_type})
    return fields


def _readback_result_summary(entry: dict) -> dict[str, object]:
    properties = entry.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    allowlisted = {
        name: properties[name] for name in READBACK_METADATA_FIELDS if name in properties
    }
    canonical = json.dumps(
        allowlisted, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "metadata_hash": "sha256:" + hashlib.sha256(canonical).hexdigest(),
        "field_presence": _readback_field_presence(properties),
        "version_label": None,
    }


def validate_readback_artifact(payload: dict[str, object]) -> bool:
    """Validate the exact sanitized read-back schema before publication."""

    top = {
        "schema_version", "event", "correlation", "target", "request",
        "result", "ordering", "privacy",
    }
    if not isinstance(payload, dict) or set(payload) != top:
        return False
    if payload.get("schema_version") != READBACK_SCHEMA_VERSION or payload.get("event") != READBACK_EVENT:
        return False
    correlation = payload["correlation"]
    target = payload["target"]
    request = payload["request"]
    result = payload["result"]
    ordering = payload["ordering"]
    privacy = payload["privacy"]
    if not all(isinstance(item, dict) for item in (correlation, target, request, result, ordering, privacy)):
        return False
    if set(correlation) != {"mode", "last_exec_seq", "valid_execution_count"}:
        return False
    if correlation.get("mode") != "final_run_state":
        return False
    if any(
        isinstance(correlation.get(name), bool)
        or not isinstance(correlation.get(name), int)
        or correlation.get(name) <= 0
        for name in ("last_exec_seq", "valid_execution_count")
    ):
        return False
    if set(target) != {"node_identity", "parent_identity", "name"}:
        return False
    if not all(
        isinstance(target.get(name), str) and target[name]
        for name in ("node_identity", "parent_identity", "name")
    ):
        return False
    if not str(target["node_identity"]).startswith("sha256:node:") or not str(target["parent_identity"]).startswith("sha256:parent:"):
        return False
    if set(request) != {"method", "status"} or request.get("method") != "GET":
        return False
    if isinstance(request.get("status"), bool) or not isinstance(request.get("status"), int):
        return False
    if set(result) != {"metadata_hash", "field_presence", "version_label"}:
        return False
    if result["metadata_hash"] is not None and not (
        isinstance(result["metadata_hash"], str)
        and result["metadata_hash"].startswith("sha256:")
    ):
        return False
    if not isinstance(result["field_presence"], list) or result["version_label"] is not None:
        return False
    for field in result["field_presence"]:
        if not isinstance(field, dict) or set(field) != {"name", "type"}:
            return False
        if not all(isinstance(field[key], str) and field[key] for key in ("name", "type")):
            return False
        if field["name"] not in READBACK_METADATA_FIELDS:
            return False
        if field["type"] not in {
            "null", "boolean", "number", "string", "array", "object"
        }:
            return False
    if set(ordering) != {"run_completed", "timestamp_ms"} or ordering["run_completed"] is not True:
        return False
    if isinstance(ordering["timestamp_ms"], bool) or not isinstance(ordering["timestamp_ms"], int):
        return False
    if set(privacy) != {"credentials_included", "authorization_included", "raw_body_included"}:
        return False
    return all(privacy[key] is False for key in privacy)


def reconcile_readback_artifact(payload: dict[str, object]) -> bool:
    """Reconcile the published summary without retaining response values."""

    if not validate_readback_artifact(payload):
        return False
    target = payload["target"]
    result = payload["result"]
    allowed_names = set(READBACK_METADATA_FIELDS)
    return all(
        isinstance(field, dict) and field["name"] in allowed_names
        for field in result["field_presence"]
    ) and bool(target["node_identity"].startswith("sha256:node:"))


def write_readback_artifact(layout: dict[str, Path], payload: dict[str, object]) -> Path:
    """Atomically publish sanitized evidence inside this run's evidence dir."""

    evidence = Path(layout["evidence"]).resolve()
    run_root = Path(layout["run_root"]).resolve()
    if evidence != run_root / "evidence" or not evidence.is_relative_to(run_root):
        raise OSError("READBACK_EVIDENCE_PATH_INVALID")
    if not validate_readback_artifact(payload):
        raise OSError("READBACK_SCHEMA_INVALID")
    evidence.mkdir(parents=True, exist_ok=True)
    destination = evidence / "readback.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=evidence, prefix=".readback-", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return destination


def _readback_request(client, node_id: str) -> tuple[int, dict]:
    requester = getattr(client, "request", None)
    if not callable(requester):
        raise RuntimeError("DEDICATED_TARGET_READBACK_GET_UNAVAILABLE")
    response = requester(
        "GET", f"{ALFRESCO_API_BASE}/nodes/{node_id}?include=aspectNames,properties"
    )
    if not isinstance(response, tuple) or len(response) != 2:
        raise RuntimeError("MALFORMED_READBACK_RESPONSE")
    status, payload = response
    if isinstance(status, bool) or not isinstance(status, int):
        raise RuntimeError("MALFORMED_READBACK_RESPONSE")
    return status, payload


def _readback_failure_result(
    base: dict[str, object],
    verdict: str,
    *,
    layout: dict[str, Path] | None = None,
    target_identity: dict[str, str] | None = None,
    snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    base["verdict"] = verdict
    base["reconciled"] = False
    if layout is not None and target_identity is not None and snapshot is not None:
        artifact = {
            "schema_version": READBACK_SCHEMA_VERSION,
            "event": READBACK_EVENT,
            "correlation": {
                "mode": "final_run_state",
                "last_exec_seq": int(snapshot["last_exec_seq"]),
                "valid_execution_count": int(snapshot["valid_execution_count"]),
            },
            "target": {
                "node_identity": _identity_digest("node", target_identity["node_id"]),
                "parent_identity": _identity_digest("parent", target_identity["parent_id"]),
                "name": target_identity["name"],
            },
            "request": {
                "method": "GET",
                "status": int(base["status"]) if isinstance(base.get("status"), int) else 0,
            },
            "result": {
                "metadata_hash": None,
                "field_presence": [],
                "version_label": None,
            },
            "ordering": {"run_completed": True, "timestamp_ms": int(time.time() * 1000)},
            "privacy": {
                "credentials_included": False,
                "authorization_included": False,
                "raw_body_included": False,
            },
        }
        try:
            write_readback_artifact(layout, artifact)
        except OSError:
            base["verdict"] = "artifact_write_failed"
            base["reconciled"] = False
            return base
        base["present"] = True
        base["path"] = str(layout["readback"])
        base["node_identity"] = artifact["target"]["node_identity"]
        base["parent_identity"] = artifact["target"]["parent_identity"]
        base["target_name"] = artifact["target"]["name"]
        base["last_exec_seq"] = artifact["correlation"]["last_exec_seq"]
    return base


def post_execution_readback(
    client,
    target_identity: dict[str, str],
    layout: dict[str, Path],
    *,
    event_log: list[str] | None = None,
) -> dict[str, object]:
    """Read the pinned node once after the final execution snapshot."""

    try:
        stats = parse_fuzzer_stats(layout["afl_output"] / "fuzzer_stats")
        valid_count = int(stats["nv_total_valid_exec"])
    except (OSError, KeyError, TypeError, ValueError):
        return _readback_failure_result(
            _readback_base(applicable=True), "final_snapshot_invalid"
        )
    if valid_count < 0:
        return _readback_failure_result(
            _readback_base(applicable=True, valid_count=valid_count),
            "final_snapshot_invalid",
        )
    if valid_count == 0:
        return _readback_base(applicable=False, valid_count=0)

    base = _readback_base(applicable=True, valid_count=valid_count)
    try:
        snapshot = parse_final_execution_snapshot(layout)
    except RuntimeError as exc:
        base["verdict"] = (
            "final_snapshot_invalid"
            if str(exc) == "FINAL_EXECUTION_SNAPSHOT_INVALID"
            else str(exc)
        )
        return base
    try:
        node_id = str(target_identity["node_id"])
        parent_id = str(target_identity["parent_id"])
        target_name = str(target_identity["name"])
    except (KeyError, TypeError):
        return _readback_failure_result(
            base, "identity_unavailable", layout=layout,
            target_identity=target_identity, snapshot=snapshot
        )
    base["attempted"] = True
    try:
        if event_log is not None:
            event_log.append("readback_get")
        status, payload = _readback_request(client, node_id)
        base["status"] = status
        if status in (401, 403):
            return _readback_failure_result(
                base, "auth_failed", layout=layout,
                target_identity=target_identity, snapshot=snapshot
            )
        if status == 404:
            return _readback_failure_result(
                base, "target_not_found", layout=layout,
                target_identity=target_identity, snapshot=snapshot
            )
        if 500 <= status <= 599 or status != 200:
            return _readback_failure_result(
                base, "readback_service_error", layout=layout,
                target_identity=target_identity, snapshot=snapshot
            )
        if not isinstance(payload, dict):
            return _readback_failure_result(
                base, "malformed_response", layout=layout,
                target_identity=target_identity, snapshot=snapshot
            )
        entry = payload.get("entry")
        if not isinstance(entry, dict):
            return _readback_failure_result(
                base, "malformed_response", layout=layout,
                target_identity=target_identity, snapshot=snapshot
            )
        returned_id = str(entry.get("id", ""))
        returned_parent = str(entry.get("parentId", ""))
        returned_name = str(entry.get("name", ""))
        if not returned_id or not returned_parent or not returned_name:
            return _readback_failure_result(
                base, "identity_unavailable", layout=layout,
                target_identity=target_identity, snapshot=snapshot
            )
        identity_match = returned_id == node_id and returned_name == target_name
        parent_match = returned_parent == parent_id
        base["identity_match"] = identity_match
        base["parent_match"] = parent_match
        if not identity_match:
            return _readback_failure_result(
                base, "identity_mismatch", layout=layout,
                target_identity=target_identity, snapshot=snapshot
            )
        if not parent_match:
            return _readback_failure_result(
                base, "parent_mismatch", layout=layout,
                target_identity=target_identity, snapshot=snapshot
            )
        artifact = {
            "schema_version": READBACK_SCHEMA_VERSION,
            "event": READBACK_EVENT,
            "correlation": {
                "mode": "final_run_state",
                "last_exec_seq": int(snapshot["last_exec_seq"]),
                "valid_execution_count": int(snapshot["valid_execution_count"]),
            },
            "target": {
                "node_identity": _identity_digest("node", node_id),
                "parent_identity": _identity_digest("parent", parent_id),
                "name": target_name,
            },
            "request": {"method": "GET", "status": status},
            "result": _readback_result_summary(entry),
            "ordering": {"run_completed": True, "timestamp_ms": int(time.time() * 1000)},
            "privacy": {
                "credentials_included": False,
                "authorization_included": False,
                "raw_body_included": False,
            },
        }
        base["node_identity"] = artifact["target"]["node_identity"]
        base["parent_identity"] = artifact["target"]["parent_identity"]
        base["target_name"] = artifact["target"]["name"]
        write_readback_artifact(layout, artifact)
        base["present"] = True
        base["verdict"] = "pass"
        base["reconciled"] = reconcile_readback_artifact(artifact)
        base["digest_reconciled"] = base["reconciled"]
        base["path"] = str(layout["readback"])
        base["metadata_hash"] = artifact["result"]["metadata_hash"]
        base["last_exec_seq"] = artifact["correlation"]["last_exec_seq"]
        return base
    except TimeoutError:
        return _readback_failure_result(
            base, "readback_timeout", layout=layout,
            target_identity=target_identity, snapshot=snapshot
        )
    except (ConnectionError, OSError):
        return _readback_failure_result(
            base,
            "artifact_write_failed" if base.get("status") == 200 and base.get("identity_match") else "readback_unreachable",
            layout=layout, target_identity=target_identity, snapshot=snapshot
        )
    except RuntimeError as exc:
        verdict = "malformed_response" if str(exc) == "MALFORMED_READBACK_RESPONSE" else "readback_unreachable"
        return _readback_failure_result(
            base, verdict, layout=layout,
            target_identity=target_identity, snapshot=snapshot
        )
    except (TypeError, ValueError, UnicodeError):
        return _readback_failure_result(
            base, "malformed_response", layout=layout,
            target_identity=target_identity, snapshot=snapshot
        )


def runtime_environment(
    layout: dict[str, Path],
    config_path: Path,
    task_path: Path,
    credentials: tuple[str, str],
    *,
    validity_backend: str = DEFAULT_VALIDITY_BACKEND,
) -> dict[str, str]:
    """Construct the complete run-scoped child environment."""

    child = sanitized_child_env(dict(os.environ))
    child.update(
        {
            "NV_TARGET_CONFIG": str(config_path),
            "NV_ENDPOINT_NAME": ENDPOINT_NAME,
            "NV_BODY_RULES": str(BODY_RULES_PATH),
            "NV_STATUS_PATH": str(layout["status"]),
            "NV_PROBE_PATH": str(layout["probe"]),
            "NV_STATE_DB": str(layout["state_db"]),
            "NV_CTX_PATH": str(layout["ctx"]),
            "NV_ERR_DIR": str(layout["err_dir"]),
            "NV_STATE_TRACE_PATH": str(layout["state_trace"]),
            "NV_BODY_VALID_STATS": str(layout["body_valid_stats"]),
            "NV_TASK_PATH": str(task_path),
            "NV_MAB_JOURNAL_PATH": str(layout["mab_journal"]),
            "NV_EXECUTION_LEDGER_PATH": str(Path(layout["evidence"]) / "executions.jsonl"),
            "NV_MULTIPART_UPLOADS_PATH": str(layout["multipart_uploads"]),
            "NV_SEED_SELECTION_AUDIT_PATH": str(layout["seed_selection_audit"]),
            # Keep the normal forkserver startup path (do NOT set
            # AFL_NO_STARTUP_CALIBRATION, which the current C core does not
            # reliably re-init for the first real fuzz case).  AFL_FAST_CAL
            # trims calibration cycles without bypassing forkserver init.
            "AFL_FAST_CAL": "1",
            "ALFRESCO_USER": credentials[0],
            "ALFRESCO_PASS": credentials[1],
            "NV_VALIDITY_BACKEND": validity_backend,
        }
    )
    try:
        task = json.loads(Path(task_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        task = {}
    if task.get("scenario") == "multipart_upload":
        child["NV_MULTIPART_MODE"] = "1"
        child["NV_ENDPOINT_NAME"] = "multipart_upload"
    return child


def artifact_contract(layout: dict[str, Path]) -> dict[str, dict[str, Path]]:
    """Return setup, execution and conditional artifact namespaces.

    The paths are derived from the current live producers: the Python
    harness writes status/sequence/body-valid/error artifacts, the state probe
    writes probe and state DB, the C runner writes the state trace, and AFL++
    writes ``fuzzer_stats`` under its output directory.  The setup seed marker
    follows the task's declared authority: a manifest run requires the
    manifest file and a materialized view, while the legacy mode requires the
    single generated ``seed.http`` file.
    """

    setup_required = {
        "target": layout["target_config"],
        "task": layout["task"],
        "seed_dir": layout["seed_dir"],
        "afl_output": layout["afl_output"],
        "evidence": layout["evidence"],
        "err_dir": layout["err_dir"],
    }
    try:
        task = json.loads(layout["task"].read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        task = {}
    if task.get("seed_source") == "manifest":
        setup_required["seed_manifest"] = Path(task.get("seed_manifest", ""))
    else:
        setup_required["seed"] = layout["seed"]

    execution_required = {
        "status": layout["status"],
        "status_seq": layout["status_seq"],
        "probe": layout["probe"],
        "state_db": layout["state_db"],
        "state_trace": layout["state_trace"],
        "afl_stats": layout["afl_output"] / "fuzzer_stats",
        "mab_journal": layout["mab_journal"],
        "seed_selection_audit": layout["seed_selection_audit"],
    }
    if task.get("scenario") == "multipart_upload":
        execution_required["multipart_uploads"] = layout["multipart_uploads"]
    else:
        execution_required["body_valid_stats"] = layout["body_valid_stats"]

    return {
        "setup_required": setup_required,
        "execution_required": execution_required,
        # Metadata body-only execution does not use the legacy context file.
        # It remains observable without masking the required contract.
        "conditional": {
            "ctx": layout["ctx"],
            "readback": layout["readback"],
        },
    }


def _artifact_present(name: str, path: Path) -> bool:
    directory_names = {"seed_dir", "afl_output", "evidence", "err_dir"}
    return Path(path).is_dir() if name in directory_names else Path(path).is_file()


def execution_ledger_path(layout: dict[str, Path]) -> Path:
    return Path(layout["evidence"]) / "executions.jsonl"


def _multi_arm_enabled(layout: dict[str, Path]) -> bool:
    try:
        task = json.loads(Path(layout["task"]).read_text(encoding="utf-8"))
        return len(task.get("mutation_scope", [])) > 1
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def parse_fuzzer_stats(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def parse_seed_selection_audit(path: Path) -> dict[str, object]:
    """Parse the strict, sanitized seed-selection JSONL artifact."""

    result: dict[str, object] = {
        "valid": True,
        "record_count": 0,
        "queue_ids": [],
        "per_queue_records": {},
        "malformed_count": 0,
        "partial_final_line": False,
        "duplicate_count": 0,
        "diagnostics": [],
    }
    diagnostics: list[str] = result["diagnostics"]  # type: ignore[assignment]
    fingerprints: set[str] = set()
    allowed = {
        "queue_id", "depth", "ss_cov_cnt", "ss_selected_cnt", "ss_prob",
    }
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        result["valid"] = False
        diagnostics.append(f"unreadable:{exc.__class__.__name__}")
        return result

    if data and not data.endswith(b"\n"):
        result["valid"] = False
        result["partial_final_line"] = True
        diagnostics.append("partial_final_line")

    for line_number, raw in enumerate(data.splitlines(), 1):
        if not raw:
            result["valid"] = False
            diagnostics.append(f"blank_line:{line_number}")
            continue
        try:
            record = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            result["valid"] = False
            result["malformed_count"] = int(result["malformed_count"]) + 1
            diagnostics.append(f"malformed_line:{line_number}")
            continue
        if not isinstance(record, dict) or set(record) != allowed:
            result["valid"] = False
            diagnostics.append(f"schema_violation:{line_number}")
            continue
        integer_fields = ("queue_id", "depth", "ss_cov_cnt", "ss_selected_cnt")
        if any(
            isinstance(record[field], bool) or not isinstance(record[field], int)
            for field in integer_fields
        ):
            result["valid"] = False
            diagnostics.append(f"integer_type:{line_number}")
            continue
        if (
            record["queue_id"] < 0
            or record["depth"] < 0
            or record["ss_cov_cnt"] < 0
            or record["ss_selected_cnt"] < 1
        ):
            result["valid"] = False
            diagnostics.append(f"integer_range:{line_number}")
            continue
        probability = record["ss_prob"]
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            result["valid"] = False
            diagnostics.append(f"probability_type:{line_number}")
            continue
        if not math.isfinite(float(probability)):
            result["valid"] = False
            diagnostics.append(f"probability_nonfinite:{line_number}")
            continue
        fingerprint = json.dumps(record, sort_keys=True, separators=(",", ":"))
        duplicate = fingerprint in fingerprints
        fingerprints.add(fingerprint)
        result["record_count"] = int(result["record_count"]) + 1
        queue_ids: list[int] = result["queue_ids"]  # type: ignore[assignment]
        queue_ids.append(record["queue_id"])
        per_queue: dict[int, list[int]] = result["per_queue_records"]  # type: ignore[assignment]
        per_queue.setdefault(record["queue_id"], []).append(record["ss_selected_cnt"])
        if duplicate:
            result["valid"] = False
            result["duplicate_count"] = int(result["duplicate_count"]) + 1
            diagnostics.append(f"duplicate_record:{line_number}")
            continue
    return result


def reconcile_seed_selection_audit(
    parsed: dict[str, object], stats: dict[str, str]
) -> dict[str, object]:
    """Reconcile JSONL records with producer-owned aggregate queue counters."""

    diagnostics: list[str] = list(parsed.get("diagnostics", []))  # type: ignore[arg-type]
    if not parsed.get("valid"):
        diagnostics.append("audit_invalid_records")
    try:
        expected = int(stats["ss_selected_sum"])
        producer_expected = int(stats["seed_audit_expected_selection_count"])
        producer_records = int(stats["seed_audit_record_count"])
        audit_enabled = int(stats["seed_audit_enabled"]) != 0
        error_count = int(stats["seed_audit_error_count"])
        audit_invalid = int(stats["seed_audit_invalid"]) != 0
    except (KeyError, ValueError):
        return {
            "reconciled": False,
            "diagnostics": ["missing_seed_selection_stats"],
            "expected_records": 0,
            "actual_records": int(parsed.get("record_count", 0)),
            "per_queue": {},
            "enabled": True,
            "error_count": 0,
            "audit_invalid": True,
            "malformed_count": int(parsed.get("malformed_count", 0)),
            "partial_final_line": bool(parsed.get("partial_final_line", False)),
            "missing_record_count": 0,
            "extra_record_count": 0,
            "duplicate_or_out_of_order_count": 0,
        }

    actual = int(parsed.get("record_count", 0))
    if not audit_enabled:
        diagnostics.append("seed_audit_not_enabled_by_fuzzer")
    if expected < 0:
        diagnostics.append("negative_expected_selection_count")
    if producer_expected != expected:
        diagnostics.append("producer_expected_selection_count_mismatch")
    if producer_records != actual:
        diagnostics.append("producer_record_count_mismatch")
    if expected != actual:
        diagnostics.append(
            "missing_selection_records" if actual < expected
            else "extra_selection_records"
        )
        if expected > 0 and actual == 0:
            diagnostics.append("selected_seeds_missing_audit_records")

    if error_count or audit_invalid:
        diagnostics.append("seed_audit_marked_invalid_by_fuzzer")

    expected_per_queue: dict[int, int] = {}
    for key, value in stats.items():
        if not key.startswith("ss_selected_queue_"):
            continue
        try:
            queue_id = int(key.removeprefix("ss_selected_queue_"))
            expected_per_queue[queue_id] = int(value)
        except ValueError:
            diagnostics.append(f"invalid_queue_selection_stat:{key}")

    if expected and not expected_per_queue:
        diagnostics.append("missing_per_queue_selection_stats")
    if sum(expected_per_queue.values()) != expected:
        diagnostics.append("per_queue_selection_total_mismatch")

    observed_per_queue: dict[int, list[int]] = parsed.get("per_queue_records", {})  # type: ignore[assignment]
    all_queue_ids = set(expected_per_queue) | set(observed_per_queue)
    per_queue: dict[str, dict[str, int]] = {}
    duplicate_or_out_of_order = 0
    for queue_id in sorted(all_queue_ids):
        expected_count = expected_per_queue.get(queue_id, 0)
        observed = observed_per_queue.get(queue_id, [])
        per_queue[str(queue_id)] = {
            "expected": expected_count,
            "observed": len(observed),
        }
        if queue_id not in expected_per_queue:
            diagnostics.append(f"queue_id_not_in_source:{queue_id}")
        if len(observed) != expected_count:
            diagnostics.append(f"queue_selection_count_mismatch:{queue_id}")
        if observed != list(range(1, expected_count + 1)):
            diagnostics.append(f"queue_selection_sequence_mismatch:{queue_id}")
            duplicate_or_out_of_order += 1

    return {
        "reconciled": not diagnostics,
        "diagnostics": diagnostics,
        "expected_records": expected,
        "actual_records": actual,
        "per_queue": per_queue,
        "enabled": audit_enabled,
        "error_count": error_count,
        "audit_invalid": audit_invalid,
        "malformed_count": int(parsed.get("malformed_count", 0)),
        "partial_final_line": bool(parsed.get("partial_final_line", False)),
        "duplicate_count": int(parsed.get("duplicate_count", 0)),
        "missing_record_count": max(expected - actual, 0),
        "extra_record_count": max(actual - expected, 0),
        "duplicate_or_out_of_order_count": duplicate_or_out_of_order,
    }


def parse_mab_journal(path: Path) -> dict[str, object]:
    """Parse the bounded C-side JSONL journal without tolerating corruption."""

    result: dict[str, object] = {
        "valid": True, "record_count": 0, "update_count": 0,
        "pending_cleared_count": 0, "mismatch_count": 0,
        "last_update_exec_seq": 0, "per_arm_pulls": [0, 0, 0],
        "per_arm_reward_sums": [0.0, 0.0, 0.0],
        "per_arm_positive": [0, 0, 0], "diagnostics": [],
    }
    diagnostics: list[str] = result["diagnostics"]  # type: ignore[assignment]
    valid_clear_reasons = {
        "budget_boundary", "stop_soon", "timeout", "invalid_input", "skip",
        "invalid_exec_identity", "pending_no_exec_id",
    }
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        result["valid"] = False
        diagnostics.append(f"unreadable:{exc.__class__.__name__}")
        return result

    if data and not data.endswith(b"\n"):
        result["valid"] = False
        diagnostics.append("partial_final_line")
    seen_updates: set[tuple[int, int]] = set()
    for line_number, raw in enumerate(data.splitlines(), 1):
        if not raw:
            result["valid"] = False
            diagnostics.append(f"blank_line:{line_number}")
            continue
        try:
            record = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            result["valid"] = False
            diagnostics.append(f"malformed_line:{line_number}")
            continue
        if not isinstance(record, dict) or record.get("schema_version") != 1:
            result["valid"] = False
            diagnostics.append(f"unsupported_schema:{line_number}")
            continue
        event = record.get("event")
        if event not in {"mab_update", "mab_pending_cleared", "mab_update_mismatch"}:
            result["valid"] = False
            diagnostics.append(f"unknown_event:{line_number}")
            continue
        result["record_count"] = int(result["record_count"]) + 1
        if event == "mab_pending_cleared":
            if record.get("reason") not in valid_clear_reasons:
                result["valid"] = False
                result["record_count"] = int(result["record_count"]) - 1
                diagnostics.append(f"unknown_reason:{line_number}")
                continue
            result["pending_cleared_count"] = int(result["pending_cleared_count"]) + 1
            continue
        if event == "mab_update_mismatch":
            result["mismatch_count"] = int(result["mismatch_count"]) + 1
            continue
        required = {"exec_seq", "selected_arm", "actual_used_arm", "arm_match", "reward", "reward_components", "pulls_before", "pulls_after", "sum_before", "sum_after", "mean_after", "positive_after", "update_source"}
        if not required.issubset(record) or record.get("arm_match") is not True:
            result["valid"] = False
            diagnostics.append(f"invalid_update:{line_number}")
            continue
        try:
            exec_seq, arm = int(record["exec_seq"]), int(record["actual_used_arm"])
            reward = float(record["reward"])
        except (TypeError, ValueError):
            result["valid"] = False
            diagnostics.append(f"invalid_update_values:{line_number}")
            continue
        key = (exec_seq, arm)
        if arm not in range(3) or exec_seq <= 0 or not math.isfinite(reward) or key in seen_updates:
            result["valid"] = False
            diagnostics.append(f"duplicate_or_invalid_update:{line_number}")
            continue
        seen_updates.add(key)
        result["update_count"] = int(result["update_count"]) + 1
        result["last_update_exec_seq"] = exec_seq
        pulls: list[int] = result["per_arm_pulls"]  # type: ignore[assignment]
        sums: list[float] = result["per_arm_reward_sums"]  # type: ignore[assignment]
        positive: list[int] = result["per_arm_positive"]  # type: ignore[assignment]
        pulls[arm] += 1
        sums[arm] += reward
        if reward > 0:
            positive[arm] += 1
    return result


def reconcile_mab_journal(parsed: dict[str, object], stats: dict[str, str]) -> dict[str, object]:
    """Reconcile complete update records with the C-side aggregate counters."""

    diagnostics: list[str] = []
    if not parsed.get("valid"):
        diagnostics.append("journal_invalid")
    try:
        expected_total = int(stats["nv_mab_total_pulls"])
        expected_last = int(stats["security_state_reward_src_seq"])
        expected_pending = int(stats.get("nv_mab_pending", "0"))
        expected_errors = int(stats.get("nv_mab_journal_error_count", "0"))
        expected_invalid = int(stats.get("nv_mab_journal_audit_invalid", "0"))
    except (KeyError, ValueError):
        return {"reconciled": False, "diagnostics": ["missing_journal_stats"]}
    if int(parsed["update_count"]) != expected_total:
        diagnostics.append("total_pulls_mismatch")
    if expected_total and int(parsed["last_update_exec_seq"]) != expected_last:
        diagnostics.append("last_exec_seq_mismatch")
    if expected_pending:
        diagnostics.append("pending_update_not_cleared")
    for arm in range(3):
        try:
            pulls = int(stats[f"nv_mab_arm{arm}_pulls"])
            total = float(stats[f"nv_mab_arm{arm}_sum"])
            positive = int(stats[f"nv_mab_arm{arm}_pos"])
        except (KeyError, ValueError):
            diagnostics.append(f"missing_arm{arm}_stats")
            continue
        if int(parsed["per_arm_pulls"][arm]) != pulls:  # type: ignore[index]
            diagnostics.append(f"arm{arm}_pulls_mismatch")
        if not math.isclose(float(parsed["per_arm_reward_sums"][arm]), total, abs_tol=1e-9):  # type: ignore[index]
            diagnostics.append(f"arm{arm}_sum_mismatch")
        if int(parsed["per_arm_positive"][arm]) != positive:  # type: ignore[index]
            diagnostics.append(f"arm{arm}_positive_mismatch")
    if expected_errors or expected_invalid:
        diagnostics.append("journal_marked_invalid_by_fuzzer")
    return {"reconciled": not diagnostics, "diagnostics": diagnostics}


def parse_execution_ledger(path: Path) -> dict[str, object]:
    """Parse append-only execution lifecycle evidence, fail-closed."""
    result: dict[str, object] = {
        "valid": True, "record_count": 0, "counted_execution_count": 0,
        "harness_invocation_count": 0, "target_invocation_count": 0,
        "status_observed_count": 0, "committed_update_count": 0,
        "pending_cleanup_count": 0, "mismatch_count": 0,
        "invalid_execution_identity_count": 0,
        "unobserved_execution_count": 0,
        "validation_reject_count": 0, "diagnostics": [],
    }
    diagnostics: list[str] = result["diagnostics"]  # type: ignore[assignment]
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        result["valid"] = False
        diagnostics.append(f"unreadable:{exc.__class__.__name__}")
        return result
    if data and not data.endswith(b"\n"):
        result["valid"] = False
        diagnostics.append("partial_final_line")
    outcomes = {"committed_update", "mab_commit_failed", "pending_cleanup", "arm_mismatch",
                "invalid_exec_identity", "body_validation_reject",
                "target_execution_no_mab"}
    for line_number, raw in enumerate(data.splitlines(), 1):
        try:
            record = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            result["valid"] = False; diagnostics.append(f"malformed_line:{line_number}"); continue
        required = {"schema_version", "event", "iteration_id", "selected_arm",
                    "actual_used_arm", "arm_match", "counted_execution",
                    "harness_invoked", "target_invoked", "body_validated",
                    "status_observed", "exec_seq", "mab_outcome"}
        if (not isinstance(record, dict) or record.get("schema_version") != 1 or
                record.get("event") != "execution" or not required.issubset(record) or
                not isinstance(record.get("iteration_id"), int) or record["iteration_id"] <= 0 or
                record.get("mab_outcome") not in outcomes):
            result["valid"] = False; diagnostics.append(f"invalid_record:{line_number}"); continue
        if record["mab_outcome"] == "pending_cleanup":
            reason = record.get("pending_cleanup_reason")
            if not isinstance(reason, str) or not reason:
                result["valid"] = False
                diagnostics.append(f"cleanup_reason_missing:{line_number}")
            if record["exec_seq"] is not None:
                result["valid"] = False
                diagnostics.append(f"cleanup_identity_present:{line_number}")
        result["record_count"] = int(result["record_count"]) + 1
        for field, key in (("counted_execution", "counted_execution_count"),
                           ("harness_invoked", "harness_invocation_count"),
                           ("target_invoked", "target_invocation_count"),
                           ("status_observed", "status_observed_count")):
            if record[field]: result[key] = int(result[key]) + 1
        outcome = record["mab_outcome"]
        key = {"committed_update": "committed_update_count",
               "pending_cleanup": "pending_cleanup_count",
               "arm_mismatch": "mismatch_count",
               "body_validation_reject": "validation_reject_count"}.get(outcome)
        if key: result[key] = int(result[key]) + 1
        if outcome == "invalid_exec_identity":
            result["invalid_execution_identity_count"] = int(result["invalid_execution_identity_count"]) + 1
        if record["counted_execution"] and not record["status_observed"]:
            result["unobserved_execution_count"] = int(result["unobserved_execution_count"]) + 1
        seq = record["exec_seq"]
        if record["status_observed"] != (isinstance(seq, int) and not isinstance(seq, bool) and seq > 0):
            result["valid"] = False; diagnostics.append(f"status_identity_mismatch:{line_number}")
        if record["target_invoked"] and not record["status_observed"] and outcome not in {"invalid_exec_identity", "pending_cleanup"}:
            result["valid"] = False; diagnostics.append(f"target_without_terminal_status:{line_number}")
        if outcome == "committed_update" and (not record["status_observed"] or not record["arm_match"]):
            result["valid"] = False; diagnostics.append(f"invalid_commit:{line_number}")
        if outcome == "mab_commit_failed":
            diagnostics.append(f"mab_commit_failed:{line_number}")
            result["valid"] = False
    return result


def reconcile_execution_ledger(parsed: dict[str, object], stats: dict[str, str] | None = None) -> dict[str, object]:
    """Return domain-separated ledger counts; never equate execution domains."""
    diagnostics = list(parsed.get("diagnostics", []))
    if not parsed.get("valid"): diagnostics.append("execution_ledger_invalid")
    if stats and int(stats.get("nv_mab_journal_audit_invalid", "0")):
        diagnostics.append("aggregate_ledger_mismatch")
    if stats:
        expected = {
            "committed_update_count": stats.get("nv_mab_total_pulls"),
            "pending_cleanup_count": stats.get("nv_mab_journal_pending_cleared_count"),
            "mismatch_count": stats.get("nv_mab_journal_mismatch_count"),
        }
        for field, raw in expected.items():
            if raw is not None and int(parsed.get(field, 0)) != int(raw):
                diagnostics.append(f"{field}_stats_mismatch")
    return {"reconciled": not diagnostics, "diagnostics": diagnostics,
            "counted_execution_count": parsed.get("counted_execution_count", 0),
            "target_execution_count": parsed.get("target_invocation_count", 0),
            "status_observed_count": parsed.get("status_observed_count", 0),
            "committed_update_count": parsed.get("committed_update_count", 0)}


def inspect_artifacts(
    layout: dict[str, Path],
    launch_returncode: int | None = None,
    readback: dict[str, object] | None = None,
) -> dict[str, object]:
    """Inspect artifacts without manufacturing or touching missing evidence.

    Execution artifacts become applicable only for a zero launch return code.
    A non-zero launch is reported as a launch failure and preserves the
    original return code; setup artifacts are checked regardless of launch
    outcome.  ``execution_proved`` is an independent marker based on the
    producer outputs, not on the return code alone.
    """

    contract = artifact_contract(layout)
    present: list[str] = []
    missing_setup: list[str] = []
    missing_execution: list[str] = []
    missing_conditional: list[str] = []

    for level, entries in contract.items():
        for name, path in entries.items():
            if _artifact_present(name, path):
                present.append(name)
            elif level == "setup_required":
                missing_setup.append(name)
            elif level == "execution_required":
                missing_execution.append(name)
            else:
                missing_conditional.append(name)

    execution_applicable = launch_returncode == 0
    missing_required = list(missing_setup)
    if execution_applicable:
        missing_required.extend(missing_execution)

    execution_markers = contract["execution_required"]
    execution_proved = all(
        _artifact_present(name, execution_markers[name])
        for name in ("status", "status_seq", "afl_stats")
    )

    if launch_returncode is None:
        final_result = "pass" if not missing_required else "artifact_contract_failed"
    elif launch_returncode == 124:
        final_result = "timeout"
    elif launch_returncode != 0:
        final_result = "launch_failed"
    elif missing_required:
        final_result = "artifact_contract_failed"
    else:
        final_result = "pass"

    paths = {
        name: str(path)
        for entries in contract.values()
        for name, path in entries.items()
    }
    journal_summary: dict[str, object] = {
        "enabled": layout["mab_journal"].is_file(),
        "path": str(layout["mab_journal"]),
        "present": layout["mab_journal"].is_file(),
        "required": True,
    }
    if launch_returncode == 0 and layout["mab_journal"].is_file() and (layout["afl_output"] / "fuzzer_stats").is_file():
        parsed = parse_mab_journal(layout["mab_journal"])
        reconciliation = reconcile_mab_journal(parsed, parse_fuzzer_stats(layout["afl_output"] / "fuzzer_stats"))
        journal_summary.update(parsed)
        journal_summary.update(reconciliation)
        if not reconciliation["reconciled"]:
            missing_required.append("mab_journal_reconciliation")
            final_result = "artifact_contract_failed"
    ledger_path = execution_ledger_path(layout)
    # Every successful execution needs lifecycle evidence, including single-arm runs.
    ledger_required = True
    ledger_summary: dict[str, object] = {
        "enabled": ledger_path.is_file(), "path": str(ledger_path),
        "present": ledger_path.is_file(), "required": ledger_required,
    }
    if launch_returncode == 0 and ledger_required and ledger_path.is_file():
        parsed_ledger = parse_execution_ledger(ledger_path)
        ledger_summary.update(parsed_ledger)
        ledger_summary.update(reconcile_execution_ledger(
            parsed_ledger, parse_fuzzer_stats(layout["afl_output"] / "fuzzer_stats")
            if (layout["afl_output"] / "fuzzer_stats").is_file() else None))
        if (int(ledger_summary.get("committed_update_count", 0)) !=
                int(journal_summary.get("update_count", 0))):
            ledger_summary.setdefault("diagnostics", []).append("ledger_journal_update_mismatch")
            ledger_summary["reconciled"] = False
        if (int(ledger_summary.get("pending_cleanup_count", 0)) !=
                int(journal_summary.get("pending_cleared_count", 0))):
            ledger_summary.setdefault("diagnostics", []).append("ledger_journal_cleanup_mismatch")
            ledger_summary["reconciled"] = False
        if (int(ledger_summary.get("mismatch_count", 0)) !=
                int(journal_summary.get("mismatch_count", 0))):
            ledger_summary.setdefault("diagnostics", []).append("ledger_journal_mismatch_count")
            ledger_summary["reconciled"] = False
        if not ledger_summary.get("reconciled"):
            missing_required.append("execution_ledger_reconciliation")
            final_result = "artifact_contract_failed"
        if not ledger_summary.get("valid") or not ledger_summary.get("reconciled"):
            execution_proved = False
        if int(ledger_summary.get("unobserved_execution_count", 0)):
            execution_proved = False
    elif launch_returncode == 0 and ledger_required:
        missing_required.append("execution_ledger")
        final_result = "artifact_contract_failed"
        execution_proved = False
    seed_audit_summary: dict[str, object] = {
        "enabled": True,
        "path": str(layout["seed_selection_audit"]),
        "present": layout["seed_selection_audit"].is_file(),
        "required": True,
    }
    if launch_returncode == 0 and layout["seed_selection_audit"].is_file():
        parsed = parse_seed_selection_audit(layout["seed_selection_audit"])
        seed_audit_summary.update(parsed)
        if (layout["afl_output"] / "fuzzer_stats").is_file():
            reconciliation = reconcile_seed_selection_audit(
                parsed, parse_fuzzer_stats(layout["afl_output"] / "fuzzer_stats")
            )
            seed_audit_summary.update(reconciliation)
            if not reconciliation["reconciled"]:
                seed_audit_summary["valid"] = False
                missing_required.append("seed_selection_audit_integrity")
                final_result = "artifact_contract_failed"
        elif not seed_audit_summary["valid"]:
            missing_required.append("seed_selection_audit_integrity")
            final_result = "artifact_contract_failed"

        try:
            task_payload = json.loads(layout["task"].read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            task_payload = {}
        if task_payload.get("seed_source") == "manifest":
            selected_queue_ids = set(seed_audit_summary.get("queue_ids", []))
            seed_audit_summary["manifest_multi_seed"] = True
            seed_audit_summary["distinct_selected_queue_count"] = len(selected_queue_ids)
            if len(selected_queue_ids) < 2:
                seed_audit_summary.setdefault("diagnostics", []).append(
                    "insufficient_distinct_seed_selection"
                )
                seed_audit_summary["reconciled"] = False
                seed_audit_summary["valid"] = False
                missing_required.append("multi_seed_selection_evidence")
                final_result = "artifact_contract_failed"
    if readback is None:
        # Direct artifact inspection is also used by launch-level offline
        # tests.  The complete runner passes the post-run result explicitly;
        # only that path can establish that read-back was attempted.
        readback = _readback_base(applicable=False)
    else:
        readback = dict(readback)
    readback_artifact_valid = True
    readback_artifact_diagnostic = None
    if _artifact_present("readback", layout["readback"]):
        if "readback" not in present:
            present.append("readback")
        if "readback" in missing_conditional:
            missing_conditional.remove("readback")
        try:
            artifact = _read_json_object(
                layout["readback"], "READBACK_ARTIFACT_INVALID"
            )
        except RuntimeError:
            artifact = None
        if artifact is None or not validate_readback_artifact(artifact):
            readback_artifact_valid = False
            readback_artifact_diagnostic = "readback_artifact_invalid"
        else:
            correlation = artifact["correlation"]
            target = artifact["target"]
            expected_last_exec_seq = readback.get("last_exec_seq")
            expected_valid_count = readback.get("valid_execution_count")
            expected_node_identity = readback.get("node_identity")
            expected_parent_identity = readback.get("parent_identity")
            expected_name = readback.get("target_name")
            if launch_returncode == 0:
                try:
                    snapshot = parse_final_execution_snapshot(layout)
                except RuntimeError:
                    readback_artifact_valid = False
                    readback_artifact_diagnostic = "readback_artifact_invalid"
                else:
                    expected_last_exec_seq = snapshot["last_exec_seq"]
                    expected_valid_count = snapshot["valid_execution_count"]
            if (
                isinstance(expected_last_exec_seq, int)
                and correlation["last_exec_seq"] != expected_last_exec_seq
            ) or (
                isinstance(expected_valid_count, int)
                and correlation["valid_execution_count"] != expected_valid_count
            ) or (
                isinstance(expected_node_identity, str)
                and target["node_identity"] != expected_node_identity
            ) or (
                isinstance(expected_parent_identity, str)
                and target["parent_identity"] != expected_parent_identity
            ) or (
                isinstance(expected_name, str)
                and target["name"] != expected_name
            ) or (
                isinstance(readback.get("metadata_hash"), str)
                and artifact["result"]["metadata_hash"]
                != readback["metadata_hash"]
            ):
                readback_artifact_valid = False
                readback_artifact_diagnostic = "readback_artifact_invalid"
    readback["artifact_valid"] = readback_artifact_valid
    readback["artifact_diagnostic"] = readback_artifact_diagnostic
    if not readback_artifact_valid:
        if "readback" not in missing_required:
            missing_required.append("readback")
        if launch_returncode == 0:
            final_result = "artifact_contract_failed"
    if readback.get("applicable") and (
        readback.get("verdict") != "pass"
        or not readback.get("present")
        or not readback.get("reconciled")
        or not readback.get("artifact_valid")
        or not _artifact_present("readback", layout["readback"])
    ):
        if "readback" not in missing_required:
            missing_required.append("readback")
        if launch_returncode == 0:
            final_result = "artifact_contract_failed"
    return {
        "ok": final_result == "pass",
        "setup_required": {name: str(path) for name, path in contract["setup_required"].items()},
        "execution_required": {name: str(path) for name, path in contract["execution_required"].items()},
        "conditional": {name: str(path) for name, path in contract["conditional"].items()},
        "present": sorted(present),
        "missing_required": sorted(missing_required),
        "missing_setup_required": sorted(missing_setup),
        "missing_execution_required": sorted(missing_execution),
        "missing_conditional": sorted(missing_conditional),
        "execution_applicable": execution_applicable,
        "execution_proved": execution_proved,
        "launch_returncode": launch_returncode,
        "final_result": final_result,
        "paths": paths,
        "mab_journal": journal_summary,
        "execution_ledger": ledger_summary,
        "seed_selection_audit": seed_audit_summary,
        "readback": readback,
    }


def runner_result_path(layout: dict[str, Path]) -> Path:
    """Return the current run's artifact report, where runner evidence lives."""

    run_root = Path(layout["run_root"]).resolve()
    evidence = Path(layout["evidence"]).resolve()
    destination = evidence / "artifact_report.json"
    if evidence != run_root / "evidence" or not evidence.is_relative_to(run_root):
        raise OSError("RUNNER_RESULT_PATH_INVALID")
    return destination


def validate_runner_result(report: dict[str, object]) -> bool:
    """Validate the independent runner result section without accepting null as success."""

    runner = report.get("runner") if isinstance(report, dict) else None
    if not isinstance(runner, dict) or set(runner) != {"exit_code", "exit_status", "recorded"}:
        return False
    code = runner["exit_code"]
    status = runner["exit_status"]
    recorded = runner["recorded"]
    if not isinstance(recorded, bool) or not isinstance(status, str) or not status:
        return False
    if recorded:
        if not isinstance(code, int) or isinstance(code, bool) or code < 0:
            return False
        return status == "success" if code == 0 else status not in {
            "success", "evidence_unavailable",
        }
    return code is None and status == "evidence_unavailable"


def _runner_status(exit_code: int, artifact_final_result: str) -> str:
    if exit_code == 0 and artifact_final_result == "pass":
        return "success"
    if exit_code == 124 or artifact_final_result == "timeout":
        return "timeout"
    if artifact_final_result == "launch_failed":
        return "launch_failed"
    if artifact_final_result == "artifact_contract_failed":
        return "artifact_contract_failed"
    if artifact_final_result == "setup_contract_failed":
        return "setup_contract_failed"
    if artifact_final_result == "readback_failed":
        return "readback_failed"
    return "runner_failed"


def _runner_report(
    report: dict[str, object],
    *,
    runner_exit_code: int,
    runner_exit_status: str | None = None,
) -> dict[str, object]:
    """Add independent runner evidence while retaining child and contract fields."""

    result = dict(report)
    result["schema_version"] = 2
    final_result = str(result.get("final_result", "runner_failed"))
    result["readback_verdict"] = str(result.get("readback", {}).get("verdict", "unavailable"))
    result["artifact_final_result"] = final_result
    result["runner"] = {
        "exit_code": int(runner_exit_code),
        "exit_status": runner_exit_status or _runner_status(runner_exit_code, final_result),
        "recorded": True,
    }
    return result


def write_artifact_report(layout: dict[str, Path], report: dict[str, object]) -> None:
    """Write a sanitized report only into the current run's evidence dir."""

    evidence = Path(layout["evidence"])
    if not evidence.is_dir():
        return
    destination = runner_result_path(layout)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=evidence,
            prefix=".artifact-report-", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def ensure_fresh_run_root(run_root: Path) -> None:
    """Reject reuse of a non-empty evidence namespace."""

    run_root = Path(run_root)
    if run_root.exists() and any(run_root.iterdir()):
        raise ValueError("RUN_ROOT_NOT_FRESH")
    run_root.mkdir(parents=True, exist_ok=True)


def _unavailable_runner_report(
    *, reason: str, launch_returncode: int | None = None
) -> dict[str, object]:
    """Describe a run whose final runner result could not be published."""

    return {
        "schema_version": 2,
        "runner": {
            "exit_code": None,
            "exit_status": "evidence_unavailable",
            "recorded": False,
        },
        "runner_failure_reason": reason,
        "launch_returncode": launch_returncode,
        "readback_verdict": "unavailable",
        "artifact_final_result": "evidence_unavailable",
    }


def _publish_runner_report(layout: dict[str, Path], report: dict[str, object]) -> None:
    """Publish a report and verify that the run-scoped result exists."""

    write_artifact_report(layout, report)
    if not runner_result_path(layout).is_file():
        raise OSError("RUNNER_RESULT_NOT_RECORDED")


def initialize_mab_journal(layout: dict[str, Path]) -> Path:
    """Create the required empty run-scoped journal before AFL launch."""

    try:
        Path(layout["evidence"]).mkdir(parents=True, exist_ok=True)
        layout["mab_journal"].touch(exist_ok=False)
    except OSError as exc:
        raise RuntimeError("MAB_JOURNAL_SETUP_FAILED") from exc
    return layout["mab_journal"]


def initialize_seed_selection_audit(layout: dict[str, Path]) -> Path:
    """Create the bounded run's empty seed-selection audit before AFL launch."""

    try:
        Path(layout["evidence"]).mkdir(parents=True, exist_ok=True)
        layout["seed_selection_audit"].touch(exist_ok=False)
    except OSError as exc:
        raise RuntimeError("SEED_SELECTION_AUDIT_SETUP_FAILED") from exc
    return layout["seed_selection_audit"]


def build_alfresco_client(base: str, credentials: tuple[str, str]):
    """Construct the read-only Alfresco client for the pinned local endpoint.

    Injectable: offline tests replace this with a fake client so that no real
    network call is ever made.  The real client object performs no I/O at
    construction time -- it only stores the endpoint, credentials and a
    proxy-disabled opener.
    """

    levelc = _load_levelc_metadata_module()
    return levelc.AlfrescoClient(base, credentials)


def perform_preflight(client) -> dict:
    """Run the Level-C preflight (container health + 401/200 root probes).

    Injectable: offline tests replace this to avoid docker/HTTP side effects.
    Returns the preflight summary, or raises ``RuntimeError`` on failure.
    """

    levelc = _load_levelc_metadata_module()
    return levelc.preflight(client)


def launch_bounded_afl(
    layout: dict[str, Path],
    config_path: Path,
    child_env: dict[str, str],
    *,
    max_test_cases: int,
    time_budget: int,
) -> int:
    """Spawn a bounded afl-fuzz campaign over the production harness.

    Injectable: offline tests replace this with a recorder so that no real
    afl-fuzz process is ever started and no network is contacted.  The
    production path mirrors ``scripts/run_p0_mab_feedback_experiment.sh`` but
    is bounded by ``max_test_cases`` (authoritative) and ``time_budget`` (a
    safety fuse only, never the primary budget).
    """

    if isinstance(max_test_cases, bool) or int(max_test_cases) <= 0:
        raise ValueError("INVALID_MAX_TEST_CASES")
    if isinstance(time_budget, bool) or int(time_budget) <= 0:
        raise ValueError("INVALID_TIME_BUDGET")

    afl_bin = Path(AFL_BINARY)
    if not afl_bin.is_file():
        raise RuntimeError("AFL_BINARY_MISSING")
    if not (afl_bin.stat().st_mode & 0o111):
        raise RuntimeError("AFL_BINARY_NOT_EXECUTABLE")

    seed_dir = layout["seed_dir"]

    cmd = [
        str(afl_bin),
        "-n",            # security-state coverage is the signal, not native edges
        "-m", "none",
    ]
    try:
        task_payload = json.loads(Path(layout["task"]).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        task_payload = {}
    manifest_seed_run = task_payload.get("seed_source") == "manifest"
    if manifest_seed_run:
        # A bounded manifest run must visit the initial queue entries in order
        # so its selection audit can prove that multiple manifest seeds ran.
        cmd.append("-Z")
    cmd.extend([
        "-i", str(seed_dir),
        "-o", str(layout["afl_output"]),
        "--",
    ])
    cmd.extend(build_harness_command_for_scenario(task_payload))

    env = dict(child_env)
    if manifest_seed_run:
        env["NV_KEEP_INITIAL_SEEDS"] = "1"
    env["NV_TARGET_CONFIG"] = str(config_path)
    env["NV_SEED_SELECTION_AUDIT_PATH"] = str(layout["seed_selection_audit"])
    env.setdefault("AFL_NO_UI", "1")
    env.setdefault("AFL_SKIP_CPUFREQ", "1")
    env.setdefault("AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES", "1")
    env.setdefault("AFL_PYTHON_MODULE", "nv_json_mutator")

    # afl-fuzz links libpython; point the loader at the same interpreter it
    # was built against, mirroring the audited P0 launcher.
    py_libdir = sysconfig.get_config_var("LIBDIR") or ""
    if py_libdir:
        existing = env.get("LD_LIBRARY_PATH")
        env["LD_LIBRARY_PATH"] = (
            py_libdir + (":" + existing if existing else "")
        )
    existing_pp = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(REPO_ROOT) + (":" + existing_pp if existing_pp else "")

    hard_timeout = time_budget + 60
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            cwd=str(layout["run_root"]),
            timeout=hard_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124
    except (FileNotFoundError, PermissionError, OSError) as exc:
        raise RuntimeError("AFL_LAUNCH_FAILED") from exc
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded Alfresco metadata real-feedback orchestrator.",
    )
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument(
        "--scenario",
        choices=("metadata_update", "multipart_upload"),
        default="metadata_update",
    )
    parser.add_argument("--run-root", default=None)
    parser.add_argument(
        "--max-test-cases", type=int, default=DEFAULT_MAX_TEST_CASES,
    )
    parser.add_argument(
        "--time-budget", type=int, default=DEFAULT_TIME_BUDGET,
    )
    parser.add_argument(
        "--mutation-scope", default=None,
        help=(
            "Comma-separated NV-MAB arms to enable: field_value, boundary, "
            "structure. Default: field_value only."
        ),
    )
    parser.add_argument(
        "--validity-backend",
        choices=VALIDITY_BACKENDS,
        default=DEFAULT_VALIDITY_BACKEND,
    )
    parser.add_argument(
        "--target-file-name",
        default=None,
        help=(
            "Existing file name under the dedicated Alfresco folder. "
            "Default: nv-afl-levelc-metadata.txt."
        ),
    )
    parser.add_argument(
        "--seed-manifest",
        default=None,
        help="Filename-only manifest controlling a multi-seed run.",
    )
    parser.add_argument(
        "--seed-source-dir",
        default=None,
        help="Directory containing the regular files listed by --seed-manifest.",
    )
    args = parser.parse_args(argv)

    # Scope gate: fail-closed before credentials, client creation,
    # preflight, node resolution, or any file/AFL launch.
    try:
        mutation_scope = parse_mutation_scope(args.mutation_scope)
        target_file_name = validate_target_file_name(args.target_file_name)
        if args.scenario == "multipart_upload" and args.target_file_name is not None:
            raise ValueError("MULTIPART_TARGET_SELECTOR_UNSUPPORTED")
        if args.scenario == "multipart_upload" and args.seed_manifest is None:
            raise ValueError("MULTIPART_MANIFEST_REQUIRED")
        if (args.seed_manifest is None) != (args.seed_source_dir is None):
            raise ValueError("MANIFEST_SOURCE_CONFIGURATION_INCOMPLETE")
        if args.seed_manifest is not None:
            load_manifest_seed_names(Path(args.seed_manifest))
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # R-credential gate: fail-closed before any service contact.
    try:
        credentials = runtime_credentials()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        base = validate_base_url(ALFRESCO_BASE_URL)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.preflight_only:
        try:
            client = build_alfresco_client(base, credentials)
            perform_preflight(client)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 3
        print("PREFLIGHT=PASS")
        return 0

    # Full bounded run.
    layout: dict[str, Path] | None = None
    try:
        repo_root = REPO_ROOT
        run_root = Path(args.run_root) if args.run_root else default_run_root()
        layout = build_run_layout(run_root, repo_root)
        ensure_fresh_run_root(layout["run_root"])
        layout["evidence"].mkdir(parents=True, exist_ok=True)
        _publish_runner_report(
            layout, _unavailable_runner_report(reason="runner_in_progress")
        )

        # Validate the requested budgets before contacting the service.
        if args.max_test_cases <= 0:
            raise ValueError("INVALID_MAX_TEST_CASES")
        if args.time_budget <= 0:
            raise ValueError("INVALID_TIME_BUDGET")

        # The full-run order is a contract: no node lookup or artifact render
        # is allowed until credentials, endpoint and the complete preflight
        # have passed.
        client = build_alfresco_client(base, credentials)
        perform_preflight(client)
        if args.scenario == "multipart_upload":
            resolved = resolve_existing_dedicated_parent(client)
            parent_identity = read_only_target_identity(client, resolved["folder_id"])
            target_identity = {
                "node_id": resolved["folder_id"],
                "parent_id": str(parent_identity["parentId"]),
                "name": str(parent_identity["name"]),
            }
        elif args.target_file_name is None:
            resolved = resolve_existing_dedicated_node(client)
        else:
            resolved = resolve_existing_dedicated_node(client, target_file_name)
        if args.scenario == "multipart_upload":
            expected_parent_id = str(parent_identity["parentId"])
            expected_target_name = str(parent_identity["name"])
        else:
            preflight_identity = read_only_target_identity(client, resolved["file_id"])
            expected_parent_id = str(
                resolved.get("parent_id") or resolved["folder_id"]
            )
        if args.scenario != "multipart_upload":
            expected_target_name = str(
                resolved.get("target_name")
                or target_file_name
            )
        if any(
            not isinstance((parent_identity if args.scenario == "multipart_upload" else preflight_identity).get(field), str)
            or not (parent_identity if args.scenario == "multipart_upload" else preflight_identity)[field]
            for field in ("id", "parentId", "name")
        ):
            raise RuntimeError("DEDICATED_TARGET_IDENTITY_INCOMPLETE")
        if args.scenario == "multipart_upload":
            if parent_identity["id"] != str(resolved["folder_id"]):
                raise RuntimeError("DEDICATED_PARENT_IDENTITY_MISMATCH")
            if parent_identity["parentId"] != expected_parent_id:
                raise RuntimeError("DEDICATED_PARENT_PARENT_IDENTITY_MISMATCH")
            if parent_identity["name"] != expected_target_name:
                raise RuntimeError("DEDICATED_PARENT_NAME_IDENTITY_MISMATCH")
            config_path = render_multipart_runtime_config(
                resolved["folder_id"], layout["target_config"]
            )
        else:
            if preflight_identity["id"] != str(resolved["file_id"]):
                raise RuntimeError("DEDICATED_TARGET_IDENTITY_MISMATCH")
            if preflight_identity["parentId"] != expected_parent_id:
                raise RuntimeError("DEDICATED_TARGET_PARENT_IDENTITY_MISMATCH")
            if preflight_identity["name"] != expected_target_name:
                raise RuntimeError("DEDICATED_TARGET_NAME_IDENTITY_MISMATCH")
            target_identity = {
                "node_id": preflight_identity["id"],
                "parent_id": preflight_identity["parentId"],
                "name": preflight_identity["name"],
            }
            config_path = render_runtime_target_config(
                resolved["file_id"], layout["target_config"]
            )

        # Materialise only after all service gates have passed.
        layout["afl_output"].mkdir(parents=True, exist_ok=True)
        initialize_mab_journal(layout)
        initialize_seed_selection_audit(layout)
        layout["err_dir"].mkdir(parents=True, exist_ok=True)
        if args.seed_manifest is None:
            write_initial_seed(config_path, layout["seed_dir"])
            seed_source = "seed_file"
            seed_manifest = None
        else:
            materialize_manifest_seed_dir(
                Path(args.seed_manifest),
                Path(args.seed_source_dir),
                layout["seed_dir"],
            )
            seed_source = "manifest"
            seed_manifest = Path(args.seed_manifest)
        task = build_task_payload(
            layout["seed_dir"],
            max_test_cases=args.max_test_cases,
            time_budget=args.time_budget,
            mutation_scope=mutation_scope,
            target_file_name=(target_identity["name"] if args.target_file_name is not None else None),
            seed_source=seed_source,
            seed_manifest=seed_manifest,
            scenario=args.scenario,
            input_format=("full_http_multipart" if args.scenario == "multipart_upload" else "full_http"),
            parent_node_id=(resolved["folder_id"] if args.scenario == "multipart_upload" else None),
            validity_backend=args.validity_backend,
        )
        layout["task"].write_text(
            json.dumps(task, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )

        # Setup artifacts are a launch gate.  Do not invoke AFL when any
        # target/task/seed/output/evidence namespace entry is missing.
        setup_report = inspect_artifacts(layout)
        if setup_report["missing_required"]:
            setup_report["final_result"] = "setup_contract_failed"
            setup_report["feedback_source"] = "real_alfresco_feedback"
            setup_report = _runner_report(
                setup_report, runner_exit_code=ARTIFACT_CONTRACT_FAILURE
            )
            _publish_runner_report(layout, setup_report)
            print(ARTIFACT_CONTRACT_FAILED, file=sys.stderr)
            return ARTIFACT_CONTRACT_FAILURE

        child_env = runtime_environment(
            layout, config_path, layout["task"], credentials,
            validity_backend=args.validity_backend,
        )

        rc = launch_bounded_afl(
            layout,
            config_path,
            child_env,
            max_test_cases=args.max_test_cases,
            time_budget=args.time_budget,
        )
        if args.scenario == "multipart_upload":
            upload_report = inspect_multipart_artifacts(
                layout, launch_returncode=int(rc)
            )
            successful_records = upload_report.get("successful_records", [])
            if isinstance(successful_records, list):
                readback_result = verify_multipart_readback(client, successful_records)
            else:
                readback_result = {"status": "FAIL", "verified_count": 0, "total_count": 0, "records": []}
            write_multipart_readback_artifact(layout, readback_result)
            if not multipart_readback_is_complete(layout, upload_report):
                upload_report.setdefault("missing_required", []).append("multipart_readback")
                upload_report["ok"] = False
            report = inspect_artifacts(layout, launch_returncode=int(rc))
            report["multipart"] = upload_report
            report["multipart_readback"] = readback_result
            if rc == 0 and not upload_report["ok"]:
                report["missing_required"].append("multipart_contract")
                report["final_result"] = "artifact_contract_failed"
                report["ok"] = False
            report["target_binding"] = {
                "parent_identity": _identity_digest("parent", target_identity["node_id"]),
            }
        else:
            try:
                readback = post_execution_readback(client, target_identity, layout)
            except Exception as exc:
                # Keep the child result distinct while making an unexpected
                # read-back failure visible to the final runner contract.
                readback = _readback_failure_result(
                    _readback_base(applicable=True), "readback_exception"
                )
                readback["attempted"] = True
                readback["exception_class"] = exc.__class__.__name__
            report = inspect_artifacts(
                layout, launch_returncode=int(rc), readback=readback
            )
            report["target_binding"] = {
                "target_file_name": target_identity["name"],
                "node_identity": _identity_digest("node", target_identity["node_id"]),
                "parent_identity": _identity_digest("parent", target_identity["parent_id"]),
            }
        report["feedback_source"] = "real_alfresco_feedback"
        if rc != 0:
            runner_exit_code = int(rc)
        elif not report["ok"]:
            runner_exit_code = (
                READBACK_CONTRACT_FAILURE
                if report["readback"].get("attempted")
                and report["readback"].get("verdict") not in {"pass", "not_applicable"}
                and "readback" in report["missing_required"]
                else ARTIFACT_CONTRACT_FAILURE
            )
        else:
            runner_exit_code = 0
        report = _runner_report(
            report,
            runner_exit_code=runner_exit_code,
            runner_exit_status=(
                "readback_failed" if runner_exit_code == READBACK_CONTRACT_FAILURE else None
            ),
        )
        try:
            _publish_runner_report(layout, report)
        except (OSError, TypeError, ValueError) as exc:
            print(f"NOT_RECORDED: {exc}", file=sys.stderr)
            return RUNNER_EXCEPTION_FAILURE
        if runner_exit_code != 0:
            print(ARTIFACT_CONTRACT_FAILED, file=sys.stderr)
            return runner_exit_code
        return 0
    except ValueError as exc:
        # Layout / run-root / target-policy violations: config class.
        if layout is not None and Path(layout["evidence"]).is_dir():
            try:
                failure = _unavailable_runner_report(reason=exc.__class__.__name__)
                failure["runner"] = {
                    "exit_code": 2,
                    "exit_status": "runner_failed",
                    "recorded": True,
                }
                _publish_runner_report(layout, failure)
            except (OSError, TypeError, ValueError) as write_exc:
                print(f"NOT_RECORDED: {write_exc}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 2
    except RuntimeError as exc:
        # Service / resolution / render / launch failures: service class.
        if layout is not None and Path(layout["evidence"]).is_dir():
            try:
                failure = _unavailable_runner_report(reason=exc.__class__.__name__)
                failure["runner"] = {
                    "exit_code": 3,
                    "exit_status": "runner_failed",
                    "recorded": True,
                }
                _publish_runner_report(layout, failure)
            except (OSError, TypeError, ValueError) as write_exc:
                print(f"NOT_RECORDED: {write_exc}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 3
    except Exception as exc:
        if layout is not None and Path(layout["evidence"]).is_dir():
            try:
                failure = _unavailable_runner_report(reason=exc.__class__.__name__)
                failure["runner"] = {
                    "exit_code": RUNNER_EXCEPTION_FAILURE,
                    "exit_status": "runner_failed",
                    "recorded": True,
                }
                _publish_runner_report(layout, failure)
            except (OSError, TypeError, ValueError) as write_exc:
                print(f"NOT_RECORDED: {write_exc}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return RUNNER_EXCEPTION_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
