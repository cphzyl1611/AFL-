from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integration.platforms.base import (  # noqa: E402
    AdapterExecutionResult,
    AdapterRegistryError,
    ExecutionIdentity,
    PlatformAdapter,
    RequestSpec,
    SecretFieldError,
)
from integration.platforms.registry import get_adapter, validate_adapter, list_adapters  # noqa: E402
from integration.platforms.mock_rest.adapter import MockRestAdapter  # noqa: E402
from integration.platforms.mock_rest.service import MockRestService  # noqa: E402
from integration.platforms.smoke import run_smoke  # noqa: E402


def identity(seq=1):
    return ExecutionIdentity("task-1", "run-1", seq, "seed-0", "arm-1")


class PlatformAdapterContractTests(unittest.TestCase):
    def test_known_adapter_resolves_and_contract_is_complete(self):
        adapter = get_adapter("mock_rest", {"base_url": "http://127.0.0.1:1"})
        self.assertIsInstance(adapter, PlatformAdapter)
        self.assertEqual(validate_adapter(adapter), [])

    def test_invalid_config_and_unsafe_target_fail_closed(self):
        with self.assertRaises(AdapterRegistryError):
            get_adapter("mock_rest", {"base_url": "http://127.0.0.1:1", "unexpected": True})
        with self.assertRaises(ValueError):
            get_adapter("mock_rest", {"base_url": "http://127.0.0.1:1@external.invalid"})

    def test_unknown_adapter_fails_closed(self):
        with self.assertRaises(AdapterRegistryError):
            get_adapter("does-not-exist", {})

    def test_required_methods_are_validated(self):
        errors = validate_adapter(object())
        self.assertTrue({"build_request", "interpret_response", "extract_object_id", "readback", "cleanup"} <= set(errors))
        class Incomplete(PlatformAdapter):
            pass
        self.assertIn("cleanup", validate_adapter(Incomplete()))

    def test_execution_identity_is_preserved_by_result(self):
        result = AdapterExecutionResult.for_identity(identity(), http_code=201, response_class="2xx")
        self.assertEqual(result.identity, identity())
        self.assertEqual(result.identity.exec_seq, 1)

    def test_business_verdict_is_structured_and_explicit(self):
        adapter = MockRestAdapter({"base_url": "http://127.0.0.1:1"})
        verdict = adapter.business_verdict("create", 422, {"error": "validation"}, identity())
        self.assertTrue(verdict.expected_rejection)
        self.assertFalse(verdict.semantic_failure)

    def test_missing_identity_fails_closed(self):
        with self.assertRaises(ValueError):
            ExecutionIdentity("task", "run", 0, "seed", "arm")
        adapter = MockRestAdapter({"base_url": "http://127.0.0.1:1"})
        with self.assertRaises(ValueError):
            adapter.create({"title": "x"}, None)

    def test_secret_fields_are_rejected_from_structured_results(self):
        with self.assertRaises(SecretFieldError):
            AdapterExecutionResult.for_identity(identity(), http_code=200, response_class="2xx", metadata={"token": "x"})
        with self.assertRaises(SecretFieldError):
            RequestSpec("GET", "/api/items", headers={"Authorization": "Bearer x"})

    def test_credential_configuration_accepts_names_only(self):
        adapter = get_adapter("mock_rest", {"base_url": "http://127.0.0.1:1", "username_env": "TASK4_USER", "password_env": "TASK4_PASS"})
        self.assertIsInstance(adapter, PlatformAdapter)
        with self.assertRaises(AdapterRegistryError):
            get_adapter("mock_rest", {"base_url": "http://127.0.0.1:1", "password_env": None})

    def test_runtime_context_update_rejects_secret_and_preserves_context(self):
        adapter = MockRestAdapter({"base_url": "http://127.0.0.1:1"})
        context = adapter.update_runtime_context({"run_id": "run-1"})
        self.assertEqual(context["run_id"], "run-1")
        with self.assertRaises(SecretFieldError):
            adapter.update_runtime_context({"token": None})

    def test_mock_full_create_read_update_read_cleanup_and_absence(self):
        with MockRestService() as service:
            adapter = MockRestAdapter({"base_url": service.base_url})
            ident = identity()
            created = adapter.create({"title": "first", "value": 1}, ident)
            self.assertTrue(created.business_success and created.object_id)
            read1 = adapter.readback(created.object_id, ident)
            self.assertTrue(read1.success and read1.payload["value"] == 1)
            updated = adapter.update(created.object_id, {"title": "second", "value": 2}, ident)
            self.assertTrue(updated.business_success and updated.object_id == created.object_id)
            read2 = adapter.readback(created.object_id, ident)
            self.assertTrue(read2.success and read2.payload["title"] == "second")
            cleaned = adapter.cleanup(created.object_id, ident)
            self.assertTrue(cleaned.success and cleaned.absent)
            self.assertTrue(adapter.readback(created.object_id, ident).absent)
            self.assertGreater(service.request_count, 0, "valid input must reach the adapter service")

    def test_expected_rejection_is_not_semantic_failure(self):
        with MockRestService() as service:
            result = MockRestAdapter({"base_url": service.base_url}).create({"reject": True}, identity())
            self.assertTrue(result.expected_rejection and not result.business_success)
            self.assertFalse(result.semantic_failure)

    def test_successful_http_with_failed_readback_is_semantic_failure(self):
        with MockRestService() as service:
            adapter = MockRestAdapter({"base_url": service.base_url})
            result = adapter.interpret_response("create", 201, {"id": "item-1"}, identity())
            self.assertTrue(result.business_success)
            failed = adapter.interpret_response("readback", 200, {"malformed": True}, identity(), object_id="missing")
            self.assertTrue(failed.semantic_failure)

    def test_unexpected_server_error_is_distinct_from_expected_rejection(self):
        result = MockRestAdapter({"base_url": "http://127.0.0.1:1"}).interpret_response("create", 503, {"error": "server"}, identity())
        self.assertTrue(result.semantic_failure)
        self.assertEqual(result.error_kind, "unexpected_http")

    def test_malformed_json_missing_id_and_connection_failure_are_safe(self):
        adapter = MockRestAdapter({"base_url": "http://127.0.0.1:1"})
        malformed = adapter.interpret_response("create", 200, b"not-json", identity())
        self.assertTrue(malformed.semantic_failure and malformed.error_kind == "malformed_json")
        missing = adapter.interpret_response("create", 201, {"ok": True}, identity())
        self.assertTrue(missing.semantic_failure and missing.error_kind == "missing_object_id")
        failure = adapter.create({"x": 1}, identity())
        self.assertTrue(failure.semantic_failure and failure.error_kind in {"connection", "timeout"})

    def test_cleanup_failure_is_reported_and_object_ids_are_exact(self):
        adapter = MockRestAdapter({"base_url": "http://127.0.0.1:1"})
        with self.assertRaises(ValueError):
            adapter.build_request("cleanup", None, identity(), "")
        request = adapter.build_request("cleanup", None, identity(), "item/a")
        self.assertEqual(request.path, "/api/items/item%2Fa")
        failure = adapter.cleanup("item-1", identity())
        self.assertFalse(failure.success)

    def test_health_only_success_is_not_business_recovery(self):
        with MockRestService() as service:
            health = MockRestAdapter({"base_url": service.base_url}).health_check(identity())
            self.assertTrue(health.success and health.business_recovery is False)

    def test_validity_rejection_happens_before_adapter(self):
        with MockRestService() as service:
            # Validity belongs to core. Once core rejects, it must not invoke
            # the adapter or mint target-side feedback.
            result = AdapterExecutionResult.for_identity(identity(), http_code=0, response_class="validation_reject", expected_rejection=True, safe_message="core validity rejected seed")
            self.assertTrue(result.expected_rejection)
            self.assertEqual(service.request_count, 0)

    def test_registry_lists_only_explicit_adapters(self):
        self.assertEqual(list_adapters(), ["mock_rest"])

    def test_cli_list_validate_and_unknown_fail_closed(self):
        cli = ROOT / "deep2fuzz"
        listed = subprocess.run([str(cli), "platform", "list"], text=True, capture_output=True, check=False)
        self.assertEqual(listed.returncode, 0)
        self.assertIn("mock_rest", listed.stdout)
        valid = subprocess.run([str(cli), "platform", "validate", "mock_rest"], text=True, capture_output=True, check=False)
        self.assertTrue(valid.returncode == 0 and "VALID" in valid.stdout)
        unknown = subprocess.run([str(cli), "platform", "validate", "unknown"], text=True, capture_output=True, check=False)
        self.assertNotEqual(unknown.returncode, 0)

    def test_cli_smoke_is_loopback_only(self):
        cli = ROOT / "deep2fuzz"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([str(cli), "platform", "smoke", "mock_rest", "--evidence-root", str(Path(directory) / "evidence")], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertTrue(summary["engineering_smoke_only"])
            self.assertFalse(summary["external_network_contacted"])

    def test_smoke_identity_matches_status_and_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence"
            summary = run_smoke(evidence)
            trace = json.loads((evidence / "identity_trace.json").read_text())
            self.assertEqual(trace["adapter_result"], trace["status_trace"])
            self.assertEqual(trace["status_trace"], trace["execution_ledger"])
            self.assertEqual(summary["identity"]["exec_seq"], trace["adapter_result"])
            self.assertEqual(trace["mab_journal"]["source_exec_seq"], trace["execution_ledger"])
            self.assertEqual(trace["report"]["source_exec_seq"], trace["execution_ledger"])

    def test_invalid_evidence_root_fails_closed(self):
        with self.assertRaises(ValueError):
            run_smoke(Path(ROOT) / "evidence-inside-repository")
        with self.assertRaises(ValueError):
            run_smoke(Path("relative-evidence"))

    def test_cli_doctor_is_offline_and_scaffold_is_safe(self):
        cli = ROOT / "deep2fuzz"
        doctor = subprocess.run([str(cli), "doctor"], text=True, capture_output=True, check=False)
        self.assertEqual(doctor.returncode, 0)
        doctor_json = json.loads(doctor.stdout)
        self.assertFalse(doctor_json["LIVE_PLATFORM_READY"])
        self.assertFalse(doctor_json["LIVE_PLATFORM_PROBED"])
        self.assertIn("zlib", doctor_json)
        self.assertIn("venv", doctor_json)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "example_platform"
            created = subprocess.run([str(cli), "platform", "init", "example_platform", "--output", str(target)], text=True, capture_output=True, check=False)
            self.assertEqual(created.returncode, 0, created.stderr)
            for relative in ("platform.json", "target.json", "rules.json", "adapter.py", "seeds/seed_0.json", "README.md"):
                self.assertTrue((target / relative).is_file())

    def test_platform_run_is_explicitly_out_of_phase(self):
        result = subprocess.run([str(ROOT / "deep2fuzz"), "platform", "run"], text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NOT_IN_PHASE1", result.stderr)


if __name__ == "__main__":
    unittest.main()
