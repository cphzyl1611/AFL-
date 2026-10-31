"""Phase 2/P1.4 CLI consistency contracts.

These tests exercise the command surface and renderer without contacting a
real platform.  Scientific and domain validation semantics are covered by
the existing P1.1-P1.3 suites; this file checks the CLI boundary around them.
"""
from __future__ import annotations

import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "deep2fuzz"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(name, None)
    return subprocess.run(
        [sys.executable, str(CLI), *args], cwd=ROOT, env=env,
        text=True, capture_output=True, check=False,
    )


def write_config(root: Path, *, valid: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    seed = root / "seed.http"
    seed.write_text("POST /api/items HTTP/1.1\nContent-Type: application/json\n\n{}\n", encoding="utf-8")
    config = {
        "schema_version": "1",
        "platform": "mock_rest",
        "run": {"max_test_cases": 2, "time_budget_seconds": 2, "timeout_seconds": 15},
        "inputs": {"seed_file": "seed.http"},
        "output": {"evidence_root": "future-output"},
        "validity": {"enabled": True},
        "cleanup": {"required": True},
        "platform_config": {"mock_rest": {}},
    }
    if not valid:
        config["run"]["max_test_cases"] = 0
    path = root / "config.json"
    path.write_text(json.dumps(config, sort_keys=True) + "\n", encoding="utf-8")
    return path


class CliConsistencyTests(unittest.TestCase):
    def test_t01_top_level_help(self):
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage: deep2fuzz", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_t02_version(self):
        result = run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "1.1.0rc2")
        self.assertEqual(result.stderr, "")

    def test_t03_unknown_top_level_is_usage_error(self):
        result = run_cli("unknown")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error:", result.stderr)

    def test_t04_unknown_option_is_usage_error(self):
        result = run_cli("--unknown-option")
        self.assertEqual(result.returncode, 2)
        self.assertIn("USAGE_ERROR", result.stderr)

    def test_t05_missing_positional_is_usage_error(self):
        result = run_cli("config", "validate")
        self.assertEqual(result.returncode, 2)
        self.assertIn("USAGE_ERROR", result.stderr)

    def test_help_contracts(self):
        commands = (
            ("platform",),
            ("platform", "list"),
            ("platform", "run"),
            ("config",),
            ("config", "validate"),
            ("evidence",),
            ("evidence", "verify"),
            ("doctor", "--help"),
        )
        for args in commands:
            args = args + ("--help",)
            result = run_cli(*args)
            self.assertEqual(result.returncode, 0, args)
            self.assertIn("usage: deep2fuzz", result.stdout, args)
            self.assertEqual(result.stderr, "", args)

    def test_t06_t08_t09_t10_t16_t17_t23_help_has_no_runtime_output(self):
        for args in (("platform", "--help"), ("platform", "list", "--help"),
                     ("platform", "run", "--help"), ("config", "--help"),
                     ("config", "validate", "--help"), ("evidence", "--help"),
                     ("evidence", "verify", "--help"), ("doctor", "--help")):
            result = run_cli(*args)
            self.assertEqual(result.returncode, 0, args)
            self.assertEqual(result.stderr, "", args)
            self.assertNotIn("Traceback", result.stdout)

    def test_config_human_exit_and_error_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = write_config(root)
            result = run_cli("config", "validate", str(valid))
            self.assertEqual(result.returncode, 0)
            self.assertIn("Command: config validate", result.stdout)
            self.assertIn("Result: PASS", result.stdout)
            self.assertEqual(result.stderr, "")
            invalid = write_config(root / "invalid", valid=False)
            result = run_cli("config", "validate", str(invalid))
            self.assertEqual(result.returncode, 1)
            self.assertIn("OUT_OF_RANGE", result.stdout)
            self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_config_input_error_is_exit_two_and_stderr_only(self):
        result = run_cli("config", "validate", "/path/that/does/not/exist")
        self.assertEqual(result.returncode, 2)
        self.assertIn("INPUT_ERROR", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_config_json_is_pure_for_valid_invalid_and_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = write_config(root)
            for path, expected in ((valid, 0), (write_config(root / "bad", valid=False), 1)):
                result = run_cli("config", "validate", str(path), "--json")
                self.assertEqual(result.returncode, expected)
                json.loads(result.stdout)
                self.assertEqual(result.stderr, "")
            result = run_cli("config", "validate", str(root / "missing.json"), "--json")
            self.assertEqual(result.returncode, 2)
            json.loads(result.stdout)
            self.assertEqual(result.stderr, "")

    def test_evidence_input_and_json_contract(self):
        human = run_cli("evidence", "verify", "/path/that/does/not/exist")
        self.assertEqual(human.returncode, 2)
        self.assertIn("INPUT_ERROR", human.stderr)
        self.assertEqual(human.stdout, "")
        machine = run_cli("evidence", "verify", "/path/that/does/not/exist", "--json")
        self.assertEqual(machine.returncode, 2)
        json.loads(machine.stdout)
        self.assertEqual(machine.stderr, "")

    def test_evidence_domain_failure_is_exit_one_in_both_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "empty-evidence"
            root.mkdir()
            human = run_cli("evidence", "verify", str(root))
            self.assertEqual(human.returncode, 1)
            self.assertIn("Command: evidence verify", human.stdout)
            self.assertIn("Result: FAIL", human.stdout)
            self.assertEqual(human.stderr, "")
            machine = run_cli("evidence", "verify", str(root), "--json")
            self.assertEqual(machine.returncode, 1)
            self.assertEqual(json.loads(machine.stdout)["verdict"], "FAIL")
            self.assertEqual(machine.stderr, "")

    def test_evidence_success_human_and_json_render_same_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "run"
            run = run_cli("platform", "run", "mock_rest", "--evidence-root", str(evidence))
            self.assertEqual(run.returncode, 0, run.stderr)
            human = run_cli("evidence", "verify", str(evidence))
            machine = run_cli("evidence", "verify", str(evidence), "--json")
            self.assertEqual(human.returncode, 0, human.stderr)
            self.assertIn("Result: PASS", human.stdout)
            self.assertEqual(human.stderr, "")
            self.assertEqual(machine.returncode, 0, machine.stderr)
            self.assertEqual(json.loads(machine.stdout)["verdict"], "PASS")
            self.assertEqual(machine.stderr, "")

    def test_invalid_config_does_not_enter_adapter_or_core(self):
        from deep2fuzz_cli import main

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_config(root, valid=False)
            output = root / "future-output"
            with mock.patch("integration.platforms.core_runner.run_core_mock") as runner, \
                 mock.patch("deep2fuzz_cli.get_adapter") as factory, \
                 mock.patch("sys.stdout", new_callable=__import__("io").StringIO), \
                 mock.patch("sys.stderr", new_callable=__import__("io").StringIO):
                code = main(["platform", "run", "mock_rest", "--config", str(path)])
            self.assertEqual(code, 1)
            runner.assert_not_called()
            factory.assert_not_called()
            self.assertFalse(output.exists())

    def test_help_and_parser_failures_do_not_instantiate_adapter(self):
        from deep2fuzz_cli import main
        from integration.platforms.mock_rest.adapter import MockRestAdapter

        with mock.patch.object(MockRestAdapter, "__init__", side_effect=AssertionError("adapter instantiated")) as init:
            with mock.patch("sys.stdout", new_callable=io.StringIO), mock.patch("sys.stderr", new_callable=io.StringIO):
                for args in (("--help",), ("platform", "--help"), ("unknown",)):
                    try:
                        main(list(args))
                    except SystemExit as exc:
                        self.assertEqual(exc.code, 0 if args[-1] == "--help" else 2)
            init.assert_not_called()

    def test_platform_runtime_failure_is_exit_one_without_traceback(self):
        from deep2fuzz_cli import main

        with mock.patch("integration.platforms.core_runner.run_core_mock", side_effect=RuntimeError("secret-bearing details")), \
             mock.patch("sys.stdout", new_callable=__import__("io").StringIO) as stdout, \
             mock.patch("sys.stderr", new_callable=__import__("io").StringIO) as stderr:
            code = main(["platform", "run", "mock_rest"])
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("RUNTIME_FAILURE", stderr.getvalue())
        self.assertNotIn("secret-bearing details", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_platform_semantic_output_matches_existing_accounting_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "run"
            result = run_cli("platform", "run", "mock_rest", "--evidence-root", str(evidence))
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            report = json.loads((evidence / "eval_report.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["COV_BEHAVIOR_UNCHANGED"], "PASS")
            self.assertEqual(summary["ERR_BEHAVIOR_UNCHANGED"], "PASS")
            self.assertEqual(summary["REPORT_ACCOUNTING_RECONCILIATION"], "PASS")
            self.assertEqual(summary["nv_err_exec"], report["err"]["err_exec"])
            self.assertEqual(summary["recovery_opportunity_count"], report["rec"]["recovery_opportunity_count"])
            self.assertEqual(summary["security_state_seed_credit"], report["security_state_cov"]["security_state_seed_credit"])
            self.assertEqual(result.stderr, "")

    def test_json_output_has_no_banner_or_ansi(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_config(Path(directory))
            result = run_cli("config", "validate", str(path), "--json")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "PASS")
            self.assertFalse(result.stdout.startswith("Deep2Fuzz"))
            self.assertNotRegex(result.stdout, r"\x1b\[[0-9;]*m")
            self.assertEqual(result.stderr, "")

    def test_config_secret_value_is_not_rendered(self):
        secret = "YOUR_TOKEN_HERE"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_config(root)
            config = json.loads(path.read_text(encoding="utf-8"))
            config["unexpected_token"] = secret
            path.write_text(json.dumps(config), encoding="utf-8")
            human = run_cli("config", "validate", str(path))
            machine = run_cli("config", "validate", str(path), "--json")
            self.assertEqual(human.returncode, 1)
            self.assertEqual(machine.returncode, 1)
            self.assertNotIn(secret, human.stdout + human.stderr)
            self.assertNotIn(secret, machine.stdout + machine.stderr)
            self.assertEqual(json.loads(machine.stdout)["errors"][0]["code"], "UNKNOWN_FIELD")

    def test_valid_config_reaches_existing_core_and_writes_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = write_config(root)
            output = root / "config-run"
            value = json.loads(config.read_text(encoding="utf-8"))
            value["output"]["evidence_root"] = str(output)
            config.write_text(json.dumps(value), encoding="utf-8")
            result = run_cli("platform", "run", "mock_rest", "--config", str(config))
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            report = json.loads((output / "eval_report.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["passed"])
            self.assertEqual(report["provenance"]["product"]["version"], "1.1.0rc2")
            self.assertEqual(summary["REPORT_ACCOUNTING_RECONCILIATION"], "PASS")

    def test_unexpected_exception_is_internal_error_not_domain_failure(self):
        from deep2fuzz_cli import main

        with mock.patch("deep2fuzz_cli._doctor", side_effect=RuntimeError("fixture internal detail")), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout, \
             mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            code = main(["doctor"])
        self.assertEqual(code, 3)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("INTERNAL_ERROR", stderr.getvalue())
        self.assertNotIn("fixture internal detail", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_platform_list_is_deterministic_and_offline(self):
        first = run_cli("platform", "list")
        second = run_cli("platform", "list")
        self.assertEqual(first.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stdout.splitlines(), ["mock_rest"])
        self.assertEqual(first.stderr, "")

    def test_platform_invocation_errors_are_exit_two(self):
        for args in (("platform",), ("platform", "run"), ("platform", "run", "unknown")):
            result = run_cli(*args)
            self.assertEqual(result.returncode, 2, args)
            self.assertNotIn("Traceback", result.stderr)

    def test_parser_never_echoes_rejected_argument_value(self):
        rejected = "fixture-secret-argument-value"
        result = run_cli("platform", "run", "mock_rest", "--scenario", rejected)
        self.assertEqual(result.returncode, 2)
        self.assertIn("USAGE_ERROR", result.stderr)
        self.assertNotIn(rejected, result.stderr)

    def test_doctor_is_deterministic_and_does_not_load_model_stack(self):
        first = run_cli("doctor")
        second = run_cli("doctor")
        self.assertEqual(first.returncode, 0)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        payload = json.loads(first.stdout)
        self.assertFalse(payload["optional_model_stack_imported"])
        self.assertFalse(payload["LIVE_PLATFORM_PROBED"])
        self.assertEqual(first.stderr, "")

    def test_expected_errors_do_not_expose_tracebacks_or_secrets(self):
        result = run_cli("platform", "validate", "unknown")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("Authorization", result.stdout + result.stderr)
        self.assertNotIn("Bearer", result.stdout + result.stderr)

    def test_unicode_input_path_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "中文目录"
            root.mkdir()
            config = write_config(root)
            result = run_cli("config", "validate", str(config), "--json")
            self.assertEqual(result.returncode, 0)
            json.loads(result.stdout)


if __name__ == "__main__":
    unittest.main()
