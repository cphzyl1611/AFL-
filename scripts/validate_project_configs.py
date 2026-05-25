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
    Path("out/alfresco_ae_v1_score_compare/summary.csv"),
    Path("out/alfresco_ae_v1_service_compare/summary.csv"),
    Path("out/alfresco_metadata_update_manual_latest/summary.csv"),
    Path("out/alfresco_content_update_manual_latest/summary.csv"),
    Path("out/alfresco_multipart_upload_manual_latest/summary.csv"),
    Path("out/cms_body_valid_compare_real/summary.csv"),
    Path("out/real_service_smoke_20260508/o2oa_real/summary.csv"),
]

MODEL_META_FILES = [
    Path("model_stage/models/alfresco_ae_v1_meta.json"),
    Path("model_stage/models/alfresco_fanogan_v1_candidate_meta.json"),
]

REPORT_FILES = [
    Path("docs/review/MCP_adapter原型接入报告.md"),
    Path("docs/review/Alfresco_fAnoGAN_v1候选有效性验证报告.md"),
    Path("docs/review/Alfresco扩展样本与fAnoGAN候选二次评估报告.md"),
    Path("docs/review/Alfresco_fAnoGAN候选劣于AE原因诊断报告.md"),
    Path("docs/review/Alfresco_torch_fAnoGAN候选复评报告.md"),
    Path("docs/review/Alfresco_torch_fAnoGAN阈值重校准与holdout验证报告.md"),
    Path("docs/review/Alfresco代表性AFL++变异链路smoke报告.md"),
]

TEXT_SEED_DIRS = [
    Path("in/alfresco_content_update_dataset"),
    Path("in/alfresco_multipart_upload_dataset"),
]

EXTENDED_EVAL_MANIFEST = Path("in/alfresco_extended_eval_dataset/manifest.json")

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

THRESHOLD_SWEEP_SUMMARIES = {
    Path("out/alfresco_ae_v1_threshold_sweep/summary.csv"): {
        "threshold",
        "total_samples",
        "expected_valid",
        "expected_invalid",
        "rule_only_pass",
        "rule_only_reject",
        "ae_only_pass",
        "ae_only_reject",
        "rule_ae_pass",
        "rule_ae_reject",
        "false_accept",
        "false_reject",
        "accuracy",
    },
}

FANOGAN_CANDIDATE_SUMMARIES = {
    Path("out/alfresco_fanogan_v1_candidate_compare/summary.csv"): {
        "mode",
        "total_samples",
        "expected_valid",
        "expected_invalid",
        "rule_only_pass",
        "rule_only_reject",
        "ae_v1_pass",
        "ae_v1_reject",
        "fanogan_pass",
        "fanogan_reject",
        "rule_fanogan_pass",
        "rule_fanogan_reject",
        "false_accept",
        "false_reject",
        "accuracy",
        "model_type",
        "summary_source",
        "execution_scope",
        "metric_semantics",
    },
}

EXTENDED_CANDIDATE_EVAL_SUMMARIES = {
    Path("out/alfresco_extended_candidate_eval/summary.csv"): {
        "total_samples",
        "expected_valid",
        "expected_invalid",
        "rule_only_false_accept",
        "rule_only_false_reject",
        "ae_only_false_accept",
        "ae_only_false_reject",
        "rule_ae_false_accept",
        "rule_ae_false_reject",
        "fanogan_only_false_accept",
        "fanogan_only_false_reject",
        "rule_fanogan_false_accept",
        "rule_fanogan_false_reject",
        "rule_ae_accuracy",
        "rule_fanogan_accuracy",
        "recommendation",
        "summary_source",
        "execution_scope",
        "metric_semantics",
    },
}

FANOGAN_DIAGNOSIS_SUMMARIES = {
    Path("out/alfresco_fanogan_candidate_diagnosis/diagnosis_summary.csv"): {
        "check_item",
        "status",
        "detail",
    },
}

FANOGAN_HOLDOUT_SUMMARIES = {
    Path("out/alfresco_fanogan_threshold_holdout_eval/holdout_summary.csv"): {
        "total_samples",
        "expected_valid",
        "expected_invalid",
        "rule_ae_false_accept",
        "rule_ae_false_reject",
        "rule_ae_accuracy",
        "rule_fanogan_default_false_accept",
        "rule_fanogan_default_false_reject",
        "rule_fanogan_default_accuracy",
        "rule_fanogan_calibrated_false_accept",
        "rule_fanogan_calibrated_false_reject",
        "rule_fanogan_calibrated_accuracy",
        "chosen_threshold",
        "recommendation",
        "summary_source",
        "execution_scope",
        "metric_semantics",
    },
}

AFL_MUTATION_CHAIN_SMOKE_SUMMARIES = {
    Path("out/alfresco_afl_content_update_smoke_latest/summary.csv"): {
        "mode",
        "nv_total_valid_exec",
        "nv_err_exec",
        "nv_err_rate",
        "saved_hangs",
        "saved_crashes",
        "last_http_code",
        "body_rule_pass",
        "body_rule_reject",
        "summary_source",
        "execution_scope",
        "metric_semantics",
    },
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


def check_model_meta(state: ValidationState, sensitive_paths: list[Path]) -> None:
    failures: list[str] = []
    for rel_path in MODEL_META_FILES:
        path = REPO_ROOT / rel_path
        if not path.is_file():
            failures.append(f"{rel_path.as_posix()}: missing")
            continue
        try:
            data = load_json(path)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{rel_path.as_posix()}: {exc}")
            continue
        if not isinstance(data, dict):
            failures.append(f"{rel_path.as_posix()}: top-level value is not object")
            continue
        for key in ("model_name", "model_type", "feature_names", "mean", "std", "threshold_high", "train_sample_count"):
            if key not in data:
                failures.append(f"{rel_path.as_posix()}: missing {key}")
        feature_names_value = data.get("feature_names")
        mean_value = data.get("mean")
        std_value = data.get("std")
        if not isinstance(feature_names_value, list) or not all(isinstance(item, str) for item in feature_names_value):
            failures.append(f"{rel_path.as_posix()}: feature_names must be list[str]")
        if not isinstance(mean_value, list) or not all(isinstance(item, (int, float)) for item in mean_value):
            failures.append(f"{rel_path.as_posix()}: mean must be list[number]")
        if not isinstance(std_value, list) or not all(isinstance(item, (int, float)) for item in std_value):
            failures.append(f"{rel_path.as_posix()}: std must be list[number]")
        if isinstance(feature_names_value, list) and isinstance(mean_value, list) and isinstance(std_value, list):
            if not (len(feature_names_value) == len(mean_value) == len(std_value)):
                failures.append(f"{rel_path.as_posix()}: feature_names/mean/std length mismatch")
        sensitive_paths.append(path)

    if failures:
        state.fail("model_meta", "; ".join(failures[:20]))
    else:
        state.pass_("model_meta", f"count={len(MODEL_META_FILES)}")


def check_report_files(state: ValidationState, sensitive_paths: list[Path]) -> None:
    failures: list[str] = []
    for rel_path in REPORT_FILES:
        path = REPO_ROOT / rel_path
        if not path.is_file():
            failures.append(f"{rel_path.as_posix()}: missing")
            continue
        sensitive_paths.append(path)
    if failures:
        state.fail("report_files", "; ".join(failures))
    else:
        state.pass_("report_files", f"count={len(REPORT_FILES)}")


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


def check_extended_eval_manifest(state: ValidationState, sensitive_paths: list[Path]) -> None:
    path = REPO_ROOT / EXTENDED_EVAL_MANIFEST
    if not path.is_file():
        state.warn("extended_eval_manifest", f"{EXTENDED_EVAL_MANIFEST.as_posix()}: missing optional extended eval manifest")
        return
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        state.fail("extended_eval_manifest", f"{EXTENDED_EVAL_MANIFEST.as_posix()}: {exc}")
        return
    if not isinstance(data, list):
        state.fail("extended_eval_manifest", "top-level value must be list")
        return

    allowed_scenarios = {"metadata_update", "content_update", "multipart_upload"}
    allowed_types = {"valid", "border", "invalid"}
    failures: list[str] = []
    counts: dict[str, int] = {"metadata_update": 0, "content_update": 0, "multipart_upload": 0}
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            failures.append(f"entry {index}: not object")
            continue
        scenario = item.get("scenario")
        rel_file = item.get("file")
        expected_valid = item.get("expected_valid")
        sample_type = item.get("sample_type")
        if scenario not in allowed_scenarios:
            failures.append(f"entry {index}: invalid scenario {scenario!r}")
        else:
            counts[str(scenario)] += 1
        if not isinstance(rel_file, str):
            failures.append(f"entry {index}: file must be string")
        else:
            sample_path = path.parent / rel_file
            if not sample_path.is_file():
                failures.append(f"entry {index}: missing file {rel_file}")
            elif sample_path.suffix in {".json", ".txt"}:
                sensitive_paths.append(sample_path)
        if not isinstance(expected_valid, bool):
            failures.append(f"entry {index}: expected_valid must be bool")
        if sample_type not in allowed_types:
            failures.append(f"entry {index}: invalid sample_type {sample_type!r}")
        if expected_valid is False and not item.get("error_type"):
            failures.append(f"entry {index}: invalid sample missing error_type")

    sensitive_paths.append(path)
    if failures:
        state.fail("extended_eval_manifest", "; ".join(failures[:20]))
    else:
        state.pass_("extended_eval_manifest", f"count={len(data)} metadata={counts['metadata_update']} content={counts['content_update']} multipart={counts['multipart_upload']}")


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

    for path, required in THRESHOLD_SWEEP_SUMMARIES.items():
        full = REPO_ROOT / path
        if not full.is_file():
            state.warn("summary_headers", f"{path.as_posix()}: missing optional threshold sweep summary")
            continue
        header = set(read_csv_header(full))
        missing = required - header
        if missing:
            failures.append(f"{path.as_posix()}: missing {sorted(missing)}")
        checked += 1

    for path, required in FANOGAN_CANDIDATE_SUMMARIES.items():
        full = REPO_ROOT / path
        if not full.is_file():
            state.warn("summary_headers", f"{path.as_posix()}: missing optional fAnoGAN candidate summary")
            continue
        header = set(read_csv_header(full))
        missing = required - header
        if missing:
            failures.append(f"{path.as_posix()}: missing {sorted(missing)}")
        checked += 1

    for path, required in EXTENDED_CANDIDATE_EVAL_SUMMARIES.items():
        full = REPO_ROOT / path
        if not full.is_file():
            state.warn("summary_headers", f"{path.as_posix()}: missing optional extended candidate eval summary")
            continue
        header = set(read_csv_header(full))
        missing = required - header
        if missing:
            failures.append(f"{path.as_posix()}: missing {sorted(missing)}")
        checked += 1

    for path, required in FANOGAN_DIAGNOSIS_SUMMARIES.items():
        full = REPO_ROOT / path
        if not full.is_file():
            state.warn("summary_headers", f"{path.as_posix()}: missing optional fAnoGAN diagnosis summary")
            continue
        header = set(read_csv_header(full))
        missing = required - header
        if missing:
            failures.append(f"{path.as_posix()}: missing {sorted(missing)}")
        checked += 1

    for path, required in FANOGAN_HOLDOUT_SUMMARIES.items():
        full = REPO_ROOT / path
        if not full.is_file():
            state.warn("summary_headers", f"{path.as_posix()}: missing optional fAnoGAN holdout summary")
            continue
        header = set(read_csv_header(full))
        missing = required - header
        if missing:
            failures.append(f"{path.as_posix()}: missing {sorted(missing)}")
        checked += 1

    for path, required in AFL_MUTATION_CHAIN_SMOKE_SUMMARIES.items():
        full = REPO_ROOT / path
        if not full.is_file():
            state.warn("summary_headers", f"{path.as_posix()}: missing optional AFL mutation-chain smoke summary")
            continue
        header = set(read_csv_header(full))
        missing = required - header
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
    check_model_meta(state, sensitive_paths)
    check_report_files(state, sensitive_paths)
    check_demo_task(state, sensitive_paths)
    check_platform_profiles(state, sensitive_paths)
    check_validity_rules(state, sensitive_paths)
    check_seeds(state, sensitive_paths)
    check_text_seeds(state, sensitive_paths)
    check_extended_eval_manifest(state, sensitive_paths)
    check_summary_headers(state)
    check_sensitive_scan(state, sensitive_paths)

    if state.failed:
        print("VALIDATE_PROJECT_CONFIGS_FAIL")
        return 1
    print("VALIDATE_PROJECT_CONFIGS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
