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


class _SafeArgumentParser(argparse.ArgumentParser):
    """Keep argparse diagnostics useful without echoing rejected argv values."""

    def error(self, message: str) -> None:
        if "required" in message:
            detail = "a required command or argument is missing"
        else:
            detail = "an option or value is invalid"
        self.exit(2, f"{self.prog}: error: USAGE_ERROR: {detail}; see --help\n")


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


def _render_config_human(result) -> None:
    """Render the validator's existing findings without changing their schema."""
    print("Command: config validate")
    print(f"File: {result.source.name}")
    print(f"Result: {result.verdict}")
    for finding in result.errors:
        print(f"Error: {finding.code}: {finding.message} (path: {finding.path})")


def _render_evidence_human(result) -> None:
    """Render verifier checks in the common human CLI shape."""
    data = result.to_dict()
    print("Command: evidence verify")
    print(f"Profile: {data['profile']}")
    print(f"Result: {data['verdict']}")
    for check in data["checks"]:
        status = check["status"]
        label = {"PASS": "PASS", "FAIL": "FAIL", "NOT_APPLICABLE": "N/A", "WARN": "WARN"}[status]
        message = f": {check['message']}" if check.get("message") else ""
        print(f"{label} {check['name']}{message}")


def _render_cli_error(command: str, code: str, message: str, *, stream=None) -> None:
    """Use one concise, secret-safe human error form for invocation failures."""
    output = stream or sys.stderr
    print(f"Command: {command}", file=output)
    print("Result: FAIL", file=output)
    print(f"Error: {code}: {message}", file=output)


def _main(argv: list[str] | None = None) -> int:
    parser = _SafeArgumentParser(
        prog="deep2fuzz",
        description="Offline Deep2Fuzz platform and evidence command line interface.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check local runtime readiness")
    test = sub.add_parser("test", help="run the offline adapter contract tests")
    test.add_argument("--pytest-args", nargs=argparse.REMAINDER)
    sub.add_parser("sample", help="run the bounded offline delivery sample")
    config_parser = sub.add_parser("config", help="validate run configuration")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_validate = config_sub.add_parser("validate", help="validate one JSON run configuration")
    config_validate.add_argument("config_file", metavar="CONFIG_FILE", help="path to the JSON configuration")
    config_validate.add_argument("--json", action="store_true", dest="json_output", help="write one JSON result to stdout")
    platform = sub.add_parser("platform", help="inspect and run registered adapters")
    platform_sub = platform.add_subparsers(dest="platform_command", required=True)
    platform_sub.add_parser("list", help="list registered adapters")
    validate = platform_sub.add_parser("validate", help="validate an adapter configuration")
    validate.add_argument("name", metavar="ADAPTER")
    validate.add_argument("--config", metavar="CONFIG_FILE", help="optional adapter configuration JSON")
    smoke = platform_sub.add_parser("smoke", help="run the loopback adapter smoke")
    smoke.add_argument("name", metavar="ADAPTER")
    smoke.add_argument("--evidence-root", metavar="PATH")
    init = platform_sub.add_parser("init", help="create a source-tree adapter scaffold")
    init.add_argument("name", metavar="NAME")
    init.add_argument("--output", metavar="PATH")
    run = platform_sub.add_parser("run", help="run the bounded offline adapter contract")
    run.add_argument("name", nargs="?", metavar="ADAPTER")
    run.add_argument("--evidence-root", metavar="PATH")
    run.add_argument("--config", dest="config_file", metavar="CONFIG_FILE", help="validated run configuration")
    run.add_argument("--scenario", choices=("success", "validity_rejection", "expected_rejection", "semantic_failure", "cleanup_failure"), default="success", help="offline contract scenario")
    evidence = sub.add_parser("evidence", help="verify an evidence root")
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    verify = evidence_sub.add_parser("verify", help="verify one evidence root")
    verify.add_argument("run_root", metavar="RUN_ROOT", help="path to the evidence root")
    verify.add_argument("--json", action="store_true", dest="json_output", help="write one JSON result to stdout")
    doctor = sub.choices["doctor"]
    doctor.add_argument("--require-extra", choices=sorted(EXTRA_MODULES), help="require one optional dependency extra")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        if args.require_extra:
            return _check_extra(args.require_extra)
        return _doctor()
    if args.command == "config":
        from deep2fuzz_config.validator import validate_config

        result = validate_config(args.config_file)
        payload = result.to_dict()
        if args.json_output:
            print(json.dumps(payload, sort_keys=True))
        else:
            if result.input_error:
                finding = result.errors[0]
                _render_cli_error("config validate", finding.code, finding.message)
            else:
                _render_config_human(result)
        if result.input_error:
            return 2
        return 0 if result.verdict == "PASS" else 1
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
                _render_cli_error("evidence verify", "INPUT_ERROR", str(exc))
            return 2
        if args.json_output:
            print(json.dumps(result.to_dict(), sort_keys=True))
        else:
            _render_evidence_human(result)
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
                _render_cli_error("platform validate", "UNKNOWN_ADAPTER", "adapter is not registered")
            else:
                _render_cli_error(
                    "platform validate", "INVALID_ADAPTER_CONFIG",
                    "adapter configuration is invalid; check base_url, timeout_sec, and credential environment-variable names",
                )
            return 2
        print(f"Command: platform validate\nResult: PASS\nVALID: {args.name}")
        return 0
    if args.platform_command == "smoke":
        if args.name != "mock_rest":
            print("SMOKE_UNSUPPORTED: only mock_rest is enabled offline", file=sys.stderr)
            return 2
        try:
            print(json.dumps(run_smoke(args.evidence_root), sort_keys=True))
            return 0
        except (OSError, ValueError, FileExistsError) as exc:
            _render_cli_error("platform smoke", "RUNTIME_FAILURE", "offline adapter smoke failed")
            return 1
    if args.platform_command == "run":
        if not args.name:
            _render_cli_error("platform run", "INPUT_ERROR", "NOT_IN_PHASE1: an explicit adapter name is required")
            return 2
        if args.name != "mock_rest":
            _render_cli_error("platform run", "UNKNOWN_ADAPTER", "adapter is not registered")
            return 2
        try:
            run_config = None
            evidence_root = args.evidence_root
            if args.config_file:
                from deep2fuzz_config.validator import validate_config

                validated = validate_config(args.config_file)
                if validated.input_error:
                    _render_cli_error("platform run", "INPUT_ERROR", "configuration file cannot be read")
                    return 2
                if validated.verdict != "PASS":
                    print("Command: platform run")
                    print("Result: FAIL")
                    for finding in validated.errors:
                        print(f"Error: {finding.code}: {finding.message} (path: {finding.path})")
                    return 1
                if validated.normalized.get("platform") != args.name:
                    _render_cli_error("platform run", "INPUT_ERROR", "platform must match the requested adapter")
                    return 2
                if args.evidence_root:
                    _render_cli_error("platform run", "INPUT_ERROR", "use output.evidence_root when --config is supplied")
                    return 2
                values = validated.normalized
                block = values["platform_config"]["mock_rest"]
                run_config = {
                    "max_test_cases": values["run"]["max_test_cases"],
                    "time_budget_seconds": values["run"]["time_budget_seconds"],
                    "timeout_seconds": values["run"]["timeout_seconds"],
                    "validity_enabled": values["validity"]["enabled"],
                    "seed_path": str(validated.resolved_paths.get("inputs.seed_file")
                                      or validated.resolved_paths.get("inputs.seed_dir")),
                    "seed_kind": "file" if "seed_file" in values["inputs"] else "dir",
                    "evidence_root": str(validated.resolved_paths["output.evidence_root"]),
                    "adapter_timeout_sec": block.get("timeout_sec", 2.0),
                    "provenance_config": values,
                }
                evidence_root = run_config["evidence_root"]
            from integration.platforms.core_runner import run_core_mock
            result = run_core_mock(evidence_root, scenario=args.scenario, run_config=run_config)
            print(json.dumps(result, sort_keys=True))
            return 0 if result.get("passed") is True else 1
        except (OSError, ValueError, RuntimeError) as exc:
            _render_cli_error("platform run", "RUNTIME_FAILURE", "offline platform execution failed")
            return 1
    if args.platform_command == "init":
        return _init_platform(args.name, args.output)
    return 2


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint with concise handling for unexpected implementation errors."""
    try:
        return _main(argv)
    except KeyboardInterrupt:
        _render_cli_error("deep2fuzz", "INPUT_ERROR", "operation interrupted")
        return 2
    except Exception:
        # Do not expose exception reprs: they can contain paths or secret-like
        # values from a platform adapter.  Detailed diagnostics remain a
        # developer concern rather than part of the stable CLI contract.
        supplied = list(sys.argv[1:] if argv is None else argv)
        top_level = {"doctor", "test", "sample", "config", "platform", "evidence"}
        context = next((item for item in supplied if item in top_level), "deep2fuzz")
        subcommands = {
            "config": {"validate"},
            "evidence": {"verify"},
            "platform": {"list", "validate", "smoke", "init", "run"},
        }
        subcommand = next((item for item in supplied if item in subcommands.get(context, set())), None)
        if subcommand:
            context = f"{context} {subcommand}"
        _render_cli_error(context, "INTERNAL_ERROR", "command failed unexpectedly")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
