#!/usr/bin/env python3
"""One-shot Alfresco multipart bounded reproduction entry.

The command is intentionally a small, bounded experiment driver.  It does not
schedule campaigns, retry indefinitely, or manage long-running services.
Credentials are inherited by child processes and are never serialized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

_REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORT))
import subprocess
import sys
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DIR = REPO_ROOT / "in" / "alfresco_multipart_upload_bounded"
RUNNER = REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py"
SCOPES = ("field_value", "boundary", "structure")
POSITIVE_NAMES = ("seed_0.http", "seed_1.http", "seed_2.http")
NEGATIVE_NAMES = ("negative_boundary_mismatch.http", "negative_missing_filedata.http")


def _load_module(name: str, path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"MODULE_LOAD_FAILED:{name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def validate_canonical_seed_set(root: Path = CANONICAL_DIR) -> dict[str, object]:
    """Validate the checked-in positive and negative multipart seed assets."""

    root = Path(root).resolve()
    manifest_path = root / "manifest.txt"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("CANONICAL_MANIFEST_NOT_REGULAR")
    names = manifest_path.read_text(encoding="utf-8").splitlines()
    if names != list(POSITIVE_NAMES):
        raise ValueError("CANONICAL_MANIFEST_UNEXPECTED_CONTENT")
    if len(set(names)) != len(names):
        raise ValueError("CANONICAL_MANIFEST_DUPLICATE")

    harness = _load_module("multipart_reproduction_harness", REPO_ROOT / "nv_http_harness.py")
    positive_parseable = True
    regular_files = True
    hashes: dict[str, str] = {}
    for name in names:
        path = root / name
        regular_files = regular_files and path.is_file() and not path.is_symlink()
        if not regular_files:
            positive_parseable = False
            continue
        hashes[name] = _digest(path)
        try:
            parsed = harness.parse_multipart_http_seed(path.read_bytes())
            fields = parsed.get("fields", {})
            positive_parseable = positive_parseable and (
                parsed.get("method") == "POST"
                and parsed.get("filename")
                and fields.get("name")
                and fields.get("nodeType") == "cm:content"
                and fields.get("autoRename", "").lower() == "true"
                and isinstance(parsed.get("file_bytes"), bytes)
            )
        except Exception:
            positive_parseable = False

    negative_rejected = True
    for name in NEGATIVE_NAMES:
        path = root / name
        if not path.is_file() or path.is_symlink():
            negative_rejected = False
            continue
        try:
            harness.parse_multipart_http_seed(path.read_bytes())
        except Exception:
            pass
        else:
            negative_rejected = False

    return {
        "manifest": str(manifest_path),
        "positive_names": list(names),
        "negative_names": list(NEGATIVE_NAMES),
        "positive_count": len(names),
        "regular_files": regular_files,
        "exact_manifest_view": sorted(
            p.name for p in root.iterdir() if p.is_file() and p.name in names
        ) == sorted(names),
        "positive_parseable": positive_parseable,
        "negative_rejected": negative_rejected,
        "sha256": hashes,
    }


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def run_negative_validation(
    *,
    canonical_root: Path,
    output_root: Path,
    client,
    parent_id: str | None = None,
    before_children: int | None = None,
) -> dict[str, object]:
    """Run negative seeds through the real harness contract without upload."""

    harness = _load_module(
        "multipart_negative_validation_harness", REPO_ROOT / "nv_http_harness.py"
    )
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    upload_path = output_root / "multipart_uploads.jsonl"
    status_path = output_root / "status.jsonl"
    old_upload_path = os.environ.get("NV_MULTIPART_UPLOADS_PATH")
    records: list[dict[str, object]] = []
    statuses: list[dict[str, object]] = []
    sequence = 0

    def status_writer(**kwargs):
        nonlocal sequence
        sequence += 1
        status = {
            "exec_seq": sequence,
            "method": str(kwargs.get("method", "POST")),
            "path": str(kwargs.get("path", "")),
            "http_code": int(kwargs.get("http_code", 0) or 0),
            "validation_reject": int(kwargs.get("validation_reject", 0) or 0),
        }
        statuses.append(status)
        with status_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(status, sort_keys=True) + "\n")
        return status

    try:
        os.environ["NV_MULTIPART_UPLOADS_PATH"] = str(upload_path)
        for name in NEGATIVE_NAMES:
            result = harness.run_multipart_seed(
                (Path(canonical_root) / name).read_bytes(),
                client=client,
                status_writer=status_writer,
            )
            records.append({"seed": name, **{
                key: result.get(key)
                for key in (
                    "validation_reject", "target_invoked", "status_observed",
                    "http_status", "exec_seq", "reject_reason",
                )
            }})
    finally:
        if old_upload_path is None:
            os.environ.pop("NV_MULTIPART_UPLOADS_PATH", None)
        else:
            os.environ["NV_MULTIPART_UPLOADS_PATH"] = old_upload_path

    after_children = None
    list_children = getattr(client, "list_children", None)
    observed_parent_id = str(parent_id or getattr(client, "parent_node_id", ""))
    if callable(list_children) and observed_parent_id:
        parent_id = observed_parent_id
        try:
            after_children = len(list_children(observed_parent_id))
        except Exception:
            after_children = None

    parent_children_observed = (
        before_children is not None and after_children is not None
    )
    passed = parent_children_observed and all(
        record.get("validation_reject") is True
        and record.get("target_invoked") is False
        and record.get("http_status") == 0
        for record in records
    )
    if before_children is not None and after_children is not None:
        passed = passed and before_children == after_children
    result = {
        "status": "pass" if passed else "failed",
        "http_sent": 0,
        "nodes_created": 0 if after_children is None or before_children is None else after_children - before_children,
        "validation_rejects": sum(1 for record in records if record.get("validation_reject") is True),
        "records": records,
        "status_records": len(statuses),
        "before_children": before_children,
        "after_children": after_children,
        "parent_children_observed": parent_children_observed,
    }
    _write_report(output_root / "negative_validation_report.json", result)
    return result


def _default_negative_runner(*, output_root: Path, canonical_root: Path) -> dict[str, object]:
    """Run negative inputs against the real local service boundary.

    The preflight and parent child-count reads are real service reads.  The
    harness parser rejects both inputs before the injected client can issue a
    POST, so this stage proves zero mutation requests and zero created nodes.
    """

    bounded = _load_module(
        "multipart_reproduction_bounded_runner",
        REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py",
    )
    credentials = bounded.runtime_credentials()
    base = bounded.validate_base_url(bounded.ALFRESCO_BASE_URL)
    client = bounded.build_alfresco_client(base, credentials)
    bounded.perform_preflight(client)
    parent = bounded.resolve_existing_dedicated_parent(client)
    parent_id = str(parent["folder_id"])
    before = len(client.list_children(parent_id))
    result = run_negative_validation(
        canonical_root=canonical_root,
        output_root=output_root / "negative_validation",
        client=client,
        parent_id=parent_id,
        before_children=before,
    )
    result["service_preflight"] = "PASS"
    result["parent_bound"] = True
    result["parent_children_unchanged"] = result.get("before_children") == result.get("after_children")
    return result


def _default_arm_runner(
    *,
    mutation_scope: str,
    run_root: Path,
    canonical_root: Path,
    max_test_cases: int,
    time_budget: int,
) -> dict[str, object]:
    manifest = canonical_root / "manifest.txt"
    command = [
        sys.executable,
        str(RUNNER),
        "--scenario", "multipart_upload",
        "--run-root", str(run_root),
        "--mutation-scope", mutation_scope,
        "--seed-manifest", str(manifest),
        "--seed-source-dir", str(canonical_root),
        "--max-test-cases", str(max_test_cases),
        "--time-budget", str(time_budget),
    ]
    environment = dict(os.environ)
    completed = subprocess.run(command, cwd=str(REPO_ROOT), env=environment, check=False)
    report_path = run_root / "evidence" / "artifact_report.json"
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if isinstance(report, dict):
                return {
                    "status": "pass" if completed.returncode == 0 and report.get("artifact_final_result") == "pass" else "failed",
                    "mutation_scope": mutation_scope,
                    "runner_exit_code": completed.returncode,
                    "run_root": str(run_root),
                    "artifact_final_result": report.get("artifact_final_result"),
                    "report_path": str(report_path),
                }
        except (OSError, UnicodeDecodeError, ValueError):
            pass
    return {
        "status": "failed",
        "mutation_scope": mutation_scope,
        "runner_exit_code": completed.returncode,
        "run_root": str(run_root),
        "artifact_final_result": "evidence_unavailable",
    }


def reproduce(
    *,
    repo_root: Path = REPO_ROOT,
    output_root: Path,
    allow_real_write: bool = False,
    negative_runner: Callable[..., dict[str, object]] | None = None,
    arm_runner: Callable[..., dict[str, object]] | None = None,
    max_test_cases: int = 12,
    time_budget: int = 45,
) -> dict[str, object]:
    repo_root = Path(repo_root).resolve()
    canonical_root = repo_root / "in" / "alfresco_multipart_upload_bounded"
    output_root = Path(output_root).resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("REPRODUCTION_OUTPUT_NOT_FRESH")
    output_root.mkdir(parents=True, exist_ok=True)
    seed_report = validate_canonical_seed_set(canonical_root)
    report: dict[str, object] = {
        "schema_version": 1,
        "scenario": "alfresco_multipart_upload",
        "status": "dry_run_pass" if not allow_real_write else "running",
        "execution_order": ["negative", *SCOPES],
        "canonical_seed": seed_report,
        "stages": [],
    }
    if not allow_real_write:
        _write_report(output_root / "multipart_reproduction_report.json", report)
        return report

    negative = (negative_runner or _default_negative_runner)(
        output_root=output_root,
        canonical_root=canonical_root,
    )
    report["stages"].append({"stage": "negative", **negative})
    if negative.get("status") != "pass":
        report.update({"status": "failed", "failed_stage": "negative"})
        _write_report(output_root / "multipart_reproduction_report.json", report)
        return report

    for scope in SCOPES:
        run_root = output_root / "runs" / scope
        run_root.mkdir(parents=True, exist_ok=True)
        result = (arm_runner or _default_arm_runner)(
            mutation_scope=scope,
            run_root=run_root,
            canonical_root=canonical_root,
            max_test_cases=max_test_cases,
            time_budget=time_budget,
        )
        report["stages"].append({"stage": scope, **result})
        if result.get("status") != "pass":
            report.update({"status": "failed", "failed_stage": scope})
            _write_report(output_root / "multipart_reproduction_report.json", report)
            return report

    report["status"] = "pass"
    _write_report(output_root / "multipart_reproduction_report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-shot Alfresco multipart bounded reproduction")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--allow-real-write", action="store_true")
    parser.add_argument("--max-test-cases", type=int, default=12)
    parser.add_argument("--time-budget", type=int, default=45)
    args = parser.parse_args(argv)
    try:
        report = reproduce(
            repo_root=Path(args.repo_root),
            output_root=Path(args.output_root),
            allow_real_write=args.allow_real_write,
            max_test_cases=args.max_test_cases,
            time_budget=args.time_budget,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "output_root": str(Path(args.output_root).resolve())}, ensure_ascii=False))
    return 0 if report["status"] in {"dry_run_pass", "pass"} else 4


if __name__ == "__main__":
    raise SystemExit(main())
