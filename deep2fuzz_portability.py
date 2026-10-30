"""Small, offline portability helpers for the supported Deep2Fuzz runtime.

This module contains platform mechanics only.  It intentionally does not know
about validity, scoring, MAB, or any other scientific/accounting contract.
Foreign Windows paths are parsed as opaque semantic values with
``PureWindowsPath``; they are never resolved as local POSIX paths.
"""
from __future__ import annotations

from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from dataclasses import dataclass
import math
import os
import platform as platform_module
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Callable, Mapping, Sequence


class PortabilityError(RuntimeError):
    """Base error for an unavailable or unsafe local capability."""


class UnsupportedCapability(PortabilityError):
    """A capability cannot be provided safely on this host or input."""


class TerminationError(PortabilityError):
    """The managed execution scope could not be verified quiescent."""


class _InspectionDeadline(TerminationError):
    """A scope scan exhausted the current termination phase's budget."""


def discover_repo_root(start: str | Path | None = None,
                       required: Sequence[str] = ("src", "scripts", "targets", "validity", "integration")) -> Path:
    """Find a source-tree root from an arbitrary current directory."""
    supplied = Path(start) if start is not None else Path.cwd()
    if supplied.exists() and supplied.is_file():
        supplied = supplied.parent
    # ``resolve`` is local-host discovery only.  Foreign path semantics use
    # ``parse_foreign_path`` and never enter this function.
    try:
        origin = supplied.resolve()
    except (OSError, RuntimeError) as exc:
        raise UnsupportedCapability("repository root cannot be resolved") from exc
    for candidate in (origin, *origin.parents):
        if all((candidate / item).exists() for item in required):
            return candidate
    raise UnsupportedCapability("repository root is unavailable from this path")


def parse_foreign_path(value: str, style: str) -> PurePath:
    """Parse a path according to its declared representation."""
    if not isinstance(value, str):
        raise TypeError("path value must be a string")
    if style == "windows":
        return PureWindowsPath(value)
    if style == "posix":
        return PurePosixPath(value)
    raise UnsupportedCapability(f"unsupported path style: {style}")


def serialize_path(value: str | PurePath, *, kind: str = "local") -> str:
    """Serialize paths without changing opaque external values.

    ``local`` uses the host ``Path`` representation, ``portable`` uses the
    declared PurePath's canonical slash representation, and ``opaque`` keeps
    the original string exactly.  No blind backslash replacement occurs.
    """
    if kind == "opaque":
        return str(value)
    if kind == "portable":
        if isinstance(value, PurePath):
            return value.as_posix()
        return Path(value).as_posix()
    if kind == "local":
        return str(Path(value))
    raise UnsupportedCapability(f"unsupported path serialization kind: {kind}")


def interpreter_command(interpreter: str | Path | None = None) -> Path:
    """Return an executable interpreter, preferring the running interpreter."""
    supplied = sys.executable if interpreter is None else str(interpreter)
    if not supplied:
        raise UnsupportedCapability("Python interpreter is unavailable")
    candidate = Path(supplied)
    if candidate.is_absolute() or any(sep in supplied for sep in ("/", "\\")):
        if candidate.is_file():
            return candidate
        raise UnsupportedCapability(f"Python interpreter is unavailable: {supplied}")
    resolved = shutil.which(supplied)
    if resolved:
        return Path(resolved)
    raise UnsupportedCapability(f"Python interpreter is unavailable: {supplied}")


def venv_interpreter_candidates(root: str | Path) -> tuple[Path, Path]:
    base = Path(root)
    return base / "bin" / "python", base / "Scripts" / "python.exe"


def find_executable(name: str, *, which: Callable[[str], str | None] = shutil.which) -> Path:
    if not isinstance(name, str) or not name.strip():
        raise UnsupportedCapability("executable name is empty")
    resolved = which(name)
    if not resolved:
        if name.lower() in {"sh", "bash", "cmd", "powershell"}:
            raise UnsupportedCapability(f"shell helper is unavailable: {name}")
        raise UnsupportedCapability(f"executable is unavailable: {name}")
    return Path(resolved)


def process_kwargs(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {"shell": False}
    values.update(overrides)
    if values.get("shell") is not False:
        raise UnsupportedCapability("shell execution is unsupported by the portable boundary")
    return values


def run_argv(argv: Sequence[str | Path], *, cwd: str | Path | None = None,
             env: Mapping[str, str] | None = None, timeout: float | None = None,
             check: bool = False) -> subprocess.CompletedProcess[str]:
    if not argv or any(not isinstance(item, (str, Path)) for item in argv):
        raise ValueError("argv must be a non-empty sequence of strings")
    kwargs = process_kwargs(cwd=Path(cwd) if cwd is not None else None,
                            env=dict(env) if env is not None else None,
                            timeout=timeout, check=check, text=True,
                            encoding="utf-8", capture_output=True)
    return subprocess.run([str(item) for item in argv], **kwargs)


def termination_plan(host_name: str | None = None) -> dict[str, str]:
    host = (host_name or platform_module.system() or os.name).lower()
    if host != "linux" or os.name != "posix":
        raise UnsupportedCapability("managed process-tree termination requires Linux /proc; native Windows is unsupported")
    for name in ("killpg", "getpgid", "getsid", "kill"):
        if not callable(getattr(os, name, None)):
            raise UnsupportedCapability(f"managed process-tree capability is unavailable: {name}")
    require_signal("SIGTERM")
    require_signal("SIGKILL")
    try:
        _read_process_record(Path("/proc") / str(os.getpid()) / "stat")
    except (OSError, ValueError) as exc:
        raise UnsupportedCapability("managed process-tree verification requires readable /proc") from exc
    return {"graceful": "process_group", "force": "process_group"}


def require_signal(name: str) -> int:
    value = getattr(signal, name, None)
    if value is None:
        raise UnsupportedCapability(f"signal is unsupported: {name}")
    return int(value)


def require_capability(name: str, supported: bool) -> None:
    if not supported:
        raise UnsupportedCapability(f"unsupported capability: {name}")


def require_local_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.exists():
        raise UnsupportedCapability(f"local path is unavailable: {candidate}")
    return candidate


@dataclass(frozen=True)
class _ProcessRecord:
    pid: int
    parent: int
    group: int
    session: int
    started: int
    state: str


def _read_process_record(path: Path) -> _ProcessRecord:
    pid_text, fields = path.read_text(encoding="utf-8").rsplit(") ", 1)
    values = fields.split()
    return _ProcessRecord(int(pid_text.split(" (", 1)[0]), int(values[1]),
                          int(values[2]), int(values[3]), int(values[19]), values[0])


def _process_snapshot(deadline: float) -> dict[int, _ProcessRecord]:
    records = {}
    try:
        for entry in Path("/proc").iterdir():
            if time.monotonic() >= deadline:
                raise _InspectionDeadline("managed process inspection reached phase deadline")
            if len(records) >= 100_000:
                raise TerminationError("managed process inspection exceeded its bound")
            if not entry.name.isdecimal():
                continue
            try:
                record = _read_process_record(entry / "stat")
            except (FileNotFoundError, ProcessLookupError):
                continue
            records[record.pid] = record
    except (OSError, ValueError) as exc:
        raise TerminationError("managed process scope cannot be inspected") from exc
    return records


def _refresh_scope(known: dict[int, _ProcessRecord], groups: set[int], sessions: set[int],
                   deadline: float) -> list[_ProcessRecord]:
    snapshot = _process_snapshot(deadline)
    # PID/start-time pairs prevent a recycled PID from acquiring old ownership.
    owned = {pid for pid, old in known.items()
             if pid in snapshot and snapshot[pid].started == old.started}
    while True:
        added = {pid for pid, record in snapshot.items() if pid not in known and (
            record.parent in owned or record.group in groups or record.session in sessions)}
        if not added:
            break
        owned.update(added)
        known.update((pid, snapshot[pid]) for pid in added)
        groups.update(pid for pid in added if snapshot[pid].group == pid)
        sessions.update(pid for pid in added if snapshot[pid].session == pid)
    return [snapshot[pid] for pid in owned if snapshot[pid].state not in {"Z", "X"}]


def _signal_scope(records: list[_ProcessRecord], signum: int) -> None:
    for group in sorted({record.group for record in records}):
        if group <= 1 or group == os.getpgrp():
            raise TerminationError("refusing to signal an unowned process group")
        try:
            os.killpg(group, signum)
        except ProcessLookupError:
            pass
        except OSError as exc:
            raise TerminationError("managed process-group signal failed") from exc


def _wait_scope_quiescent(process, known, groups, sessions, deadline: float,
                          signum: int) -> bool:
    while True:
        process.poll()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        try:
            records = _refresh_scope(known, groups, sessions, deadline)
        except _InspectionDeadline:
            return False
        if not records:
            return process.poll() is not None
        _signal_scope(records, signum)
        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))


def terminate_process(process: subprocess.Popen, *, grace_seconds: float = 2.0,
                      force_seconds: float = 2.0) -> bool:
    """Stop an isolated Linux execution scope; return only after quiescence.

    The caller owns a child started with start_new_session=True. Capture its
    descendants before signalling, including AFL forkservers creating their own
    sessions. Zombies cannot execute and are quiescent; only their parent can
    reap them. Native Windows/other unverifiable capabilities fail closed.
    """
    for value in (grace_seconds, force_seconds):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("termination waits must be finite positive seconds")
    termination_plan()
    try:
        record = _read_process_record(Path("/proc") / str(process.pid) / "stat")
    except (OSError, ValueError) as exc:
        raise UnsupportedCapability("managed execution scope ownership cannot be established") from exc
    if record.group != process.pid or record.session != process.pid or record.parent != os.getpid():
        raise UnsupportedCapability("termination requires an owned child in an isolated session")
    known = {record.pid: record}
    groups, sessions = {record.group}, {record.session}
    # Snapshot before SIGTERM: the leader may exit before its resistant children.
    _refresh_scope(known, groups, sessions, time.monotonic() + 2.0)
    if _wait_scope_quiescent(process, known, groups, sessions,
                             time.monotonic() + grace_seconds, signal.SIGTERM):
        return False
    if not _wait_scope_quiescent(process, known, groups, sessions,
                                 time.monotonic() + force_seconds, signal.SIGKILL):
        raise TerminationError("managed execution scope still has live processes after forced deadline")
    return True


def new_temp_root(*, parent: str | Path | None = None, prefix: str = "deep2fuzz-") -> Path:
    parent_path = None if parent is None else Path(parent)
    if parent_path is not None and not parent_path.is_dir():
        raise UnsupportedCapability("temporary root parent is unavailable")
    try:
        return Path(tempfile.mkdtemp(prefix=prefix, dir=str(parent_path) if parent_path else None))
    except (OSError, ValueError) as exc:
        raise UnsupportedCapability("temporary root cannot be created") from exc


def read_text_utf8(path: str | Path) -> str:
    with Path(path).open("r", encoding="utf-8", newline=None) as stream:
        return stream.read()


def write_text_utf8(path: str | Path, value: str) -> None:
    Path(path).write_text(value, encoding="utf-8", newline="\n")


def home_path() -> Path:
    return Path.home()


def optional_environment(name: str, env: Mapping[str, str] | None = None) -> str | None:
    return (os.environ if env is None else env).get(name)


def stable_environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build an offline test environment without requiring POSIX-only names."""
    values = dict(os.environ)
    values.update({"PYTHONHASHSEED": "0", "LC_ALL": "C", "LANG": "C", "TZ": "UTC", "TASK4_OFFLINE": "1"})
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        values.pop(name, None)
    if extra:
        values.update({str(key): str(value) for key, value in extra.items()})
    return values


def default_evidence_parent() -> Path:
    configured = os.environ.get("DEEP2FUZZ_EVIDENCE_PARENT")
    return Path(configured).expanduser() if configured else home_path() / "task4-evidence"
