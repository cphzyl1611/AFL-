#!/usr/bin/env python3
"""Deterministic pytest group runner with fail-closed gate projections."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import re
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Iterator, Sequence


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tests" / "test_groups.json"
DEFAULT_RETRY = 0
FORMAL_GROUPS = frozenset({
    "phase1", "phase1_1", "phase1_1b", "phase1_1c", "formal_score",
    "p1_1", "p1_2", "p1_3", "p1_4", "required-74", "combined-227",
})
_PASSED_RE = re.compile(r"(?P<count>\d+) passed")
_FAILED_RE = re.compile(r"(?P<count>\d+) failed")
_SECRET_RE = re.compile(
    r"(?i)(password|passwd|token|cookie|authorization|private[_ -]?key)(\s*[=:]\s*)[^\s,;]+"
)
# Pytest parameter IDs may contain spaces (and escaped newlines); the path and
# node separator are the stable parts of an exact node id.
_NODE_RE = re.compile(r"^[^\s:]+\.py::.+$")


class ManifestError(ValueError):
    """The selection manifest cannot safely define a test gate."""


def stable_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update({"PYTHONHASHSEED": "0", "LC_ALL": "C", "LANG": "C", "TZ": "UTC", "TASK4_OFFLINE": "1"})
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(name, None)
    if extra:
        env.update(extra)
    return env


def _sanitized(text: str, limit: int = 4000) -> str:
    return _SECRET_RE.sub(r"\1=<redacted>", text)[-limit:]


def _node_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip() or not _NODE_RE.fullmatch(value):
        raise ManifestError(f"{path} must be an exact pytest node id")
    return value


def _collect_output_nodes(output: str) -> set[str]:
    return {line.strip() for line in output.splitlines() if _NODE_RE.fullmatch(line.strip())}


def _collect_declared_nodes(members: Sequence[str], *, timeout_seconds: float = 180.0) -> set[str]:
    if not members:
        return set()
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *members],
        cwd=ROOT, env=stable_environment(), text=True, capture_output=True,
        timeout=timeout_seconds, check=False,
    )
    nodes = _collect_output_nodes(completed.stdout or "")
    if completed.returncode != 0:
        raise ManifestError(f"pytest collection failed: {_sanitized(completed.stderr or completed.stdout or '')}")
    missing = sorted(set(members) - nodes)
    if missing:
        raise ManifestError(f"uncollectable formal node ids: {', '.join(missing)}")
    unexpected = sorted(nodes - set(members))
    if unexpected:
        raise ManifestError(f"pytest collection drift: {', '.join(unexpected)}")
    return nodes


def _validate_members(group: str, members: Any) -> list[str]:
    if not isinstance(members, list) or not members:
        raise ManifestError(f"groups.{group}.members must be a non-empty array")
    values = [_node_id(value, f"groups.{group}.members[{index}]") for index, value in enumerate(members)]
    if values != sorted(values):
        raise ManifestError(f"groups.{group}.members must be in stable lexical order")
    if len(values) != len(set(values)):
        raise ManifestError(f"groups.{group}.members contains duplicate node ids")
    return values


def load_manifest(*, validate_collection: bool = False) -> dict[str, Any]:
    try:
        with MANIFEST_PATH.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"manifest cannot be read: {exc.__class__.__name__}") from None
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("groups"), dict):
        raise ManifestError("manifest schema is unsupported")
    declared: dict[str, list[str]] = {}
    for group, spec in value["groups"].items():
        if not isinstance(group, str) or not isinstance(spec, dict):
            raise ManifestError("manifest group entries are malformed")
        if "members" in spec:
            declared[group] = _validate_members(group, spec["members"])
        elif group in FORMAL_GROUPS:
            raise ManifestError(f"formal group {group} lacks exact members")
    for group in FORMAL_GROUPS:
        if group not in declared:
            raise ManifestError(f"required formal group {group} is missing exact members")
    if validate_collection:
        all_members = sorted({member for members in declared.values() for member in members})
        collected = _collect_declared_nodes(all_members)
        for group, members in declared.items():
            if not set(members).issubset(collected):
                raise ManifestError(f"formal group {group} contains an uncollectable node")
    return value


def _group_spec(manifest: dict[str, Any], group: str) -> dict[str, Any]:
    groups = manifest.get("groups")
    if not isinstance(groups, dict) or group not in groups or not isinstance(groups[group], dict):
        raise ManifestError(f"unknown test group: {group}")
    return groups[group]


def _expected_members(spec: dict[str, Any]) -> list[str] | None:
    if "members" not in spec:
        return None
    return _validate_members("selected", spec["members"])


def project_gates(
    manifest: dict[str, Any], group: str, physical_results: Sequence[dict[str, Any]] | None = None,
    *, collection_status: str = "NOT_EXECUTED", deselected: Sequence[str] = (),
    collection_errors: Sequence[str] = (),
) -> dict[str, Any]:
    """Project real physical results onto one explicit logical gate."""
    spec = _group_spec(manifest, group)
    expected = _expected_members(spec)
    if expected is None:
        return {
            "group": group, "verdict": "NOT_APPLICABLE", "expected_members": [],
            "executed_members": [], "missing_members": [], "failed_members": [],
            "error_members": [], "unexpected_members": [], "duplicate_members": [],
            "deselected_members": [], "collection_status": collection_status,
            "logical_projection_synthesizes_test_result": False,
        }
    results = list(physical_results or [])
    expected_set = set(expected)
    by_node: dict[str, list[dict[str, Any]]] = {}
    malformed_result_indexes: list[int] = []
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            malformed_result_indexes.append(index)
            continue
        node = result.get("node_id")
        if not isinstance(node, str) or not _NODE_RE.fullmatch(node):
            malformed_result_indexes.append(index)
            continue
        by_node.setdefault(node, []).append(result)
    executed = sorted(by_node)
    unexpected = sorted(node for node in by_node if node not in expected_set)
    missing = sorted(expected_set - set(executed))
    duplicates = sorted(node for node, entries in by_node.items() if len(entries) > 1 and node in expected_set)
    conflicting = sorted(
        node for node, entries in by_node.items()
        if len(entries) > 1 and len({entry.get("terminal_status") for entry in entries}) > 1
    )
    failed = sorted(node for node, entries in by_node.items() if node in expected_set and any(entry.get("terminal_status") == "FAIL" for entry in entries))
    errors = sorted(node for node, entries in by_node.items() if node in expected_set and any(entry.get("terminal_status") == "ERROR" for entry in entries))
    deselected_expected = sorted(set(deselected) & expected_set)
    invalid_status = sorted(
        node for node, entries in by_node.items()
        if node in expected_set and any(entry.get("terminal_status") not in {"PASS", "FAIL", "ERROR"} for entry in entries)
    )
    valid = (
        collection_status == "PASS" and not collection_errors and not missing and
        not unexpected and not duplicates and not conflicting and not failed and
        not errors and not deselected_expected and not invalid_status and
        not malformed_result_indexes and executed == expected
    )
    return {
        "group": group, "verdict": "PASS" if valid else "FAIL", "expected_members": expected,
        "executed_members": executed, "missing_members": missing, "failed_members": failed,
        "error_members": errors, "unexpected_members": unexpected, "duplicate_members": duplicates,
        "conflicting_duplicate_members": conflicting, "invalid_status_members": invalid_status,
        "deselected_members": deselected_expected, "collection_status": collection_status,
        "malformed_result_indexes": malformed_result_indexes,
        "collection_errors": list(collection_errors),
        "logical_projection_synthesizes_test_result": False,
        "unknown_executed_member_policy": "ERROR_ON_SELECTION_DRIFT",
    }


def new_temp_root(parent: Path, label: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"deep2fuzz-{label}-", dir=parent))


def sorted_entries(path: Path) -> list[str]:
    return sorted((entry.name for entry in path.iterdir()), key=lambda value: value.encode("utf-8"))


def seeded_sequence(seed: int, count: int) -> list[int]:
    generator = random.Random(seed)
    return [generator.randrange(0, 2**31) for _ in range(count)]


def utc_timestamp(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_sort(values: list[str]) -> list[str]:
    return sorted(values, key=lambda value: value.encode("utf-8"))


def deadline_clock_name() -> str:
    return "monotonic"


def timeout_diagnostic(test_id: str, elapsed: float, deadline: float, process_state: str, stderr: str = "") -> dict[str, Any]:
    return {"test_id": test_id, "attempt": 1, "elapsed_seconds": elapsed,
            "deadline_seconds": deadline, "process_state": process_state,
            "stderr": _sanitized(stderr)}


def poll_until(predicate: Callable[[], bool], *, deadline_seconds: float, interval_seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, deadline_seconds)
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(min(interval_seconds, max(0.0, deadline - time.monotonic())))


def finish_process(process: subprocess.Popen[Any], *, deadline_seconds: float) -> str:
    try:
        process.wait(timeout=deadline_seconds)
        return "exited"
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        return "killed"


@contextmanager
def ephemeral_listener() -> Iterator[socket.socket]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        yield sock
    finally:
        sock.close()


def record_attempts(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    if not attempts:
        raise ValueError("at least one acceptance attempt is required")
    first = attempts[0]
    first_status = first.get("acceptance_status", first.get("result", "ERROR"))
    diagnostics = attempts[1:]
    statuses = [item.get("acceptance_status", item.get("result", "ERROR")) for item in diagnostics]
    return {
        "acceptance": {"attempt": 1, "status": first_status},
        "diagnostic_reruns": [{"attempt": index + 2, "status": status} for index, status in enumerate(statuses)],
        "final_acceptance_status": first_status,
        "flaky_observed": bool(diagnostics and any(status != first_status for status in statuses)),
    }


def retry_masks_failure(results: list[str]) -> bool:
    """The repair policy never erases an acceptance failure."""
    return False


def repeat_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "runs": len(reports),
        "durations": [report["duration_seconds"] for report in reports],
        **record_attempts(reports[:1]),
        **repeat_stability(reports),
    }


def repeat_stability(reports: Sequence[dict[str, Any]]) -> dict[str, Any]:
    statuses = [report.get("acceptance_status", report.get("result", "ERROR")) for report in reports]
    failures = [index + 1 for index, status in enumerate(statuses) if status != "PASS"]
    return {
        "repeat_statuses": statuses,
        "repeat_failed_attempts": failures,
        "repeat_stable": not failures,
    }


def critical_repeat_groups() -> dict[str, str]:
    return dict(load_manifest()["critical_repeats"])


def build_timing_report(group: str, tests: int, passed: int, failed: int, duration_seconds: float,
                        slowest: list[str]) -> dict[str, Any]:
    return {"group": group, "tests": tests, "passed": passed, "failed": failed,
            "duration_seconds": duration_seconds, "slowest": list(slowest)}


_PLUGIN_SOURCE = r'''
import json, os
_results = {}
_collection_errors = []
_deselected = []
def pytest_collectreport(report):
    if report.failed:
        _collection_errors.append(str(report.nodeid))
def pytest_deselected(items):
    _deselected.extend(item.nodeid for item in items)
def pytest_runtest_logreport(report):
    if report.when not in ("setup", "call", "teardown"):
        return
    current = _results.setdefault(report.nodeid, {"node_id": report.nodeid, "terminal_status": "PASS", "duration": 0.0, "attempt": 1})
    current["duration"] += float(getattr(report, "duration", 0.0) or 0.0)
    if report.failed:
        current["terminal_status"] = "FAIL" if report.when == "call" else "ERROR"
    elif report.skipped and current["terminal_status"] == "PASS":
        current["terminal_status"] = "SKIP"
def pytest_sessionfinish(session, exitstatus):
    payload = {"collection_status": "ERROR" if _collection_errors else "PASS", "collection_errors": list(_collection_errors), "deselected": sorted(_deselected), "results": sorted(_results.values(), key=lambda item: item["node_id"]), "pytest_exitstatus": int(exitstatus)}
    path = os.environ.get("P2_RESULTS_PATH")
    if path:
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True)
'''


def _capture_pytest(selection: Sequence[str], *, cwd: Path, timeout_seconds: float = 600.0,
                    pytest_args: Sequence[str] = ()) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="deep2fuzz-p2-capture-") as temp:
        temp_root = Path(temp)
        (temp_root / "p2_capture_plugin.py").write_text(_PLUGIN_SOURCE, encoding="utf-8")
        result_path = temp_root / "results.json"
        path_value = f"{temp_root}{os.pathsep}{ROOT}"
        if os.environ.get("PYTHONPATH"):
            path_value += os.pathsep + os.environ["PYTHONPATH"]
        env = stable_environment({"P2_RESULTS_PATH": str(result_path), "PYTHONPATH": path_value})
        command = [sys.executable, "-m", "pytest", "-p", "p2_capture_plugin", *selection, *pytest_args, "-q", "--durations=20"]
        started = time.monotonic()
        try:
            completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - started
            out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return {"collection_status": "ERROR", "collection_errors": ["timeout"], "deselected": [], "results": [], "pytest_exitstatus": None, "returncode": None, "timed_out": True, "duration_seconds": elapsed, "diagnostic": timeout_diagnostic(";".join(selection), elapsed, timeout_seconds, "timeout", err), "stdout": _sanitized(out), "stderr": _sanitized(err)}
        payload: dict[str, Any] = {"collection_status": "ERROR", "collection_errors": ["capture plugin did not emit results"], "deselected": [], "results": [], "pytest_exitstatus": completed.returncode}
        if result_path.is_file():
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                payload["collection_errors"] = ["capture result malformed"]
        payload.update({"returncode": completed.returncode, "timed_out": False, "duration_seconds": time.monotonic() - started, "stdout": _sanitized(completed.stdout or ""), "stderr": _sanitized(completed.stderr or "")})
        return payload


def _pytest_command(spec: dict[str, Any]) -> tuple[list[str], list[str]]:
    if isinstance(spec.get("members"), list):
        return list(spec["members"]), []
    return list(spec.get("files", [])), list(spec.get("pytest_args", []))


def _physical_status(payload: dict[str, Any]) -> str:
    if payload.get("timed_out") or payload.get("returncode") not in (0, None):
        return "FAIL"
    if payload.get("collection_status") != "PASS":
        return "ERROR"
    statuses = {result.get("terminal_status") for result in payload.get("results", [])}
    if "ERROR" in statuses:
        return "ERROR"
    if "FAIL" in statuses:
        return "FAIL"
    return "PASS"


def run_group(group: str, *, timeout_seconds: float = 600.0, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = manifest or load_manifest(validate_collection=True)
    spec = _group_spec(manifest, group)
    selection, pytest_args = _pytest_command(spec)
    started = time.monotonic()
    if "command" in spec:
        output_root = Path(tempfile.mkdtemp(prefix="deep2fuzz-p2-delivery-"))
        output_root.rmdir()
        environment = stable_environment({"ROOT": str(ROOT), "OUT_DIR": str(output_root), "PYTHON_BIN": sys.executable, "MAX_TEST_CASES": "8", "TIME_BUDGET": "5", "HARD_TIMEOUT": "20", "AFL_RAND_SEED": "20261026"})
        try:
            completed = subprocess.run([sys.executable, *spec["command"]], cwd=ROOT, env=environment, text=True, capture_output=True, timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - started
            err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return {"group": group, "tests": spec["expected_tests"], "passed": 0, "failed": 1, "duration_seconds": elapsed, "timed_out": True, "returncode": None, "acceptance_status": "FAIL", "physical_execution": {"returncode": None, "results": []}, "diagnostic": timeout_diagnostic(group, elapsed, timeout_seconds, "timeout", err), "stderr": _sanitized(err)}
        output = completed.stdout or ""
        passed_match = _PASSED_RE.search(output)
        failed_match = _FAILED_RE.search(output)
        passed = int(passed_match.group("count")) if passed_match else (spec["expected_tests"] if completed.returncode == 0 else 0)
        failed = int(failed_match.group("count")) if failed_match else (0 if completed.returncode == 0 else 1)
        return {"group": group, "tests": spec["expected_tests"], "passed": passed, "failed": failed, "duration_seconds": time.monotonic() - started, "timed_out": False, "returncode": completed.returncode, "acceptance_status": "PASS" if completed.returncode == 0 else "FAIL", "physical_execution": {"returncode": completed.returncode, "results": []}, "stdout_tail": _sanitized(output), "stderr": _sanitized(completed.stderr or "")}
    payload = _capture_pytest(selection, cwd=ROOT, timeout_seconds=timeout_seconds, pytest_args=pytest_args)
    results = payload.get("results", [])
    projection = project_gates(manifest, group, results, collection_status=payload.get("collection_status", "ERROR"), deselected=payload.get("deselected", []), collection_errors=payload.get("collection_errors", []))
    physical_status = _physical_status(payload)
    acceptance_status = projection["verdict"] if projection["verdict"] != "NOT_APPLICABLE" else physical_status
    passed = sum(result.get("terminal_status") == "PASS" for result in results)
    failed = sum(result.get("terminal_status") in {"FAIL", "ERROR"} for result in results)
    return {"group": group, "tests": spec["expected_tests"], "passed": passed, "failed": failed, "duration_seconds": payload.get("duration_seconds", 0.0), "timed_out": payload.get("timed_out", False), "returncode": payload.get("returncode"), "acceptance_status": acceptance_status, "physical_execution": payload, "logical_gate_projection": projection, "slowest": [line.strip() for line in payload.get("stdout", "").splitlines() if "s call" in line][-20:], "stdout_tail": payload.get("stdout", ""), "stderr": payload.get("stderr", "")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run explicit Deep2Fuzz offline test groups")
    parser.add_argument("--group", required=True, metavar="GROUP")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.repeat <= 0:
        parser.error("--repeat must be positive")
    try:
        manifest = load_manifest(validate_collection=True)
        _group_spec(manifest, args.group)
        reports = [run_group(args.group, timeout_seconds=args.timeout, manifest=manifest) for _ in range(args.repeat)]
        retry = record_attempts(reports[:1])
        stability = repeat_stability(reports)
        payload = {"group": args.group, "repeat": args.repeat, "automatic_retry": False, "diagnostic_reruns": [], "independent_repeats": reports[1:], "first_attempt_acceptance": reports[0], "retry_semantics": retry, "repeat_stability": stability, "runs": reports, "logical_gate_projection": reports[0].get("logical_gate_projection")}
        print(json.dumps(payload, sort_keys=True))
        return 0 if retry["final_acceptance_status"] == "PASS" and stability["repeat_stable"] else 1
    except (ManifestError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"runner_status": "ERROR", "error": _sanitized(str(exc)), "automatic_retry": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
