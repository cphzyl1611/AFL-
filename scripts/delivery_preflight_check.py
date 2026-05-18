#!/usr/bin/env python3
"""Unified local delivery preflight checks for the fuzzing module.

The checks are intentionally lightweight: file presence, Python syntax,
configuration validation, unittest, lightweight API smoke,
sensitive-placeholder scanning, and wording-boundary scanning. They do not run
O2OA, Flowable, Alfresco, or long fuzzing jobs.
"""

from __future__ import annotations

import os
import py_compile
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "docs/reproduce/实验复现指南.md",
    "docs/review/最终交付状态说明.md",
    "docs/review/模糊测试模块项目要求完成证明与复现说明.md",
    "integration/api_server.py",
    "docs/integration/轻量API调用说明.md",
    "docs/integration/MCP接入预研说明.md",
    "out/nv_mab_smoke_summary.csv",
    "out/nv_mab_stability_summary.csv",
    "out/nv_mab_ablation_summary.csv",
    "schemas/fuzz_task.schema.json",
    "schemas/platform_profile.schema.json",
    "schemas/validity_rule.schema.json",
    "schemas/summary_header.schema.json",
    "scripts/validate_project_configs.py",
    "tests/test_api_server_basic.py",
    "tests/test_project_configs.py",
    "tests/test_summary_evidence.py",
]

PY_COMPILE_FILES = [
    "integration/api_server.py",
    "nv_json_mutator.py",
    "scripts/compute_security_score.py",
    "scripts/analyze_seed_quality.py",
    "scripts/validate_project_configs.py",
]

SCAN_ROOTS = [
    "README.md",
    "docs",
    "integration",
    "scripts",
    "runner",
    "validity",
    "in",
    "out",
]

WORDING_ROOTS = [
    "README.md",
    "docs",
    "integration",
]

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

OVERCLAIM_PATTERNS = [
    re.compile(r"完整动态异构冗余已经完成"),
    re.compile(r"完整拟态系统级动态异构冗余.*完成"),
    re.compile(r"O2OA 原生电子公文.*全覆盖"),
    re.compile(r"Flowable-GAN 完成"),
    re.compile(r"完整 NC_MAB 理论闭环.*完成"),
    re.compile(r"完整自动化语义种子生成.*完成"),
    re.compile(r"完整 MCP.*完成"),
    re.compile(r"完整 MCP Server 已完成"),
    re.compile(r"完整平台级 HTTP/RPC 网关.*完成"),
    re.compile(r"完整平台级 HTTP/RPC 网关已完成"),
]

BOUNDARY_TERMS = [
    "不能宣称",
    "不能说",
    "不宣称",
    "不等同于",
    "不等于",
    "未完成",
    "未实现",
    "不代表",
    "边界",
    "风险",
    "不能扩大",
    "不是",
    "不含",
    "不应",
    "不得",
    "不可",
    "当前不能",
    "不能表述",
]

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
}

SKIP_SUFFIXES = {
    ".bin",
    ".pyc",
    ".pt",
    ".pkl",
    ".zip",
    ".tar",
    ".gz",
    ".xz",
    ".bz2",
    ".7z",
    ".so",
    ".o",
    ".a",
}

MAX_TEXT_SIZE = 2 * 1024 * 1024


class CheckState:
    def __init__(self) -> None:
        self.failed = False

    def pass_(self, name: str, detail: str = "") -> None:
        suffix = f" - {detail}" if detail else ""
        print(f"PASS {name}{suffix}")

    def fail(self, name: str, detail: str) -> None:
        self.failed = True
        print(f"FAIL {name} - {detail}")


def is_probably_text(path: Path) -> bool:
    try:
        if path.stat().st_size > MAX_TEXT_SIZE:
            return False
        sample = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\x00" not in sample


def iter_scan_files(roots: list[str]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        start = REPO_ROOT / root
        if not start.exists():
            continue
        if start.is_file():
            files.append(start)
            continue
        for current_root, dirs, filenames in os.walk(start):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for filename in filenames:
                path = Path(current_root) / filename
                if filename == "fastresume.bin":
                    continue
                if path.suffix in SKIP_SUFFIXES:
                    continue
                if is_probably_text(path):
                    files.append(path)
    return files


def check_required_files(state: CheckState) -> None:
    missing = [path for path in REQUIRED_FILES if not (REPO_ROOT / path).is_file()]
    if missing:
        state.fail("required_files", ", ".join(missing))
    else:
        state.pass_("required_files", f"{len(REQUIRED_FILES)} files present")


def check_py_compile(state: CheckState) -> None:
    failures: list[str] = []
    for rel in PY_COMPILE_FILES:
        path = REPO_ROOT / rel
        try:
            py_compile.compile(path.as_posix(), doraise=True)
        except Exception as exc:  # noqa: BLE001 - report compile failure.
            failures.append(f"{rel}: {exc}")
    if failures:
        state.fail("py_compile", "; ".join(failures))
    else:
        state.pass_("py_compile", f"{len(PY_COMPILE_FILES)} files")


def check_api_smoke(state: CheckState) -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/smoke_api_server.py"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode == 0:
        state.pass_("api_smoke", proc.stdout.strip())
    else:
        state.fail("api_smoke", proc.stdout.strip() or f"returncode={proc.returncode}")


def check_config_validation(state: CheckState) -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/validate_project_configs.py"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode == 0:
        state.pass_("config_validation", "VALIDATE_PROJECT_CONFIGS_PASS")
    else:
        state.fail("config_validation", proc.stdout.strip() or f"returncode={proc.returncode}")


def check_unittest(state: CheckState) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode == 0:
        state.pass_("unittest", "tests passed")
    else:
        state.fail("unittest", proc.stdout.strip() or f"returncode={proc.returncode}")


def has_allowed_sensitive_context(line: str) -> bool:
    lowered = line.lower()
    return any(token.lower() in lowered for token in ALLOW_SENSITIVE_CONTEXT)


def check_sensitive_scan(state: CheckState) -> None:
    findings: list[str] = []
    for path in iter_scan_files(SCAN_ROOTS):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            if not any(pattern.search(line) for pattern in SENSITIVE_PATTERNS):
                continue
            if has_allowed_sensitive_context(line):
                continue
            findings.append(f"{rel}:{lineno}:{line[:180]}")
            if len(findings) >= 20:
                break
        if len(findings) >= 20:
            break
    if findings:
        state.fail("sensitive_scan", "\n".join(findings))
    else:
        state.pass_("sensitive_scan", "no real token-like values found")


def has_boundary_context(lines: list[str], index: int) -> bool:
    start = max(0, index - 12)
    end = min(len(lines), index + 5)
    context = "\n".join(lines[start:end])
    return any(term in context for term in BOUNDARY_TERMS)


def check_wording_scan(state: CheckState) -> None:
    findings: list[str] = []
    for path in iter_scan_files(WORDING_ROOTS):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(lines):
            if not any(pattern.search(line) for pattern in OVERCLAIM_PATTERNS):
                continue
            if has_boundary_context(lines, idx):
                continue
            findings.append(f"{rel}:{idx + 1}:{line[:180]}")
            if len(findings) >= 20:
                break
        if len(findings) >= 20:
            break
    if findings:
        state.fail("wording_scan", "\n".join(findings))
    else:
        state.pass_("wording_scan", "overclaim matches are absent or boundary-qualified")


def main() -> int:
    state = CheckState()
    check_required_files(state)
    check_py_compile(state)
    check_config_validation(state)
    check_unittest(state)
    check_api_smoke(state)
    check_sensitive_scan(state)
    check_wording_scan(state)
    if state.failed:
        print("DELIVERY_PREFLIGHT_FAIL")
        return 1
    print("DELIVERY_PREFLIGHT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
