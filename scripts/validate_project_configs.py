#!/usr/bin/env python3
"""Validate stage-delivery schemas, configs, seeds, and summary evidence.

This script intentionally uses only the Python standard library. It performs
lightweight structural checks; it is not a full jsonschema replacement and does
not start O2OA, Flowable, Alfresco, or fuzzing jobs.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

SCHEMA_FILES = [
    "schemas/fuzz_task.schema.json",
    "schemas/platform_profile.schema.json",
    "schemas/validity_rule.schema.json",
    "schemas/summary_header.schema.json",
]

DEMO_TASK = Path("docs/integration/examples/fuzz_submit_demo.json")
PLATFORM_PROFILE_GLOB = "integration/platform_profiles/*.json"
VALIDITY_RULE_GLOB = "validity/*.json"
SEED_GLOB = "in/**/*.json"

STANDARD_SUMMARIES = [
    Path("out/alfresco_metadata_update_manual_latest/summary.csv"),
    Path("out/alfresco_content_update_manual_latest/summary.csv"),
    Path("out/alfresco_multipart_upload_manual_latest/summary.csv"),
    Path("out/cms_body_valid_compare_real/summary.csv"),
    Path("out/real_service_smoke_20260508/o2oa_real/summary.csv"),
]

TEXT_SEED_DIRS = [
    Path("in/alfresco_content_update_dataset"),
    Path("in/alfresco_multipart_upload_dataset"),
]

NV_MAB_SUMMARIES = {
    Path("out/nv_mab_smoke_summary.csv"): {"case_name", "nv_mab_total_pulls", "arm0_pulls", "arm1_pulls", "arm2_pulls", "expected_pass"},
    Path("out/nv_mab_stability_summary.csv"): {
        "run_id",
        "nv_mab_total_pulls",
        "nv_mab_arm0_pulls",
        "nv_mab_arm1_pulls",
        "nv_mab_arm2_pulls",
        "expected_pass",
    },
    Path("out/nv_mab_ablation_summary.csv"): {"group", "nv_mab_total_pulls", "arm0_pulls", "arm1_pulls", "arm2_pulls", "expected_pass"},
}

SENSITIVE_PATTERNS = [
    re.compile("JOFj" + r"_[A-Za-z0-9_-]+"),
    re.compile("Authorization: " + r"[A-Za-z0-9_-]{10,}"),
    re.compile("x-token" + r"[:=][A-Za-z0-9_-]{10,}"),
    re.compile("Cookie: x-token=" + r"[A-Za-z0-9_-]{10,}"),
    re.compile("NV" + "_TOKEN=" + r"[A-Za-z0-9_-]{10,}"),
    re.compile("NV" + "_TOKEN=" + r".*[A-Za-z0-9_-]{24,}"),
]

ALLOW_SENSITIVE_CONTEXT = [
    "${NV_TOKEN}",
    "你的当前会话token",
    "placeholder",
    "example",
    "示例",
    "占位",
]


class ValidationState:
    def __init__(self) -> None:
        self.failed = False
        self.warnings: list[str] = []

    def pass_(self, name: str, detail: str = "") -> None:
        suffix = f" {detail}" if detail else ""
        print(f"PASS {name}{suffix}")

    def warn(self, name: str, detail: str) -> None:
        self.warnings.append(f"{name}: {detail}")
        print(f"WARN {name} {detail}")

    def fail(self, name: str, detail: str) -> None:
        self.failed = True
        print(f"FAIL {name} {detail}")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def has_allowed_sensitive_context(line: str) -> bool:
    lowered = line.lower()
    return any(token.lower() in lowered for token in ALLOW_SENSITIVE_CONTEXT)


def check_sensitive_text(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [f"{rel(path)}: read failed: {exc}"]
    for lineno, line in enumerate(lines, start=1):
        if not any(pattern.search(line) for pattern in SENSITIVE_PATTERNS):
            continue
        if has_allowed_sensitive_context(line):
            continue
        findings.append(f"{rel(path)}:{lineno}:{line[:180]}")
    return findings


def check_schemas(state: ValidationState) -> None:
    failures: list[str] = []
    for schema_file in SCHEMA_FILES:
        path = REPO_ROOT / schema_file
        if not path.is_file():
            failures.append(f"{schema_file}: missing")
            continue
        try:
            data = load_json(path)
        except Exception as exc:  # noqa: BLE001 - report parse failure.
            failures.append(f"{schema_file}: {exc}")
            continue
        if not isinstance(data, dict):
            failures.append(f"{schema_file}: top-level value is not object")
    if failures:
        state.fail("schemas", "; ".join(failures))
    else:
        state.pass_("schemas", f"count={len(SCHEMA_FILES)}")


def mutation_scope_is_valid(value: Any) -> bool:
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        return True
    if isinstance(value, list):
        return all(isinstance(item, str) for item in value)
    return False


def check_demo_task(state: ValidationState, sensitive_paths: list[Path]) -> None:
    path = REPO_ROOT / DEMO_TASK
    if not path.is_file():
        state.fail("fuzz_task_demo", f"{DEMO_TASK.as_posix()} missing")
        return
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        state.fail("fuzz_task_demo", f"{DEMO_TASK.as_posix()}: {exc}")
        return
    if not isinstance(data, dict):
        state.fail("fuzz_task_demo", "top-level value is not object")
        return
    if "target_type" not in data and "scenario" not in data:
        state.fail("fuzz_task_demo", "missing target_type or scenario")
        return
    if "mutation_scope" in data and not mutation_scope_is_valid(data["mutation_scope"]):
        state.fail("fuzz_task_demo", "mutation_scope must be int, str, or list[str]")
        return
    sensitive_paths.append(path)
    state.pass_("fuzz_task_demo", DEMO_TASK.as_posix())


def check_platform_profiles(state: ValidationState, sensitive_paths: list[Path]) -> None:
    paths = sorted((REPO_ROOT / "integration/platform_profiles").glob("*.json"))
    failures: list[str] = []
    warnings: list[str] = []
    for path in paths:
        try:
            data = load_json(path)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{rel(path)}: {exc}")
            continue
        if not isinstance(data, dict):
            failures.append(f"{rel(path)}: top-level value is not object")
            continue
        if "profile" not in data and "platform" not in data:
            failures.append(f"{rel(path)}: missing profile or platform")
        for key in ("endpoint", "method", "body_type"):
            if key in data and not isinstance(data[key], str):
                failures.append(f"{rel(path)}: {key} must be string")
        if "decision" in data:
            decision = data["decision"]
            if not isinstance(decision, dict):
                failures.append(f"{rel(path)}: decision must be object")
            elif "enable_second_stage" in decision and not isinstance(decision["enable_second_stage"], bool):
                failures.append(f"{rel(path)}: decision.enable_second_stage must be bool")
        if "validation_scope" not in data:
            warnings.append(f"{rel(path)}: missing validation_scope")
        sensitive_paths.append(path)
    for warning in warnings:
        state.warn("platform_profiles", warning)
    if failures:
        state.fail("platform_profiles", "; ".join(failures))
    else:
        state.pass_("platform_profiles", f"count={len(paths)}")


def validate_rule_value(path: Path, key: str, value: Any, failures: list[str]) -> None:
    path_label = rel(path)
    if key == "type" and not (isinstance(value, str) or (isinstance(value, list) and all(isinstance(item, str) for item in value))):
        failures.append(f"{path_label}: type must be string or list[str]")
    if key == "required" and not (isinstance(value, bool) or (isinstance(value, list) and all(isinstance(item, str) for item in value))):
        failures.append(f"{path_label}: required must be bool or list[str]")
    if key == "properties" and not isinstance(value, dict):
        failures.append(f"{path_label}: properties must be object")
    if key in {"minLength", "maxLength"} and not (isinstance(value, int) and value >= 0):
        failures.append(f"{path_label}: {key} must be non-negative integer")


def walk_rule_fields(path: Path, node: Any, failures: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            validate_rule_value(path, key, value, failures)
            walk_rule_fields(path, value, failures)
    elif isinstance(node, list):
        for item in node:
            walk_rule_fields(path, item, failures)


def check_validity_rules(state: ValidationState, sensitive_paths: list[Path]) -> None:
    paths = sorted((REPO_ROOT / "validity").glob("*.json"))
    failures: list[str] = []
    for path in paths:
        try:
            data = load_json(path)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{rel(path)}: {exc}")
            continue
        if not isinstance(data, (dict, list)):
            failures.append(f"{rel(path)}: top-level value must be object or array")
            continue
        walk_rule_fields(path, data, failures)
        sensitive_paths.append(path)
    if failures:
        state.fail("validity_rules", "; ".join(failures[:20]))
    else:
        state.pass_("validity_rules", f"count={len(paths)}")


def check_seeds(state: ValidationState, sensitive_paths: list[Path]) -> None:
    paths = sorted((REPO_ROOT / "in").glob("**/*.json"))
    failures: list[str] = []
    for path in paths:
        try:
            load_json(path)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{rel(path)}: {exc}")
            if len(failures) >= 20:
                break
        sensitive_paths.append(path)
    if failures:
        state.fail("seeds", "; ".join(failures))
    else:
        state.pass_("seeds", f"json_count={len(paths)}")


def check_text_seeds(state: ValidationState, sensitive_paths: list[Path]) -> None:
    failures: list[str] = []
    checked = 0
    for seed_dir in TEXT_SEED_DIRS:
        full_dir = REPO_ROOT / seed_dir
        if not full_dir.is_dir():
            failures.append(f"{seed_dir.as_posix()}: missing")
            continue
        txt_seeds = sorted(full_dir.glob("*.txt"))
        if len(txt_seeds) < 4:
            failures.append(f"{seed_dir.as_posix()}: expected at least 4 .txt seeds")
            continue
        for path in txt_seeds:
            try:
                body = path.read_bytes()
            except OSError as exc:
                failures.append(f"{rel(path)}: {exc}")
                continue
            if b"\x00" in body:
                failures.append(f"{rel(path)}: contains NUL byte")
            try:
                body.decode("utf-8")
            except UnicodeDecodeError as exc:
                failures.append(f"{rel(path)}: not utf-8 text: {exc}")
            sensitive_paths.append(path)
            checked += 1
    if failures:
        state.fail("text_seeds", "; ".join(failures[:20]))
    else:
        state.pass_("text_seeds", f"count={checked}")


def read_csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        return next(reader)


def check_summary_headers(state: ValidationState) -> None:
    schema = load_json(REPO_ROOT / "schemas/summary_header.schema.json")
    expected_standard = set(schema.get("expected_header", []))
    if not expected_standard:
        state.fail("summary_headers", "schemas/summary_header.schema.json missing expected_header")
        return

    failures: list[str] = []
    checked = 0

    for path, required in NV_MAB_SUMMARIES.items():
        full = REPO_ROOT / path
        if not full.is_file():
            failures.append(f"{path.as_posix()}: missing required NV_MAB summary")
            continue
        header = set(read_csv_header(full))
        missing = required - header
        if missing:
            failures.append(f"{path.as_posix()}: missing {sorted(missing)}")
        checked += 1

    for path in STANDARD_SUMMARIES:
        full = REPO_ROOT / path
        if not full.is_file():
            state.warn("summary_headers", f"{path.as_posix()}: missing optional historical summary")
            continue
        header = set(read_csv_header(full))
        missing = expected_standard - header
        if missing:
            failures.append(f"{path.as_posix()}: missing {sorted(missing)}")
        checked += 1

    if failures:
        state.fail("summary_headers", "; ".join(failures))
    else:
        state.pass_("summary_headers", f"checked={checked}")


def check_sensitive_scan(state: ValidationState, paths: list[Path]) -> None:
    findings: list[str] = []
    for path in paths:
        findings.extend(check_sensitive_text(path))
        if len(findings) >= 20:
            break
    if findings:
        state.fail("sensitive_scan", "\n".join(findings[:20]))
    else:
        state.pass_("sensitive_scan")


def main() -> int:
    state = ValidationState()
    sensitive_paths: list[Path] = []

    check_schemas(state)
    sensitive_paths.extend(REPO_ROOT / schema for schema in SCHEMA_FILES)
    check_demo_task(state, sensitive_paths)
    check_platform_profiles(state, sensitive_paths)
    check_validity_rules(state, sensitive_paths)
    check_seeds(state, sensitive_paths)
    check_text_seeds(state, sensitive_paths)
    check_summary_headers(state)
    check_sensitive_scan(state, sensitive_paths)

    if state.failed:
        print("VALIDATE_PROJECT_CONFIGS_FAIL")
        return 1
    print("VALIDATE_PROJECT_CONFIGS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
