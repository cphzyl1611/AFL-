#!/usr/bin/env python3
"""Fail-closed repository secret scanner used by the release gate.

The scanner deliberately records locations and classifications only.  It never
puts a candidate secret in a report.  A file that cannot be inspected is
accounted for in ``files_skipped`` and makes a required scan INCOMPLETE.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_MAX_BYTES = 10 * 1024 * 1024
PLACEHOLDER_RE = re.compile(
    r"^(?:<[^>]+>|\$\{[^}]+\}|\$[A-Z][A-Z0-9_]*|"
    r"(?:USER|USERNAME|PASSWORD|PASSWD|EXAMPLE|DEMO|REDACTED|REDACTED_[A-Z0-9_]+|YOUR[_ -]?[A-Z0-9_]+|"
    r"THE[_ -]?REAL[_ -]?(?:TOKEN|PASSWORD)|CHANGE[_ -]?ME))$",
    re.IGNORECASE,
)
LOGGER_FALSE_POSITIVE_RE = re.compile(r"^alfresco\.repo\.admin(?:\.|$)", re.IGNORECASE)
ASSIGNMENT_RE = re.compile(
    r"(?P<name>ALFRESCO_PASS|FLOWABLE_PASS|API[_-]?KEY|SECRET(?:[_-]?KEY)?|"
    r"(?:ACCESS|AUTH)[_-]?TOKEN|TOKEN)"
    r"\s*(?<![=!<>])(?:=(?!=)|:(?!=))\s*(?:os\.getenv\([^,]+,\s*)?[\"']?(?P<value>[^\"'\s,)]+)"
)
USER_PASSWORD_RE = re.compile(
    r"(?P<user>[A-Za-z][A-Za-z0-9_.-]{1,40}):(?P<password>[^\s'\"`\\]{3,})"
)
BASIC_RE = re.compile(r"\bBasic\s+(?P<blob>[A-Za-z0-9+/]{12,}={0,2})")
BEARER_RE = re.compile(r"\bBearer\s+(?P<token>[A-Za-z0-9._~+/=-]{16,})")
AUTH_VALUE_RE = re.compile(
    r"(?i)(?:authorization\s*[:=]\s*[\"']?(?:basic|bearer)\s+)(?P<value>[^\s\"']+)"
)

# Explicit credential contexts.  A non-empty, non-placeholder value assigned to
# one of these field names is sensitive regardless of how "complex" it looks: a
# short all-lowercase dictionary word in a password field is a real credential,
# not a weak one to be waved through.  No complexity heuristic is applied.
CREDENTIAL_FIELD_NAMES = ("password", "passwd", "pwd", "secret", "token", "authorization")
# The separator must be a real assignment/mapping (``=``, ``:=``, ``:``), never a
# comparison (``==``, ``!=``, ``<=``) -- ``if (secret == NULL)`` is code, not a
# credential.  A leading ``$``/``%`` means a variable reference (``$PWD``).
CREDENTIAL_FIELD_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_$%])(?P<name>" + "|".join(CREDENTIAL_FIELD_NAMES) + r")(?![A-Za-z0-9_])"
    r"[\"']?\s*(?<![=!<>+\-*/&|^])(?::=|=|:)(?!=)\s*"
    r"(?P<value>\\?\"[^\"]*\\?\"|\\?\'[^\']*\\?\'|[^\s,;}\)]+)"
)
# Values that only name an auth *scheme* or a language constant.
CREDENTIAL_NON_VALUES = {
    "basic", "bearer", "digest", "none", "null", "nil", "undefined",
    "true", "false", "n/a", "na",
}
# Characters that only occur in code expressions, never inside a committed
# credential literal we would need to catch.
CREDENTIAL_VALUE_REJECT_CHARS = set("()[]{}<>\"'`\\|")
CREDENTIAL_VALUE_REJECT_PREFIXES = ("$", "%", "=", "+", "*", "&", ",", "#", "!=", "os.getenv",
                                    "os.environ", "getenv(", "process.env", "http://", "https://")
MIN_CREDENTIAL_VALUE_LEN = 3
# Formats where an unquoted ``key=value`` really is a committed literal.
CONFIG_LIKE_SUFFIXES = {".env", ".ini", ".cfg", ".conf", ".properties", ".yaml", ".yml", ".toml"}
# Environment variables whose value is treated as a live runtime secret and fed
# into the fail-closed report guard.  PWD/OLDPWD are shell state, not secrets.
# These are the credential variables used by the repository's HTTP paths.
# Keeping this explicit prevents unrelated CI/database secrets from entering
# the report guard merely because their names happen to look sensitive.
PROJECT_RUNTIME_SECRET_ENV_NAMES = frozenset(
    {
        "ALFRESCO_USER",
        "ALFRESCO_PASS",
        "FLOWABLE_USER",
        "FLOWABLE_PASS",
        "NV_TOKEN",
    }
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    category: str
    classification: str
    reason: str


@dataclass(frozen=True)
class SkippedFile:
    path: str
    reason: str


def _is_placeholder(value: str) -> bool:
    value = value.strip()
    folded = value.casefold()
    return (
        bool(PLACEHOLDER_RE.fullmatch(value))
        or bool(re.fullmatch(r"%[A-Z][A-Z0-9_]*%", value, re.IGNORECASE))
        or folded in {
            "...", "-}", "?nv_token", "none", "null", "nil", "undefined",
            "true", "false", "redacted", "empty",
        }
        or any(marker in folded for marker in ("your", "local-evidence", "audit-local"))
        or any(marker in value for marker in ("你的", "真实token", "当前会话token"))
    )


def _looks_like_logger_false_positive(value: str) -> bool:
    return bool(LOGGER_FALSE_POSITIVE_RE.match(value.strip()))


def _candidate(value: str, *, category: str, line: str) -> tuple[str, str] | None:
    value = value.strip().strip("'\"")
    if not value or value.startswith("$") or value.endswith("(") or "require_runtime_secret" in line or _is_placeholder(value):
        return None
    if _looks_like_logger_false_positive(value):
        return "FALSE_POSITIVE", "known Alfresco logger namespace"
    # Environment access is a runtime reference, not a committed value.
    if "getenv(" in line or "environ[" in line:
        if value.startswith(("os.getenv", "os.environ")):
            return None
    return "REAL_SECRET", category


def _unwrap_credential_value(raw: str, *, allow_unquoted: bool) -> str | None:
    """Return the committed literal behind a credential assignment, else None.

    Deliberately conservative about what counts as a *literal*: an unquoted
    value in a source file is an expression (``token = strtok(...)``), not a
    credential.  No complexity heuristic is applied -- a short, all-lowercase
    quoted value is still a credential.
    """
    value = raw.strip()
    quoted = False
    while value[:1] == "\\":
        value = value[1:]
    if value[:1] in {'"', "'"}:
        quote = value[0]
        quoted = True
        value = value[1:]
        if value.endswith("\\" + quote):
            value = value[:-2]
        elif value.endswith(quote):
            value = value[:-1]
    value = value.strip()
    if not quoted and not allow_unquoted:
        return None
    if len(value) < MIN_CREDENTIAL_VALUE_LEN:
        return None
    if value.lower() in CREDENTIAL_NON_VALUES:
        return None
    if any(ch.isspace() for ch in value):
        return None
    if any(ch in CREDENTIAL_VALUE_REJECT_CHARS for ch in value):
        return None
    if value.startswith(CREDENTIAL_VALUE_REJECT_PREFIXES) or "${" in value:
        return None
    return value


def _find_line_candidates(line: str, *, allow_unquoted: bool = False) -> list[tuple[str, str, str]]:
    """Return (category, value, reason) tuples without retaining them later."""
    out: list[tuple[str, str, str]] = []
    for m in ASSIGNMENT_RE.finditer(line):
        if "${" in line and m.group("name") in line:
            continue
        value = m.group("value")
        result = _candidate(value, category=m.group("name").upper(), line=line)
        if result:
            classification, reason = result
            out.append((m.group("name").upper(), value, reason if classification == "FALSE_POSITIVE" else classification))

    for m in BASIC_RE.finditer(line):
        blob = m.group("blob")
        # Decode only in memory; report metadata never includes the blob.
        try:
            decoded = base64.b64decode(blob, validate=True).decode("utf-8")
        except Exception:
            decoded = ""
        if decoded and ":" in decoded and not all(_is_placeholder(x) for x in decoded.split(":", 1)):
            out.append(("AUTHORIZATION_BASIC", blob, "Basic authorization value"))

    for m in BEARER_RE.finditer(line):
        out.append(("AUTHORIZATION_BEARER", m.group("token"), "Bearer authorization value"))

    for m in USER_PASSWORD_RE.finditer(line):
        user, password = m.group("user"), m.group("password")
        if user.lower() in {"http", "https", "ssh", "git", "file", "unix"}:
            continue
        literal = re.escape(m.group(0))
        explicit_context = re.search(rf"(?i)(?:-u|--user)\s+[\"']?{literal}", line)
        named_context = re.search(
            rf"(?i)(?:credential|auth(?:orization)?|account)\s*[:=]\s*[\"']?{literal}", line
        )
        if not (explicit_context or named_context):
            continue
        if _is_placeholder(user) or _is_placeholder(password):
            continue
        # Keep logger names and documentation prose out of credential findings.
        if _looks_like_logger_false_positive(user + ":" + password):
            continue
        out.append(("USER_PASSWORD", password, "user:password credential-shaped literal"))

    # Context-aware check: a literal next to account/password/user remains a
    # finding; broad suppression based on those words is intentionally absent.
    context_re = re.compile(
        r"(?i)[\"']?(?:account|password|passwd)[\"']?\s*[:=]\s*[\"']?(?P<value>[^\s,}\"']{8,})"
    )
    for m in context_re.finditer(line):
        value = m.group("value")
        if value.lower() in {"authorization", "alfresco.repo.admin"} or _is_placeholder(value):
            continue
        if value.startswith(("http://", "https://", "${", "<")):
            continue
        if any(value == prior[1] for prior in out):
            continue
        if re.search(r"[A-Z]", value) and re.search(r"[0-9]", value) and re.search(r"[^A-Za-z0-9]", value):
            out.append(("ACCOUNT_PASSWORD_CONTEXT", value, "credential in account/password context"))

    # Explicit credential fields: no complexity heuristic is applied here.
    for m in CREDENTIAL_FIELD_RE.finditer(line):
        value = _unwrap_credential_value(m.group("value"), allow_unquoted=allow_unquoted)
        if value is None:
            continue
        if _candidate(value, category="", line=line) is None:
            continue
        if _looks_like_logger_false_positive(value):
            continue
        if any(value == prior[1] for prior in out):
            continue
        out.append(
            (
                m.group("name").upper(),
                value,
                "literal value in explicit credential context",
            )
        )
    return out


def scan_file(path: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> tuple[list[Finding], SkippedFile | None]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        return [], SkippedFile(str(path), f"stat_error:{type(exc).__name__}")
    if size > max_bytes:
        return [], SkippedFile(str(path), f"oversized:{size}>{max_bytes}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [], SkippedFile(str(path), f"read_error:{type(exc).__name__}")
    if b"\x00" in data:
        return [], SkippedFile(str(path), "binary_or_nul")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [], SkippedFile(str(path), "non_utf8_binary")

    allow_unquoted = path.suffix.lower() in CONFIG_LIKE_SUFFIXES or path.name.startswith(".env")
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for category, _value, reason in _find_line_candidates(line, allow_unquoted=allow_unquoted):
            classification = "FALSE_POSITIVE" if reason == "known Alfresco logger namespace" else "REAL_SECRET"
            findings.append(Finding(str(path), lineno, category, classification, reason))
    return findings, None


def scan_paths(paths: Iterable[Path], *, required: bool = True, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    findings: list[Finding] = []
    skipped: list[SkippedFile] = []
    files_scanned = 0
    for path in paths:
        if path.is_dir():
            children = sorted(p for p in path.rglob("*") if p.is_file())
            nested = scan_paths(children, required=required, max_bytes=max_bytes)
            findings.extend(Finding(**x) for x in nested["findings"])
            skipped.extend(SkippedFile(**x) for x in nested["files_skipped"])
            files_scanned += nested["files_scanned"]
            continue
        file_findings, skipped_file = scan_file(path, max_bytes=max_bytes)
        if skipped_file:
            skipped.append(skipped_file)
        else:
            files_scanned += 1
            findings.extend(file_findings)

    real = [f for f in findings if f.classification == "REAL_SECRET"]
    # Precedence is deliberate: a confirmed secret is a FAIL even when part of
    # the requested scope could not be inspected.  INCOMPLETE only ever reports
    # "clean so far, but coverage was not total".
    if real:
        status = "FAIL"
    elif required and skipped:
        status = "INCOMPLETE"
    else:
        status = "PASS"
    return {
        "status": status,
        "files_scanned": files_scanned,
        "files_skipped": [asdict(s) for s in skipped],
        "findings": [asdict(f) for f in findings],
        "real_secret_findings": len(real),
    }


class SecretSerializationError(RuntimeError):
    pass


# Fixed and non-sensitive: the message must never echo the value that tripped
# the guard, the environment variable it came from, or a path containing it.
SECRET_SERIALIZATION_MESSAGE = "refusing to serialize a report containing a secret"


def canonical_serialize(report: dict) -> bytes:
    """One canonical Unicode serialization used for both guard and disk."""
    return (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _iter_json_strings(value: object) -> Iterator[str]:
    """Yield every string a JSON consumer can read back out of ``value``."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from _iter_json_strings(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            yield from _iter_json_strings(item)


def assert_no_secrets(serialized_output: bytes, secret_values: Sequence[str]) -> None:
    """Fail closed unless the exact emitted bytes decode free of every secret.

    Raw-byte containment is not enough.  The canonical serializer escapes
    ``"``, ``\\``, tabs and newlines, so a secret carrying any of them never
    appears verbatim in the output -- while ``json.loads()`` over those same
    bytes hands the value back in full.  The guard therefore asks the only
    question that matches what a consumer can actually read: decode the bytes
    that are about to reach the sink and inspect every recoverable string.
    """
    # Blank and whitespace-only values carry no secret; ``strip`` decides
    # emptiness only, and the untouched value is what is matched against.
    monitored = [value for value in secret_values if isinstance(value, str) and value.strip()]
    if not monitored:
        return
    try:
        decoded = json.loads(serialized_output.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        # Output that cannot be inspected cannot be cleared.
        raise SecretSerializationError(SECRET_SERIALIZATION_MESSAGE) from None
    for text in _iter_json_strings(decoded):
        for protected in monitored:
            if protected in text:
                raise SecretSerializationError(SECRET_SERIALIZATION_MESSAGE)


def safe_write_report(path: Path, report: dict, secret_values: Sequence[str]) -> None:
    serialized_output = guarded_report_bytes(report, secret_values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(serialized_output)


def guarded_report_bytes(report: dict, secret_values: Sequence[str]) -> bytes:
    serialized_output = canonical_serialize(report)
    assert_no_secrets(serialized_output, secret_values)
    return serialized_output


def _emit_report_bytes(serialized_output: bytes) -> None:
    stream = getattr(sys.stdout, "buffer", None)
    if stream is not None:
        stream.write(serialized_output)
        stream.flush()
    else:
        sys.stdout.write(serialized_output.decode("utf-8"))
        sys.stdout.flush()


def runtime_secret_values(env: dict | None = None) -> list[str]:
    """Collect live credential values held by the current process environment.

    These are the values the fail-closed report guard must never emit.  Blank,
    whitespace-only and placeholder values carry no secret and are dropped.

    Surrounding whitespace is part of the value.  ``strip`` therefore decides
    only whether a value is blank -- the raw string is what gets monitored, and
    what dedup compares.  Monitoring a stripped copy would be wrong in both
    directions: it misses the padded value a report can really carry, and it
    blocks a report that only ever held the trimmed form.
    """
    source = os.environ if env is None else env
    values: list[str] = []
    for name in PROJECT_RUNTIME_SECRET_ENV_NAMES:
        if name not in source:
            continue
        value = source[name] or ""
        probe = value.strip()
        if not probe or _is_placeholder(probe):
            continue
        if value not in values:
            values.append(value)
    return values


def _tracked_files(root: Path) -> list[Path]:
    import subprocess

    names = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"], text=False).split(b"\0")
    return [root / n.decode("utf-8") for n in names if n]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--path", action="append", dest="paths", default=[])
    parser.add_argument("--include-tracked", action="store_true")
    parser.add_argument("--optional", action="store_true", help="skipped files do not make status INCOMPLETE")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    paths = [args.root / p for p in args.paths]
    if args.include_tracked:
        paths.extend(_tracked_files(args.root))
    if not paths:
        paths = [args.root]
    result = scan_paths(paths, required=not args.optional)
    secret_values = runtime_secret_values()
    # Guard stdout with the same fail-closed check before anything is emitted.
    serialized_output = guarded_report_bytes(result, secret_values)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(serialized_output)
    _emit_report_bytes(serialized_output)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
