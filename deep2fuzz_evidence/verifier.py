"""Deterministic, offline, read-only validation of Deep2Fuzz evidence roots."""
from __future__ import annotations

import hashlib
import importlib.util
import csv
import json
import math
import os
import re
import stat
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable


ABS_TOL = 1e-12
REL_TOL = 1e-9
CHUNK_SIZE = 64 * 1024
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_JSONL_ROW_BYTES = 16 * 1024 * 1024
_JSON_REQUIRED_PLATFORM = (
    "eval_report.json", "formal_security_score.json", "identity_reconciliation.json",
    "core_mock_summary.json",
)
_JSONL_REQUIRED_PLATFORM = (
    "evidence/status.jsonl", "evidence/executions.jsonl", "evidence/state.jsonl",
    "evidence/mab_updates.jsonl", "evidence/seed_selection.jsonl",
    "evidence/adapter_events.jsonl",
)
_SECRET_PATTERNS = (
    ("authorization-header", re.compile(rb"(?i)authorization\s*[:=]\s*(?:basic|token|apikey)\s+([^\r\n]{8,})")),
    ("authorization-bearer", re.compile(rb"(?i)authorization\s*[:=]\s*bearer\s+([A-Za-z0-9._~+/=-]{12,})")),
    ("bearer-token", re.compile(rb"(?i)\bbearer\s+([A-Za-z0-9._~+/=-]{16,})")),
    ("private-key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("credential-field", re.compile(rb"(?i)[\"']?(?:password|passwd|client_secret|access_token|refresh_token|api[_-]?key|nv_token)[\"']?\s*[:=]\s*[\"']?([^\s\"',;}]{4,})")),
    ("cookie-value", re.compile(rb"(?i)(?:set-cookie|cookie)\s*[:=]\s*([^\r\n;]{8,})")),
)
_SAFE_SECRET_VALUES = {b"redacted", b"<redacted>", b"***", b"********", b"${secret}", b"${token}", b"<secret>"}


class EvidenceInputError(ValueError):
    """The evidence-root argument cannot be opened as a directory."""


@dataclass
class Check:
    name: str
    status: str
    message: str = ""
    artifact: str | None = None
    verification_level: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"name": self.name, "status": self.status}
        if self.message:
            value["message"] = self.message
        if self.artifact:
            value["artifact"] = self.artifact
        if self.verification_level:
            value["verification_level"] = self.verification_level
        return value


@dataclass
class VerificationResult:
    profile: str
    checks: list[Check] = field(default_factory=list)
    files_checked: int = 0
    bytes_checked: int = 0
    duration_ms: int = 0

    @property
    def verdict(self) -> str:
        return "FAIL" if any(check.status == "FAIL" for check in self.checks) else "PASS"

    def add(self, name: str, passed: bool | None, message: str = "", artifact: str | None = None,
            verification_level: str | None = None) -> None:
        status = "NOT_APPLICABLE" if passed is None else "PASS" if passed else "FAIL"
        self.checks.append(Check(name, status, message, artifact, verification_level))

    def to_dict(self) -> dict[str, Any]:
        counts = {name.lower(): sum(check.status == name for check in self.checks)
                  for name in ("PASS", "FAIL", "NOT_APPLICABLE", "WARN")}
        return {
            "schema_version": "1",
            "verdict": self.verdict,
            "profile": self.profile,
            "checks": [check.to_dict() for check in self.checks],
            "summary": {**counts, "files_checked": self.files_checked,
                        "bytes_checked": self.bytes_checked, "duration_ms": self.duration_ms},
        }


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _json_load(path: Path) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON numeric constant: {value}")

    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"JSON artifact exceeds the {MAX_JSON_BYTES}-byte validation limit")
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream, parse_constant=reject_constant)


def _jsonl_load(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            if len(line.encode("utf-8")) > MAX_JSONL_ROW_BYTES:
                raise ValueError(f"JSONL row {line_no} exceeds the validation limit")
            value = json.loads(line, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row {line_no} is not an object")
            rows.append(value)
    return rows


def _stats_load(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _int(values: dict[str, Any], key: str, default: int | None = None) -> int | None:
    if not isinstance(values, dict):
        return default
    value = values.get(key, default)
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _float(values: dict[str, Any], key: str) -> float | None:
    if not isinstance(values, dict):
        return None
    value = values.get(key)
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _same_number(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    try:
        a, b = float(left), float(right)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)


def _identity(row: dict[str, Any]) -> dict[str, Any]:
    nested = row.get("identity")
    return nested if isinstance(nested, dict) else row


def _seq(row: dict[str, Any]) -> int | None:
    value = row.get("exec_seq")
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _manifest(root: Path, files: list[Path]) -> tuple[str, str]:
    manifest = root / "SHA256SUMS.txt"
    if not manifest.exists():
        return "NOT_PRESENT", "checksum manifest is absent"
    parsed: dict[str, str] = {}
    try:
        with manifest.open("r", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                line = line.rstrip("\r\n")
                if not line:
                    continue
                match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", line)
                if not match:
                    return "FAIL", f"malformed checksum row {line_no}"
                digest, name = match.group(1).lower(), match.group(2).strip()
                rel = PurePosixPath(name)
                if rel.is_absolute() or ".." in rel.parts or not name or "\\" in name:
                    return "FAIL", f"unsafe checksum path on row {line_no}"
                previous = parsed.get(name)
                if previous is not None and previous != digest:
                    return "FAIL", f"conflicting duplicate checksum entry: {name}"
                parsed[name] = digest
        if not parsed:
            return "FAIL", "checksum manifest has no entries"
        for name, expected in parsed.items():
            path = root.joinpath(*PurePosixPath(name).parts)
            try:
                path.resolve(strict=True).relative_to(root)
            except (OSError, ValueError):
                return "FAIL", f"listed file is absent or escapes evidence root: {name}"
            if not path.is_file() or path.is_symlink():
                return "FAIL", f"listed file is absent or not a regular file: {name}"
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                return "FAIL", f"checksum mismatch: {name}"
    except (OSError, UnicodeError) as exc:
        return "FAIL", f"cannot read checksum manifest: {type(exc).__name__}"
    return "PASS", f"verified {len(parsed)} listed file(s)"


def _safe_secret_value(value: bytes) -> bool:
    cleaned = value.strip().strip(b"\"'").strip().lower()
    return not cleaned or cleaned in _SAFE_SECRET_VALUES or cleaned.startswith((b"${", b"<"))


def _secret_scan(path: Path) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    overlap = 1024
    tail = b""
    offset = 0
    seen: set[tuple[str, int]] = set()
    with path.open("rb") as stream:
        while True:
            block = stream.read(CHUNK_SIZE)
            if not block:
                break
            data = tail + block
            base = max(0, offset - len(tail))
            for category, pattern in _SECRET_PATTERNS:
                for match in pattern.finditer(data):
                    marker = (category, base + match.start())
                    if marker in seen:
                        continue
                    seen.add(marker)
                    candidate = match.group(1) if match.lastindex else b"secret"
                    if category == "private-key" or not _safe_secret_value(candidate):
                        findings.append((category, hashlib.sha256(candidate).hexdigest()[:12]))
            offset += len(block)
            tail = data[-overlap:]
    return findings


def _path_safety(root: Path, all_paths: list[Path]) -> tuple[bool, str]:
    for path in all_paths:
        try:
            mode = path.lstat().st_mode
        except OSError:
            return False, f"cannot inspect filesystem entry: {_relative(path, root)}"
        if stat.S_ISLNK(mode):
            resolved = path.resolve(strict=False)
            try:
                resolved.relative_to(root)
            except ValueError:
                return False, f"symlink escapes evidence root: {_relative(path, root)}"
    return True, "all filesystem entries remain within the selected root"


def _classify(root: Path) -> str:
    def regular(name: str) -> bool:
        try:
            return stat.S_ISREG((root / name).lstat().st_mode)
        except OSError:
            return False

    def directory(name: str) -> bool:
        try:
            return stat.S_ISDIR((root / name).lstat().st_mode)
        except OSError:
            return False

    # Profile detection must survive a missing contract artifact so the
    # profile-specific REQUIRED_ARTIFACTS check can explain the failure.
    if directory("evidence") and any(
        regular(name)
        for name in ("eval_report.json", "fuzzer_stats", "formal_score_stats.txt",
                     "identity_reconciliation.json", "core_mock_summary.json")
    ):
        return "platform-run"
    if any(regular(name) for name in (
        "sample_eval_report.json", "sample_fuzzer_stats.txt", "sample_metadata.json", "summary.csv"
    )):
        return "delivery-sample"
    if any(regular(name) for name in ("FINAL_STATUS.json", "EVIDENCE_PATHS.json")):
        return "audit-evidence"
    return "unknown"


def _walk(root: Path) -> tuple[list[Path], list[Path], list[str]]:
    files: list[Path] = []
    entries: list[Path] = []

    def record_error(exc: OSError) -> None:
        errors.append(f"{type(exc).__name__} while scanning evidence root")

    errors: list[str] = []
    for current, dirs, names in os.walk(root, topdown=True, onerror=record_error, followlinks=False):
        base = Path(current)
        dirs.sort()
        names.sort()
        for name in list(dirs):
            entry = base / name
            entries.append(entry)
            if entry.is_symlink():
                dirs.remove(name)
        for name in names:
            entry = base / name
            entries.append(entry)
            if not entry.is_symlink() and entry.is_file():
                files.append(entry)
    return files, entries, errors


def _common_checks(root: Path, result: VerificationResult, profile: str, files: list[Path], entries: list[Path],
                   scan_errors: list[str]) -> None:
    result.add("FILESYSTEM_SCAN", not scan_errors,
               "all evidence directories were traversed" if not scan_errors else "; ".join(scan_errors[:4]))
    safe, message = _path_safety(root, entries)
    result.add("PATH_SAFETY", safe, message)
    status, message = _manifest(root, files) if safe else ("FAIL", "manifest verification skipped because path safety failed")
    result.add("SHA256_MANIFEST", status == "PASS" if status != "NOT_PRESENT" else (False if profile == "audit-evidence" else None),
               message, "SHA256SUMS.txt")

    malformed: list[str] = []
    for path in files:
        suffix = path.suffix.lower()
        if suffix not in {".json", ".jsonl"}:
            continue
        try:
            if suffix == ".jsonl":
                _jsonl_load(path)
            else:
                parsed = _json_load(path)
                if not isinstance(parsed, (dict, list)):
                    raise ValueError("top-level JSON value must be object or array")
                if profile == "platform-run" and _relative(path, root) in _JSON_REQUIRED_PLATFORM and not isinstance(parsed, dict):
                    raise ValueError("platform contract JSON must be an object")
                if profile == "delivery-sample" and _relative(path, root) in {
                    "sample_eval_report.json", "eval_report.json", "sample_metadata.json"
                } and not isinstance(parsed, dict):
                    raise ValueError("delivery-sample contract JSON must be an object")
                if profile == "audit-evidence" and _relative(path, root) in {"FINAL_STATUS.json", "EVIDENCE_PATHS.json"} and not isinstance(parsed, dict):
                    raise ValueError("audit contract JSON must be an object")
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            malformed.append(_relative(path, root))
    result.add("JSON_PARSE_VALIDATION", not malformed,
               "all JSON artifacts parse" if not malformed else f"malformed JSON artifacts: {', '.join(malformed[:8])}")

    secrets: list[tuple[str, str, str]] = []
    secret_scan_errors: list[str] = []
    text_suffixes = {".json", ".jsonl", ".txt", ".log", ".csv", ".md", ".yaml", ".yml", ".env", ".ini", ".conf"}
    for path in files:
        if path.suffix.lower() not in text_suffixes:
            continue
        try:
            matches = _secret_scan(path)
        except OSError:
            secret_scan_errors.append(_relative(path, root))
            continue
        secrets.extend((_relative(path, root), category, fingerprint) for category, fingerprint in matches)
    if secrets:
        first = secrets[0]
        message = f"{len(secrets)} possible secret(s); first at {first[0]} ({first[1]}, fingerprint {first[2]})"
    else:
        message = "no credential-shaped values found in supported text artifacts"
    if secret_scan_errors:
        message += f"; could not scan {len(secret_scan_errors)} text artifact(s): {', '.join(secret_scan_errors[:4])}"
    result.add("SECRET_SCAN", not secrets and not secret_scan_errors, message)


def _platform_shape_ok(parsed: dict[str, Any]) -> tuple[bool, str]:
    expected_objects = [
        "eval_report.json", "formal_security_score.json", "identity_reconciliation.json",
        "core_mock_summary.json",
    ]
    for name in expected_objects:
        if not isinstance(parsed.get(name), dict):
            return False, f"{name} must contain a JSON object"
    identity_checks = parsed["identity_reconciliation.json"].get("checks")
    if not isinstance(identity_checks, dict):
        return False, "identity_reconciliation.json checks must be an object"
    report = parsed["eval_report.json"]
    for key in ("task", "validity", "exec", "security_state_cov", "err", "rec", "mab", "mab_journal", "formal_score_provenance"):
        if not isinstance(report.get(key), dict):
            return False, f"eval_report.json field {key} must be an object"
    score = parsed["formal_security_score.json"]
    if "formal_security_score" not in score or not isinstance(score.get("provenance"), dict):
        return False, "formal_security_score.json must contain score and provenance objects"
    score_provenance = report["formal_score_provenance"]
    if not isinstance(score_provenance.get("weights"), dict) or not isinstance(score_provenance.get("normalized_metrics"), dict):
        return False, "eval_report.json formal score provenance must contain weights and normalized_metrics objects"
    identity = parsed["identity_reconciliation.json"].get("identity")
    if identity is not None and not isinstance(identity, dict):
        return False, "identity_reconciliation.json identity must be an object when present"
    arms = report["mab"].get("arms")
    if not isinstance(arms, list) or any(not isinstance(arm, dict) for arm in arms):
        return False, "eval_report.json mab.arms must be an array of objects"
    return True, "platform-run contract JSON shapes are valid"



def _read_platform(root: Path, result: VerificationResult) -> tuple[dict[str, Any], dict[str, str], dict[str, list[dict[str, Any]]]]:
    parsed: dict[str, Any] = {}
    stats: dict[str, str] = {}
    rows: dict[str, list[dict[str, Any]]] = {}
    required = list(_JSON_REQUIRED_PLATFORM) + list(_JSONL_REQUIRED_PLATFORM) + ["fuzzer_stats", "formal_score_stats.txt"]
    missing = [name for name in required if not (root / name).is_file()]
    result.add("REQUIRED_ARTIFACTS", not missing,
               "all platform-run contract artifacts present" if not missing else "missing required artifacts: " + ", ".join(missing))
    json_names = [name for name in _JSON_REQUIRED_PLATFORM]
    if (root / "control/abort.json").is_file():
        json_names += ["control/abort.json", "run_status.json", "supervisor_termination.json"]
    for name in json_names:
        path = root / name
        if path.is_file():
            try:
                value = _json_load(path)
                if not isinstance(value, dict):
                    raise ValueError("expected JSON object")
                parsed[name] = value
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                pass
    for name in _JSONL_REQUIRED_PLATFORM:
        path = root / name
        if path.is_file():
            try:
                rows[name] = _jsonl_load(path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                rows[name] = []
    for name in ("fuzzer_stats", "formal_score_stats.txt"):
        if (root / name).is_file():
            try:
                stats[name] = _stats_load(root / name)
            except OSError:
                stats[name] = {}
    return parsed, stats, rows


def _platform_identity(result: VerificationResult, parsed: dict[str, Any], stats: dict[str, str],
                       rows: dict[str, list[dict[str, Any]]], root: Path) -> dict[int, dict[str, Any]]:
    statuses = rows.get("evidence/status.jsonl", [])
    executions = rows.get("evidence/executions.jsonl", [])
    states = rows.get("evidence/state.jsonl", [])
    events = rows.get("evidence/adapter_events.jsonl", [])
    mabs = [row for row in rows.get("evidence/mab_updates.jsonl", []) if row.get("event") == "mab_update"]
    status_by_seq: dict[int, dict[str, Any]] = {}
    identity_ok = bool(statuses)
    baseline: dict[str, Any] | None = None
    for row in statuses:
        seq = _seq(row)
        identity = {key: row.get(key) for key in ("task_id", "run_id", "seed_id")}
        if seq is None or any(not isinstance(identity[key], str) or not identity[key] for key in identity):
            identity_ok = False
            continue
        if not isinstance(row.get("mutation_arm"), str) or not row["mutation_arm"]:
            identity_ok = False
        if seq in status_by_seq:
            identity_ok = False
        status_by_seq[seq] = row
        task_run = {key: identity[key] for key in ("task_id", "run_id")}
        if baseline is None:
            baseline = task_run
        elif task_run != baseline:
            identity_ok = False
        if row.get("run_id") != root.name:
            identity_ok = False

    executed_ledger: dict[int, dict[str, Any]] = {}
    for row in executions:
        if row.get("event") != "execution" or not row.get("status_observed"):
            continue
        seq = _seq(row)
        if seq is None or seq not in status_by_seq or seq in executed_ledger:
            identity_ok = False
            continue
        status = status_by_seq[seq]
        if row.get("target_invoked") is not True or row.get("arm_match") is not True:
            identity_ok = False
        if row.get("selected_arm") != row.get("actual_used_arm"):
            identity_ok = False
        if status.get("mutation_arm") != f"arm-{row.get('actual_used_arm')}":
            identity_ok = False
        executed_ledger[seq] = row
    for row in executions:
        if row.get("status_observed") and _seq(row) is None:
            identity_ok = False

    state_by_seq: dict[int, dict[str, Any]] = {}
    for row in states:
        seq = _seq(row)
        if seq is None or seq not in status_by_seq:
            identity_ok = False
            continue
        if seq in state_by_seq:
            identity_ok = False
        state_by_seq[seq] = row
        status = status_by_seq[seq]
        expected_state = f"{status.get('method')} {status.get('path')}|{status.get('class')}"
        if row.get("state") != expected_state:
            identity_ok = False
    state_seqs = [_seq(row) for row in states]
    if len(state_seqs) != len(set(state_seqs)):
        identity_ok = False

    for row in events:
        identity = _identity(row)
        seq = _seq(identity)
        if seq is None or seq not in status_by_seq:
            identity_ok = False
            continue
        status = status_by_seq[seq]
        if any(identity.get(key) != status.get(key) for key in ("task_id", "run_id", "seed_id", "mutation_arm")):
            identity_ok = False
        if row.get("created_object_id") is not None and status.get("run_id") != root.name:
            identity_ok = False

    mab_ok = True
    seen_mabs: set[int] = set()
    arm_counts = [0, 0, 0]
    for row in mabs:
        seq = _seq(row)
        if seq is None or seq not in status_by_seq or seq not in executed_ledger or seq in seen_mabs:
            mab_ok = False
            continue
        seen_mabs.add(seq)
        status = status_by_seq[seq]
        if (row.get("arm_match") is not True or row.get("selected_arm") != row.get("actual_used_arm")
                or status.get("mutation_arm") != f"arm-{row.get('actual_used_arm')}"):
            mab_ok = False
        arm = row.get("actual_used_arm")
        if isinstance(arm, bool) or not isinstance(arm, int) or not 0 <= arm < len(arm_counts):
            mab_ok = False
        else:
            arm_counts[arm] += 1

    mab_stats = stats.get("fuzzer_stats", {})
    expected_mab_total = _int(mab_stats, "nv_mab_total_pulls")
    expected_arm_counts = [_int(mab_stats, f"nv_mab_arm{index}_pulls") for index in range(3)]
    mab_counts_ok = (
        expected_mab_total is not None
        and expected_arm_counts == arm_counts
        and expected_mab_total == len(mabs)
    )

    identity_json = parsed.get("identity_reconciliation.json", {})
    recorded = identity_json.get("checks", {}) if isinstance(identity_json, dict) else {}
    for name in ("status_identity", "adapter_to_status", "execution_ledger_to_status", "state_to_status", "mab_arm_to_status", "report_to_reward_source"):
        if recorded.get(name) not in (True, "PASS", "NOT_APPLICABLE"):
            identity_ok = False
    report = parsed.get("eval_report.json", {})
    report_seq = _int(report.get("security_state_cov", {}), "security_state_reward_src_seq") if isinstance(report, dict) else None
    if report_seq:
        if report_seq not in status_by_seq or report_seq not in seen_mabs:
            identity_ok = False
        else:
            src = status_by_seq[report_seq]
            ident = identity_json.get("identity", {}) if isinstance(identity_json, dict) else {}
            if ident and any(ident.get(key) != src.get(key) for key in ("task_id", "run_id", "seed_id", "mutation_arm")):
                identity_ok = False
            if ident and _seq(ident) != report_seq:
                identity_ok = False
    elif report_seq != 0:
        identity_ok = False

    no_execution_rejection = (parsed.get("core_mock_summary.json", {}).get("scenario") == "validity_rejection"
                              and not statuses and not states and not mabs)
    result.add("EXECUTION_IDENTITY_RECONCILIATION", None if no_execution_rejection or
               parsed.get("core_mock_summary.json", {}).get("scenario") == "validity_rejection" else identity_ok,
               "no target execution occurred after validity rejection" if no_execution_rejection else
               "status, execution, state, adapter, MAB, report and run identities reconcile")
    result.add("MAB_ATTRIBUTION_RECONCILIATION", mab_ok and mab_counts_ok,
               "each MAB update has one attributable execution and journal pull counters agree")
    return status_by_seq


def _platform_validity(result: VerificationResult, parsed: dict[str, Any], stats: dict[str, str], rows: dict[str, list[dict[str, Any]]]) -> None:
    values = stats.get("fuzzer_stats", {})
    summary = parsed.get("core_mock_summary.json", {})
    report = parsed.get("eval_report.json", {})
    valid, invalid, executions = (_int(values, key) for key in ("nv_valid_cnt", "nv_invalid_cnt", "nv_total_valid_exec"))
    enabled = _int(values, "nv_enable_validity")
    candidates = _int(values, "nv_execution_iteration")
    passed = bool(valid is not None and invalid is not None and executions is not None and enabled == 1
                  and min(valid, invalid, executions) >= 0 and executions <= valid
                  and (candidates is None or candidates == valid + invalid)
                  and summary.get("validity_enabled") is True
                  and report.get("task", {}).get("enable_validity") == 1
                  and report.get("validity", {}).get("valid_cnt") == valid
                  and report.get("validity", {}).get("invalid_cnt") == invalid
                  and report.get("exec", {}).get("valid_exec") == executions)
    if candidates is not None and candidates > 0:
        expected_invalid_rate = invalid / candidates if invalid is not None and candidates else None
        report_rate = _float(report.get("validity", {}), "invalid_rate")
        stat_rate = _float(values, "nv_invalid_rate")
        passed = bool(passed and expected_invalid_rate is not None
                      and _same_number(report_rate, expected_invalid_rate)
                      and (stat_rate is None or _same_number(stat_rate, expected_invalid_rate)))
    scenario = summary.get("scenario")
    if scenario == "validity_rejection":
        ledger = rows.get("evidence/executions.jsonl", [])
        rejected = [row for row in ledger if row.get("mab_outcome") == "body_validation_reject"]
        events = rows.get("evidence/adapter_events.jsonl", [])
        journal_updates = [row for row in rows.get("evidence/mab_updates.jsonl", []) if row.get("event") == "mab_update"]
        passed = bool(passed and invalid > 0 and executions == 0 and summary.get("requests") == 0
                      and not journal_updates
                      and not rows.get("evidence/status.jsonl")
                      and not rows.get("evidence/state.jsonl")
                      and _int(values, "nv_mab_total_pulls") == 0
                      and report.get("mab", {}).get("total_pulls") == 0
                      and _int(values, "security_state_seed_credit") == 0
                      and rejected and all(row.get("target_invoked") is False and row.get("status_observed") is False
                                           and row.get("exec_seq") is None for row in rejected)
                      and all(row.get("result", {}).get("expected_rejection") is True
                              and row.get("created_object_id") is None and not row.get("operations")
                              for row in events))
    result.add("VALIDITY_ACCOUNTING_RECONCILIATION", passed,
               "validity counts, execution totals and validity-enabled report agree")


def _platform_seed(result: VerificationResult, root: Path, parsed: dict[str, Any], stats: dict[str, str], rows: dict[str, list[dict[str, Any]]]) -> None:
    values = stats.get("fuzzer_stats", {})
    report = parsed.get("eval_report.json", {})
    credit = _int(values, "security_state_seed_credit")
    cov_sum = _int(values, "ss_cov_sum")
    total_new = _int(values, "security_state_new_total")
    selected = _int(values, "ss_selected_sum")
    seed_rows = rows.get("evidence/seed_selection.jsonl", [])
    raw_status_seed_ids = [row.get("seed_id") for row in rows.get("evidence/status.jsonl", [])]
    raw_event_seed_ids = [_identity(row).get("seed_id") for row in rows.get("evidence/adapter_events.jsonl", [])]
    seed_identity_types_ok = all(
        value is None or isinstance(value, str)
        for value in raw_status_seed_ids + raw_event_seed_ids
    )
    status_seed_ids = {value for value in raw_status_seed_ids if isinstance(value, str)}
    event_seed_ids = {value for value in raw_event_seed_ids if isinstance(value, str)}
    seed_files = sorted(path for path in (root / "seeds").glob("*") if path.is_file())
    try:
        derived_seed_ids = {"seed-" + _sha256_file(path)[:12] for path in seed_files}
    except OSError:
        derived_seed_ids = set()
    attributable_seed_ids = (status_seed_ids | event_seed_ids) - {None}
    passed = bool(credit is not None and cov_sum is not None and total_new is not None and selected is not None
                  and credit >= 0 and credit <= total_new and cov_sum == credit and selected >= cov_sum
                  and seed_rows and len(status_seed_ids - {None}) <= len(seed_files)
                  and len(event_seed_ids - {None}) <= len(seed_files)
                  and seed_identity_types_ok and (credit == 0 or attributable_seed_ids)
                  and (status_seed_ids - {None}).issubset(derived_seed_ids)
                  and (event_seed_ids - {None}).issubset(derived_seed_ids)
                  and report.get("security_state_cov", {}).get("security_state_seed_credit") == credit)
    result.add("SEED_ACCOUNTING_RECONCILIATION", passed,
               "selected seed, security-state credit and report counters reconcile")


def _platform_cov_err_rec(result: VerificationResult, parsed: dict[str, Any], stats: dict[str, str],
                          rows: dict[str, list[dict[str, Any]]]) -> None:
    values = stats.get("fuzzer_stats", {})
    score_stats = stats.get("formal_score_stats.txt", {})
    report = parsed.get("eval_report.json", {})
    cov = report.get("security_state_cov", {})
    state_total = _int(values, "security_state_new_total")
    capacity = _int(values, "security_state_capacity")
    obs = _int(values, "ss_cov_cnt")
    selected = _int(values, "ss_selected_cnt")
    cov_sum = _int(values, "ss_cov_sum")
    selected_sum = _int(values, "ss_selected_sum")
    cov_pass = bool(state_total is not None and capacity is not None and capacity > 0
                    and 0 <= state_total <= capacity and cov.get("security_state_new_total") == state_total
                    and cov.get("security_state_capacity") == capacity
                    and _int(values, "security_state_total") == cov.get("security_state_total")
                    and _int(values, "security_state_observations") == cov.get("security_state_observations")
                    and obs is not None and selected is not None and 0 <= obs <= selected
                    and obs <= capacity
                    and cov_sum is not None and selected_sum is not None and 0 <= cov_sum <= selected_sum)
    normalized_cov = report.get("formal_score_provenance", {}).get("normalized_metrics", {}).get("Cov")
    if state_total is not None and capacity:
        cov_pass = cov_pass and _same_number(normalized_cov, state_total / capacity)
    result.add("COV_ACCOUNTING_RECONCILIATION", cov_pass,
               "state totals, capacity, slot and scheduler accounting agree")

    err_exec = _int(values, "nv_err_exec")
    valid_exec = _int(values, "nv_total_valid_exec")
    err_rate = _float(values, "nv_err_rate")
    expected_rate = (err_exec / valid_exec) if err_exec is not None and valid_exec and valid_exec > 0 else (0.0 if err_exec == 0 and valid_exec == 0 else None)
    report_err = report.get("err", {})
    err_pass = bool(err_exec is not None and valid_exec is not None and err_rate is not None
                    and err_exec >= 0 and err_exec <= valid_exec and expected_rate is not None
                    and math.isclose(err_rate, expected_rate, rel_tol=1e-6, abs_tol=1e-6)
                    and report_err.get("err_exec") == err_exec and _same_number(report_err.get("err_rate"), err_rate))
    mab_records = _int(values, "nv_mab_journal_record_count")
    journal_records = sum(1 for row in rows.get("evidence/mab_updates.jsonl", []) if row.get("event"))
    if report.get("mab_journal", {}).get("record_count") != mab_records or journal_records != mab_records:
        err_pass = False
    result.add("ERR_ACCOUNTING_RECONCILIATION", err_pass,
               "Err numerator, eligible execution denominator and reported rate agree")

    rec = report.get("rec", {})
    opportunities = _int(score_stats, "recovery_opportunity_count")
    successes = _int(score_stats, "recovery_success_count")
    rec_policy = bool(opportunities is not None and successes is not None and 0 <= successes <= opportunities
                      and rec.get("recovery_opportunity_count") == opportunities
                      and rec.get("recovery_success_count") == successes
                      and rec.get("rec_total") == _int(values, "nv_rec_total")
                      and rec.get("rec_success") == _int(values, "nv_rec_success"))
    if opportunities == 0:
        rec_policy = rec_policy and rec.get("rec_rate", "missing") is None
    elif opportunities is not None and opportunities > 0:
        expected_rec = successes / opportunities
        rec_policy = rec_policy and _same_number(rec.get("rec_rate"), expected_rec)
    else:
        rec_policy = False
    result.add("REC_NULL_POLICY", rec_policy,
               "zero opportunities require null Rec; observed opportunities use successes/opportunities")


def _platform_state(result: VerificationResult, parsed: dict[str, Any], stats: dict[str, str],
                    rows: dict[str, list[dict[str, Any]]]) -> None:
    values = stats.get("fuzzer_stats", {})
    states = rows.get("evidence/state.jsonl", [])
    sequences = [_seq(row) for row in states]
    total_new = _int(values, "security_state_new_total")
    credit = _int(values, "security_state_seed_credit")
    summary = parsed.get("core_mock_summary.json", {})
    scenario = summary.get("scenario")
    if scenario == "validity_rejection" and not states:
        passed = total_new == 0 and credit == 0
    else:
        new_state_ids = [row.get("state_id") for row in states if _int(row, "new") == 1]
        passed = bool(states and None not in sequences and len(sequences) == len(set(sequences))
                      and sum(_int(row, "new", -1) or 0 for row in states) == total_new
                      and all(_int(row, "new") in (0, 1) for row in states)
                      and all(isinstance(row.get("state"), str) and row.get("state")
                              and isinstance(row.get("state_id"), str) and row.get("state_id") for row in states)
                      and all(isinstance(state_id, str) and state_id for state_id in new_state_ids)
                      and len(new_state_ids) == len(set(new_state_ids)) == total_new
                      and credit is not None and credit <= total_new
                      and parsed.get("eval_report.json", {}).get("security_state_cov", {}).get("security_state_new_total") == total_new)
    result.add("STATE_ACCOUNTING_RECONCILIATION", passed,
               "state observation ledger and cumulative state counters agree")


def _platform_err_classification(parsed: dict[str, Any], rows: dict[str, list[dict[str, Any]]], stats: dict[str, str]) -> bool:
    statuses = {_seq(row): row for row in rows.get("evidence/status.jsonl", []) if _seq(row) is not None}
    events = rows.get("evidence/adapter_events.jsonl", [])
    errors = _int(stats.get("fuzzer_stats", {}), "nv_err_exec")
    semantic_failures: set[int] = set()
    anomalous_statuses = {
        seq for seq, status in statuses.items()
        if bool(status.get("is_exception")) or (_int(status, "http_code") is not None and _int(status, "http_code") >= 500)
    }
    for event in events:
        identity = _identity(event)
        seq = _seq(identity)
        status = statuses.get(seq)
        response = event.get("result", {})
        if status is None or not isinstance(response, dict):
            continue
        http_code = _int(response, "http_code", 0)
        if response.get("expected_rejection") is True:
            if (response.get("semantic_failure") is True or bool(status.get("is_exception"))
                    or http_code is None or not 400 <= http_code < 500):
                return False
        if response.get("semantic_failure") is True:
            if status.get("semantic_failure") is False or not bool(status.get("is_exception")):
                return False
            semantic_failures.add(seq)
    return bool(errors is not None and errors >= 0 and errors <= len(anomalous_statuses)
                and (not semantic_failures or errors > 0))


def _platform_overall(result: VerificationResult, root: Path, parsed: dict[str, Any]) -> None:
    report = parsed.get("eval_report.json", {})
    score_doc = parsed.get("formal_security_score.json", {})
    provenance = report.get("formal_score_provenance")
    weights = provenance.get("weights") if isinstance(provenance, dict) else None
    if not isinstance(weights, dict) or not all(key in weights for key in ("beta1", "beta2", "beta3")):
        result.add("OVERALL_SCORE_RECONCILIATION", False, "formal score weights are missing from report provenance")
        return
    try:
        scorer_path = Path(__file__).resolve().parents[1] / "scripts" / "compute_formal_security_score.py"
        spec = importlib.util.spec_from_file_location("deep2fuzz_formal_security_score", scorer_path)
        if spec is None or spec.loader is None:
            raise ImportError("authoritative scorer is unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        FormalScoreConfig = module.FormalScoreConfig
        compute_from_stats = module.compute_from_stats
        config = FormalScoreConfig(float(weights["beta1"]), float(weights["beta2"]), float(weights["beta3"]))
        recomputed, _ = compute_from_stats(root / "formal_score_stats.txt", config)
    except (ImportError, OSError, ValueError, TypeError):
        result.add("OVERALL_SCORE_RECONCILIATION", False, "authoritative score utility could not recompute the score")
        return
    score_value = score_doc.get("formal_security_score", "missing")
    score_report = report.get("formal_security_score", "missing")
    passed = (score_report != "missing" and score_value != "missing"
              and _same_number(score_report, recomputed) and _same_number(score_value, recomputed))
    result.add("OVERALL_SCORE_RECONCILIATION", passed,
               f"formal score matches scripts/compute_formal_security_score.py (abs_tol={ABS_TOL:g}, rel_tol={REL_TOL:g})")


def _platform_reporting(result: VerificationResult, parsed: dict[str, Any], stats: dict[str, str]) -> None:
    report = parsed.get("eval_report.json", {})
    values = stats.get("fuzzer_stats", {})
    validity, execution, cov, err, rec, mab = (report.get(key, {}) for key in
                                               ("validity", "exec", "security_state_cov", "err", "rec", "mab"))
    checks = [
        execution.get("total_execs") == _int(values, "execs_done"),
        validity.get("valid_cnt") == _int(values, "nv_valid_cnt"),
        validity.get("invalid_cnt") == _int(values, "nv_invalid_cnt"),
        execution.get("valid_exec") == _int(values, "nv_total_valid_exec"),
        cov.get("security_state_seed_credit") == _int(values, "security_state_seed_credit"),
        cov.get("security_state_new_total") == _int(values, "security_state_new_total"),
        err.get("err_exec") == _int(values, "nv_err_exec"),
        rec.get("rec_total") == _int(values, "nv_rec_total"),
        rec.get("rec_success") == _int(values, "nv_rec_success"),
        mab.get("total_pulls") == _int(values, "nv_mab_total_pulls"),
        report.get("mab_journal", {}).get("record_count") == _int(values, "nv_mab_journal_record_count"),
        [arm.get("pulls") for arm in mab.get("arms", [])] == [_int(values, f"nv_mab_arm{index}_pulls") for index in range(3)],
    ]
    summary = parsed.get("core_mock_summary.json", {})
    terminal = summary.get("terminal") is True
    if not terminal:
        checks.append(summary.get("passed") is True)
    else:
        run_status = parsed.get("run_status.json", {})
        checks.extend((run_status.get("terminal") is True,
                       run_status.get("run_complete") is False,
                       run_status.get("passed") is False,
                       run_status.get("terminal_reason") == summary.get("terminal_reason")))
    result.add("REPORT_STATS_RECONCILIATION", all(checks),
               "eval report and fuzzer stats agree for fields exposed by this profile")


def _platform_cleanup_abort(result: VerificationResult, root: Path, parsed: dict[str, Any],
                            rows: dict[str, list[dict[str, Any]]], stats: dict[str, str]) -> None:
    events = rows.get("evidence/adapter_events.jsonl", [])
    summary = parsed.get("core_mock_summary.json", {})
    failed_cleanup_events: list[dict[str, Any]] = []
    if not events:
        cleanup_ok = summary.get("scenario") == "validity_rejection" and _int(stats.get("fuzzer_stats", {}), "nv_invalid_cnt", 0) > 0
    else:
        cleanup_ok = True
        for event in events:
            obj = event.get("created_object_id")
            if obj is not None:
                event_ok = event.get("cleanup_object_id") == obj and event.get("cleanup") is True and event.get("absence_verified") is True
                cleanup_ok = cleanup_ok and event_ok
                if not event_ok:
                    failed_cleanup_events.append(event)
            elif event.get("cleanup") is not True:
                cleanup_ok = False
    abort_path = root / "control/abort.json"
    abort_exists = abort_path.is_file()
    if abort_exists:
        marker = parsed.get("control/abort.json", {})
        terminal = parsed.get("run_status.json", {})
        supervisor = parsed.get("supervisor_termination.json", {})
        seq = _seq(marker)
        summary_counts = ["POST_CLEANUP_FAILURE_PLATFORM_EXECUTIONS", "POST_CLEANUP_FAILURE_OBJECT_CREATIONS",
                          "POST_ABORT_FALSE_MAB_PULLS", "POST_ABORT_FALSE_MAB_COMMITS",
                          "POST_ABORT_FALSE_SEED_CREDIT", "POST_ABORT_FALSE_STATE_UPDATES"]
        post_rows = []
        for name in ("evidence/status.jsonl", "evidence/executions.jsonl", "evidence/state.jsonl", "evidence/mab_updates.jsonl", "evidence/adapter_events.jsonl"):
            for row in rows.get(name, []):
                ident = _identity(row)
                row_seq = _seq(ident)
                if row_seq is not None and seq is not None and row_seq > seq:
                    post_rows.append(row)
        abort_ok = bool(marker.get("terminal") is True and marker.get("reason") == "CLEANUP_FAILED" and seq
                        and all(marker.get(key) for key in ("task_id", "run_id", "seed_id", "mutation_arm"))
                        and marker.get("run_id") == root.name
                        and terminal.get("terminal") is True and terminal.get("terminal_reason") == "CLEANUP_FAILED"
                        and terminal.get("passed") is False and terminal.get("run_complete") is False
                        and terminal.get("abort_exec_seq") == seq
                        and terminal.get("task_id") == marker.get("task_id")
                        and terminal.get("run_id") == marker.get("run_id")
                        and supervisor.get("requests_after_abort") == 0
                        and supervisor.get("creations_after_abort") == 0
                        and all(_int(summary, key) == 0 for key in summary_counts)
                        and not post_rows)
        if failed_cleanup_events:
            cleanup_ok = bool(abort_ok and all(
                _identity(event).get("task_id") == marker.get("task_id")
                and _identity(event).get("run_id") == marker.get("run_id")
                and _identity(event).get("seed_id") == marker.get("seed_id")
                and _identity(event).get("mutation_arm") == marker.get("mutation_arm")
                and _seq(_identity(event)) == seq
                and event.get("created_object_id") is not None
                for event in failed_cleanup_events
            ))
        else:
            cleanup_ok = cleanup_ok and abort_ok
        result.add("FAIL_CLOSED_RECONCILIATION", abort_ok,
                   "cleanup abort is terminal and no post-abort platform or accounting activity exists")
    else:
        result.add("FAIL_CLOSED_RECONCILIATION", None, "no abort marker present")
    result.add("CLEANUP_RECONCILIATION", cleanup_ok,
               "created objects have exact-ID cleanup and absence proof, or cleanup failure is terminal")


def _verify_platform(root: Path, result: VerificationResult, parsed: dict[str, Any], stats: dict[str, str], rows: dict[str, list[dict[str, Any]]]) -> None:
    shape_ok, shape_message = _platform_shape_ok(parsed)
    result.add("JSON_SCHEMA_VALIDATION", shape_ok, shape_message)
    if not shape_ok:
        for name in (
            "EXECUTION_IDENTITY_RECONCILIATION", "VALIDITY_ACCOUNTING_RECONCILIATION",
            "MAB_ATTRIBUTION_RECONCILIATION", "SEED_ACCOUNTING_RECONCILIATION",
            "COV_ACCOUNTING_RECONCILIATION", "ERR_ACCOUNTING_RECONCILIATION",
            "REC_NULL_POLICY", "OVERALL_SCORE_RECONCILIATION",
            "REPORT_STATS_RECONCILIATION", "CLEANUP_RECONCILIATION",
            "FAIL_CLOSED_RECONCILIATION",
        ):
            result.add(name, False, "skipped because platform contract JSON shape is invalid")
        return
    _platform_identity(result, parsed, stats, rows, root)
    _platform_validity(result, parsed, stats, rows)
    _platform_seed(result, root, parsed, stats, rows)
    _platform_cov_err_rec(result, parsed, stats, rows)
    _platform_state(result, parsed, stats, rows)
    err_check = next((check for check in result.checks if check.name == "ERR_ACCOUNTING_RECONCILIATION"), None)
    if err_check and err_check.status == "PASS" and not _platform_err_classification(parsed, rows, stats):
        err_check.status = "FAIL"
        err_check.message = "expected rejection and semantic failure classifications disagree with status/Err accounting"
    _platform_overall(result, root, parsed)
    _platform_reporting(result, parsed, stats)
    _platform_cleanup_abort(result, root, parsed, rows, stats)
    _verify_provenance(root, result, parsed.get("eval_report.json", {}), "platform-run", parsed)


def _verify_sample(root: Path, result: VerificationResult, files: list[Path]) -> None:
    required = ("sample_eval_report.json", "sample_fuzzer_stats.txt", "fuzzer_stats", "eval_report.json",
                "summary.csv", "security_states.jsonl")
    missing = [name for name in required if not (root / name).is_file()]
    result.add("REQUIRED_ARTIFACTS", not missing,
               "delivery sample contract artifacts present" if not missing else "missing required artifacts: " + ", ".join(missing))
    try:
        sample = _json_load(root / "sample_eval_report.json")
        report = _json_load(root / "eval_report.json")
        values = _stats_load(root / "fuzzer_stats")
        sample_stats = _stats_load(root / "sample_fuzzer_stats.txt")
        with (root / "summary.csv").open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            summary_row = next(reader, {})
            has_extra_rows = next(reader, None) is not None
        if has_extra_rows:
            summary_row = {}
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        sample, report, values, sample_stats, summary_row = {}, {}, {}, {}, {}
    shape_ok = bool(
        isinstance(sample, dict) and isinstance(report, dict)
        and isinstance(sample.get("formal_score_provenance"), dict)
        and isinstance(report.get("rec"), dict)
        and isinstance(sample.get("formal_score_provenance", {}).get("weights"), dict)
    )
    result.add("JSON_SCHEMA_VALIDATION", shape_ok,
               "delivery-sample report shapes are valid" if shape_ok else
               "sample_eval_report.json, eval_report.json, and nested score/Rec fields must be objects")
    if not shape_ok:
        for name in (
            "REPORT_STATS_RECONCILIATION", "REC_NULL_POLICY",
            "EXECUTION_IDENTITY_RECONCILIATION", "VALIDITY_ACCOUNTING_RECONCILIATION",
            "MAB_ATTRIBUTION_RECONCILIATION", "COV_ACCOUNTING_RECONCILIATION",
            "ERR_ACCOUNTING_RECONCILIATION", "SEED_ACCOUNTING_RECONCILIATION",
            "OVERALL_SCORE_RECONCILIATION", "SUMMARY_CSV_RECONCILIATION",
            "CLEANUP_RECONCILIATION", "FAIL_CLOSED_RECONCILIATION",
        ):
            result.add(name, False, "skipped because delivery-sample JSON shape is invalid")
        return
    sample_opportunities = sample.get("recovery_opportunity_count")
    sample_successes = sample.get("recovery_success_count")
    if sample_opportunities is None:
        sample_opportunities = _int(sample_stats, "nv_rec_total")
    if sample_successes is None:
        sample_successes = _int(sample_stats, "nv_rec_success")
    recovery_counts_ok = (
        isinstance(sample_opportunities, int) and not isinstance(sample_opportunities, bool)
        and isinstance(sample_successes, int) and not isinstance(sample_successes, bool)
        and 0 <= sample_successes <= sample_opportunities
    )
    if not recovery_counts_ok:
        result.add("JSON_SCHEMA_VALIDATION", False,
                   "delivery-sample recovery opportunity/success counts must be nonnegative integers with successes <= opportunities")
        for name in (
            "REPORT_STATS_RECONCILIATION", "REC_NULL_POLICY",
            "EXECUTION_IDENTITY_RECONCILIATION", "VALIDITY_ACCOUNTING_RECONCILIATION",
            "MAB_ATTRIBUTION_RECONCILIATION", "COV_ACCOUNTING_RECONCILIATION",
            "ERR_ACCOUNTING_RECONCILIATION", "SEED_ACCOUNTING_RECONCILIATION",
            "OVERALL_SCORE_RECONCILIATION", "SUMMARY_CSV_RECONCILIATION",
            "CLEANUP_RECONCILIATION", "FAIL_CLOSED_RECONCILIATION",
        ):
            result.add(name, False, "skipped because delivery-sample recovery counts are invalid")
        return
    mirrored_stat_keys = (
        "execs_done", "nv_enable_validity", "nv_valid_cnt", "nv_invalid_cnt",
        "nv_total_valid_exec", "nv_err_exec", "nv_err_rate", "nv_rec_total",
        "nv_rec_success", "nv_mab_total_pulls", "nv_mab_arm0_pulls",
        "nv_mab_arm1_pulls", "nv_mab_arm2_pulls", "security_state_total",
        "security_state_new_total", "security_state_observations",
        "security_state_seed_credit", "security_state_capacity", "ss_cov_sum",
        "ss_selected_sum",
    )
    mirrors_agree = all(
        key not in sample_stats or key not in values or sample_stats[key] == values[key]
        for key in mirrored_stat_keys
    )
    summary_ok = bool(mirrors_agree and sample.get("validity_enabled") is True
                      and sample.get("valid_exec") == _int(values, "nv_total_valid_exec")
                      and _int(sample_stats, "nv_total_valid_exec") == _int(values, "nv_total_valid_exec")
                      and sample.get("mab_total_pulls") == _int(values, "nv_mab_total_pulls")
                      and sample.get("security_state_new_total") == _int(values, "security_state_new_total")
                      and sample.get("security_state_capacity") == _int(values, "security_state_capacity")
                      and sample.get("task_id") and sample.get("run_id") == root.name
                      and _int(values, "nv_enable_validity") == 1
                      and sample_opportunities is not None and sample_successes is not None
                      and 0 <= sample_successes <= sample_opportunities
                      and report.get("rec", {}).get("recovery_opportunity_count") == sample_opportunities
                      and report.get("rec", {}).get("recovery_success_count") == sample_successes
                      and _same_number(report.get("formal_security_score"), sample.get("overall_score"))
                      and _same_number(sample.get("recovery_rate"), None if sample_opportunities == 0 else sample_successes / sample_opportunities))
    result.add("REPORT_STATS_RECONCILIATION", summary_ok,
               "sample report, core report and raw stats agree for shared fields")
    score_stats_path = root / "formal_score_stats.txt"
    scorer_path = score_stats_path if score_stats_path.is_file() else root / "sample_fuzzer_stats.txt"
    provenance = sample.get("formal_score_provenance", {})
    weights = provenance.get("weights", {}) if isinstance(provenance, dict) else {}
    opportunities = sample_opportunities
    successes = sample_successes
    rec_value = sample.get("recovery_rate")
    rec_expected = None if opportunities == 0 else (successes / opportunities if opportunities and successes is not None else None)
    rec_ok = opportunities is not None and successes is not None and 0 <= successes <= opportunities and _same_number(rec_value, rec_expected)
    result.add("REC_NULL_POLICY", rec_ok,
               "zero opportunity profiles require null; legacy profiles use their recorded recovery denominator")
    result.add("EXECUTION_IDENTITY_RECONCILIATION", bool(sample.get("task_id") and sample.get("run_id") == root.name),
               "sample task/run identity is present")
    result.add("VALIDITY_ACCOUNTING_RECONCILIATION", bool(sample.get("validity_enabled") is True and _int(values, "nv_enable_validity") == 1),
               "sample validity is explicitly enabled")
    result.add("MAB_ATTRIBUTION_RECONCILIATION", bool(sample.get("mab_total_pulls") == _int(values, "nv_mab_total_pulls")),
               "sample MAB pull total agrees with stats")
    state_total = _int(values, "security_state_new_total")
    capacity = _int(values, "security_state_capacity")
    cov_rate = sample.get("coverage_rate")
    cov_ok = bool(state_total is not None and capacity is not None and capacity > 0
                  and 0 <= state_total <= capacity and _same_number(cov_rate, state_total / capacity))
    result.add("COV_ACCOUNTING_RECONCILIATION", cov_ok, "sample coverage proxy matches state count/capacity")
    err = _int(values, "nv_err_exec")
    denominator = _int(values, "nv_total_valid_exec")
    err_rate = _float(values, "nv_err_rate")
    err_ok = bool(err is not None and denominator is not None and denominator >= err >= 0
                  and err_rate is not None and _same_number(sample.get("anomaly_rate"), err_rate)
                  and (denominator > 0 and math.isclose(err_rate, err / denominator, rel_tol=1e-6, abs_tol=1e-6)
                       or denominator == 0 and err == 0 and err_rate == 0.0))
    result.add("ERR_ACCOUNTING_RECONCILIATION", err_ok, "sample Err rate matches its eligible execution count")
    result.add("SEED_ACCOUNTING_RECONCILIATION",
               _int(values, "ss_cov_sum") == _int(values, "security_state_seed_credit"),
               "sample seed credit matches scheduler credit")
    score_ok = False
    if isinstance(weights, dict) and all(key in weights for key in ("beta1", "beta2", "beta3")):
        try:
            scorer_path = Path(__file__).resolve().parents[1] / "scripts" / "compute_formal_security_score.py"
            spec = importlib.util.spec_from_file_location("deep2fuzz_formal_security_score", scorer_path)
            if spec is None or spec.loader is None:
                raise ImportError("authoritative scorer is unavailable")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            score_source = score_stats_path if score_stats_path.is_file() else root / "sample_fuzzer_stats.txt"
            recomputed, _ = module.compute_from_stats(score_source, module.FormalScoreConfig(
                float(weights["beta1"]), float(weights["beta2"]), float(weights["beta3"])))
            score_ok = (_same_number(sample.get("overall_score"), recomputed)
                        and _same_number(report.get("formal_security_score"), recomputed))
        except (ImportError, OSError, ValueError, TypeError):
            score_ok = False
    result.add("OVERALL_SCORE_RECONCILIATION", score_ok,
               "sample score matches the existing formal scorer and recorded weights")
    csv_fields = (
        "execs_done", "nv_total_valid_exec", "nv_err_exec", "nv_mab_total_pulls",
        "arm0_pulls", "arm1_pulls", "arm2_pulls", "security_state_total",
        "security_state_new_total", "security_state_observations", "security_state_seed_credit",
        "security_state_capacity", "ss_cov_sum", "ss_selected_sum",
    )
    csv_stat_keys = {f"arm{index}_pulls": f"nv_mab_arm{index}_pulls" for index in range(3)}
    csv_ok = bool(summary_row and all(
        summary_row.get(field) == values.get(csv_stat_keys.get(field, field)) for field in csv_fields
    ))
    result.add("SUMMARY_CSV_RECONCILIATION", csv_ok,
               "delivery summary.csv exposes the same raw counters as fuzzer_stats")
    result.add("CLEANUP_RECONCILIATION", None, "delivery sample does not create platform objects")
    result.add("FAIL_CLOSED_RECONCILIATION", None, "delivery sample has no platform cleanup abort contract")
    _verify_provenance(root, result, sample, "delivery-sample", {"eval_report.json": report})


def _verify_provenance(root: Path, result: VerificationResult, report: dict[str, Any],
                       expected_profile: str, parsed: dict[str, Any]) -> None:
    from deep2fuzz_provenance import (
        ADAPTER_CONTRACT_VERSIONS,
        EVIDENCE_SCHEMA_VERSION,
        PRODUCT_NAME,
        PROVENANCE_SCHEMA_VERSION,
        SCORER_CONTRACT_FILES,
        SCORER_CONTRACT_ID,
        config_fingerprint_sha256,
        is_timezone_aware_iso8601,
        scorer_contract_fingerprint,
        source_identity,
    )
    from deep2fuzz_version import __version__

    provenance = report.get("provenance") if isinstance(report, dict) else None
    required = ((isinstance(report, dict) and report.get("provenance_required") is True)
                or (root / "provenance.json").is_file())
    if not isinstance(provenance, dict):
        result.add("PROVENANCE_MISSING", False if required else None,
                   "required provenance object is missing" if required else "legacy evidence has no provenance",
                   verification_level="STRUCTURAL")
        return

    result.add("PROVENANCE_MISSING", True, "machine-readable provenance object is present",
               verification_level="STRUCTURAL")
    schema_ok = provenance.get("provenance_schema_version") == PROVENANCE_SCHEMA_VERSION
    result.add("PROVENANCE_SCHEMA_UNSUPPORTED", schema_ok,
               "provenance schema version is supported" if schema_ok else "provenance schema is missing or unsupported",
               verification_level="STRUCTURAL")

    product = provenance.get("product") if isinstance(provenance.get("product"), dict) else {}
    result.add("PRODUCT_VERSION_MISMATCH",
               product.get("name") == PRODUCT_NAME and product.get("version") == __version__,
               "product name/version match the installed single source of truth",
               verification_level="RECOMPUTABLE")

    source = provenance.get("source") if isinstance(provenance.get("source"), dict) else {}
    commit = source.get("git_commit")
    tree = source.get("git_tree")
    commit_format = isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None
    tree_format = isinstance(tree, str) and re.fullmatch(r"[0-9a-f]{40}", tree) is not None
    try:
        actual_source = source_identity(Path(__file__).resolve().parents[1])
    except (OSError, RuntimeError, subprocess.SubprocessError):
        actual_source = None
    result.add("SOURCE_COMMIT_MISMATCH", bool(commit_format and actual_source and commit == actual_source["git_commit"]),
               "full commit SHA matches the current local source identity",
               verification_level="RECOMPUTABLE")
    result.add("SOURCE_TREE_MISMATCH", bool(tree_format and actual_source and tree == actual_source["git_tree"]),
               "full tree SHA matches the current local source identity",
               verification_level="RECOMPUTABLE")
    dirty = source.get("dirty")
    fingerprint = source.get("dirty_fingerprint_sha256")
    dirty_shape = (isinstance(dirty, bool)
                   and ((dirty and isinstance(fingerprint, str) and re.fullmatch(r"[0-9a-f]{64}", fingerprint))
                        or (not dirty and fingerprint is None)))
    dirty_match = bool(dirty_shape and actual_source
                       and dirty == actual_source["dirty"]
                       and fingerprint == actual_source["dirty_fingerprint_sha256"])
    result.add("SOURCE_DIRTY_FINGERPRINT_MISMATCH", dirty_match,
               "relevant dirty-source state/fingerprint matches the current local source",
               verification_level="RECOMPUTABLE")

    config = provenance.get("config") if isinstance(provenance.get("config"), dict) else {}
    config_path = root / "provenance_config.json"
    config_ok = False
    try:
        snapshot = _json_load(config_path)
        config_ok = bool(
            isinstance(snapshot, dict)
            and config.get("schema_version") == snapshot.get("schema_version")
            and isinstance(config.get("fingerprint_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", config["fingerprint_sha256"])
            and config_fingerprint_sha256(snapshot) == config["fingerprint_sha256"]
        )
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        snapshot = None
    result.add("CONFIG_FINGERPRINT_MISMATCH", config_ok,
               "P1.2 canonical config fingerprint matches the evidence config snapshot",
               verification_level="RECOMPUTABLE")

    platform = provenance.get("platform") if isinstance(provenance.get("platform"), dict) else {}
    if expected_profile == "delivery-sample":
        expected_adapter = report.get("platform_adapter", report.get("platform"))
    else:
        expected_adapter = report.get("platform_adapter", "mock_rest")
    adapter = platform.get("adapter")
    adapter_ok = bool(
        isinstance(adapter, str)
        and adapter in ADAPTER_CONTRACT_VERSIONS
        and adapter == expected_adapter
        and platform.get("adapter_contract_version") == ADAPTER_CONTRACT_VERSIONS.get(adapter)
    )
    result.add("ADAPTER_IDENTITY_MISMATCH", adapter_ok,
               "adapter name and contract version match the report profile; adapter identity is declared, not source-audited",
               verification_level="DECLARED_ONLY")

    scoring = provenance.get("scoring") if isinstance(provenance.get("scoring"), dict) else {}
    try:
        scorer_ok = bool(
            scoring.get("contract_id") == SCORER_CONTRACT_ID
            and scoring.get("contract_files") == list(SCORER_CONTRACT_FILES)
            and isinstance(scoring.get("contract_fingerprint_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", scoring["contract_fingerprint_sha256"])
            and scorer_contract_fingerprint(Path(__file__).resolve().parents[1])
                == scoring["contract_fingerprint_sha256"]
        )
    except (OSError, RuntimeError):
        scorer_ok = False
    result.add("SCORER_FINGERPRINT_MISMATCH", scorer_ok,
               "formal scorer contract ID/files/fingerprint recompute successfully",
               verification_level="RECOMPUTABLE")

    run = provenance.get("run") if isinstance(provenance.get("run"), dict) else {}
    reported_task = report.get("task_id") if expected_profile in {"delivery-sample", "audit-evidence"} else None
    if reported_task is None and isinstance(parsed.get("identity_reconciliation.json"), dict):
        identity = parsed["identity_reconciliation.json"].get("identity")
        if isinstance(identity, dict):
            reported_task = identity.get("task_id")
        elif expected_profile == "platform-run":
            reported_task = "phase1-1-mock"
    reported_run = report.get("run_id") if expected_profile == "audit-evidence" else None
    run_ok = bool(
        isinstance(run.get("run_id"), str) and run.get("run_id") == root.name
        and (reported_run is None or reported_run == run.get("run_id"))
        and isinstance(run.get("task_id"), str) and run.get("task_id")
        and (reported_task is None or run.get("task_id") == reported_task)
    )
    result.add("RUN_IDENTITY_INVALID", run_ok, "run/task identity is present and consistent",
               verification_level="STRUCTURAL")

    evidence = provenance.get("evidence") if isinstance(provenance.get("evidence"), dict) else {}
    profile_ok = evidence.get("profile") == expected_profile
    result.add("EVIDENCE_PROFILE_MISMATCH", profile_ok,
               "evidence profile matches the independently detected profile",
               verification_level="RECOMPUTABLE")
    evidence_schema_ok = evidence.get("schema_version") == EVIDENCE_SCHEMA_VERSION
    result.add("EVIDENCE_SCHEMA_VERSION_MISMATCH", evidence_schema_ok,
               "evidence schema version is supported", verification_level="STRUCTURAL")

    timestamp_ok = is_timezone_aware_iso8601(run.get("generated_at"))
    result.add("TIMESTAMP_INVALID", timestamp_ok,
               "generated_at is timezone-aware ISO 8601", verification_level="STRUCTURAL")

    artifact = root / "provenance.json"
    artifact_matches = False
    artifact_provenance = None
    try:
        artifact_provenance = _json_load(artifact)
        artifact_matches = artifact_provenance == provenance
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        pass
    result.add("PROVENANCE_ARTIFACT_MISMATCH", artifact_matches,
               "standalone evidence provenance matches the report object",
               verification_level="RECOMPUTABLE")
    embedded_report = parsed.get("eval_report.json") if isinstance(parsed, dict) else None
    report_matches = (isinstance(embedded_report, dict)
                      and embedded_report.get("provenance") == artifact_provenance
                      if isinstance(embedded_report, dict) else expected_profile != "delivery-sample")
    result.add("REPORT_PROVENANCE_MISMATCH", report_matches,
               "core and delivery report provenance objects agree",
               verification_level="RECOMPUTABLE")


def _verify_audit(root: Path, result: VerificationResult, files: list[Path]) -> None:
    final = root / "FINAL_STATUS.json"
    paths = root / "EVIDENCE_PATHS.json"
    try:
        status = _json_load(final)
        manifest = _json_load(paths)
        if not isinstance(status, dict) or not isinstance(manifest, dict):
            raise ValueError("expected JSON objects")
        status_ok = bool(status) and any(
            key.lower() in {"status", "result", "verdict"}
            or key.lower().endswith(("_status", "_result", "_verdict"))
            or key.lower() in {"passed", "complete", "completed"}
            or key.lower().endswith("_passed") and isinstance(value, bool)
            or isinstance(value, str) and value.upper() in {"PASS", "FAIL", "BLOCKED", "COMPLETE", "INCOMPLETE"}
            for key, value in status.items()
        )
        listed = manifest.get("files")
        if not isinstance(listed, list) or any(not isinstance(item, str) for item in listed):
            raise ValueError("EVIDENCE_PATHS files must be a string array")
        safe_listed: set[str] = set()
        integrity = True
        if len(listed) != len(set(listed)):
            integrity = False
        for item in listed:
            rel = PurePosixPath(item)
            if rel.is_absolute() or ".." in rel.parts or "\\" in item or not item:
                integrity = False
                continue
            name = rel.as_posix()
            safe_listed.add(name)
            target = root.joinpath(*rel.parts)
            try:
                target.resolve(strict=True).relative_to(root)
            except (OSError, ValueError):
                integrity = False
                continue
            if not target.is_file() or target.is_symlink():
                integrity = False
        actual = {_relative(path, root) for path in files
                  if _relative(path, root) not in {"EVIDENCE_PATHS.json", "SHA256SUMS.txt"}}
        # Both conventions exist in historical roots: some list the path
        # manifest itself, while newer manifests explicitly exclude it.
        comparable_listed = safe_listed - {"EVIDENCE_PATHS.json", "SHA256SUMS.txt"}
        count_key = next((key for key in (
            "file_count_excluding_path_manifest_and_checksum_manifest",
            "file_count_before_manifest",
        ) if key in manifest), None)
        count = _int(manifest, count_key) if count_key else None
        count_expected = len(comparable_listed) if count_key == "file_count_excluding_path_manifest_and_checksum_manifest" else len(safe_listed)
        if count is not None and count != count_expected:
            integrity = False
        if comparable_listed != actual:
            integrity = False
        result.add("AUDIT_FINAL_STATUS", status_ok, "machine-readable final status is present", "FINAL_STATUS.json")
        result.add("EVIDENCE_PATH_INTEGRITY", integrity, "listed artifact paths match files contained by the root", "EVIDENCE_PATHS.json")
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        result.add("AUDIT_FINAL_STATUS", False, "final status artifact is malformed", "FINAL_STATUS.json")
        result.add("EVIDENCE_PATH_INTEGRITY", False, "evidence path manifest is malformed", "EVIDENCE_PATHS.json")
    for name in ("EXECUTION_IDENTITY_RECONCILIATION", "VALIDITY_ACCOUNTING_RECONCILIATION",
                 "MAB_ATTRIBUTION_RECONCILIATION", "SEED_ACCOUNTING_RECONCILIATION",
                 "COV_ACCOUNTING_RECONCILIATION", "ERR_ACCOUNTING_RECONCILIATION",
                 "REC_NULL_POLICY", "OVERALL_SCORE_RECONCILIATION", "REPORT_STATS_RECONCILIATION",
                 "CLEANUP_RECONCILIATION", "FAIL_CLOSED_RECONCILIATION"):
        result.add(name, None, "not applicable to audit evidence")
    _verify_provenance(root, result, status if isinstance(status, dict) else {}, "audit-evidence", {})


def verify_evidence(run_root: str | os.PathLike[str]) -> VerificationResult:
    """Verify one existing evidence root without modifying it or contacting a service."""
    started = time.monotonic()
    supplied = Path(run_root).expanduser()
    try:
        mode = supplied.lstat().st_mode
    except OSError as exc:
        raise EvidenceInputError("evidence root does not exist or is not accessible") from exc
    if stat.S_ISLNK(mode):
        raise EvidenceInputError("evidence root must not be a symlink")
    if not stat.S_ISDIR(mode) or not os.access(supplied, os.R_OK | os.X_OK):
        raise EvidenceInputError("evidence root must be a readable directory")
    root = supplied.resolve(strict=True)
    files, entries, scan_errors = _walk(root)
    profile = _classify(root)
    result = VerificationResult(profile=profile)
    result.files_checked = len(files)
    for path in files:
        try:
            result.bytes_checked += path.stat(follow_symlinks=False).st_size
        except OSError:
            pass
    result.add("PROFILE_DETECTION", profile != "unknown", f"detected {profile}" if profile != "unknown" else "unsupported evidence-root profile")
    _common_checks(root, result, profile, files, entries, scan_errors)
    # Do not let any profile-specific reader follow an escaping symlink after
    # PATH_SAFETY has already failed.
    path_check = next(check for check in result.checks if check.name == "PATH_SAFETY")
    if path_check.status == "FAIL":
        result.duration_ms = max(0, int((time.monotonic() - started) * 1000))
        return result
    if profile == "platform-run":
        parsed, stats, rows = _read_platform(root, result)
        _verify_platform(root, result, parsed, stats, rows)
    elif profile == "delivery-sample":
        _verify_sample(root, result, files)
    elif profile == "audit-evidence":
        _verify_audit(root, result, files)
    result.duration_ms = max(0, int((time.monotonic() - started) * 1000))
    return result
