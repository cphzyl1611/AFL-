"""Strict, offline validation for the versioned Deep2Fuzz run config.

The validator deliberately has no platform clients and never reads secret
values.  It only parses JSON, checks the local filesystem shape of declared
paths, and returns deterministic findings for the CLI or an execution hook.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping


SUPPORTED_SCHEMA_VERSIONS = frozenset({"1"})
SUPPORTED_PLATFORMS = frozenset({"mock_rest", "o2oa", "alfresco"})
MAX_EXACT_JSON_INTEGER = (2 ** 53) - 1
O2OA_PROFILES = frozenset({"o2oa_default"})
ALFRESCO_PROFILES = frozenset({
    "alfresco_ae_v1",
    "alfresco_afl_content_update_smoke",
    "alfresco_afl_online_filter_smoke",
    "alfresco_content_update",
    "alfresco_fanogan_v1_candidate",
    "alfresco_metadata_online_filter_smoke",
    "alfresco_metadata_update",
    "alfresco_multipart_online_filter_smoke",
    "alfresco_multipart_upload",
})
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOP_LEVEL = {
    "schema_version", "platform", "run", "inputs", "output", "validity",
    "cleanup", "platform_config",
}
_RUN_FIELDS = {"max_test_cases", "time_budget_seconds", "timeout_seconds"}
_INPUT_FIELDS = {"seed_file", "seed_dir"}
_OUTPUT_FIELDS = {"evidence_root"}
_VALIDITY_FIELDS = {"enabled"}
_CLEANUP_FIELDS = {"required"}
_PLATFORM_FIELDS = {"mock_rest", "o2oa", "alfresco"}
_MOCK_FIELDS = {"timeout_sec"}
_O2OA_FIELDS = {"profile", "token_env"}
_ALFRESCO_FIELDS = {"profile", "username_env", "password_env"}


@dataclass(frozen=True)
class ConfigFinding:
    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "message": self.message}


@dataclass
class ConfigValidationResult:
    """Validation result with a stable machine-readable representation."""

    source: Path
    normalized: dict[str, Any]
    errors: list[ConfigFinding]
    input_error: bool = False
    resolved_paths: dict[str, Path] | None = None

    @property
    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"

    def to_dict(self) -> dict[str, Any]:
        supplied = self.normalized.get("schema_version") if isinstance(self.normalized, dict) else None
        version = supplied if isinstance(supplied, str) and supplied in SUPPORTED_SCHEMA_VERSIONS else None
        payload: dict[str, Any] = {
            "schema_version": "1",
            "verdict": self.verdict,
            "config_schema_version": version,
            "errors": [finding.to_dict() for finding in self.errors],
        }
        return payload


def canonical_config_bytes(normalized: Mapping[str, Any]) -> bytes:
    """Serialize the already validated P1.2 representation deterministically."""
    return json.dumps(
        normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def config_fingerprint_sha256(normalized: Mapping[str, Any]) -> str:
    """Return the P1.2 canonical semantic configuration fingerprint."""
    import hashlib

    return hashlib.sha256(canonical_config_bytes(normalized)).hexdigest()


def _finding(errors: list[ConfigFinding], path: str, code: str, message: str) -> None:
    errors.append(ConfigFinding(path, code, message))


def _obj(value: Any, path: str, errors: list[ConfigFinding]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        _finding(errors, path, "INVALID_TYPE", "must be an object")
        return None
    return value


def _unknown_fields(value: Mapping[str, Any], allowed: set[str], path: str, errors: list[ConfigFinding]) -> None:
    for key in sorted(value):
        if key not in allowed:
            _finding(errors, f"{path}.{key}" if path else key, "UNKNOWN_FIELD", "field is not supported")


def _required(value: Mapping[str, Any], name: str, path: str, errors: list[ConfigFinding]) -> bool:
    if name not in value:
        _finding(errors, f"{path}.{name}" if path else name, "MISSING_REQUIRED", "field is required")
        return False
    return True


def _strict_bool(value: Any, path: str, errors: list[ConfigFinding]) -> bool:
    if not isinstance(value, bool):
        _finding(errors, path, "INVALID_TYPE", "must be a boolean")
        return False
    return True


def _strict_number(value: Any, path: str, errors: list[ConfigFinding]) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _finding(errors, path, "INVALID_TYPE", "must be a number")
        return False
    try:
        finite = math.isfinite(float(value))
    except OverflowError:
        finite = False
    if not finite:
        _finding(errors, path, "OUT_OF_RANGE", "must be finite")
        return False
    return True


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _strict_positive_number(value: Any, path: str, errors: list[ConfigFinding]) -> bool:
    if not _strict_number(value, path, errors):
        return False
    if float(value) <= 0:
        _finding(errors, path, "OUT_OF_RANGE", "must be greater than 0")
        return False
    return True


def _strict_positive_integer(value: Any, path: str, errors: list[ConfigFinding]) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        _finding(errors, path, "INVALID_TYPE", "must be an integer")
        return False
    if value <= 0:
        _finding(errors, path, "OUT_OF_RANGE", "must be greater than 0")
        return False
    if value > MAX_EXACT_JSON_INTEGER:
        _finding(errors, path, "OUT_OF_RANGE", "exceeds the exact integer range of the runtime JSON parser")
        return False
    return True


def _nonempty_string(value: Any, path: str, errors: list[ConfigFinding]) -> bool:
    if not isinstance(value, str):
        _finding(errors, path, "INVALID_TYPE", "must be a string")
        return False
    if not value.strip():
        _finding(errors, path, "INVALID_VALUE", "must not be empty")
        return False
    return True


def _env_name(value: Any, path: str, errors: list[ConfigFinding]) -> bool:
    if not _nonempty_string(value, path, errors):
        return False
    if not _ENV_NAME.fullmatch(value):
        _finding(errors, path, "INVALID_VALUE", "must name an environment variable")
        return False
    return True


def _path_value(value: Any, path: str, errors: list[ConfigFinding]) -> str | None:
    if not _nonempty_string(value, path, errors):
        return None
    return value


def _resolved_path(raw: str, config_dir: Path, path: str, errors: list[ConfigFinding]) -> Path | None:
    # A config-relative path stays relative; shell-style `~` expansion would
    # silently defeat the containment rule and make validation environment
    # dependent.
    supplied = Path(raw)
    candidate = supplied if supplied.is_absolute() else config_dir / supplied
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        _finding(errors, path, "PATH_ESCAPE", "path cannot be resolved safely")
        return None
    if not supplied.is_absolute():
        try:
            resolved.relative_to(config_dir)
        except ValueError:
            _finding(errors, path, "PATH_ESCAPE", "relative path escapes the config directory")
            return None
    return resolved


def _validate_input_path(value: Any, path: str, kind: str, config_dir: Path,
                         errors: list[ConfigFinding], resolved: dict[str, Path]) -> None:
    raw = _path_value(value, path, errors)
    if raw is None:
        return
    target = _resolved_path(raw, config_dir, path, errors)
    if target is None:
        return
    resolved[path] = target
    if not target.exists():
        _finding(errors, path, "PATH_NOT_FOUND", "declared input path does not exist")
    elif kind == "file" and not target.is_file():
        _finding(errors, path, "PATH_TYPE_MISMATCH", "declared seed_file must be a file")
    elif kind == "dir" and not target.is_dir():
        _finding(errors, path, "PATH_TYPE_MISMATCH", "declared seed_dir must be a directory")


def _validate_evidence_path(value: Any, config_dir: Path, errors: list[ConfigFinding], resolved: dict[str, Path]) -> None:
    raw = _path_value(value, "output.evidence_root", errors)
    if raw is None:
        return
    target = _resolved_path(raw, config_dir, "output.evidence_root", errors)
    if target is None:
        return
    resolved["output.evidence_root"] = target
    repo = Path(__file__).resolve().parents[1]
    try:
        target.relative_to(repo)
    except ValueError:
        pass
    else:
        _finding(errors, "output.evidence_root", "PATH_ESCAPE", "evidence root must be outside the repository")
    if target.exists():
        _finding(errors, "output.evidence_root", "INVALID_VALUE", "evidence root already exists")


def _validate_platform_block(platform: str, value: Any, errors: list[ConfigFinding]) -> None:
    path = f"platform_config.{platform}"
    block = _obj(value, path, errors)
    if block is None:
        return
    if platform == "mock_rest":
        _unknown_fields(block, _MOCK_FIELDS, path, errors)
        if "timeout_sec" in block:
            _strict_positive_number(block["timeout_sec"], f"{path}.timeout_sec", errors)
    elif platform == "o2oa":
        _unknown_fields(block, _O2OA_FIELDS, path, errors)
        if _required(block, "profile", path, errors) and _nonempty_string(block["profile"], f"{path}.profile", errors):
            if block["profile"] not in O2OA_PROFILES:
                _finding(errors, f"{path}.profile", "INVALID_ENUM", "profile is not supported")
        if _required(block, "token_env", path, errors):
            _env_name(block["token_env"], f"{path}.token_env", errors)
    else:
        _unknown_fields(block, _ALFRESCO_FIELDS, path, errors)
        if _required(block, "profile", path, errors) and _nonempty_string(block["profile"], f"{path}.profile", errors):
            if block["profile"] not in ALFRESCO_PROFILES:
                _finding(errors, f"{path}.profile", "INVALID_ENUM", "profile is not supported")
        for field in ("username_env", "password_env"):
            if _required(block, field, path, errors):
                _env_name(block[field], f"{path}.{field}", errors)


def _parse(path: Path) -> tuple[dict[str, Any] | None, ConfigFinding | None, bool]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, ConfigFinding("$", "INPUT_ERROR", "configuration file cannot be read"), True

    def reject_constant(_value: str) -> None:
        raise ValueError("non-finite JSON number")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = item
        return result

    try:
        value = json.loads(text, parse_constant=reject_constant, object_pairs_hook=reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError, TypeError, RecursionError):
        return None, ConfigFinding("$", "PARSE_ERROR", "configuration is not valid JSON"), False
    if not isinstance(value, dict):
        return None, ConfigFinding("$", "INVALID_TYPE", "configuration root must be an object"), False
    return value, None, False


def validate_config(path: str | Path) -> ConfigValidationResult:
    """Validate one JSON config without contacting services or mutating files."""
    source = Path(path)
    if not source.exists() or not source.is_file():
        result = ConfigValidationResult(source, {}, [ConfigFinding("$", "INPUT_ERROR", "configuration file does not exist")], True, {})
        return result
    try:
        config_dir = source.resolve().parent
    except (OSError, RuntimeError):
        return ConfigValidationResult(source, {}, [ConfigFinding("$", "INPUT_ERROR", "configuration path cannot be resolved")], True, {})
    value, parse_error, input_error = _parse(source)
    if parse_error is not None:
        return ConfigValidationResult(source, {}, [parse_error], input_error, {})
    assert value is not None
    config = copy.deepcopy(value)
    errors: list[ConfigFinding] = []
    resolved: dict[str, Path] = {}
    _unknown_fields(config, _TOP_LEVEL, "", errors)

    schema = config.get("schema_version")
    if "schema_version" not in config:
        _finding(errors, "schema_version", "MISSING_REQUIRED", "field is required")
    elif not isinstance(schema, str):
        _finding(errors, "schema_version", "INVALID_TYPE", "must be a string")
    elif schema not in SUPPORTED_SCHEMA_VERSIONS:
        _finding(errors, "schema_version", "UNSUPPORTED_SCHEMA_VERSION", "schema version is not supported")

    platform = config.get("platform")
    if "platform" not in config:
        _finding(errors, "platform", "MISSING_REQUIRED", "field is required")
    elif not isinstance(platform, str):
        _finding(errors, "platform", "INVALID_TYPE", "must be a string")
    elif platform not in SUPPORTED_PLATFORMS:
        _finding(errors, "platform", "UNSUPPORTED_PLATFORM", "platform is not supported")

    run = _obj(config.get("run"), "run", errors) if "run" in config else None
    if run is None and "run" not in config:
        _finding(errors, "run", "MISSING_REQUIRED", "field is required")
    if run is not None:
        _unknown_fields(run, _RUN_FIELDS, "run", errors)
        for field in sorted(_RUN_FIELDS):
            _required(run, field, "run", errors)
        if "max_test_cases" in run:
            _strict_positive_integer(run["max_test_cases"], "run.max_test_cases", errors)
        if "time_budget_seconds" in run:
            if _strict_positive_number(run["time_budget_seconds"], "run.time_budget_seconds", errors) and run["time_budget_seconds"] < 1:
                _finding(errors, "run.time_budget_seconds", "OUT_OF_RANGE", "must be at least 1 second")
            elif _is_finite_number(run["time_budget_seconds"]) and run["time_budget_seconds"] > MAX_EXACT_JSON_INTEGER:
                _finding(errors, "run.time_budget_seconds", "OUT_OF_RANGE", "exceeds the exact integer range of the runtime JSON parser")
        if "timeout_seconds" in run:
            _strict_positive_number(run["timeout_seconds"], "run.timeout_seconds", errors)
        if all(key in run and isinstance(run[key], (int, float)) and not isinstance(run[key], bool)
               and _is_finite_number(run[key]) for key in ("time_budget_seconds", "timeout_seconds")):
            if float(run["timeout_seconds"]) < float(run["time_budget_seconds"]):
                _finding(errors, "run.timeout_seconds", "CROSS_FIELD_CONSTRAINT", "timeout must cover the time budget")

    inputs = _obj(config.get("inputs"), "inputs", errors) if "inputs" in config else None
    if inputs is None and "inputs" not in config:
        _finding(errors, "inputs", "MISSING_REQUIRED", "field is required")
    if inputs is not None:
        _unknown_fields(inputs, _INPUT_FIELDS, "inputs", errors)
        has_file, has_dir = "seed_file" in inputs, "seed_dir" in inputs
        if not has_file and not has_dir:
            _finding(errors, "inputs", "MISSING_REQUIRED", "one of seed_file or seed_dir is required")
        if has_file and has_dir:
            _finding(errors, "inputs", "MUTUALLY_EXCLUSIVE", "seed_file and seed_dir cannot both be set")
        if has_file:
            _validate_input_path(inputs["seed_file"], "inputs.seed_file", "file", config_dir, errors, resolved)
        if has_dir:
            _validate_input_path(inputs["seed_dir"], "inputs.seed_dir", "dir", config_dir, errors, resolved)

    output = _obj(config.get("output"), "output", errors) if "output" in config else None
    if output is None and "output" not in config:
        _finding(errors, "output", "MISSING_REQUIRED", "field is required")
    if output is not None:
        _unknown_fields(output, _OUTPUT_FIELDS, "output", errors)
        if _required(output, "evidence_root", "output", errors):
            _validate_evidence_path(output["evidence_root"], config_dir, errors, resolved)

    validity = _obj(config.get("validity"), "validity", errors) if "validity" in config else None
    if validity is None and "validity" not in config:
        _finding(errors, "validity", "MISSING_REQUIRED", "field is required")
    if validity is not None:
        _unknown_fields(validity, _VALIDITY_FIELDS, "validity", errors)
        if _required(validity, "enabled", "validity", errors):
            _strict_bool(validity["enabled"], "validity.enabled", errors)

    selected = platform if isinstance(platform, str) and platform in SUPPORTED_PLATFORMS else None
    platform_config = _obj(config.get("platform_config"), "platform_config", errors) if "platform_config" in config else None
    if platform_config is None and "platform_config" not in config:
        _finding(errors, "platform_config", "MISSING_REQUIRED", "field is required")
    if platform_config is not None:
        _unknown_fields(platform_config, _PLATFORM_FIELDS, "platform_config", errors)
        if selected is not None and selected not in platform_config:
            _finding(errors, f"platform_config.{selected}", "MISSING_REQUIRED", "selected platform block is required")
        if selected is not None and selected in platform_config:
            _validate_platform_block(selected, platform_config[selected], errors)
        for other in sorted(set(platform_config) - ({selected} if selected else set())):
            if other in _PLATFORM_FIELDS:
                _finding(errors, f"platform_config.{other}", "CROSS_FIELD_CONSTRAINT", "only the selected platform block may be present")

    if selected == "mock_rest" and inputs is not None and "seed_dir" in inputs:
        seed_dir = resolved.get("inputs.seed_dir")
        if seed_dir is not None and seed_dir.is_dir():
            try:
                candidates = sorted(seed_dir.iterdir(), key=lambda item: item.name)
                files = [item for item in candidates if item.is_file()]
                escapes = [item for item in files if not item.resolve(strict=False).is_relative_to(seed_dir)]
            except (OSError, RuntimeError):
                files, escapes = [], []
                _finding(errors, "inputs.seed_dir", "INVALID_VALUE", "seed directory cannot be inspected safely")
            if escapes:
                _finding(errors, "inputs.seed_dir", "PATH_ESCAPE", "seed directory contains a symlink outside the directory")
            elif len(files) != 1:
                _finding(errors, "inputs.seed_dir", "CROSS_FIELD_CONSTRAINT", "mock_rest requires exactly one regular seed file")

    cleanup = config.get("cleanup")
    if selected == "mock_rest":
        if "cleanup" not in config:
            _finding(errors, "cleanup", "MISSING_REQUIRED", "field is required for mock_rest")
        else:
            cleanup_obj = _obj(cleanup, "cleanup", errors)
            if cleanup_obj is not None:
                _unknown_fields(cleanup_obj, _CLEANUP_FIELDS, "cleanup", errors)
                if _required(cleanup_obj, "required", "cleanup", errors):
                    if _strict_bool(cleanup_obj["required"], "cleanup.required", errors) and not cleanup_obj["required"]:
                        _finding(errors, "cleanup.required", "CROSS_FIELD_CONSTRAINT", "mock_rest object operations require cleanup")
    elif "cleanup" in config:
        cleanup_obj = _obj(cleanup, "cleanup", errors)
        if cleanup_obj is not None:
            _unknown_fields(cleanup_obj, _CLEANUP_FIELDS, "cleanup", errors)
            if "required" in cleanup_obj:
                _strict_bool(cleanup_obj["required"], "cleanup.required", errors)

    errors.sort(key=lambda item: (item.path, item.code, item.message))
    return ConfigValidationResult(source, config, errors, False, resolved)
