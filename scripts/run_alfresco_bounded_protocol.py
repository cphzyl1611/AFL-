"""Serial, fail-closed A/B/C protocol for Alfresco bounded feedback runs."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Callable, Iterator


PROTOCOL_ENTRIES = (
    ("A", "nv-afl-levelc-metadata.txt", "field_value"),
    ("B", "nv-afl-levelc-metadata-arm1.txt", "boundary"),
    ("C", "nv-afl-levelc-metadata-arm2.txt", "structure"),
)


class _FileLock:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.handle = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            self.handle.close()
            self.handle = None
            raise RuntimeError("PROTOCOL_LOCK_HELD")

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


@contextlib.contextmanager
def acquire_protocol_lock(lock_path: Path) -> Iterator[None]:
    lock = _FileLock(Path(lock_path))
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def _validate_external_path(path: Path, repo_root: Path, name: str) -> Path:
    value = _resolved(path)
    repo = _resolved(repo_root)
    if value == repo or value.is_relative_to(repo):
        raise ValueError(f"{name}_INSIDE_GIT_WORKTREE")
    return value


def build_single_run_command(
    *,
    runner: Path,
    run_root: Path,
    target_file_name: str,
    mutation_scope: str,
    seed_manifest: Path | None = None,
    seed_source_dir: Path | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(_resolved(runner)),
        "--run-root",
        str(_resolved(run_root)),
        "--target-file-name",
        target_file_name,
        "--mutation-scope",
        mutation_scope,
    ]
    if (seed_manifest is None) != (seed_source_dir is None):
        raise ValueError("MANIFEST_SOURCE_CONFIGURATION_INCOMPLETE")
    if seed_manifest is not None and seed_source_dir is not None:
        command.extend(
            [
                "--seed-manifest",
                str(_resolved(seed_manifest)),
                "--seed-source-dir",
                str(_resolved(seed_source_dir)),
            ]
        )
    return command


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _child_report_is_success(
    report_path: Path, *, target_file_name: str, mutation_scope: str, run_root: Path
) -> bool:
    report = _read_json(report_path)
    if report is None or report.get("ok") is not True:
        return False
    if report.get("artifact_final_result") != "pass":
        return False
    runner = report.get("runner")
    if not isinstance(runner, dict) or runner != {
        "exit_code": 0,
        "exit_status": "success",
        "recorded": True,
    }:
        return False
    for name in ("execution_ledger", "mab_journal"):
        evidence = report.get(name)
        if not isinstance(evidence, dict):
            return False
        if evidence.get("required") is not True:
            return False
        if evidence.get("present") is not True or evidence.get("reconciled") is not True:
            return False
    readback = report.get("readback")
    if not isinstance(readback, dict) or not (
        readback.get("applicable") is True
        and readback.get("attempted") is True
        and readback.get("present") is True
        and readback.get("reconciled") is True
        and readback.get("artifact_valid") is True
        and readback.get("verdict") == "pass"
    ):
        return False
    binding = report.get("target_binding")
    if not isinstance(binding, dict) or binding.get("target_file_name") != target_file_name:
        return False
    task = _read_json(run_root / "task.json")
    return task is not None and task.get("mutation_scope") == [mutation_scope]


def _write_summary(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run_protocol(
    *,
    repo_root: Path,
    output_root: Path,
    runner: Path,
    seed_manifest: Path | None = None,
    seed_source_dir: Path | None = None,
    command_runner: Callable[[list[str]], int] | None = None,
) -> dict[str, object]:
    repo = _resolved(repo_root)
    output = _validate_external_path(Path(output_root), repo, "PROTOCOL_OUTPUT")
    runner_path = _resolved(runner)
    if not runner_path.is_file():
        raise ValueError("RUNNER_NOT_FOUND")
    if (seed_manifest is None) != (seed_source_dir is None):
        raise ValueError("MANIFEST_SOURCE_CONFIGURATION_INCOMPLETE")
    if seed_manifest is not None:
        manifest_path = _resolved(seed_manifest)
        source_path = _resolved(seed_source_dir)
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValueError("MANIFEST_NOT_REGULAR")
        if not source_path.is_dir() or source_path.is_symlink():
            raise ValueError("MANIFEST_SOURCE_NOT_DIRECTORY")
    else:
        manifest_path = None
        source_path = None
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise ValueError("PROTOCOL_OUTPUT_NOT_FRESH")
    else:
        output.mkdir(parents=True)
    runs_root = output / "runs"
    runs_root.mkdir()
    lock_path = output / "protocol.lock"
    invoke = command_runner or (lambda command: subprocess.run(command, check=False).returncode)
    entries: list[dict[str, object]] = []
    target_identities: set[str] = set()
    result: dict[str, object]

    try:
        with acquire_protocol_lock(lock_path):
            for label, target_file_name, mutation_scope in PROTOCOL_ENTRIES:
                run_root = runs_root / label
                run_root.mkdir()
                command = build_single_run_command(
                    runner=runner_path,
                    run_root=run_root,
                    target_file_name=target_file_name,
                    mutation_scope=mutation_scope,
                    seed_manifest=manifest_path,
                    seed_source_dir=source_path,
                )
                return_code = int(invoke(command))
                report_path = run_root / "evidence" / "artifact_report.json"
                report = _read_json(report_path)
                identity = None
                if isinstance(report, dict):
                    binding = report.get("target_binding")
                    if isinstance(binding, dict) and isinstance(binding.get("node_identity"), str):
                        identity = binding["node_identity"]
                entry = {
                    "label": label,
                    "target_file_name": target_file_name,
                    "mutation_scope": mutation_scope,
                    "run_root": str(run_root),
                    "return_code": return_code,
                    "report_path": str(report_path),
                    "target_identity": identity,
                    "success": return_code == 0 and _child_report_is_success(
                        report_path,
                        target_file_name=target_file_name,
                        mutation_scope=mutation_scope,
                        run_root=run_root,
                    ),
                }
                entries.append(entry)
                if entry["success"] and identity is not None:
                    if identity in target_identities:
                        result = {
                            "schema_version": 1,
                            "protocol": "alfresco_bounded_single_arm_abc",
                            "status": "failed",
                            "failure": "TARGET_IDENTITY_NOT_DISTINCT",
                            "failed_entry": label,
                            "entries": entries,
                        }
                        _write_summary(output / "protocol_report.json", result)
                        return result
                    target_identities.add(identity)
                if not entry["success"]:
                    result = {
                        "schema_version": 1,
                        "protocol": "alfresco_bounded_single_arm_abc",
                        "status": "failed",
                        "failed_entry": label,
                        "entries": entries,
                    }
                    _write_summary(output / "protocol_report.json", result)
                    return result
    except RuntimeError as exc:
        if str(exc) != "PROTOCOL_LOCK_HELD":
            raise
        result = {
            "schema_version": 1,
            "protocol": "alfresco_bounded_single_arm_abc",
            "status": "failed",
            "failure": "PROTOCOL_LOCK_HELD",
            "entries": [],
        }
        _write_summary(output / "protocol_report.json", result)
        return result

    result = {
        "schema_version": 1,
        "protocol": "alfresco_bounded_single_arm_abc",
        "status": "pass",
        "entries": entries,
    }
    _write_summary(output / "protocol_report.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Alfresco bounded A/B/C protocol serially.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--runner", default=None)
    parser.add_argument("--seed-manifest", default=None)
    parser.add_argument("--seed-source-dir", default=None)
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[1]
    runner = Path(args.runner) if args.runner else repo_root / "scripts" / "run_alfresco_bounded_feedback.py"
    try:
        result = run_protocol(
            repo_root=repo_root,
            output_root=Path(args.output_root),
            runner=runner,
            seed_manifest=Path(args.seed_manifest) if args.seed_manifest else None,
            seed_source_dir=Path(args.seed_source_dir) if args.seed_source_dir else None,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
