#!/usr/bin/env python3
"""Deep2Fuzz Phase 1.1 CLI implementation."""
from __future__ import annotations

import argparse
import importlib.util
from importlib.metadata import PackageNotFoundError, version as installed_version
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from deep2fuzz_version import __version__
from integration.platforms.registry import get_adapter, list_adapters
from integration.platforms.smoke import run_smoke

ROOT = Path(__file__).resolve().parent
EXTRA_MODULES = {
    "live": ("requests",),
    "model": ("numpy", "pandas", "torch"),
    "analysis": ("pandas", "matplotlib"),
    "dev": ("pytest",),
}


def _discover_repo_root() -> Path | None:
    for start in (ROOT, Path.cwd()):
        for candidate in (start, *start.parents):
            if all((candidate / item).exists() for item in ("src", "scripts", "targets", "validity", "integration")):
                return candidate.resolve()
    return None


def _check_extra(name: str, find_spec=importlib.util.find_spec) -> int:
    modules = EXTRA_MODULES[name]
    missing = [module for module in modules if find_spec(module) is None]
    if missing:
        quoted = ", ".join(missing)
        print(f"MISSING_OPTIONAL_DEPENDENCY: {name} requires {quoted}. Install it with `python -m pip install -e '.[{name}]'`.", file=sys.stderr)
        return 2
    print(f"OPTIONAL_DEPENDENCY_READY: {name}")
    return 0


def _doctor() -> int:
    repo_root = _discover_repo_root()
    native_assets = bool(repo_root and (repo_root / "afl-fuzz").is_file() and os.access(repo_root / "afl-fuzz", os.X_OK))
    core_imports = all(importlib.util.find_spec(name) is not None for name in (
        "integration.platforms.registry", "integration.platforms.mock_rest.adapter"))
    try:
        adapter_registry = list_adapters() == ["mock_rest"]
    except Exception:
        adapter_registry = False
    model_backend = all(importlib.util.find_spec(name) is not None for name in ("numpy", "torch"))
    try:
        installed = installed_version("deep2fuzz-es") == __version__
    except PackageNotFoundError:
        installed = False
    available = {
        "package_install": installed,
        "python3-config": bool(shutil.which("python3-config")),
        "afl-fuzz": native_assets or bool(shutil.which("afl-fuzz")),
    }
    checks: dict[str, object] = {
        "python": sys.version.split()[0], "package_version": __version__,
        "package_install": installed, "venv": sys.prefix != sys.base_prefix,
        "repo_root": str(repo_root) if repo_root else "unavailable",
        "repo_runtime_root": str(repo_root) if repo_root else "unavailable",
        "pytest": bool(shutil.which("pytest") or importlib.util.find_spec("pytest")),
        "gcc": bool(shutil.which("gcc")), "make": bool(shutil.which("make")),
        "python3-config": bool(shutil.which("python3-config")),
        "zlib": importlib.util.find_spec("zlib") is not None,
        "afl-fuzz": native_assets or bool(shutil.which("afl-fuzz")),
        "scripts": bool(repo_root and (repo_root / "scripts").is_dir()),
        "targets": bool(repo_root and (repo_root / "targets").is_dir()),
        "validity": bool(repo_root and (repo_root / "validity").is_dir()),
        "integration": bool(repo_root and (repo_root / "integration").is_dir()),
        "core_imports": core_imports, "adapter_registry": adapter_registry,
        "optional_model_stack_imported": any(name in sys.modules for name in ("numpy", "torch", "pandas")),
        "next_actions": [
            action for key, action in (
                ("package_install", "run `python -m pip install -e .`"),
                ("python3-config", "install the Python development headers/tools"),
                ("afl-fuzz", "run `make -j2 afl-fuzz` in the source tree"),
            ) if not available.get(key, False)
        ],
        "OFFLINE_READY": bool(core_imports and adapter_registry),
        "PLUGIN_READY": bool(core_imports and adapter_registry),
        "MOCK_PLATFORM_READY": bool(adapter_registry),
        "NATIVE_RUNTIME_READY": bool(native_assets and repo_root and (repo_root / "scripts").is_dir()),
        # Preserve Phase 1's NOT_CHECKED value: this field means no live
        # service was probed.  The local capability result is separate.
        "LIVE_PLATFORM_READY": False,
        "LIVE_PLATFORM_PROBED": False,
        "MODEL_BACKEND_READY": bool(model_backend),
    }
    print(json.dumps(checks, sort_keys=True))
    return 0


def _init_platform(name: str, output: str | None) -> int:
    safe = name.replace("-", "_")
    if not safe or not safe.replace("_", "").isalnum():
        print("invalid platform name", file=sys.stderr)
        return 2
    target = Path(output).resolve() if output else ROOT / "integration" / "platforms" / safe
    if target.exists():
        print(f"refusing to overwrite existing path: {target}", file=sys.stderr)
        return 2
    target.mkdir(parents=True)
    (target / "seeds").mkdir()
    (target / "platform.json").write_text(json.dumps({"name": safe, "base_url": "http://127.0.0.1:8080"}, indent=2) + "\n")
    (target / "target.json").write_text(json.dumps({"endpoints": []}, indent=2) + "\n")
    (target / "rules.json").write_text(json.dumps({"common": {}}, indent=2) + "\n")
    (target / "adapter.py").write_text("# TODO: implement the explicit PlatformAdapter contract.\n")
    (target / "seeds" / "seed_0.json").write_text("{}\n")
    (target / "README.md").write_text(f"# {safe}\n\nImplement a local adapter; do not place credentials in config.\n")
    print(json.dumps({"scaffold": str(target), "status": "CREATED"}))
    return 0


def _delivery_sample() -> int:
    evidence_parent = Path("/home/cphzy/task4-evidence")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = evidence_parent / f"DEEP2FUZZ_DELIVERY_SAMPLE-{stamp}"
    suffix = 1
    while output.exists():
        output = evidence_parent / f"DEEP2FUZZ_DELIVERY_SAMPLE-{stamp}-{suffix}"
        suffix += 1
    env = os.environ.copy()
    env.update({"ROOT": str(ROOT), "OUT_DIR": str(output), "PYTHON_BIN": sys.executable,
                "MAX_TEST_CASES": "8", "TIME_BUDGET": "5", "HARD_TIMEOUT": "20",
                "AFL_RAND_SEED": "20261026"})
    for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env.pop(name, None)
    return subprocess.call([sys.executable, str(ROOT / "scripts" / "run_task4_sample.py")], cwd=ROOT, env=env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deep2fuzz")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    test = sub.add_parser("test")
    test.add_argument("--pytest-args", nargs=argparse.REMAINDER)
    sub.add_parser("sample")
    platform = sub.add_parser("platform")
    platform_sub = platform.add_subparsers(dest="platform_command", required=True)
    platform_sub.add_parser("list")
    validate = platform_sub.add_parser("validate")
    validate.add_argument("name")
    validate.add_argument("--config")
    smoke = platform_sub.add_parser("smoke")
    smoke.add_argument("name")
    smoke.add_argument("--evidence-root")
    init = platform_sub.add_parser("init")
    init.add_argument("name")
    init.add_argument("--output")
    run = platform_sub.add_parser("run")
    run.add_argument("name", nargs="?")
    run.add_argument("--evidence-root")
    run.add_argument("--scenario", choices=("success", "validity_rejection", "expected_rejection", "semantic_failure", "cleanup_failure"), default="success")
    evidence = sub.add_parser("evidence")
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    verify = evidence_sub.add_parser("verify")
    verify.add_argument("run_root")
    verify.add_argument("--json", action="store_true", dest="json_output")
    doctor = sub.choices["doctor"]
    doctor.add_argument("--require-extra", choices=sorted(EXTRA_MODULES))
    args = parser.parse_args(argv)
    if args.command == "doctor":
        if args.require_extra:
            return _check_extra(args.require_extra)
        return _doctor()
    if args.command == "evidence":
        from deep2fuzz_evidence.verifier import EvidenceInputError, verify_evidence

        try:
            result = verify_evidence(args.run_root)
        except EvidenceInputError as exc:
            if args.json_output:
                print(json.dumps({
                    "schema_version": "1", "verdict": "FAIL", "profile": "unknown",
                    "checks": [{"name": "INPUT", "status": "FAIL", "message": str(exc)}],
                    "summary": {"passed": 0, "failed": 1, "not_applicable": 0,
                                "warnings": 0, "files_checked": 0, "bytes_checked": 0,
                                "duration_ms": 0},
                }, sort_keys=True))
            else:
                print(f"EVIDENCE_INPUT_ERROR: {exc}", file=sys.stderr)
            return 2
        if args.json_output:
            print(json.dumps(result.to_dict(), sort_keys=True))
        else:
            data = result.to_dict()
            print("Deep2Fuzz Evidence Verification")
            print(f"Profile: {data['profile']}")
            print(f"Result: {data['verdict']}")
            for check in data["checks"]:
                status = check["status"]
                label = {"PASS": "PASS", "FAIL": "FAIL", "NOT_APPLICABLE": "N/A", "WARN": "WARN"}[status]
                message = f" - {check['message']}" if check.get("message") else ""
                print(f"[{label}] {check['name']}{message}")
        return 0 if result.verdict == "PASS" else 1
    if args.command == "test":
        command = ([sys.executable, "-m", "pytest", "tests/test_deep2fuzz_platform_adapter.py", "-q"]
                   if shutil.which("pytest") else
                   [sys.executable, "-m", "unittest", "tests.test_deep2fuzz_platform_adapter", "-v"])
        if args.pytest_args:
            command.extend(args.pytest_args)
        return subprocess.call(command, cwd=ROOT)
    if args.command == "sample":
        return _delivery_sample()
    if args.platform_command == "list":
        print("\n".join(list_adapters()))
        return 0
    if args.platform_command == "validate":
        try:
            config = {"base_url": "http://127.0.0.1:1"}
            if args.config:
                value = json.loads(Path(args.config).read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("adapter config must be a JSON object")
                config.update(value)
            get_adapter(args.name, config)
        except Exception as exc:
            if "unknown adapter" in str(exc).lower():
                print(f"UNKNOWN_ADAPTER: {exc}; run `deep2fuzz platform list`", file=sys.stderr)
            else:
                print(f"INVALID_ADAPTER_CONFIG: {exc}; valid fields are base_url, timeout_sec, and credential environment-variable names", file=sys.stderr)
            return 2
        print(f"VALID: {args.name}")
        return 0
    if args.platform_command == "smoke":
        if args.name != "mock_rest":
            print("SMOKE_UNSUPPORTED: only mock_rest is enabled offline", file=sys.stderr)
            return 2
        try:
            print(json.dumps(run_smoke(args.evidence_root), sort_keys=True))
            return 0
        except (OSError, ValueError, FileExistsError) as exc:
            print(f"SMOKE_FAILED: {exc}", file=sys.stderr)
            return 2
    if args.platform_command == "run":
        if not args.name:
            print("NOT_IN_PHASE1: platform run requires an explicit adapter", file=sys.stderr)
            return 2
        if args.name != "mock_rest":
            print(f"UNKNOWN_ADAPTER: {args.name}; use `deep2fuzz platform list`", file=sys.stderr)
            return 2
        try:
            from integration.platforms.core_runner import run_core_mock
            result = run_core_mock(args.evidence_root, scenario=args.scenario)
            print(json.dumps(result, sort_keys=True))
            return 0 if result.get("passed") is True else 2
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"PLATFORM_RUN_FAILED: {exc}", file=sys.stderr)
            return 2
    if args.platform_command == "init":
        return _init_platform(args.name, args.output)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
