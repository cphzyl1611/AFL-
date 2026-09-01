#!/usr/bin/env python3
import argparse
import base64
import csv
import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path


def _canonical_root(value, name: str, *, require_existing=False) -> Path:
    if value is None or not str(value).strip():
        raise ValueError(f"{name} is required")
    root = Path(value)
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    if require_existing and not root.exists():
        raise ValueError(f"{name} does not exist")
    if root.exists() and not root.is_dir():
        raise ValueError(f"{name} must be a directory")
    return root


def validate_roots(repo_root, run_root) -> tuple[Path, Path]:
    repo = _canonical_root(repo_root, "repo_root", require_existing=True)
    run = _canonical_root(run_root, "run_root")
    worktree = None
    for parent in (repo, *repo.parents):
        if (parent / ".git").exists():
            worktree = parent
            break
    if worktree is None:
        raise ValueError("repo_root must be a Git worktree")
    if repo == run or run.is_relative_to(worktree):
        raise ValueError("run_root must be outside repo_root")
    return repo, run


def _safe_path(value, root: Path, name: str) -> Path:
    if value is None or not str(value).strip():
        raise ValueError(f"{name} must not be empty")
    raw = Path(value)
    if ".." in raw.parts:
        raise ValueError(f"{name} must not contain path traversal")
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError(f"{name} escapes its root")
    return resolved


def _resolve_task_json(value, repo_root: Path, run_root: Path) -> Path:
    if value is None or not str(value).strip():
        raise ValueError("task_json must not be empty")
    raw = Path(value)
    if ".." in raw.parts:
        raise ValueError("task_json must not contain path traversal")
    if raw.is_absolute():
        candidate = raw
    else:
        candidate = repo_root / raw
    resolved = candidate.resolve(strict=False)
    if resolved.is_relative_to(repo_root) or (
        raw.is_absolute() and resolved.is_relative_to(run_root)
    ):
        return resolved
    raise ValueError("task_json must be inside repo_root or run_root")


def resolve_repo_path(value, repo_root) -> Path:
    return _safe_path(value, _canonical_root(repo_root, "repo_root"), "repo path")


def resolve_run_path(value, run_root) -> Path:
    return _safe_path(value, _canonical_root(run_root, "run_root"), "run path")


def _reject_source_seed_dir_symlinks(value, repo_root: Path) -> None:
    """Check the supplied seed directory lexically before resolving it."""
    raw = Path(value)
    if raw.is_absolute():
        lexical = raw
    else:
        lexical = repo_root / raw
    if ".." in raw.parts:
        raise ValueError("seed_dir must not contain path traversal")
    try:
        relative = lexical.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("seed_dir escapes repo_root") from exc

    current = repo_root
    for component in relative.parts:
        current /= component
        try:
            if stat.S_ISLNK(os.lstat(current).st_mode):
                raise ValueError(
                    f"seed_dir path component must not be a symlink: {component}"
                )
        except FileNotFoundError:
            break


def resolve_manifest_seed_paths(seed_dir_value, manifest_value, *, repo_root) -> list[Path]:
    repo_root = _canonical_root(repo_root, "repo_root", require_existing=True)
    _reject_source_seed_dir_symlinks(seed_dir_value, repo_root)
    seed_dir = resolve_repo_path(seed_dir_value, repo_root)
    manifest = resolve_repo_path(manifest_value, repo_root)
    if not seed_dir.is_dir():
        raise ValueError("seed_dir must be an existing directory")
    if not manifest.is_file():
        raise ValueError("manifest must be an existing file")

    seeds = []
    seen = set()
    for line_number, raw_line in enumerate(
        manifest.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise ValueError(f"invalid manifest entry at line {line_number}")
        relative = Path(parts[0])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"manifest seed path is unsafe at line {line_number}")
        lexical_seed = seed_dir / relative
        current = seed_dir
        for component in relative.parts:
            current = current / component
            if current.is_symlink():
                raise ValueError(f"manifest seed source must not be a symlink at line {line_number}")
        seed = lexical_seed.resolve(strict=False)
        if not seed.is_relative_to(seed_dir) or not seed.is_relative_to(repo_root):
            raise ValueError(f"manifest seed path escapes seed_dir at line {line_number}")
        if seed in seen:
            raise ValueError(f"duplicate manifest seed at line {line_number}")
        if not seed.is_file() or not stat.S_ISREG(seed.stat().st_mode):
            raise ValueError(f"manifest seed is missing at line {line_number}")

        metadata = {}
        for field in parts[2:]:
            if "=" in field:
                key, value = field.split("=", 1)
                metadata[key.strip().lower()] = value.strip()
        if "size" in metadata and seed.stat().st_size != int(metadata["size"]):
            raise ValueError(f"manifest seed size mismatch at line {line_number}")
        if "sha256" in metadata:
            import hashlib

            digest = hashlib.sha256(seed.read_bytes()).hexdigest()
            if digest != metadata["sha256"].lower():
                raise ValueError(f"manifest seed hash mismatch at line {line_number}")

        seen.add(seed)
        seeds.append(seed)

    if not seeds:
        raise ValueError("manifest must contain at least one seed")
    return seeds


def materialize_manifest_seed_dir(task_obj: dict, *, repo_root, run_dir) -> Path:
    manifest = task_obj.get("manifest")
    if not manifest:
        repo_root = _canonical_root(repo_root, "repo_root", require_existing=True)
        _reject_source_seed_dir_symlinks(
            task_obj.get("seed_dir", "in/o2oa_body_cms_score"), repo_root
        )
        return resolve_repo_path(task_obj.get("seed_dir", "in/o2oa_body_cms_score"), repo_root)

    seeds = resolve_manifest_seed_paths(
        task_obj.get("seed_dir", "in/o2oa_body_cms_score"),
        manifest,
        repo_root=repo_root,
    )
    repo_root = _canonical_root(repo_root, "repo_root", require_existing=True)
    run_dir = Path(run_dir).resolve(strict=False)
    if run_dir.is_relative_to(repo_root):
        raise ValueError("manifest seed view must be outside repo_root")
    view = run_dir / "manifest_seeds"
    if view.exists() and view.is_symlink():
        raise ValueError("manifest seed view must not be a symlink")
    view.mkdir(parents=True, exist_ok=True)
    names = set()
    manifest_names = set()
    for index, seed in enumerate(seeds, 1):
        if seed.name in names:
            raise ValueError(f"manifest seed basenames must be unique: {seed.name}")
        names.add(seed.name)
        # Manifest-order zero-padded prefix keeps directory iteration order
        # identical to manifest order, so AFL queue ids map deterministically
        # onto manifest entries and the seed-selection audit stays auditable.
        destination_name = f"{index:04d}__{seed.name}"
        manifest_names.add(destination_name)
        destination = view / destination_name
        if destination.is_symlink() or (
            destination.exists() and not destination.is_file()
        ):
            raise ValueError(f"manifest seed view entry is not a regular file: {destination.name}")
        if destination.exists():
            if destination.read_bytes() != seed.read_bytes():
                raise ValueError(f"manifest seed view entry already exists: {destination.name}")
            continue

        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=view, prefix=f".{seed.name}.", delete=False
            ) as handle:
                temporary = Path(handle.name)
                with seed.open("rb") as source:
                    shutil.copyfileobj(source, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except Exception:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise

        if not destination.is_file() or destination.is_symlink():
            raise ValueError(f"manifest seed materialization is not a regular file: {destination.name}")

    for entry in view.iterdir():
        if entry.name not in manifest_names:
            raise ValueError(f"manifest seed view contains an extra entry: {entry.name}")
    return view


def build_run_layout(run_root, repo_root, task_id: str = "preview") -> dict[str, Path]:
    repo, run = validate_roots(repo_root, run_root)
    if not task_id or Path(str(task_id)).name != str(task_id):
        raise ValueError("invalid task_id")
    task_root = resolve_run_path("tasks", run)
    task_dir = resolve_run_path(f"tasks/{task_id}", run)
    run_dir = resolve_run_path(f"runs/{task_id}", run)
    afl_out_dir = resolve_run_path(f"runs/{task_id}/afl_out", run)
    stdout = resolve_run_path(f"runs/{task_id}/stdout.log", run)
    stderr = resolve_run_path(f"runs/{task_id}/stderr.log", run)
    evidence = resolve_run_path(f"runs/{task_id}/evidence", run)
    return {
        "repo_root": repo,
        "run_root": run,
        "task_root": task_root,
        "task_dir": task_dir,
        "run_dir": run_dir,
        "afl_out_dir": afl_out_dir,
        "stdout": stdout,
        "stderr": stderr,
        "evidence": evidence,
    }


def _task_dir(run_root: Path, task_id: str) -> Path:
    if not task_id or Path(str(task_id)).name != str(task_id):
        raise ValueError("invalid task_id")
    return resolve_run_path(f"tasks/{task_id}", run_root)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"refusing to write through symlink: {path}")
    payload = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def path_exists_str(p: str, repo_root) -> bool:
    if not p:
        return False
    return resolve_repo_path(p, repo_root).exists()


def is_pid_alive(pid: int) -> bool:
    proc_stat = Path(f"/proc/{pid}/stat")
    try:
        if proc_stat.exists():
            state = proc_stat.read_text(encoding="ascii").split()[2]
            if state == "Z":
                return False
    except (OSError, IndexError):
        pass
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


TERMINAL_STATUSES = {"exited", "failed", "timed_out", "stopped"}


def _sanitize_failure_reason(reason: str) -> str:
    text = str(reason or "").lower()
    if not text.strip():
        return ""
    if "missing_fuzzer_stats" in text:
        return "missing_fuzzer_stats"
    if re.search(r"no[ _-]+usable[ _-]+test", text):
        return "no_usable_test_cases"
    if "timeout" in text or "timed out" in text:
        return "runner_timeout"
    if "popen" in text or "no such file" in text:
        return "child_popen_failed"
    if re.fullmatch(r"runner_exit_code_-?\d+", text):
        return text
    if text in {"runner_stopped", "supervisor_failed", "supervisor_lost"}:
        return text
    return "runner_failed"


def _write_status_fallback(path: Path, status: dict, error: Exception) -> None:
    fallback = dict(status)
    fallback.update(
        {
            "status": "failed",
            "failure_reason": "status_write_failed",
            "status_write_error": _sanitize_failure_reason(str(error)),
            "recorded": False,
            "status_artifact": "fallback",
            "supervisor_exit_code": 70,
            "updated_at": now_str(),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(fallback, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _save_supervisor_status(
    status_path: Path, status: dict, *, fallback_path: Path
) -> bool:
    try:
        save_json(status_path, status)
        return True
    except Exception as error:
        try:
            _write_status_fallback(fallback_path, status, error)
        except Exception as fallback_error:
            print(
                f"status_write_failed: fallback_write_failed: "
                f"{_sanitize_failure_reason(str(fallback_error))}",
                file=sys.stderr,
                flush=True,
            )
        else:
            print(
                "status_write_failed: supervisor status written to independent fallback",
                file=sys.stderr,
                flush=True,
            )
        return False


def _load_observable_status(status_path: Path) -> dict:
    status = load_json(status_path)
    fallback_value = status.get("status_fallback_path")
    if not fallback_value:
        return status
    fallback_path = Path(fallback_value)
    if not fallback_path.is_absolute():
        fallback_path = status_path.parent / fallback_path
    try:
        fallback = load_json(fallback_path)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return status
    if fallback.get("status_artifact") == "fallback":
        return fallback
    return status


def _sanitize_command(command: list[str], env: dict[str, str]) -> list[str]:
    secrets = {
        str(value) for name, value in env.items()
        if any(marker in str(name).upper() for marker in ("TOKEN", "AUTH", "COOKIE"))
        and value
    }
    return [
        "<redacted>"
        if any(secret in token for secret in secrets)
        or any(marker in token.lower() for marker in ("authorization:", "bearer ", "nv_token"))
        else token
        for token in command
    ]


def _failure_reason_from_stderr(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[-8192:]
    except OSError:
        return ""
    if not text.strip():
        return ""
    return _sanitize_failure_reason(text)


def _terminal_status(
    status: dict,
    *,
    final_status: str,
    runner_exit_code=None,
    child_launch_returncode=None,
    failure_reason=None,
) -> dict:
    status["status"] = final_status
    status["runner_exit_code"] = runner_exit_code
    status["launch_returncode"] = runner_exit_code
    status["child_launch_returncode"] = child_launch_returncode
    if failure_reason:
        status["failure_reason"] = _sanitize_failure_reason(failure_reason)
    else:
        status.pop("failure_reason", None)
    status["finished_at"] = now_str()
    status["recorded"] = True
    status["updated_at"] = status["finished_at"]
    return status


def _finalize_result_paths(status: dict, artifact_root: Path) -> None:
    """Point terminal result fields at the run-scoped files that actually
    exist. The task template may declare a plan-level summary path that the
    downstream chain no longer writes; the authoritative summary is
    collected under the run artifact root."""
    if not artifact_root:
        return
    summary_csv = Path(artifact_root) / "summary.csv"
    if summary_csv.is_file():
        status["result_summary_csv"] = str(summary_csv)


def _refresh_terminal_status(status_path: Path, status: dict) -> tuple[dict, bool]:
    if status.get("status") in TERMINAL_STATUSES:
        return status, False
    pid = status.get("pid")
    if status.get("status") in {"running", "stopping"} and isinstance(pid, int):
        if is_pid_alive(pid):
            return status, False
        _terminal_status(
            status,
            final_status="stopped" if status.get("status") == "stopping" else "failed",
            runner_exit_code=status.get("runner_exit_code"),
            child_launch_returncode=status.get("child_launch_returncode"),
            failure_reason=(
                "runner_stopped" if status.get("status") == "stopping"
                else "supervisor_lost"
            ),
        )
        save_json(status_path, status)
        return status, True
    return status, False


def _supervisor_status(status_path: Path, *, spec_path: Path) -> None:
    status = load_json(status_path)
    spec = load_json(spec_path)
    encoded_command = os.environ.pop("RUNNER_COMMAND_B64", "")
    try:
        command = json.loads(base64.b64decode(encoded_command).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        command = None
    proc = None
    stop_requested = False
    fallback_path = Path(
        spec.get("fallback_path")
        or status.get("status_fallback_path")
        or status_path.with_name("status-fallback.json")
    )

    def save_status() -> bool:
        return _save_supervisor_status(
            status_path, status, fallback_path=fallback_path
        )

    def fail_for_status_write() -> int:
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            proc.wait()
        return 70

    def request_stop(signum, frame):
        nonlocal stop_requested
        stop_requested = True
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGINT)
            except ProcessLookupError:
                pass

    try:
        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)
        start_marker = Path(spec["start_marker"])
        while not start_marker.exists():
            time.sleep(0.01)
        if stop_requested:
            _terminal_status(
                status,
                final_status="stopped",
                runner_exit_code=None,
                child_launch_returncode=None,
                failure_reason="runner_stopped",
            )
            if not save_status():
                return fail_for_status_write()
            return 0

        stdout_path = Path(spec["stdout"])
        stderr_path = Path(spec["stderr"])
        with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
            stop_marker = Path(spec["stop_marker"])
            try:
                if not isinstance(command, list) or not command:
                    raise ValueError("supervisor command is unavailable")
                proc = subprocess.Popen(
                    command,
                    cwd=spec["cwd"],
                    env=os.environ.copy(),
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=True,
                )
            except OSError:
                _terminal_status(
                    status,
                    final_status="failed",
                    runner_exit_code=None,
                    child_launch_returncode=None,
                    failure_reason="child_popen_failed",
                )
                if not save_status():
                    return fail_for_status_write()
                return 0

            status = load_json(status_path)
            if status.get("status") == "stopping" or stop_marker.exists():
                stop_requested = True
                try:
                    os.killpg(proc.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
            status["child_launch_returncode"] = 0
            status["updated_at"] = now_str()
            if not save_status():
                return fail_for_status_write()
            timeout = spec.get("timeout_sec")
            try:
                timeout = float(timeout) if timeout is not None else None
            except (TypeError, ValueError):
                timeout = None

            deadline = time.monotonic() + timeout if timeout is not None else None
            timed_out = False
            while True:
                if stop_marker.exists() or stop_requested:
                    stop_requested = True
                    try:
                        os.killpg(proc.pid, signal.SIGINT)
                    except ProcessLookupError:
                        pass
                try:
                    wait_for = 0.1
                    if deadline is not None:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            timed_out = True
                            break
                        wait_for = min(wait_for, remaining)
                    returncode = proc.wait(timeout=wait_for)
                    break
                except subprocess.TimeoutExpired:
                    continue

            if timed_out:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                returncode = proc.wait()
                _terminal_status(
                    status,
                    final_status="timed_out",
                    runner_exit_code=returncode,
                    child_launch_returncode=0,
                    failure_reason="runner_timeout",
                )
                status["launch_returncode"] = 124
                _finalize_result_paths(status, Path(spec.get("artifact_root", "")))
                if not save_status():
                    return fail_for_status_write()
                return 0

            # Give redirected stderr/stdout a chance to flush before classifying it.
            stdout.flush()
            stderr.flush()

            if stop_requested:
                _terminal_status(
                    status,
                    final_status="stopped",
                    runner_exit_code=returncode,
                    child_launch_returncode=0,
                    failure_reason="runner_stopped",
                )
            elif returncode == 124:
                _terminal_status(
                    status,
                    final_status="timed_out",
                    runner_exit_code=124,
                    child_launch_returncode=0,
                    failure_reason="runner_timeout",
                )
            elif returncode == 0:
                stats_path = find_afl_artifact(
                    spec.get("afl_out_dir", ""), "fuzzer_stats"
                ) or find_afl_artifact(
                    spec.get("artifact_root", ""), "fuzzer_stats"
                )
                if stats_path is None or not stats_path.is_file():
                    _terminal_status(
                        status,
                        final_status="failed",
                        runner_exit_code=0,
                        child_launch_returncode=0,
                        failure_reason="missing_fuzzer_stats",
                    )
                else:
                    _terminal_status(
                        status,
                        final_status="exited",
                        runner_exit_code=0,
                        child_launch_returncode=0,
                    )
            else:
                reason = ""
                try:
                    combined = (
                        stderr_path.read_text(encoding="utf-8", errors="ignore")
                        + stdout_path.read_text(encoding="utf-8", errors="ignore")
                    )[-8192:]
                    reason = _sanitize_failure_reason(combined)
                except OSError:
                    pass
                if reason == "runner_failed":
                    try:
                        sensitive_output = any(
                            marker in combined.lower()
                            for marker in ("authorization:", "bearer ", "cookie:", "nv_token")
                        )
                    except UnboundLocalError:
                        sensitive_output = False
                    if not sensitive_output:
                        reason = f"runner_exit_code_{returncode}"
                if not reason:
                    reason = f"runner_exit_code_{returncode}"
                _terminal_status(
                    status,
                    final_status="failed",
                    runner_exit_code=returncode,
                    child_launch_returncode=0,
                    failure_reason=reason,
                )
            _finalize_result_paths(status, Path(spec.get("artifact_root", "")))
            if not save_status():
                return fail_for_status_write()
            return 0
    except Exception as error:
        try:
            status = _load_observable_status(status_path)
            _terminal_status(
                status,
                final_status="failed",
                runner_exit_code=status.get("runner_exit_code"),
                child_launch_returncode=status.get("child_launch_returncode"),
                failure_reason="supervisor_failed",
            )
            if not save_status():
                return fail_for_status_write()
        except Exception:
            print(
                f"supervisor_failed: {_sanitize_failure_reason(str(error))}",
                file=sys.stderr,
                flush=True,
            )
            return 70
    return 70


def _supervise_cli(status_path: str, spec_path: str) -> int:
    return _supervisor_status(Path(status_path), spec_path=Path(spec_path))




def infer_summary_source(path: Path, context: dict | None = None):
    context = context or {}
    haystack = " ".join([
        str(path),
        str(context.get("model_name", "")),
        str(context.get("manifest", "")),
        str(context.get("notes", "")),
        str(context.get("task_json", "")),
    ]).lower()
    if "flowable" in haystack:
        return {
            "summary_source": "python_static_loop",
            "execution_scope": "flowable_min_calibration",
            "metric_semantics": (
                "Flowable summary comes from a Python static-loop request replay over "
                "the Flowable seed dataset; nv_total_valid_exec is the replay loop count, "
                "not a full AFL++ mutation-chain execution count."
            ),
        }
    if "o2oa" in haystack or "cms_body_valid" in haystack:
        return {
            "summary_source": "aflpp_harness",
            "execution_scope": "o2oa_aflpp_body_harness",
            "metric_semantics": (
                "O2OA summary combines AFL++ fuzzer_stats with nv_http_harness "
                "body validity counters."
            ),
        }
    return {
        "summary_source": "summary_csv",
        "execution_scope": "unspecified",
        "metric_semantics": "Summary CSV source was not classified; inspect task notes and artifacts.",
    }


def find_afl_artifact(afl_out_dir: str, name: str) -> Path | None:
    if not afl_out_dir:
        return None
    base = Path(afl_out_dir)
    for p in [base / "default" / name, base / name]:
        if p.exists():
            return p
    for p in sorted(base.glob(f"**/{name}")):
        if p.is_file():
            return p
    return None


def read_summary_csv(path: Path, context: dict | None = None, preferred_mode: str = "rule_score"):
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            return None
        row = None
        if preferred_mode:
            row = next((r for r in rows if r.get("mode") == preferred_mode), None)
        if row is None:
            row = rows[0]

        def to_int(name: str) -> int:
            try:
                return int(float(row.get(name, 0) or 0))
            except Exception:
                return 0

        def to_float_str(name: str) -> str:
            v = row.get(name, "")
            if v == "":
                return "0.000000"
            return str(v)

        source = infer_summary_source(path, context)
        return {
            "source_file": str(path),
            "summary_source": row.get("summary_source") or source["summary_source"],
            "execution_scope": row.get("execution_scope") or source["execution_scope"],
            "metric_semantics": row.get("metric_semantics") or source["metric_semantics"],
            "available_modes": [r.get("mode", "") for r in rows],
            "selected_mode": row.get("mode", ""),
            "mode": row.get("mode", ""),
            "nv_total_valid_exec": to_int("nv_total_valid_exec"),
            "nv_err_exec": to_int("nv_err_exec"),
            "nv_err_rate": to_float_str("nv_err_rate"),
            "saved_hangs": to_int("saved_hangs"),
            "saved_crashes": to_int("saved_crashes"),
            "last_http_code": to_int("last_http_code"),
            "last_latency_ms": to_int("last_latency_ms"),
            "last_ncov_total": to_int("last_ncov_total"),
            "body_rule_pass": to_int("body_rule_pass"),
            "body_rule_reject": to_int("body_rule_reject"),
            "body_score_pass": to_int("body_score_pass"),
            "body_score_reject": to_int("body_score_reject"),
            "body_score_rpc_ok": to_int("body_score_rpc_ok"),
            "body_score_rpc_fail": to_int("body_score_rpc_fail"),
        }
    except Exception:
        return None


def read_fuzzer_stats(path: Path):
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out

def build_decision_summary(status: dict, summary_20: dict, summary_60: dict):
    def fmt_sr(s: dict):
        if not s:
            return ""
        p = s.get("body_score_pass", 0)
        r = s.get("body_score_reject", 0)
        return f"{p}/{r}"

    rpc_fail_total = 0
    if summary_20:
        rpc_fail_total += int(summary_20.get("body_score_rpc_fail", 0))
    if summary_60:
        rpc_fail_total += int(summary_60.get("body_score_rpc_fail", 0))

    return {
        "model": status.get("model_name", ""),
        "threshold": status.get("threshold", ""),
        "status": status.get("status", ""),
        "dur20_pass_reject": fmt_sr(summary_20),
        "dur60_pass_reject": fmt_sr(summary_60),
        "rpc_fail_total": rpc_fail_total,
        "has_dur20": bool(summary_20),
        "has_dur60": bool(summary_60),
        "summary_source": (summary_60 or summary_20 or {}).get("summary_source", ""),
        "execution_scope": (summary_60 or summary_20 or {}).get("execution_scope", ""),
    }


def expand_tokens_in_list(items, mapping):
    out = []
    for x in items:
        s = str(x)
        for k, v in mapping.items():
            s = s.replace("{" + k + "}", str(v))
        out.append(s)
    return out


def _validate_launch_paths(
    cmd: list[str], repo_root: Path, run_root: Path
) -> None:
    """Reject expanded absolute filesystem paths outside the two approved roots."""
    for index, token in enumerate(cmd):
        if ".." in Path(token).parts:
            raise ValueError(f"launch command path contains traversal: {token}")
        if not token.startswith("/"):
            continue
        path = Path(token)
        resolved = path.resolve(strict=False)
        if resolved.is_relative_to(repo_root) or resolved.is_relative_to(run_root):
            continue
        if index == 0 and resolved in {
            Path(sys.executable).resolve(),
            Path("/bin/bash"),
            Path("/usr/bin/bash"),
            Path("/bin/sh"),
            Path("/usr/bin/sh"),
            Path("/usr/bin/env"),
        }:
            continue
        if token.startswith(("http://", "https://", "unix://")):
            continue
        raise ValueError(f"launch command path escapes approved roots: {token}")

def build_launch_cmd(
    task_obj: dict,
    task_id: str,
    run_dir: Path,
    afl_out_dir: Path,
    repo_root: Path,
    run_root: Path | None = None,
):
    """
    优先使用 task.json 中的 launch_cmd。
    支持两种写法：
      1) launch_cmd: ["bash", "xxx.sh", ...]
      2) launch_cmd: "bash xxx.sh ..."
    可用占位符：
      {ROOT}
      {TASK_ID}
      {RUN_DIR}
      {AFL_OUT_DIR}
      {SEED_DIR}
    """
    launch_cmd = task_obj.get("launch_cmd")
    repo_root = _canonical_root(repo_root, "repo_root")
    seed_dir = materialize_manifest_seed_dir(
        task_obj, repo_root=repo_root, run_dir=run_dir
    )
    manifest = task_obj.get("manifest", "")
    manifest_path = resolve_repo_path(manifest, repo_root) if manifest else ""
    mapping = {
        "ROOT": str(repo_root),
        "TASK_ID": task_id,
        "RUN_DIR": str(run_dir),
        "AFL_OUT_DIR": str(afl_out_dir),
        "SEED_DIR": str(seed_dir),
        "MANIFEST": str(manifest_path),
    }

    if launch_cmd:
        if isinstance(launch_cmd, str):
            cmd = shlex.split(launch_cmd)
        elif isinstance(launch_cmd, list):
            cmd = [str(x) for x in launch_cmd]
        else:
            raise ValueError("launch_cmd must be string or list")
        cmd = expand_tokens_in_list(cmd, mapping)
        _validate_launch_paths(cmd, repo_root, Path(run_root or run_dir).resolve())
        return cmd

    # fallback：如果没写 launch_cmd，就尝试自动拼一个最小 AFL 命令
    target_cmd = task_obj.get("target_cmd")
    if not target_cmd:
        raise ValueError(
            "task.json must provide launch_cmd, or provide target_cmd for auto AFL launch"
        )

    if isinstance(target_cmd, str):
        target_cmd = shlex.split(target_cmd)
    elif isinstance(target_cmd, list):
        target_cmd = [str(x) for x in target_cmd]
    else:
        raise ValueError("target_cmd must be string or list")

    target_cmd = expand_tokens_in_list(target_cmd, mapping)

    afl_bin_raw = str(task_obj.get("afl_bin", "afl-fuzz")).replace(
        "{ROOT}", str(repo_root)
    )
    afl_bin = resolve_repo_path(afl_bin_raw, repo_root)
    if not afl_bin.is_file() or not os.access(afl_bin, os.X_OK):
        raise ValueError(f"bounded afl-fuzz not found: {afl_bin}")

    cmd = [
        str(afl_bin),
        "-i", str(seed_dir),
        "-o", str(afl_out_dir),
        "--",
    ] + target_cmd
    _validate_launch_paths(cmd, repo_root, Path(run_root or run_dir).resolve())
    return cmd

def build_launch_env(
    task_obj: dict,
    task_id: str,
    run_dir: Path,
    afl_out_dir: Path,
    repo_root: Path,
    task_path: Path | None = None,
):
    env = os.environ.copy()

    repo_root = _canonical_root(repo_root, "repo_root")
    seed_dir = materialize_manifest_seed_dir(
        task_obj, repo_root=repo_root, run_dir=run_dir
    )
    manifest = task_obj.get("manifest", "")
    manifest_path = resolve_repo_path(manifest, repo_root) if manifest else ""
    # The shell chain receives only bounded source paths and run-scoped outputs.
    mapping = {
        "ROOT": str(repo_root),
        "TASK_ID": task_id,
        "RUN_DIR": str(run_dir),
        "AFL_OUT_DIR": str(afl_out_dir),
        "SEED_DIR": str(seed_dir),
        "MANIFEST": str(manifest_path),
        "CFG": str(resolve_repo_path(
            task_obj.get("target_config", "targets/o2oa_query.json"), repo_root
        )),
        "OUT_ROOT": str(run_dir / "out"),
        "STATUS_PATH": str(run_dir / "nv_http_status.json"),
        "BODY_VALID_STATS": str(run_dir / "nv_body_valid_stats.json"),
        "RUNNER_RUN_DIR": str(run_dir),
        "NV_STATUS_LEDGER_PATH": str(run_dir / "evidence" / "status.jsonl"),
        "NV_PROBE_PATH": str(run_dir / "nv_probe.json"),
        "NV_STATE_TRACE_PATH": str(run_dir / "nv_state_trace.jsonl"),
        "NV_CTX_PATH": str(run_dir / "nv_ctx.json"),
        "NV_MAB_JOURNAL_PATH": str(run_dir / "evidence" / "mab_updates.jsonl"),
        "NV_EXECUTION_LEDGER_PATH": str(run_dir / "evidence" / "executions.jsonl"),
        "NV_SEED_SELECTION_AUDIT_PATH": str(run_dir / "evidence" / "seed_selection.jsonl"),
    }

    duration_plan = task_obj.get("duration_plan", [])
    if duration_plan:
        mapping["DUR"] = str(duration_plan[0])
        mapping["RUNNER_DURATION_PLAN"] = " ".join(
            str(item) for item in duration_plan
        )

    task_obj["seed_source"] = "manifest" if manifest else "seed_file"
    task_obj["seed_location"] = str(seed_dir)
    task_obj["target_endpoint"] = task_obj.get("target_endpoint", "")
    task_obj["mutation_scope"] = task_obj.get(
        "mutation_scope", ["field_value", "boundary", "structure"]
    )
    task_obj["max_test_cases"] = int(task_obj.get("max_test_cases") or 30)
    task_obj["time_budget"] = int(
        task_obj.get("time_budget") or (duration_plan[-1] if duration_plan else 30)
    )
    task_obj["enable_validity"] = int(task_obj.get("enable_validity", 1))
    if task_path is not None:
        save_json(Path(task_path), task_obj)

    user_env = task_obj.get("env", {})
    for k, v in user_env.items():
        s = str(v)
        for mk, mv in mapping.items():
            s = s.replace("{" + mk + "}", str(mv))
        env[str(k)] = s

    for name in (
        "ROOT",
        "CFG",
        "OUT_ROOT",
        "STATUS_PATH",
        "BODY_VALID_STATS",
        "RUNNER_RUN_DIR",
        "NV_STATUS_LEDGER_PATH",
        "NV_PROBE_PATH",
        "NV_STATE_TRACE_PATH",
        "NV_CTX_PATH",
        "NV_MAB_JOURNAL_PATH",
        "NV_EXECUTION_LEDGER_PATH",
        "NV_SEED_SELECTION_AUDIT_PATH",
    ):
        env[name] = mapping[name]
    env["IN_DIR"] = mapping["SEED_DIR"]
    env["SEED_MANIFEST"] = mapping["MANIFEST"]
    if "DUR" in mapping:
        env["DUR"] = mapping["DUR"]
        env["RUNNER_DURATION_PLAN"] = mapping["RUNNER_DURATION_PLAN"]
    env["NV_STATUS_PATH"] = mapping["STATUS_PATH"]
    env["NV_BODY_VALID_STATS"] = mapping["BODY_VALID_STATS"]
    if task_path is not None:
        env["NV_TASK_PATH"] = str(Path(task_path).resolve())

    return env


def submit(task_json_path: str, *, repo_root=None, run_root=None):
    repo_root, run_root = validate_roots(repo_root, run_root)
    src = _resolve_task_json(task_json_path, repo_root, run_root)
    if not src.is_file():
        raise FileNotFoundError(f"task json not found: {src}")

    task_obj = load_json(src)

    task_id = uuid.uuid4().hex[:12]
    layout = build_run_layout(run_root, repo_root, task_id)
    task_dir = layout["task_dir"]
    task_dir.mkdir(parents=True, exist_ok=True)

    run_dir = layout["run_dir"]
    run_dir.mkdir(parents=True, exist_ok=True)

    afl_out_dir_raw = task_obj.get("out_dir", "")
    if afl_out_dir_raw:
        afl_out_dir = resolve_run_path(afl_out_dir_raw, run_root)
    else:
        afl_out_dir = resolve_run_path(
            f"runs/{task_id}/afl_out", run_root
        )
    afl_out_dir.mkdir(parents=True, exist_ok=True)

    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"

    dst_task = task_dir / "task.json"
    shutil.copy2(src, dst_task)

    cmd = build_launch_cmd(
        task_obj, task_id, run_dir, afl_out_dir, repo_root, run_root
    )
    env = build_launch_env(
        task_obj, task_id, run_dir, afl_out_dir, repo_root, task_path=dst_task
    )

    status = {
        "task_id": task_id,
        "repo_root": str(repo_root),
        "run_root": str(run_root),
        "status": "running",
        "created_at": now_str(),
        "updated_at": now_str(),
        "start_time": now_str(),
        "task_json": str(dst_task),
        "report_json": str(task_dir / "report.json"),
        "experiment_dir": str(resolve_run_path(task_obj["experiment_dir"], run_root))
        if task_obj.get("experiment_dir") else "",
        "model_name": task_obj.get("model_name", ""),
        "threshold": str(task_obj.get("threshold", "")),
        "manifest": task_obj.get("manifest", ""),
        "duration_plan": task_obj.get("duration_plan", []),
        "notes": task_obj.get("notes", ""),
        "pid": None,
        "run_dir": str(run_dir),
        "afl_out_dir": str(afl_out_dir),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "command": [],
        "submit_process_result": None,
        "launch_returncode": None,
        "child_launch_returncode": None,
        "runner_exit_code": None,
        "failure_reason": None,
        "finished_at": None,
        "recorded": False,
        "timeout_sec": task_obj.get("timeout_sec"),
        "result_summary_csv": str(resolve_run_path(task_obj["result_summary_csv"], run_root))
        if task_obj.get("result_summary_csv") else "",
        "result_stats_json": str(resolve_run_path(task_obj["result_stats_json"], run_root))
        if task_obj.get("result_stats_json") else "",
    }
    status_path = task_dir / "status.json"
    spec_path = run_dir / "supervisor_spec.json"
    start_marker = run_dir / ".supervisor_start"
    spec = {
        "cwd": str(repo_root),
        "afl_out_dir": str(afl_out_dir),
        "artifact_root": str(run_dir / "out"),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "start_marker": str(start_marker),
        "stop_marker": str(run_dir / ".supervisor_stop"),
        "fallback_path": str(run_dir / "status-fallback.json"),
        "timeout_sec": task_obj.get("timeout_sec"),
    }
    status["status_fallback_path"] = spec["fallback_path"]
    save_json(status_path, status)
    save_json(spec_path, spec)
    supervisor_env = dict(env)
    supervisor_env["RUNNER_COMMAND_B64"] = base64.b64encode(
        json.dumps(cmd, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")

    supervisor_cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "_supervise",
        "--status-path", str(status_path),
        "--spec-path", str(spec_path),
    ]
    try:
        supervisor_pid = os.posix_spawn(
            sys.executable,
            supervisor_cmd,
            supervisor_env,
            setsid=True,
        )
    except OSError as exc:
        _terminal_status(
            status,
            final_status="failed",
            runner_exit_code=None,
            child_launch_returncode=None,
            failure_reason="supervisor_popen_failed",
        )
        status["submit_process_result"] = 1
        status["launch_returncode"] = None
        save_json(status_path, status)
        raise RuntimeError("supervisor_popen_failed") from exc

    status["pid"] = supervisor_pid
    status["supervisor_pid"] = supervisor_pid
    status["supervisor_command"] = supervisor_cmd
    status["submit_process_result"] = 0
    status["launch_returncode"] = 0
    status["updated_at"] = now_str()
    save_json(status_path, status)
    start_marker.touch()

    print(json.dumps({
        "ok": True,
        "task_id": task_id,
        "pid": supervisor_pid,
        "run_dir": str(run_dir),
        "afl_out_dir": str(afl_out_dir),
    }, ensure_ascii=False))


def query(task_id: str, *, repo_root=None, run_root=None):
    repo_root, run_root = validate_roots(repo_root, run_root)
    task_dir = _task_dir(run_root, task_id)
    status_path = task_dir / "status.json"
    if not status_path.exists():
        raise FileNotFoundError(f"task not found: {task_id}")

    status = _load_observable_status(status_path)
    status, _ = _refresh_terminal_status(status_path, status)

    pid = status.get("pid")
    live = isinstance(pid, int) and is_pid_alive(pid)
    current_status = status.get("status", "")

    fuzzer_stats = {}
    eval_report = {}
    afl_out_dir = (
        str(resolve_run_path(status["afl_out_dir"], run_root))
        if status.get("afl_out_dir") else ""
    )
    if afl_out_dir:
        stats_path = find_afl_artifact(afl_out_dir, "fuzzer_stats")
        if stats_path:
            fuzzer_stats = read_fuzzer_stats(stats_path)
        eval_path = find_afl_artifact(afl_out_dir, "eval_report.json")
        if eval_path:
            try:
                eval_report = load_json(eval_path)
            except Exception:
                eval_report = {}

    out = dict(status)
    out["status"] = current_status
    out["pid_alive"] = live
    out["fuzzer_stats"] = fuzzer_stats
    out["eval_report"] = eval_report
    out["metric_sources"] = {
        "fuzzer_stats": "aflpp_native_or_demo" if fuzzer_stats else "not_available",
        "eval_report": (
            eval_report.get("task", {}).get("source", "aflpp_eval_report")
            if eval_report else "not_available"
        ),
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))


def stop(task_id: str, *, repo_root=None, run_root=None):
    repo_root, run_root = validate_roots(repo_root, run_root)
    task_dir = _task_dir(run_root, task_id)
    status_path = task_dir / "status.json"
    if not status_path.exists():
        raise FileNotFoundError(f"task not found: {task_id}")

    status = _load_observable_status(status_path)
    status, _ = _refresh_terminal_status(status_path, status)
    pid = status.get("pid")

    sent = False
    if isinstance(pid, int) and is_pid_alive(pid):
        stop_marker = Path(status.get("run_dir", "")) / ".supervisor_stop"
        if status.get("run_dir"):
            stop_marker.touch()
        try:
            os.kill(pid, signal.SIGINT)
            sent = True
        except ProcessLookupError:
            sent = False

    latest = load_json(status_path)
    if sent and latest.get("status") not in TERMINAL_STATUSES:
        latest["status"] = "stopping"
        latest["updated_at"] = now_str()
        save_json(status_path, latest)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            time.sleep(0.02)
            latest = load_json(status_path)
            if latest.get("status") in TERMINAL_STATUSES:
                break
            if not is_pid_alive(pid):
                break
        if latest.get("status") not in TERMINAL_STATUSES:
            child_pid = latest.get("child_pid")
            if isinstance(child_pid, int) and is_pid_alive(child_pid):
                try:
                    os.killpg(child_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            _terminal_status(
                latest,
                final_status="stopped",
                runner_exit_code=latest.get("runner_exit_code"),
                child_launch_returncode=latest.get("child_launch_returncode"),
                failure_reason="runner_stopped",
            )
            save_json(status_path, latest)
        status = latest
    else:
        status = latest

    print(json.dumps({
        "ok": True,
        "task_id": task_id,
        "status": status["status"],
        "pid": pid,
        "signal_sent": sent,
    }, ensure_ascii=False))


def report(task_id: str, *, repo_root=None, run_root=None):
    repo_root, run_root = validate_roots(repo_root, run_root)
    task_dir = _task_dir(run_root, task_id)
    status_path = task_dir / "status.json"
    if not status_path.exists():
        raise FileNotFoundError(f"task not found: {task_id}")

    status = _load_observable_status(status_path)
    status, _ = _refresh_terminal_status(status_path, status)

    exp_dir = status.get("experiment_dir", "")
    exp_path = resolve_run_path(exp_dir, run_root) if exp_dir else None

    artifacts = {}
    summary_20 = {}
    summary_60 = {}
    run_dir = status.get("run_dir", "")
    run_path = resolve_run_path(run_dir, run_root) if run_dir else None

    if run_path and run_path.exists():
        p20 = run_path / "summary_dur20.csv"
        p60 = run_path / "summary_dur60.csv"

        s20 = read_summary_csv(p20, status)
        s60 = read_summary_csv(p60, status)

        if s20:
            summary_20 = s20
            artifacts[p20.name] = str(p20)

        if s60:
            summary_60 = s60
            artifacts[p60.name] = str(p60)

        for name in ["body_valid_stats_dur20.json", "body_valid_stats_dur60.json"]:
            p = run_path / name
            if p.exists():
                artifacts[p.name] = str(p)
    result_summary_csv = status.get("result_summary_csv", "")
    result_stats_json = status.get("result_stats_json", "")

    if not summary_20 and result_summary_csv:
        p = resolve_run_path(result_summary_csv, run_root)
        s = read_summary_csv(p, status)
        if s:
            summary_20 = s
            artifacts[p.name] = str(p)

    if result_stats_json:
        p = resolve_run_path(result_stats_json, run_root)
        if p.exists():
            artifacts[p.name] = str(p)

    # 实验目录里的结果
    if exp_path and exp_path.exists():
        p20 = exp_path / "summary_dur20.csv"
        p60 = exp_path / "summary_dur60.csv"
        s20 = read_summary_csv(p20, status)
        s60 = read_summary_csv(p60, status)
        if s20:
            summary_20 = s20
        if s60:
            summary_60 = s60

        for name in [
            "summary_dur20.csv",
            "summary_dur60.csv",
            "sefanogan_ae_meta.json",
            "sefanogan_gan_meta.json",
            "README.md",
        ]:
            p = exp_path / name
            if p.exists():
                artifacts[name] = str(p)

    # 运行目录里的文件
    for k in ["stdout_log", "stderr_log"]:
        p = status.get(k, "")
        if p:
            safe_p = resolve_run_path(p, run_root)
            if safe_p.exists():
                artifacts[safe_p.name] = str(safe_p)

    afl_out_dir = (
        str(resolve_run_path(status["afl_out_dir"], run_root))
        if status.get("afl_out_dir") else ""
    )
    if afl_out_dir:
        for name in ["fuzzer_stats", "eval_report.json"]:
            p = find_afl_artifact(afl_out_dir, name)
            if p and p.exists():
                artifacts[name] = str(p)

    fuzzer_stats = {}
    eval_report = {}
    if afl_out_dir:
        stats_path = find_afl_artifact(afl_out_dir, "fuzzer_stats")
        if stats_path:
            fuzzer_stats = read_fuzzer_stats(stats_path)
        eval_path = find_afl_artifact(afl_out_dir, "eval_report.json")
        if eval_path:
            try:
                eval_report = load_json(eval_path)
            except Exception:
                eval_report = {}
    
    pid = status.get("pid")
    live = isinstance(pid, int) and is_pid_alive(pid)
    current_status = status.get("status", "")

    decision_summary = build_decision_summary(status, summary_20, summary_60)
    metric_sources = {
        "fuzzer_stats": "aflpp_native" if fuzzer_stats else "not_available",
        "eval_report": (
            eval_report.get("task", {}).get("source", "aflpp_eval_report")
            if eval_report else "not_available"
        ),
        "summary_dur20": summary_20.get("summary_source", "not_available") if summary_20 else "not_available",
        "summary_dur60": summary_60.get("summary_source", "not_available") if summary_60 else "not_available",
    }
    integration_boundary = (
        "runner/adapter-level task semantics; this report is not proof of a deployed HTTP/RPC gateway service"
    )

    report_obj = {
        "task_id": task_id,
        "status": current_status,
        "task_json": status.get("task_json"),
        "report_json": status.get("report_json"),
        "experiment_dir": exp_dir,
        "model_name": status.get("model_name", ""),
        "threshold": status.get("threshold", ""),
        "manifest": status.get("manifest", ""),
        "duration_plan": status.get("duration_plan", []),
        "notes": status.get("notes", ""),
        "pid": status.get("pid"),
        "submit_process_result": status.get("submit_process_result"),
        "launch_returncode": status.get("launch_returncode"),
        "child_launch_returncode": status.get("child_launch_returncode"),
        "runner_exit_code": status.get("runner_exit_code"),
        "failure_reason": status.get("failure_reason"),
        "finished_at": status.get("finished_at"),
        "recorded": status.get("recorded", False),
        "status_artifact": status.get("status_artifact", "primary"),
        "status_fallback_path": status.get("status_fallback_path"),
        "status_write_error": status.get("status_write_error"),
        "supervisor_exit_code": status.get("supervisor_exit_code"),
        "run_dir": status.get("run_dir", ""),
        "afl_out_dir": status.get("afl_out_dir", ""),
        "command": status.get("command", []),
        "artifacts": artifacts,
        "summary_dur20": summary_20,
        "summary_dur60": summary_60,
        "fuzzer_stats": fuzzer_stats,
        "eval_report": eval_report,
        "metric_sources": metric_sources,
        "integration_boundary": integration_boundary,
        "generated_at": now_str(),
        "decision_summary": decision_summary,
    }

    report_path = task_dir / "report.json"
    save_json(report_path, report_obj)
    print(json.dumps(report_obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_submit = sub.add_parser("submit")
    p_submit.add_argument("--task-json", required=True)
    p_submit.add_argument("--repo-root", required=True)
    p_submit.add_argument("--run-root", required=True)

    p_query = sub.add_parser("query")
    p_query.add_argument("--task-id", required=True)
    p_query.add_argument("--repo-root", required=True)
    p_query.add_argument("--run-root", required=True)

    p_stop = sub.add_parser("stop")
    p_stop.add_argument("--task-id", required=True)
    p_stop.add_argument("--repo-root", required=True)
    p_stop.add_argument("--run-root", required=True)

    p_report = sub.add_parser("report")
    p_report.add_argument("--task-id", required=True)
    p_report.add_argument("--repo-root", required=True)
    p_report.add_argument("--run-root", required=True)

    p_supervise = sub.add_parser("_supervise")
    p_supervise.add_argument("--status-path", required=True)
    p_supervise.add_argument("--spec-path", required=True)

    args = parser.parse_args()

    if args.cmd == "_supervise":
        raise SystemExit(_supervise_cli(args.status_path, args.spec_path))
    elif args.cmd == "submit":
        submit(args.task_json, repo_root=args.repo_root, run_root=args.run_root)
    elif args.cmd == "query":
        query(args.task_id, repo_root=args.repo_root, run_root=args.run_root)
    elif args.cmd == "stop":
        stop(args.task_id, repo_root=args.repo_root, run_root=args.run_root)
    elif args.cmd == "report":
        report(args.task_id, repo_root=args.repo_root, run_root=args.run_root)
    else:
        raise RuntimeError(f"unknown cmd: {args.cmd}")


if __name__ == "__main__":
    main()
