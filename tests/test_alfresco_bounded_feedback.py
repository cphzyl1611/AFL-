"""Offline contracts for the bounded Alfresco real-feedback orchestrator."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
import hashlib
import json
import tempfile



REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
RUNNER_PATH = REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py"


def _materialize_execution_artifacts(layout, *, include_fuzzer_stats=True):
    """Materialize only producer-shaped artifacts for offline launch fakes."""

    payloads = {
        "status": {"http_code": 200},
        "status_seq": "1",
        "probe": {"ncov_total": 1},
        "state_db": [],
        "state_trace": '{"event":"state"}\n',
        "body_valid_stats": {"body_rule_pass": 1},
    }
    for name, payload in payloads.items():
        path = Path(layout[name])
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")
    if include_fuzzer_stats:
        afl_stats = Path(layout["afl_output"]) / "fuzzer_stats"
        afl_stats.parent.mkdir(parents=True, exist_ok=True)
        afl_stats.write_text(
            "execs_done : 1\n"
            "nv_total_valid_exec : 0\n"
            "nv_mab_total_pulls : 0\n"
            "nv_mab_arm0_pulls : 0\n"
            "nv_mab_arm1_pulls : 0\n"
            "nv_mab_arm2_pulls : 0\n"
            "nv_mab_arm0_sum : 0\n"
            "nv_mab_arm1_sum : 0\n"
            "nv_mab_arm2_sum : 0\n"
            "nv_mab_arm0_pos : 0\n"
            "nv_mab_arm1_pos : 0\n"
            "nv_mab_arm2_pos : 0\n"
            "security_state_reward_src_seq : 0\n"
            "nv_mab_journal_error_count : 0\n"
            "nv_mab_journal_audit_invalid : 0\n"
            "ss_selected_sum : 0\n"
            "seed_audit_enabled : 1\n"
            "seed_audit_error_count : 0\n"
            "seed_audit_invalid : 0\n"
            "seed_audit_record_count : 0\n"
            "seed_audit_expected_selection_count : 0\n",
            encoding="utf-8",
        )
    Path(layout["mab_journal"]).parent.mkdir(parents=True, exist_ok=True)
    Path(layout["mab_journal"]).touch(exist_ok=True)
    # Multi-arm runs require an append-only ledger even when this fake launch
    # produces no committed execution records.
    Path(layout["evidence"] / "executions.jsonl").touch(exist_ok=True)
    Path(layout["seed_selection_audit"]).touch(exist_ok=True)


class AlfrescoMetadataMutationContractTest(unittest.TestCase):
    SEED = (
        b"PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/node-id HTTP/1.1\r\n"
        b"Content-Type: application/json\r\n\r\n"
        b'{"properties":{"cm:title":"seed title",'
        b'"cm:description":"seed description"}}'
    )

    def test_field_value_arm_preserves_nested_object_shape(self) -> None:
        import nv_json_mutator

        original_getenv = nv_json_mutator._live_getenv
        original_random = nv_json_mutator.random
        try:
            nv_json_mutator._live_getenv = (
                lambda name, default="": "0" if name == "NV_CUR_ARM" else default
            )
            nv_json_mutator.random.seed(1)
            mutated = nv_json_mutator.afl_custom_fuzz(
                None, self.SEED, None, 10000
            )
        finally:
            nv_json_mutator._live_getenv = original_getenv
            nv_json_mutator.random = original_random

        separator = b"\r\n\r\n" if b"\r\n\r\n" in mutated else b"\n\n"
        body = json.loads(mutated.split(separator, 1)[1].decode("utf-8"))
        self.assertIsInstance(body["properties"], dict)
        self.assertIsInstance(body["properties"]["cm:title"], str)
        self.assertIsInstance(body["properties"]["cm:description"], str)

    def test_boundary_arm_preserves_metadata_properties_object(self) -> None:
        import nv_json_mutator

        original_getenv = nv_json_mutator._live_getenv
        original_random = nv_json_mutator.random
        try:
            nv_json_mutator._live_getenv = (
                lambda name, default="": "1" if name == "NV_CUR_ARM" else default
            )
            nv_json_mutator.random.seed(1)
            mutated = nv_json_mutator.afl_custom_fuzz(None, self.SEED, None, 10000)
        finally:
            nv_json_mutator._live_getenv = original_getenv
            nv_json_mutator.random = original_random

        separator = b"\r\n\r\n" if b"\r\n\r\n" in mutated else b"\n\n"
        body = json.loads(mutated.split(separator, 1)[1].decode("utf-8"))
        self.assertIsInstance(body["properties"], dict)
        self.assertIn("cm:title", body["properties"])
        self.assertIn("cm:description", body["properties"])

    def test_structure_arm_preserves_metadata_properties_object(self) -> None:
        import nv_json_mutator

        original_getenv = nv_json_mutator._live_getenv
        original_random = nv_json_mutator.random
        try:
            nv_json_mutator._live_getenv = (
                lambda name, default="": "2" if name == "NV_CUR_ARM" else default
            )
            nv_json_mutator.random.seed(1)
            mutated = nv_json_mutator.afl_custom_fuzz(None, self.SEED, None, 10000)
        finally:
            nv_json_mutator._live_getenv = original_getenv
            nv_json_mutator.random = original_random

        separator = b"\r\n\r\n" if b"\r\n\r\n" in mutated else b"\n\n"
        body = json.loads(mutated.split(separator, 1)[1].decode("utf-8"))
        self.assertIsInstance(body["properties"], dict)
        self.assertIn("cm:title", body["properties"])
        self.assertIn("cm:description", body["properties"])

    def test_body_only_mutator_returns_json_without_http_envelope(self) -> None:
        import nv_json_mutator

        original_getenv = nv_json_mutator._live_getenv
        original_random = nv_json_mutator.random
        try:
            nv_json_mutator._live_getenv = (
                lambda name, default="": "1" if name == "NV_BODY_ONLY_MODE" else default
            )
            nv_json_mutator.random.seed(1)
            mutated = nv_json_mutator.afl_custom_fuzz(
                None, b'{"key":"seed"}', None, 10000
            )
        finally:
            nv_json_mutator._live_getenv = original_getenv
            nv_json_mutator.random = original_random

        body = json.loads(mutated.decode("utf-8"))
        self.assertIsInstance(body, dict)
        self.assertNotIn(b"HTTP/1.1", mutated)
        self.assertIn("key", body)

    def test_metadata_update_rules_use_the_validator_endpoint_contract(self) -> None:
        from nv_body_valid import body_validate

        rules = REPO_ROOT / "validity" / "alfresco_metadata_update_rules.json"
        valid = body_validate(
            endpoint_name="metadata_update",
            raw_body=b'{"properties":{"cm:title":"seed title",'
            b'"cm:description":"seed description"}}',
            rules_path=str(rules),
        )
        invalid = body_validate(
            endpoint_name="metadata_update",
            raw_body=b'{"properties":"mut"}',
            rules_path=str(rules),
        )

        self.assertTrue(valid["ok"], valid["reason"])
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["reason"], "field_type_mismatch")


class ExistingDedicatedResourceResolutionTest(unittest.TestCase):
    def _load_runner(self):
        return _load_runner_module("target_binding_red_test")

    @staticmethod
    def _client(module, entries):
        folder_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        class FakeClient:
            def __init__(self):
                self.create_calls = []

            def list_children(self, parent_id):
                if parent_id == "-my-":
                    return [{
                        "id": folder_id,
                        "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                        "parentId": "-my-",
                        "isFolder": True,
                        "isFile": False,
                    }]
                if parent_id == folder_id:
                    return entries
                raise AssertionError(parent_id)

            def create_child(self, *args, **kwargs):
                self.create_calls.append((args, kwargs))
                raise AssertionError("existing-target resolver must never create")

        return FakeClient()

    def test_default_target_binding_preserves_canonical_file(self):
        module = self._load_runner()
        client = self._client(module, [{
            "id": "11111111-2222-3333-4444-555555555555",
            "parentId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "nv-afl-levelc-metadata.txt",
            "isFolder": False, "isFile": True,
        }])
        result = module.resolve_existing_dedicated_node(client)
        self.assertEqual(result["target_name"], "nv-afl-levelc-metadata.txt")

    def test_explicit_target_file_name_selects_existing_target(self):
        module = self._load_runner()
        entries = [
            {"id": f"{index:08d}-2222-3333-4444-555555555555",
             "parentId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
             "name": name, "isFolder": False, "isFile": True}
            for index, name in enumerate((
                "nv-afl-levelc-metadata.txt",
                "nv-afl-levelc-metadata-arm1.txt",
                "nv-afl-levelc-metadata-arm2.txt",
            ), 1)
        ]
        client = self._client(module, entries)
        for name, expected_id in zip(
            (entry["name"] for entry in entries), (entry["id"] for entry in entries)
        ):
            result = module.resolve_existing_dedicated_node(client, name)
            self.assertEqual(result["file_id"], expected_id)
            self.assertEqual(result["target_name"], name)
            self.assertEqual(result["parent_id"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
            self.assertEqual(result["folder_id"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertEqual(client.create_calls, [])

    def test_explicit_target_binding_fails_closed_for_missing_ambiguous_wrong_parent(self):
        module = self._load_runner()
        base = {
            "id": "11111111-2222-3333-4444-555555555555",
            "parentId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "nv-afl-levelc-metadata-arm1.txt",
            "isFolder": False, "isFile": True,
        }
        for entries, error in (
            ([], "BOUNDED_DEDICATED_FILE_MISSING"),
            ([base, dict(base, id="22222222-3333-4444-5555-666666666666")],
             "BOUNDED_DEDICATED_FILE_AMBIGUOUS"),
            ([dict(base, parentId="bbbbbbbb-cccc-dddd-eeee-ffffffffffff")],
             "BOUNDED_DEDICATED_FILE_WRONG_PARENT"),
            ([dict(base, isFolder=True, isFile=False)],
             "BOUNDED_DEDICATED_FILE_MISSING"),
        ):
            with self.subTest(error=error):
                client = self._client(module, entries)
                with self.assertRaisesRegex(RuntimeError, f"^{error}$"):
                    module.resolve_existing_dedicated_node(
                        client, "nv-afl-levelc-metadata-arm1.txt"
                    )
                self.assertEqual(client.create_calls, [])

    def test_target_selector_rejects_path_traversal_and_absolute_path(self):
        module = self._load_runner()
        client = self._client(module, [])
        for selector in (
            "../other.txt",
            "../../AFLplusplus/x",
            "/etc/passwd",
            "nested/target.txt",
            "nested\\target.txt",
        ):
            with self.subTest(selector=selector):
                with self.assertRaisesRegex(ValueError, "^INVALID_TARGET_FILE_NAME$"):
                    module.resolve_existing_dedicated_node(client, selector)

    def test_whitespace_only_target_file_name_is_rejected(self):
        module = self._load_runner()
        for selector in (" ", "   ", "\t", "\n", " \t "):
            with self.subTest(selector=repr(selector)):
                with self.assertRaisesRegex(ValueError, "^INVALID_TARGET_FILE_NAME$"):
                    module.validate_target_file_name(selector)

    def test_target_selector_rejects_empty_elements(self):
        module = self._load_runner()

        class NoSideEffectClient:
            def list_children(self, parent_id):
                raise AssertionError("invalid selector must fail before node resolution")

            def request(self, *args, **kwargs):
                raise AssertionError("invalid selector must not perform network requests")

            def create_child(self, *args, **kwargs):
                raise AssertionError("invalid selector must not create Alfresco nodes")

        client = NoSideEffectClient()
        for selector in ("", " ", "   ", "\t", "\n", " \t "):
            with self.subTest(selector=repr(selector)):
                with self.assertRaisesRegex(ValueError, "^INVALID_TARGET_FILE_NAME$"):
                    module.resolve_existing_dedicated_node(client, selector)

    def test_whitespace_only_target_selector_fails_before_side_effects(self):
        import contextlib
        import io
        import tempfile

        module = self._load_runner()
        for index, selector in enumerate((" ", "   ", "\t", "\n", " \t ")):
            with self.subTest(selector=repr(selector)):
                events = []

                def credential_gate():
                    events.append("credentials")
                    raise RuntimeError("CREDENTIAL_GATE_REACHED")

                module.runtime_credentials = credential_gate
                module.build_alfresco_client = lambda *args, **kwargs: events.append("client")
                module.perform_preflight = lambda *args, **kwargs: events.append("preflight")
                module.resolve_existing_dedicated_node = (
                    lambda *args, **kwargs: events.append("resolver")
                )
                module.build_run_layout = lambda *args, **kwargs: events.append("layout")
                module.render_runtime_target_config = (
                    lambda *args, **kwargs: events.append("target_write")
                )
                module.build_task_payload = lambda *args, **kwargs: events.append("task_write")
                module.launch_bounded_afl = lambda *args, **kwargs: events.append("launch")

                with tempfile.TemporaryDirectory(prefix="target-selector-gate-") as tmp:
                    run_root = Path(tmp) / f"run-{index}"
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        rc = module.main([
                            "--run-root", str(run_root),
                            "--target-file-name", selector,
                        ])

                    self.assertEqual(rc, 2)
                    self.assertEqual(stderr.getvalue().strip(), "INVALID_TARGET_FILE_NAME")
                    self.assertEqual(events, [])
                    self.assertFalse(run_root.exists())
                    self.assertFalse((run_root / "task.json").exists())
                    self.assertFalse((run_root / "target.json").exists())


class TargetBindingPayloadTest(unittest.TestCase):
    def test_task_payload_records_selected_target_without_changing_other_fields(self):
        module = _load_runner_module("target_binding_payload_red_test")
        with __import__("tempfile").TemporaryDirectory(prefix="target-binding-task-") as tmp:
            seed_dir = Path(tmp) / "seed_input"
            base = module.build_task_payload(seed_dir, max_test_cases=3, time_budget=30)
            selected = module.build_task_payload(
                seed_dir, max_test_cases=3, time_budget=30,
                mutation_scope=["boundary"],
                target_file_name="nv-afl-levelc-metadata-arm1.txt",
            )
            self.assertEqual(selected["target_file_name"], "nv-afl-levelc-metadata-arm1.txt")
            for key in ("target_type", "target_endpoint", "seed_source", "seed_location",
                        "max_test_cases", "time_budget", "enable_validity"):
                self.assertEqual(base[key], selected[key])
            self.assertEqual(selected["mutation_scope"], ["boundary"])

    def test_selected_target_identity_is_reused_for_render_and_readback(self):
        module = _load_runner_module("target_binding_identity_reuse_test")
        import contextlib
        import io
        import tempfile

        folder_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        canonical_id = "11111111-2222-3333-4444-555555555555"
        arm1_id = "22222222-3333-4444-5555-666666666666"
        arm1_name = "nv-afl-levelc-metadata-arm1.txt"
        calls = []

        class FakeClient:
            def list_children(self, parent_id):
                if parent_id == "-my-":
                    return [{"id": folder_id, "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                             "isFolder": True, "isFile": False}]
                if parent_id == folder_id:
                    return [
                        {"id": canonical_id, "parentId": folder_id,
                         "name": "nv-afl-levelc-metadata.txt",
                         "isFolder": False, "isFile": True},
                        {"id": arm1_id, "parentId": folder_id, "name": arm1_name,
                         "isFolder": False, "isFile": True},
                    ]
                raise AssertionError(parent_id)

            def get_node(self, node_id):
                calls.append(("identity", node_id))
                return {"id": node_id, "parentId": folder_id,
                        "name": arm1_name}

            def request(self, method, path, **kwargs):
                calls.append((method, path))
                return 200, {"entry": {"id": arm1_id, "parentId": folder_id,
                                       "name": arm1_name, "properties": {}}}

        client = FakeClient()
        module.build_alfresco_client = lambda base, credentials: client
        module.perform_preflight = lambda client: {"ok": True}

        def fake_render(node_id, output):
            calls.append(("render", node_id))
            output.write_text(json.dumps({"endpoints": [{"name": "metadata_update",
                "method": "PUT", "path": "/nodes/" + node_id}]}), encoding="utf-8")
            return output

        def fake_launch(layout, config_path, child_env, **kwargs):
            calls.append(("launch", json.loads(Path(layout["task"]).read_text(encoding="utf-8"))))
            _materialize_execution_artifacts(layout)
            return 0

        def fake_readback(client, target_identity, layout, **kwargs):
            calls.append(("readback_identity", dict(target_identity)))
            return module._readback_base(applicable=False)

        module.render_runtime_target_config = fake_render
        module.launch_bounded_afl = fake_launch
        module.post_execution_readback = fake_readback
        old_credentials = (os.environ.get("ALFRESCO_USER"), os.environ.get("ALFRESCO_PASS"))
        os.environ["ALFRESCO_USER"] = "offline-user"
        os.environ["ALFRESCO_PASS"] = "offline-pass"
        try:
            with tempfile.TemporaryDirectory(prefix="target-binding-main-") as tmp:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    rc = module.main([
                        "--run-root", tmp,
                        "--target-file-name", arm1_name,
                        "--mutation-scope", "boundary",
                    ])
                self.assertEqual(rc, 0, stderr.getvalue())
                task = json.loads((Path(tmp) / "task.json").read_text(encoding="utf-8"))
                report = json.loads((Path(tmp) / "evidence" / "artifact_report.json").read_text(encoding="utf-8"))
                self.assertEqual(task["target_file_name"], arm1_name)
                self.assertEqual(report["target_binding"]["target_file_name"], arm1_name)
                self.assertIn(("render", arm1_id), calls)
                self.assertIn(("readback_identity", {
                    "node_id": arm1_id, "parent_id": folder_id, "name": arm1_name,
                }), calls)
                self.assertNotIn(("render", canonical_id), calls)
        finally:
            for key, value in zip(("ALFRESCO_USER", "ALFRESCO_PASS"), old_credentials):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    def test_duplicate_dedicated_folder_fails_closed_without_creation(self) -> None:
        """Duplicate dedicated folders must abort instead of guessing one."""

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bounded_runner_duplicate_folder_test",
            RUNNER_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class FakeClient:
            def __init__(self) -> None:
                self.list_calls = []
                self.create_calls = 0

            def list_children(self, parent_id: str):
                self.list_calls.append(parent_id)

                if parent_id == "-my-":
                    return [
                        {
                            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                            "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                            "isFolder": True,
                            "isFile": False,
                        },
                        {
                            "id": "11111111-2222-3333-4444-555555555555",
                            "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                            "isFolder": True,
                            "isFile": False,
                        },
                    ]

                raise AssertionError(
                    f"resolver must stop after ambiguous folder; got lookup {parent_id}"
                )

            def create_child(self, *args, **kwargs):
                self.create_calls += 1
                raise AssertionError(
                    "bounded resolver must never create nodes"
                )

        client = FakeClient()

        observed_type = None
        observed_message = None

        try:
            module.resolve_existing_dedicated_node(client)
        except Exception as exc:
            observed_type = type(exc)
            observed_message = str(exc)

        self.assertIs(
            observed_type,
            RuntimeError,
            (
                "duplicate folder must produce a stable bounded-runner RuntimeError; "
                f"got {observed_type}"
            ),
        )
        self.assertEqual(
            observed_message,
            "BOUNDED_DEDICATED_FOLDER_AMBIGUOUS",
        )

        self.assertEqual(client.list_calls, ["-my-"])
        self.assertEqual(client.create_calls, 0)
    def test_missing_dedicated_file_fails_closed_without_creation(self) -> None:
        """A missing dedicated file must abort instead of creating one."""

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bounded_runner_missing_file_test",
            RUNNER_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        folder_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        class FakeClient:
            def __init__(self) -> None:
                self.list_calls = []
                self.create_calls = 0

            def list_children(self, parent_id: str):
                self.list_calls.append(parent_id)

                if parent_id == "-my-":
                    return [
                        {
                            "id": folder_id,
                            "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                            "isFolder": True,
                            "isFile": False,
                        }
                    ]

                if parent_id == folder_id:
                    return []

                raise AssertionError(
                    f"unexpected parent lookup: {parent_id}"
                )

            def create_child(self, *args, **kwargs):
                self.create_calls += 1
                raise AssertionError(
                    "bounded resolver must never create nodes"
                )

        client = FakeClient()

        observed_type = None
        observed_message = None

        try:
            module.resolve_existing_dedicated_node(client)
        except Exception as exc:
            observed_type = type(exc)
            observed_message = str(exc)

        self.assertIs(
            observed_type,
            RuntimeError,
            (
                "missing file must produce a stable bounded-runner RuntimeError; "
                f"got {observed_type}"
            ),
        )
        self.assertEqual(
            observed_message,
            "BOUNDED_DEDICATED_FILE_MISSING",
        )

        self.assertEqual(
            client.list_calls,
            ["-my-", folder_id],
        )
        self.assertEqual(client.create_calls, 0)
    def test_missing_dedicated_folder_fails_closed_without_creation(self) -> None:
        """A missing dedicated folder must abort instead of creating one."""

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bounded_runner_missing_folder_test",
            RUNNER_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class FakeClient:
            def __init__(self) -> None:
                self.list_calls = []
                self.create_calls = 0

            def list_children(self, parent_id: str):
                self.list_calls.append(parent_id)

                if parent_id == "-my-":
                    return []

                raise AssertionError(
                    f"resolver must stop after missing folder; got lookup {parent_id}"
                )

            def create_child(self, *args, **kwargs):
                self.create_calls += 1
                raise AssertionError("bounded resolver must never create nodes")

        client = FakeClient()

        observed_type = None
        observed_message = None

        try:
            module.resolve_existing_dedicated_node(client)
        except Exception as exc:
            observed_type = type(exc)
            observed_message = str(exc)

        self.assertIs(
            observed_type,
            RuntimeError,
            (
                "missing folder must produce a stable bounded-runner RuntimeError; "
                f"got {observed_type}"
            ),
        )
        self.assertEqual(
            observed_message,
            "BOUNDED_DEDICATED_FOLDER_MISSING",
        )

        self.assertEqual(client.list_calls, ["-my-"])
        self.assertEqual(client.create_calls, 0)
        
    def test_unique_existing_folder_and_file_are_resolved_without_creation(
        self,
    ) -> None:
        """The bounded runner may reuse exactly one existing dedicated resource only."""

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bounded_runner_existing_resource_test",
            RUNNER_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertTrue(
            hasattr(module, "resolve_existing_dedicated_node"),
            "runner must provide resolve_existing_dedicated_node()",
        )

        folder_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        file_id = "11111111-2222-3333-4444-555555555555"

        class FakeClient:
            def __init__(self) -> None:
                self.list_calls = []
                self.create_calls = 0

            def list_children(self, parent_id: str):
                self.list_calls.append(parent_id)

                if parent_id == "-my-":
                    return [
                        {
                            "id": folder_id,
                            "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                            "isFolder": True,
                            "isFile": False,
                        }
                    ]

                if parent_id == folder_id:
                    return [
                        {
                            "id": file_id,
                            "parentId": folder_id,
                            "name": "nv-afl-levelc-metadata.txt",
                            "isFolder": False,
                            "isFile": True,
                            "aspectNames": ["cm:auditable", "cm:titled"],
                        }
                    ]

                raise AssertionError(f"unexpected parent lookup: {parent_id}")

            def create_child(self, *args, **kwargs):
                self.create_calls += 1
                raise AssertionError("bounded resolver must never create nodes")

        client = FakeClient()

        result = module.resolve_existing_dedicated_node(client)

        self.assertEqual(result["folder_id"], folder_id)
        self.assertEqual(result["file_id"], file_id)
        self.assertEqual(
            result["aspect_names"],
            ["cm:auditable", "cm:titled"],
        )

        self.assertEqual(
            client.list_calls,
            ["-my-", folder_id],
        )
        self.assertEqual(client.create_calls, 0)

    def test_folder_parent_uuid_from_api_is_accepted(self) -> None:
        """The API may expose -my- parent as its concrete node UUID."""

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bounded_runner_parent_uuid_test",
            RUNNER_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        folder_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        file_id = "11111111-2222-3333-4444-555555555555"
        parent_uuid = "22222222-3333-4444-5555-666666666666"

        class FakeClient:
            def list_children(self, parent_id: str):
                if parent_id == "-my-":
                    return [{
                        "id": folder_id,
                        "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                        "parentId": parent_uuid,
                        "isFolder": True,
                        "isFile": False,
                    }]
                if parent_id == folder_id:
                    return [{
                        "id": file_id,
                        "name": "nv-afl-levelc-metadata.txt",
                        "parentId": folder_id,
                        "isFolder": False,
                        "isFile": True,
                    }]
                raise AssertionError(f"unexpected parent lookup: {parent_id}")

            def get_node(self, node_id: str):
                if node_id == "-my-":
                    return {"id": parent_uuid}
                raise AssertionError(f"unexpected node lookup: {node_id}")

        result = module.resolve_existing_dedicated_node(FakeClient())

        self.assertEqual(result["folder_id"], folder_id)
        self.assertEqual(result["file_id"], file_id)

class RuntimeTargetConfigTest(unittest.TestCase):
    def test_runtime_target_config_reuses_levelc_contract_without_mutating_template(
        self,
    ) -> None:
        """Runtime config resolves only the node id and preserves the Level-C contract."""

        import importlib.util
        import tempfile

        spec = importlib.util.spec_from_file_location(
            "bounded_runner_target_render_test",
            RUNNER_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertTrue(
            hasattr(module, "render_runtime_target_config"),
            "runner must provide render_runtime_target_config()",
        )

        template = REPO_ROOT / "targets" / "alfresco_metadata_update.json"
        before = template.read_bytes()
        before_hash = hashlib.sha256(before).hexdigest()

        node_id = "11111111-2222-3333-4444-555555555555"

        with tempfile.TemporaryDirectory(
            prefix="alfresco-bounded-target-"
        ) as tmp:
            out_path = Path(tmp).resolve() / "target.json"

            result = module.render_runtime_target_config(
                node_id,
                out_path,
            )

            self.assertEqual(Path(result).resolve(), out_path)
            self.assertTrue(out_path.is_file())

            rendered_text = out_path.read_text(encoding="utf-8")
            rendered = json.loads(rendered_text)

            self.assertNotIn("__ALFRESCO_NODE_ID__", rendered_text)

            self.assertEqual(
                rendered["base"],
                "http://127.0.0.1:8080",
            )
            self.assertEqual(rendered["body_only_mode"], 1)

            self.assertEqual(
                rendered["endpoints"][0]["method"],
                "PUT",
            )
            self.assertEqual(
                rendered["endpoints"][0]["path"],
                (
                    "/alfresco/api/-default-/public/alfresco/versions/1/"
                    f"nodes/{node_id}"
                ),
            )

            self.assertEqual(rendered["auth"]["type"], "basic")
            self.assertEqual(
                rendered["auth"]["username_env"],
                "ALFRESCO_USER",
            )
            self.assertEqual(
                rendered["auth"]["password_env"],
                "ALFRESCO_PASS",
            )

            # No literal runtime credentials or Authorization material.
            self.assertNotIn("username", rendered["auth"])
            self.assertNotIn("password", rendered["auth"])
            self.assertNotIn("Authorization", rendered_text)
            self.assertNotIn("Basic ", rendered_text)
            self.assertNotIn("Bearer ", rendered_text)

        after = template.read_bytes()
        after_hash = hashlib.sha256(after).hexdigest()

        self.assertEqual(after, before)
        self.assertEqual(after_hash, before_hash)

class RunnerBootstrapTest(unittest.TestCase):
    def test_approved_runner_module_exists(self) -> None:
        self.assertTrue(RUNNER_PATH.is_file(), f"missing runner: {RUNNER_PATH}")


class MultipartProfileTest(unittest.TestCase):
    def test_multipart_profile_declares_creating_upload_contract(self) -> None:
        profile_path = REPO_ROOT / "targets" / "alfresco_multipart_upload.json"
        self.assertTrue(profile_path.is_file(), f"missing profile: {profile_path}")
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        self.assertEqual(profile["scenario"], "multipart_upload")
        self.assertEqual(profile["method"], "POST")
        self.assertEqual(profile["input_format"], "full_http_multipart")
        self.assertEqual(profile["target_kind"], "creating_upload")
        self.assertEqual(profile["readback"], "created_node_content")
        self.assertEqual(
            profile["endpoint"],
            "/alfresco/api/-default-/public/alfresco/versions/1/nodes/-my-/children",
        )

    def test_multipart_task_payload_preserves_scenario_contract(self) -> None:
        module = _load_runner_module("multipart_profile_task_test")
        with self.subTest("scenario fields"):
            payload = module.build_task_payload(
                Path("/tmp/multipart-seeds"),
                max_test_cases=3,
                time_budget=30,
                scenario="multipart_upload",
                input_format="full_http_multipart",
                parent_node_id="parent-1",
            )
            self.assertEqual(payload["scenario"], "multipart_upload")
            self.assertEqual(payload["input_format"], "full_http_multipart")
            self.assertEqual(payload["target_kind"], "creating_upload")
            self.assertEqual(payload["target_endpoint"], "multipart_upload")
            self.assertEqual(payload["parent_node_id"], "parent-1")
            self.assertEqual(payload["enable_validity"], 0)
            self.assertEqual(payload["readback"], "created_node_content")


def _load_runner_module(name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("RUNNER_MODULE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MultipartRunnerWiringTest(unittest.TestCase):
    def test_multipart_task_selects_stdin_harness_without_legacy_target_lookup(self) -> None:
        module = _load_runner_module("multipart_runner_wiring_test")
        command = module.build_harness_command_for_scenario(
            {"scenario": "multipart_upload", "input_format": "full_http_multipart"}
        )
        self.assertEqual(command[-1], str(module.HARNESS_PATH))
        self.assertNotIn("@@", command)

    def test_multipart_runtime_config_binds_parent_not_fixed_target(self) -> None:
        module = _load_runner_module("multipart_runtime_config_test")
        with tempfile.TemporaryDirectory(prefix="multipart-config-") as tmp:
            output = Path(tmp) / "target.json"
            module.render_multipart_runtime_config("parent-1", output)
            config = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(config["scenario"], "multipart_upload")
        self.assertEqual(config["parent_node_id"], "parent-1")
        self.assertEqual(config["endpoints"][0]["name"], "multipart_upload")
        self.assertEqual(config["endpoints"][0]["method"], "POST")
        self.assertEqual(config["endpoints"][0]["path"], "/alfresco/api/-default-/public/alfresco/versions/1/nodes/parent-1/children")

    def test_multipart_scenario_requires_manifest_authority(self) -> None:
        module = _load_runner_module("multipart_manifest_required_test")
        original_user = os.environ.get("ALFRESCO_USER")
        original_pass = os.environ.get("ALFRESCO_PASS")
        os.environ["ALFRESCO_USER"] = "u"
        os.environ["ALFRESCO_PASS"] = "p"
        try:
            with tempfile.TemporaryDirectory(prefix="multipart-no-manifest-") as tmp:
                rc = module.main([
                    "--scenario", "multipart_upload",
                    "--run-root", str(Path(tmp) / "run"),
                ])
                self.assertEqual(rc, 2)
        finally:
            if original_user is None:
                os.environ.pop("ALFRESCO_USER", None)
            else:
                os.environ["ALFRESCO_USER"] = original_user
            if original_pass is None:
                os.environ.pop("ALFRESCO_PASS", None)
            else:
                os.environ["ALFRESCO_PASS"] = original_pass

    def test_multipart_artifact_contract_requires_upload_record(self) -> None:
        module = _load_runner_module("multipart_artifact_contract_test")
        with tempfile.TemporaryDirectory(prefix="multipart-artifact-") as tmp:
            layout = module.build_run_layout(Path(tmp) / "run", REPO_ROOT)
            Path(layout["multipart_uploads"]).parent.mkdir(parents=True)
            Path(layout["multipart_uploads"]).touch()
            report = module.inspect_multipart_artifacts(layout, launch_returncode=0)
        self.assertFalse(report["ok"])
        self.assertIn("multipart_successful_upload", report["missing_required"])

    def test_multipart_readback_artifact_is_required_for_success(self) -> None:
        module = _load_runner_module("multipart_readback_artifact_contract_test")
        with tempfile.TemporaryDirectory(prefix="multipart-readback-artifact-") as tmp:
            layout = module.build_run_layout(Path(tmp) / "run", REPO_ROOT)
            Path(layout["multipart_uploads"]).parent.mkdir(parents=True)
            Path(layout["multipart_uploads"]).write_text(
                json.dumps({
                    "target_invoked": True,
                    "status_observed": True,
                    "http_status": 201,
                    "exec_seq": 1,
                    "response_node_id": "node-1",
                    "parent_node_id": "parent-1",
                    "uploaded_name": "sample.txt",
                    "file_size": 6,
                    "file_sha256": "sha256:" + hashlib.sha256(b"hello\n").hexdigest(),
                }) + "\n",
                encoding="utf-8",
            )
            report = module.inspect_multipart_artifacts(layout, launch_returncode=0)
            self.assertTrue(report["ok"])
            self.assertEqual(report["successful_uploads"], 1)
            self.assertNotIn("body_valid_stats", report["missing_required"])
            task = {"scenario": "multipart_upload"}
            (Path(tmp) / "run" / "task.json").write_text(json.dumps(task), encoding="utf-8")
            contract = module.artifact_contract(layout)
            self.assertNotIn("body_valid_stats", contract["execution_required"])
            self.assertFalse(module.multipart_readback_is_complete(layout, report))


class MultipartMutatorContractTest(unittest.TestCase):
    def test_multipart_mutator_preserves_parseable_envelope(self) -> None:
        import nv_json_mutator

        original_getenv = nv_json_mutator._live_getenv
        original_random = nv_json_mutator.random
        original_used = os.environ.get("NV_JSON_ARM_USED")
        used_arm = None
        try:
            nv_json_mutator._live_getenv = lambda name, default="": {
                "NV_MULTIPART_MODE": "1",
                "NV_CUR_ARM": "0",
            }.get(name, default)
            os.environ.pop("NV_JSON_ARM_USED", None)
            nv_json_mutator.random.seed(2)
            mutated = nv_json_mutator.afl_custom_fuzz(
                None, MultipartParserTest.VALID_SEED, None, 10000
            )
            used_arm = os.environ.get("NV_JSON_ARM_USED")
        finally:
            nv_json_mutator._live_getenv = original_getenv
            nv_json_mutator.random = original_random
            if original_used is None:
                os.environ.pop("NV_JSON_ARM_USED", None)
            else:
                os.environ["NV_JSON_ARM_USED"] = original_used

        import nv_http_harness
        parsed = nv_http_harness.parse_multipart_http_seed(mutated)
        self.assertEqual(nv_json_mutator._get_arm(), 0)
        self.assertEqual(used_arm, "0")
        self.assertEqual(parsed["filename"], "sample.txt")
        self.assertEqual(parsed["fields"]["nodeType"], "cm:content")
        self.assertTrue(parsed["file_bytes"])

    def test_boundary_arm_changes_header_and_delimiters_consistently(self) -> None:
        import nv_json_mutator

        original_getenv = nv_json_mutator._live_getenv
        try:
            nv_json_mutator._live_getenv = lambda name, default="": {
                "NV_MULTIPART_MODE": "1",
                "NV_CUR_ARM": "1",
            }.get(name, default)
            nv_json_mutator.random.seed(3)
            mutated = nv_json_mutator.afl_custom_fuzz(
                None, MultipartParserTest.VALID_SEED, None, 10000
            )
        finally:
            nv_json_mutator._live_getenv = original_getenv

        import nv_http_harness
        parsed = nv_http_harness.parse_multipart_http_seed(mutated)
        self.assertNotEqual(parsed["boundary"], "nv-boundary")
        self.assertNotIn(b"--nv-boundary\r\n", mutated)
        self.assertNotIn(b"--nv-boundary--", mutated)
        self.assertIn((b"--" + parsed["boundary"].encode("ascii")), mutated)

    def test_structure_arm_adds_a_valid_optional_part(self) -> None:
        import nv_json_mutator

        original_getenv = nv_json_mutator._live_getenv
        try:
            nv_json_mutator._live_getenv = lambda name, default="": {
                "NV_MULTIPART_MODE": "1",
                "NV_CUR_ARM": "2",
            }.get(name, default)
            nv_json_mutator.random.seed(4)
            mutated = nv_json_mutator.afl_custom_fuzz(
                None, MultipartParserTest.VALID_SEED, None, 10000
            )
        finally:
            nv_json_mutator._live_getenv = original_getenv

        import nv_http_harness
        parsed = nv_http_harness.parse_multipart_http_seed(mutated)
        self.assertEqual(parsed["fields"].get("description"), "nv-structure")
        self.assertEqual(parsed["fields"]["nodeType"], "cm:content")
        self.assertEqual(parsed["filename"], "sample.txt")


class MultipartParserTest(unittest.TestCase):
    VALID_SEED = (
        b"POST /alfresco/api/-default-/public/alfresco/versions/1/nodes/-my-/children HTTP/1.1\r\n"
        b"Host: 127.0.0.1:8080\r\n"
        b"Content-Type: multipart/form-data; boundary=nv-boundary\r\n"
        b"\r\n"
        b"--nv-boundary\r\n"
        b'Content-Disposition: form-data; name="name"\r\n\r\n'
        b"sample.txt\r\n"
        b"--nv-boundary\r\n"
        b'Content-Disposition: form-data; name="nodeType"\r\n\r\n'
        b"cm:content\r\n"
        b"--nv-boundary\r\n"
        b'Content-Disposition: form-data; name="filedata"; filename="sample.txt"\r\n'
        b"Content-Type: text/plain\r\n\r\n"
        b"hello\n"
        b"\r\n--nv-boundary--\r\n"
    )

    def test_valid_multipart_seed_is_parsed_without_decoding_file_bytes(self) -> None:
        import nv_http_harness

        parsed = nv_http_harness.parse_multipart_http_seed(self.VALID_SEED)
        self.assertEqual(parsed["method"], "POST")
        self.assertEqual(parsed["path"], "/alfresco/api/-default-/public/alfresco/versions/1/nodes/-my-/children")
        self.assertEqual(parsed["boundary"], "nv-boundary")
        self.assertEqual(parsed["fields"]["name"], "sample.txt")
        self.assertEqual(parsed["fields"]["nodeType"], "cm:content")
        self.assertEqual(parsed["filename"], "sample.txt")
        self.assertEqual(parsed["file_bytes"], b"hello\n")

    def test_boundary_mismatch_is_rejected_fail_closed(self) -> None:
        import nv_http_harness

        seed = self.VALID_SEED.replace(b"--nv-boundary\r\n", b"--other-boundary\r\n", 1)
        with self.assertRaises(ValueError):
            nv_http_harness.parse_multipart_http_seed(seed)

    def test_missing_filedata_is_rejected(self) -> None:
        import nv_http_harness

        seed = self.VALID_SEED.replace(
            b'Content-Disposition: form-data; name="filedata"; filename="sample.txt"\r\n'
            b"Content-Type: text/plain\r\n\r\nhello\n\r\n",
            b"",
        )
        with self.assertRaises(ValueError):
            nv_http_harness.parse_multipart_http_seed(seed)

    def test_duplicate_filedata_is_rejected(self) -> None:
        import nv_http_harness

        duplicate = self.VALID_SEED.replace(
            b"--nv-boundary--\r\n",
            b"--nv-boundary\r\n"
            b'Content-Disposition: form-data; name="filedata"; filename="second.txt"\r\n'
            b"\r\nsecond\r\n"
            b"--nv-boundary--\r\n",
        )
        with self.assertRaises(ValueError):
            nv_http_harness.parse_multipart_http_seed(duplicate)

    def test_unsafe_filename_is_rejected(self) -> None:
        import nv_http_harness

        seed = self.VALID_SEED.replace(b'filename="sample.txt"', b'filename="../evil.txt"')
        with self.assertRaises(ValueError):
            nv_http_harness.parse_multipart_http_seed(seed)


class MultipartHarnessTest(unittest.TestCase):
    def _seed(self, content=b"hello\n"):
        return MultipartParserTest.VALID_SEED.replace(b"hello\n", content)

    def test_successful_upload_requires_status_identity_and_exec_seq(self) -> None:
        import nv_http_harness

        class FakeClient:
            def __init__(self):
                self.calls = []

            def upload_multipart(self, *, fields, filename, file_bytes):
                self.calls.append((fields, filename, file_bytes))
                return {"status": 201, "body": {"entry": {"id": "node-1", "name": "sample.txt"}}}

        statuses = []
        client = FakeClient()
        result = nv_http_harness.run_multipart_seed(
            self._seed(),
            client=client,
            status_writer=lambda **kwargs: statuses.append(kwargs) or {"exec_seq": 7},
        )
        self.assertEqual(result["http_status"], 201)
        self.assertTrue(result["target_invoked"])
        self.assertEqual(result["response_node_id"], "node-1")
        self.assertEqual(result["exec_seq"], 7)
        self.assertEqual(result["file_size"], len(b"hello\n"))
        self.assertTrue(result["file_sha256"].startswith("sha256:"))
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(statuses), 1)

    def test_validation_reject_never_calls_upload_client(self) -> None:
        import nv_http_harness

        class FakeClient:
            def __init__(self):
                self.calls = 0

            def upload_multipart(self, **kwargs):
                self.calls += 1
                raise AssertionError("validation reject must not upload")

        client = FakeClient()
        result = nv_http_harness.run_multipart_seed(
            self._seed(b""),
            client=client,
            status_writer=lambda **kwargs: {"exec_seq": 8},
        )
        self.assertTrue(result["validation_reject"])
        self.assertFalse(result["target_invoked"])
        self.assertEqual(result["http_status"], 0)
        self.assertEqual(client.calls, 0)

    def test_multipart_success_writes_upload_record_with_identity(self) -> None:
        import nv_http_harness

        class FakeClient:
            def upload_multipart(self, **kwargs):
                return {"status": 201, "body": {"entry": {"id": "node-1", "name": "sample.txt"}}}

        with tempfile.TemporaryDirectory(prefix="multipart-record-") as tmp:
            record_path = Path(tmp) / "multipart_uploads.jsonl"
            original_record_path = os.environ.get("NV_MULTIPART_UPLOADS_PATH")
            os.environ["NV_MULTIPART_UPLOADS_PATH"] = str(record_path)
            try:
                result = nv_http_harness.run_multipart_seed(
                    self._seed(),
                    client=FakeClient(),
                    status_writer=lambda **kwargs: {"exec_seq": 7},
                )
            finally:
                if original_record_path is None:
                    os.environ.pop("NV_MULTIPART_UPLOADS_PATH", None)
                else:
                    os.environ["NV_MULTIPART_UPLOADS_PATH"] = original_record_path
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(record["response_node_id"], "node-1")
            self.assertEqual(record["uploaded_name"], "sample.txt")
            self.assertEqual(record["exec_seq"], 7)
            self.assertEqual(record["file_size"], len(b"hello\n"))

    def test_multipart_validation_reject_writes_non_target_status(self) -> None:
        import nv_http_harness

        statuses = []
        result = nv_http_harness.run_multipart_seed(
            self._seed(b""),
            client=object(),
            status_writer=lambda **kwargs: statuses.append(kwargs) or {"exec_seq": 8},
        )
        self.assertTrue(result["validation_reject"])
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0]["validation_reject"], 1)
        self.assertEqual(statuses[0]["http_code"], 0)

    def test_upload_http_error_records_terminal_status_without_fake_success(self) -> None:
        import nv_http_harness

        class FakeClient:
            def upload_multipart(self, **kwargs):
                return {"status": 409, "body": {"error": "duplicate"}}

        statuses = []
        result = nv_http_harness.run_multipart_seed(
            self._seed(),
            client=FakeClient(),
            status_writer=lambda **kwargs: statuses.append(kwargs) or {"exec_seq": 9},
        )
        self.assertEqual(result["http_status"], 409)
        self.assertTrue(result["target_invoked"])
        self.assertTrue(result["status_observed"])
        self.assertEqual(result["response_node_id"], "")
        self.assertEqual(statuses[0]["http_code"], 409)
        self.assertEqual(statuses[0]["validation_reject"], 0)

    def test_success_record_uses_server_name_when_auto_renamed(self) -> None:
        import nv_http_harness

        class FakeClient:
            def upload_multipart(self, **kwargs):
                return {
                    "status": 201,
                    "body": {"entry": {"id": "node-2", "name": "sample-1.txt"}},
                }

        with tempfile.TemporaryDirectory(prefix="multipart-server-name-") as tmp:
            record_path = Path(tmp) / "uploads.jsonl"
            original = os.environ.get("NV_MULTIPART_UPLOADS_PATH")
            os.environ["NV_MULTIPART_UPLOADS_PATH"] = str(record_path)
            try:
                result = nv_http_harness.run_multipart_seed(
                    self._seed(),
                    client=FakeClient(),
                    status_writer=lambda **kwargs: {"exec_seq": 10},
                )
            finally:
                if original is None:
                    os.environ.pop("NV_MULTIPART_UPLOADS_PATH", None)
                else:
                    os.environ["NV_MULTIPART_UPLOADS_PATH"] = original
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(result["response_node_id"], "node-2")
            self.assertEqual(record["uploaded_name"], "sample-1.txt")

    def test_default_status_writer_returns_execution_identity(self) -> None:
        import nv_http_harness

        original_status = nv_http_harness.STATUS_PATH
        original_seq = nv_http_harness.SEQ
        try:
            with tempfile.TemporaryDirectory(prefix="multipart-status-") as tmp:
                nv_http_harness.STATUS_PATH = str(Path(tmp) / "status.json")
                nv_http_harness.SEQ = 0
                status = nv_http_harness.write_status("POST", "/upload", 201)
                self.assertIsInstance(status, dict)
                self.assertGreater(status["exec_seq"], 0)
                self.assertEqual(status["http_code"], 201)
        finally:
            nv_http_harness.STATUS_PATH = original_status
            nv_http_harness.SEQ = original_seq


class MultipartClientContractTest(unittest.TestCase):
    def test_bounded_runner_exposes_binary_content_readback_adapter(self) -> None:
        module = _load_runner_module("multipart_bounded_client_contract")
        self.assertTrue(hasattr(module, "read_multipart_content_bytes"))


class MultipartReadbackRealFallbackTest(unittest.TestCase):
    def test_real_fallback_reads_exact_bytes_via_urllib_opener(self) -> None:
        """Exercise the non-delegated branch of read_multipart_content_bytes.

        The fake client deliberately has no get_content_bytes, so production
        code must fall through to its own urllib.request.Request(...) call.
        We do not monkeypatch urllib itself -- only client.opener is fake --
        so this fails with a bare NameError on unfixed source.
        """

        module = _load_runner_module("multipart_readback_real_fallback_test")

        expected_bytes = b"real content bytes\n"

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def getcode(self):
                return 200

            def read(self):
                return expected_bytes

        class FakeOpener:
            def open(self, request, timeout=None):
                self.last_request = request
                self.last_timeout = timeout
                return FakeResponse()

        class FakeClient:
            base = "https://alfresco.example.test"
            _auth = "Basic dGVzdDp0ZXN0"
            opener = FakeOpener()
            timeout = 30

        content = module.read_multipart_content_bytes(FakeClient(), "node-real-1")
        self.assertEqual(content, expected_bytes)


class MultipartReadbackTest(unittest.TestCase):
    def test_created_upload_readback_requires_identity_and_exact_content(self) -> None:
        module = _load_runner_module("multipart_readback_test")

        class FakeClient:
            def get_node(self, node_id):
                return {
                    "id": node_id,
                    "parentId": "parent-1",
                    "name": "sample.txt",
                }

            def get_content_bytes(self, node_id):
                if node_id != "node-1":
                    raise AssertionError(node_id)
                return b"hello\n"

        records = [{
            "exec_seq": 7,
            "response_node_id": "node-1",
            "parent_node_id": "parent-1",
            "uploaded_name": "sample.txt",
            "file_size": 6,
            "file_sha256": "sha256:" + hashlib.sha256(b"hello\n").hexdigest(),
        }]
        result = module.verify_multipart_readback(FakeClient(), records)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["verified_count"], 1)
        self.assertTrue(result["records"][0]["identity_match"])
        self.assertTrue(result["records"][0]["content_hash_match"])

    def test_created_upload_readback_fails_on_content_mismatch(self) -> None:
        module = _load_runner_module("multipart_readback_mismatch_test")

        class FakeClient:
            def get_node(self, node_id):
                return {"id": node_id, "parentId": "parent-1", "name": "sample.txt"}

            def get_content_bytes(self, node_id):
                return b"different"

        records = [{
            "exec_seq": 7,
            "response_node_id": "node-1",
            "parent_node_id": "parent-1",
            "uploaded_name": "sample.txt",
            "file_size": 6,
            "file_sha256": "sha256:" + hashlib.sha256(b"hello\n").hexdigest(),
        }]
        result = module.verify_multipart_readback(FakeClient(), records)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["records"][0]["content_hash_match"])


class MutationScopeParserTest(unittest.TestCase):
    """Pure --mutation-scope parsing/normalization (Batch 1)."""

    def _load(self):
        return _load_runner_module("mutation_scope_parser_test")

    def test_default_mutation_scope_is_field_value(self) -> None:
        module = self._load()
        self.assertEqual(module.parse_mutation_scope(None), ["field_value"])

    def test_single_allowed_mutation_scope_is_accepted(self) -> None:
        module = self._load()
        self.assertEqual(module.parse_mutation_scope("field_value"), ["field_value"])
        self.assertEqual(module.parse_mutation_scope("boundary"), ["boundary"])
        self.assertEqual(module.parse_mutation_scope("structure"), ["structure"])

    def test_all_three_mutation_scopes_are_accepted(self) -> None:
        module = self._load()
        self.assertEqual(
            module.parse_mutation_scope("field_value,boundary,structure"),
            ["field_value", "boundary", "structure"],
        )

    def test_mutation_scope_is_normalized_deterministically(self) -> None:
        module = self._load()
        self.assertEqual(
            module.parse_mutation_scope("structure,field_value"),
            ["field_value", "structure"],
        )
        self.assertEqual(
            module.parse_mutation_scope("boundary,field_value"),
            ["field_value", "boundary"],
        )
        self.assertEqual(
            module.parse_mutation_scope(" field_value , boundary "),
            ["field_value", "boundary"],
        )

    def test_unknown_mutation_scope_is_rejected(self) -> None:
        module = self._load()
        for bad in ("all", "auto", "random", "any", "FIELD_VALUE", "Boundary", "boundry"):
            with self.assertRaises(ValueError):
                module.parse_mutation_scope(bad)

    def test_duplicate_mutation_scope_is_rejected(self) -> None:
        module = self._load()
        with self.assertRaises(ValueError):
            module.parse_mutation_scope("boundary,boundary")
        with self.assertRaises(ValueError):
            module.parse_mutation_scope("field_value,boundary,field_value")

    def test_empty_mutation_scope_is_rejected(self) -> None:
        module = self._load()
        with self.assertRaises(ValueError):
            module.parse_mutation_scope("")
        with self.assertRaises(ValueError):
            module.parse_mutation_scope(",")
        with self.assertRaises(ValueError):
            module.parse_mutation_scope("   ")

    def test_empty_mutation_scope_element_is_rejected(self) -> None:
        module = self._load()
        with self.assertRaises(ValueError):
            module.parse_mutation_scope("field_value,,boundary")
        with self.assertRaises(ValueError):
            module.parse_mutation_scope("field_value,")
        with self.assertRaises(ValueError):
            module.parse_mutation_scope(",field_value")

    def test_injection_like_mutation_scope_is_rejected(self) -> None:
        module = self._load()
        for bad in (
            "field_value;rm -rf /",
            "field_value\nboundary",
            "$(reboot)",
            "field_value' OR '1'='1",
        ):
            with self.assertRaises(ValueError):
                module.parse_mutation_scope(bad)

    def test_parse_mutation_scope_does_not_touch_environment_or_filesystem(self) -> None:
        module = self._load()
        before = dict(os.environ)
        result = module.parse_mutation_scope("boundary,structure")
        self.assertEqual(os.environ, before)
        self.assertEqual(result, ["boundary", "structure"])
        # Returned list must be a fresh object, not aliased to module state.
        result.append("mutated")
        self.assertEqual(
            module.parse_mutation_scope("boundary,structure"),
            ["boundary", "structure"],
        )


class MutationScopeTaskPayloadTest(unittest.TestCase):
    """build_task_payload must take mutation_scope explicitly (Batch 2)."""

    def _load(self):
        return _load_runner_module("mutation_scope_task_payload_test")

    def test_task_payload_uses_requested_mutation_scope(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="mutation-scope-task-") as tmp:
            seed_dir = Path(tmp) / "seed_input"
            task = module.build_task_payload(
                seed_dir,
                max_test_cases=3,
                time_budget=30,
                mutation_scope=["field_value", "boundary", "structure"],
            )
            self.assertEqual(
                task["mutation_scope"], ["field_value", "boundary", "structure"]
            )

    def test_task_payload_default_scope_remains_field_value(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="mutation-scope-task-default-") as tmp:
            seed_dir = Path(tmp) / "seed_input"
            task = module.build_task_payload(
                seed_dir, max_test_cases=3, time_budget=30
            )
            self.assertEqual(task["mutation_scope"], ["field_value"])

    def test_task_payload_never_contains_unknown_scope(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="mutation-scope-task-unknown-") as tmp:
            seed_dir = Path(tmp) / "seed_input"
            with self.assertRaises(ValueError):
                module.build_task_payload(
                    seed_dir,
                    max_test_cases=3,
                    time_budget=30,
                    mutation_scope=["field_value", "all"],
                )
            with self.assertRaises(ValueError):
                module.build_task_payload(
                    seed_dir,
                    max_test_cases=3,
                    time_budget=30,
                    mutation_scope=[],
                )

    def test_task_payload_scope_is_canonical(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="mutation-scope-task-canonical-") as tmp:
            seed_dir = Path(tmp) / "seed_input"
            task = module.build_task_payload(
                seed_dir,
                max_test_cases=3,
                time_budget=30,
                mutation_scope=["structure", "field_value"],
            )
            self.assertEqual(task["mutation_scope"], ["field_value", "structure"])


class MutationScopeRunnerOrchestrationTest(unittest.TestCase):
    """CLI --mutation-scope must reach task.json through main() (Batch 3 + 5)."""

    _CRED_USER = " u "
    _CRED_PASS = " p "
    _FOLDER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    _FILE_ID = "11111111-2222-3333-4444-555555555555"

    def _load(self):
        return _load_runner_module("mutation_scope_runner_orchestration_test")

    def _set_creds(self):
        original = (
            os.environ.get("ALFRESCO_USER"),
            os.environ.get("ALFRESCO_PASS"),
        )
        os.environ["ALFRESCO_USER"] = self._CRED_USER
        os.environ["ALFRESCO_PASS"] = self._CRED_PASS
        return original

    def _restore_creds(self, original):
        u, p = original
        if u is None:
            os.environ.pop("ALFRESCO_USER", None)
        else:
            os.environ["ALFRESCO_USER"] = u
        if p is None:
            os.environ.pop("ALFRESCO_PASS", None)
        else:
            os.environ["ALFRESCO_PASS"] = p

    def _wire_fake_module(self, module, *, launch):
        folder_id = self._FOLDER_ID
        file_id = self._FILE_ID

        class FakeClient:
            def __init__(self) -> None:
                self.list_calls = []

            def list_children(self, parent_id):
                self.list_calls.append(parent_id)
                if parent_id == "-my-":
                    return [
                        {
                            "id": folder_id,
                            "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                            "isFolder": True,
                            "isFile": False,
                        }
                    ]
                if parent_id == folder_id:
                    return [
                        {
                            "id": file_id,
                            "parentId": folder_id,
                            "name": "nv-afl-levelc-metadata.txt",
                            "isFolder": False,
                            "isFile": True,
                            "aspectNames": ["cm:auditable"],
                        }
                    ]
                raise AssertionError(f"unexpected parent lookup: {parent_id}")

            def create_child(self, *args, **kwargs):
                raise AssertionError("bounded resolver must never create nodes")

        client = FakeClient()
        module.build_alfresco_client = lambda base, credentials: client
        module.perform_preflight = lambda client: {"ok": True}
        module.read_only_target_identity = lambda client, node_id: {
            "id": node_id,
            "parentId": folder_id,
            "name": "nv-afl-levelc-metadata.txt",
        }
        module.launch_bounded_afl = launch
        return client

    def test_main_writes_requested_mutation_scope_to_task_json(self) -> None:
        import contextlib
        import io
        import tempfile

        module = self._load()

        def fake_launch(layout, config_path, child_env, *, max_test_cases, time_budget):
            _materialize_execution_artifacts(layout)
            return 0

        self._wire_fake_module(module, launch=fake_launch)

        orig = self._set_creds()
        try:
            with tempfile.TemporaryDirectory(prefix="mutation-scope-main-") as tmp:
                run_root = Path(tmp).resolve()
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(
                        [
                            "--run-root", str(run_root),
                            "--max-test-cases", "5",
                            "--time-budget", "20",
                            "--mutation-scope", "field_value,boundary,structure",
                        ]
                    )
                self.assertEqual(rc, 0, f"stderr={err.getvalue()!r}")
                task = json.loads(
                    (run_root / "task.json").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    task["mutation_scope"],
                    ["field_value", "boundary", "structure"],
                )
        finally:
            self._restore_creds(orig)

    def test_main_passes_scope_to_fake_launch_environment(self) -> None:
        import contextlib
        import io
        import tempfile

        module = self._load()
        launch_calls: dict = {}

        def fake_launch(layout, config_path, child_env, *, max_test_cases, time_budget):
            launch_calls["task_scope"] = json.loads(
                Path(layout["task"]).read_text(encoding="utf-8")
            )["mutation_scope"]
            launch_calls["nv_task_path"] = child_env.get("NV_TASK_PATH")
            _materialize_execution_artifacts(layout)
            return 0

        self._wire_fake_module(module, launch=fake_launch)

        orig = self._set_creds()
        try:
            with tempfile.TemporaryDirectory(prefix="mutation-scope-main-env-") as tmp:
                run_root = Path(tmp).resolve()
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(
                        ["--run-root", str(run_root), "--mutation-scope", "boundary"]
                    )
                self.assertEqual(rc, 0, f"stderr={err.getvalue()!r}")
                self.assertEqual(launch_calls["task_scope"], ["boundary"])
                self.assertEqual(
                    launch_calls["nv_task_path"], str(run_root / "task.json")
                )
        finally:
            self._restore_creds(orig)

    def test_invalid_scope_blocks_credentials_client_preflight_and_launch(self) -> None:
        import contextlib
        import io

        module = self._load()

        def must_not_build(base, credentials):
            raise AssertionError("client must not be built for invalid scope")

        def must_not_preflight(client):
            raise AssertionError("preflight must not run for invalid scope")

        def must_not_launch(*args, **kwargs):
            raise AssertionError("AFL must not launch for invalid scope")

        module.build_alfresco_client = must_not_build
        module.perform_preflight = must_not_preflight
        module.launch_bounded_afl = must_not_launch

        original_user = os.environ.get("ALFRESCO_USER")
        original_pass = os.environ.get("ALFRESCO_PASS")
        os.environ.pop("ALFRESCO_USER", None)
        os.environ.pop("ALFRESCO_PASS", None)
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = module.main(["--mutation-scope", "all"])
        finally:
            if original_user is None:
                os.environ.pop("ALFRESCO_USER", None)
            else:
                os.environ["ALFRESCO_USER"] = original_user
            if original_pass is None:
                os.environ.pop("ALFRESCO_PASS", None)
            else:
                os.environ["ALFRESCO_PASS"] = original_pass

        self.assertEqual(rc, 2)
        self.assertIn("INVALID_MUTATION_SCOPE", err.getvalue())

    def test_preflight_only_does_not_launch_with_scope_argument(self) -> None:
        import contextlib
        import io

        module = self._load()
        calls: dict = {}

        module.build_alfresco_client = lambda base, credentials: "CLIENT_SENTINEL"
        module.perform_preflight = lambda client: calls.setdefault("preflight", True)

        def must_not_launch(*args, **kwargs):
            raise AssertionError("preflight-only must never launch AFL")

        module.launch_bounded_afl = must_not_launch

        orig = self._set_creds()
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = module.main(
                    ["--preflight-only", "--mutation-scope", "boundary,structure"]
                )
        finally:
            self._restore_creds(orig)

        self.assertEqual(rc, 0, f"stderr={err.getvalue()!r}")
        self.assertTrue(calls.get("preflight"))

    def test_default_main_behavior_remains_field_value_only(self) -> None:
        import contextlib
        import io
        import tempfile

        module = self._load()
        launch_calls: dict = {}

        def fake_launch(layout, config_path, child_env, *, max_test_cases, time_budget):
            launch_calls["task_scope"] = json.loads(
                Path(layout["task"]).read_text(encoding="utf-8")
            )["mutation_scope"]
            _materialize_execution_artifacts(layout)
            return 0

        self._wire_fake_module(module, launch=fake_launch)

        orig = self._set_creds()
        try:
            with tempfile.TemporaryDirectory(
                prefix="mutation-scope-main-default-"
            ) as tmp:
                run_root = Path(tmp).resolve()
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(["--run-root", str(run_root)])
                self.assertEqual(rc, 0, f"stderr={err.getvalue()!r}")
                self.assertEqual(launch_calls["task_scope"], ["field_value"])
        finally:
            self._restore_creds(orig)

    # -- Batch 5: scope changes must stay isolated ---------------------------

    def _run_with_scope(self, scope_arg, bucket, tmp_prefix):
        import contextlib
        import io
        import tempfile

        module = self._load()

        def fake_launch(layout, config_path, child_env, *, max_test_cases, time_budget):
            bucket["task"] = json.loads(
                Path(layout["task"]).read_text(encoding="utf-8")
            )
            bucket["layout"] = {k: str(v) for k, v in layout.items()}
            _materialize_execution_artifacts(layout)
            return 0

        self._wire_fake_module(module, launch=fake_launch)

        orig = self._set_creds()
        try:
            with tempfile.TemporaryDirectory(prefix=tmp_prefix) as tmp:
                run_root = Path(tmp).resolve()
                argv = ["--run-root", str(run_root)]
                if scope_arg is not None:
                    argv += ["--mutation-scope", scope_arg]
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(argv)
                self.assertEqual(rc, 0, f"stderr={err.getvalue()!r}")
        finally:
            self._restore_creds(orig)

    def test_scope_change_only_changes_task_mutation_scope(self) -> None:
        default_bucket: dict = {}
        scoped_bucket: dict = {}
        self._run_with_scope(None, default_bucket, "mutation-scope-isolation-default-")
        self._run_with_scope(
            "field_value,boundary,structure",
            scoped_bucket,
            "mutation-scope-isolation-scoped-",
        )

        default_task = dict(default_bucket["task"])
        scoped_task = dict(scoped_bucket["task"])
        self.assertEqual(default_task["mutation_scope"], ["field_value"])
        self.assertEqual(
            scoped_task["mutation_scope"], ["field_value", "boundary", "structure"]
        )
        # seed_location is run-root-scoped and legitimately differs between
        # the two separate temporary run roots used here; every other field
        # must be identical.
        for key in (
            "target_type", "target_endpoint", "seed_source",
            "max_test_cases", "time_budget", "enable_validity",
        ):
            self.assertEqual(default_task[key], scoped_task[key])

    def test_scope_does_not_change_budget_or_endpoint(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="mutation-scope-budget-") as tmp:
            seed_dir = Path(tmp) / "seed_input"
            base_task = module.build_task_payload(
                seed_dir, max_test_cases=3, time_budget=30
            )
            scoped_task = module.build_task_payload(
                seed_dir,
                max_test_cases=3,
                time_budget=30,
                mutation_scope=["field_value", "boundary", "structure"],
            )
            for key in (
                "target_type", "target_endpoint", "seed_source",
                "seed_location", "max_test_cases", "time_budget",
                "enable_validity",
            ):
                self.assertEqual(base_task[key], scoped_task[key])
            self.assertNotEqual(
                base_task["mutation_scope"], scoped_task["mutation_scope"]
            )

    def test_scope_does_not_change_run_scoped_paths(self) -> None:
        default_bucket: dict = {}
        scoped_bucket: dict = {}
        self._run_with_scope(None, default_bucket, "mutation-scope-paths-default-")
        self._run_with_scope(
            "boundary,structure", scoped_bucket, "mutation-scope-paths-scoped-"
        )

        default_layout = default_bucket["layout"]
        scoped_layout = scoped_bucket["layout"]
        for key in (
            "status", "probe", "state_db", "ctx", "err_dir", "state_trace",
            "body_valid_stats", "mab_journal", "seed_selection_audit", "readback",
        ):
            self.assertEqual(
                Path(default_layout[key]).name, Path(scoped_layout[key]).name
            )

    def test_scope_is_not_read_from_environment(self) -> None:
        import contextlib
        import io
        import tempfile

        module = self._load()
        launch_calls: dict = {}

        def fake_launch(layout, config_path, child_env, *, max_test_cases, time_budget):
            launch_calls["task_scope"] = json.loads(
                Path(layout["task"]).read_text(encoding="utf-8")
            )["mutation_scope"]
            _materialize_execution_artifacts(layout)
            return 0

        self._wire_fake_module(module, launch=fake_launch)

        env_backup = (
            os.environ.get("MUTATION_SCOPE"),
            os.environ.get("NV_MUTATION_SCOPE"),
        )
        os.environ["MUTATION_SCOPE"] = "boundary,structure"
        os.environ["NV_MUTATION_SCOPE"] = "boundary,structure"
        orig = self._set_creds()
        try:
            with tempfile.TemporaryDirectory(
                prefix="mutation-scope-env-isolation-"
            ) as tmp:
                run_root = Path(tmp).resolve()
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(["--run-root", str(run_root)])
                self.assertEqual(rc, 0, f"stderr={err.getvalue()!r}")
                self.assertEqual(launch_calls["task_scope"], ["field_value"])
        finally:
            self._restore_creds(orig)
            if env_backup[0] is None:
                os.environ.pop("MUTATION_SCOPE", None)
            else:
                os.environ["MUTATION_SCOPE"] = env_backup[0]
            if env_backup[1] is None:
                os.environ.pop("NV_MUTATION_SCOPE", None)
            else:
                os.environ["NV_MUTATION_SCOPE"] = env_backup[1]


class RunScopedArtifactTest(unittest.TestCase):
    def test_run_root_inside_git_worktree_is_rejected(self) -> None:
        """Runtime artifacts must never be placed inside the Git worktree."""

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bounded_runner_run_guard_test",
            RUNNER_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        repo_root = REPO_ROOT.resolve()

        rejected = [
            repo_root,
            repo_root / "out",
            repo_root / ".runtime" / "alfresco-feedback",
        ]

        for run_root in rejected:
            with self.subTest(run_root=run_root):
                with self.assertRaisesRegex(
                    ValueError,
                    "^RUN_ROOT_INSIDE_GIT_WORKTREE$",
                ):
                    module.build_run_layout(run_root, repo_root)

    def test_single_arm_launch_requires_execution_ledger(self) -> None:
        module = _load_runner_module("single_arm_ledger_required_test")
        import tempfile

        with tempfile.TemporaryDirectory(prefix="single-arm-ledger-required-") as tmp:
            layout = module.build_run_layout(Path(tmp) / "run", REPO_ROOT)
            _materialize_execution_artifacts(layout)
            layout["target_config"].write_text("{}", encoding="utf-8")
            layout["task"].write_text(
                json.dumps({"mutation_scope": ["field_value"]}), encoding="utf-8"
            )
            layout["seed_dir"].mkdir(parents=True, exist_ok=True)
            layout["seed"].write_bytes(b"PUT /offline HTTP/1.1\\r\\n\\r\\n{}")
            layout["err_dir"].mkdir(parents=True, exist_ok=True)
            layout["evidence"] .joinpath("executions.jsonl").unlink()

            report = module.inspect_artifacts(layout, launch_returncode=0)

            self.assertTrue(report["execution_ledger"]["required"])
            self.assertIn("execution_ledger", report["missing_required"])
            self.assertEqual(report["final_result"], "artifact_contract_failed")
            self.assertFalse(report["execution_proved"])

    def test_single_arm_launch_reconciles_execution_ledger(self) -> None:
        module = _load_runner_module("single_arm_ledger_reconciled_test")
        import tempfile

        with tempfile.TemporaryDirectory(prefix="single-arm-ledger-reconciled-") as tmp:
            layout = module.build_run_layout(Path(tmp) / "run", REPO_ROOT)
            _materialize_execution_artifacts(layout)
            layout["target_config"].write_text("{}", encoding="utf-8")
            layout["task"].write_text(
                json.dumps({"mutation_scope": ["field_value"]}), encoding="utf-8"
            )
            layout["seed_dir"].mkdir(parents=True, exist_ok=True)
            layout["seed"].write_bytes(b"PUT /offline HTTP/1.1\\r\\n\\r\\n{}")
            layout["err_dir"].mkdir(parents=True, exist_ok=True)

            report = module.inspect_artifacts(layout, launch_returncode=0)

            self.assertTrue(report["execution_ledger"]["required"])
            self.assertTrue(report["execution_ledger"]["present"])
            self.assertTrue(report["execution_ledger"]["reconciled"])
            self.assertEqual(report["final_result"], "pass")

    def test_runtime_artifacts_are_planned_outside_git_worktree(self) -> None:
        """Rendered config, seed, status, AFL output, and evidence stay outside Git."""

        import importlib.util
        import tempfile

        spec = importlib.util.spec_from_file_location(
            "bounded_runner_run_layout_test",
            RUNNER_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertTrue(
            hasattr(module, "build_run_layout"),
            "runner must provide build_run_layout()",
        )

        with tempfile.TemporaryDirectory(prefix="alfresco-bounded-run-") as tmp:
            run_root = Path(tmp).resolve()
            repo_root = REPO_ROOT.resolve()

            layout = module.build_run_layout(run_root, repo_root)

            expected_keys = {
                "run_root", "target_config", "task", "seed_dir", "seed",
                "status", "status_seq", "probe", "state_db", "ctx",
                "err_dir", "state_trace", "body_valid_stats", "afl_output",
                "evidence", "readback", "multipart_readback", "multipart_uploads",
                "mab_journal", "seed_selection_audit",
            }
            self.assertEqual(set(layout), expected_keys)

            self.assertEqual(layout["run_root"], run_root)
            self.assertEqual(layout["target_config"], run_root / "target.json")
            self.assertEqual(layout["task"], run_root / "task.json")
            self.assertEqual(layout["seed_dir"], run_root / "seed_input")
            self.assertEqual(layout["seed"], run_root / "seed_input" / "seed.http")
            self.assertEqual(layout["status"], run_root / "nv_http_status.json")
            self.assertEqual(layout["status_seq"], run_root / "nv_http_status.json.seq")
            self.assertEqual(layout["probe"], run_root / "nv_probe.json")
            self.assertEqual(layout["state_db"], run_root / "nv_state_db.json")
            self.assertEqual(layout["ctx"], run_root / "nv_ctx.json")
            self.assertEqual(layout["err_dir"], run_root / "err_cases")
            self.assertEqual(layout["state_trace"], run_root / "nv_state_trace.jsonl")
            self.assertEqual(
                layout["mab_journal"],
                run_root / "evidence" / "mab_updates.jsonl",
            )
            self.assertEqual(
                layout["seed_selection_audit"],
                run_root / "evidence" / "seed_selection.jsonl",
            )
            self.assertEqual(layout["readback"], run_root / "evidence" / "readback.json")
            self.assertEqual(layout["multipart_readback"], run_root / "evidence" / "multipart_readback.json")
            self.assertEqual(layout["multipart_uploads"], run_root / "evidence" / "multipart_uploads.jsonl")
            self.assertEqual(layout["body_valid_stats"], run_root / "nv_body_valid_stats.json")
            self.assertEqual(layout["afl_output"], run_root / "afl-out")
            self.assertEqual(layout["evidence"], run_root / "evidence")

            for name, path in layout.items():
                with self.subTest(name=name, path=path):
                    resolved = Path(path).resolve()

                    self.assertTrue(
                        resolved == run_root or resolved.is_relative_to(run_root),
                        f"{name} escaped run root: {resolved}",
                    )

                    self.assertFalse(
                        resolved == repo_root or resolved.is_relative_to(repo_root),
                        f"{name} must not live inside Git worktree: {resolved}",
                    )

class LoopbackTargetPolicyTest(unittest.TestCase):
    def test_only_exact_local_alfresco_base_url_is_allowed(self) -> None:
        """The bounded runner is pinned to one exact owner-controlled endpoint."""

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bounded_runner_target_policy_test",
            RUNNER_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertTrue(
            hasattr(module, "validate_base_url"),
            "runner must provide validate_base_url()",
        )

        expected = "http://127.0.0.1:8080"

        self.assertEqual(
            module.validate_base_url(expected),
            expected,
        )

        rejected = [
            "http://localhost:8080",
            "http://127.0.0.1",
            "http://127.0.0.1:8888",
            "https://127.0.0.1:8080",
            "http://127.0.0.2:8080",
            "http://0.0.0.0:8080",
            "http://example.invalid:8080",
            "http://127.0.0.1:8080/",
            " http://127.0.0.1:8080",
        ]

        for value in rejected:
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    "^INVALID_ALFRESCO_BASE_URL$",
                ):
                    module.validate_base_url(value)

class ProxyIsolationTest(unittest.TestCase):
    def test_child_environment_removes_ambient_proxies_and_forces_loopback_bypass(
        self,
    ) -> None:
        """Child processes must never inherit ambient proxy routing."""

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bounded_runner_proxy_test",
            RUNNER_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        source = {
            "PATH": "/usr/bin",
            "HOME": "/tmp/example-home",
            "ALFRESCO_USER": " user-preserve ",
            "ALFRESCO_PASS": " pass-preserve ",
            "http_proxy": "http://proxy.invalid:18080",
            "https_proxy": "http://proxy.invalid:18443",
            "HTTP_PROXY": "http://proxy.invalid:28080",
            "HTTPS_PROXY": "http://proxy.invalid:28443",
            "all_proxy": "socks5://proxy.invalid:19090",
            "ALL_PROXY": "socks5://proxy.invalid:29090",
            "no_proxy": "127.*,example.invalid",
            "NO_PROXY": "old.example.invalid",
        }

        original = dict(source)

        self.assertTrue(
            hasattr(module, "sanitized_child_env"),
            "runner must provide sanitized_child_env()",
        )

        child = module.sanitized_child_env(source)

        for key in (
            "http_proxy",
            "https_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "all_proxy",
            "ALL_PROXY",
        ):
            self.assertNotIn(key, child)

        self.assertEqual(child["no_proxy"], "127.0.0.1,localhost")
        self.assertEqual(child["NO_PROXY"], "127.0.0.1,localhost")

        # Unrelated values and credentials are passed through byte-for-byte
        # as Python text; sanitisation must not trim or rewrite them.
        self.assertEqual(child["PATH"], "/usr/bin")
        self.assertEqual(child["HOME"], "/tmp/example-home")
        self.assertEqual(child["ALFRESCO_USER"], " user-preserve ")
        self.assertEqual(child["ALFRESCO_PASS"], " pass-preserve ")

        # A helper that unexpectedly mutates its caller's environment mapping
        # would make later audit reasoning much harder.
        self.assertEqual(source, original)

class CredentialFailClosedTest(unittest.TestCase):
    def test_missing_runtime_credentials_abort_before_work(self) -> None:
        """Missing Alfresco credentials must fail closed immediately."""

        env = os.environ.copy()

        # This RED test must not inherit real service credentials.
        env.pop("ALFRESCO_USER", None)
        env.pop("ALFRESCO_PASS", None)

        # Keep the test independent of the machine's ambient proxy state.
        for key in (
            "http_proxy",
            "https_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "all_proxy",
            "ALL_PROXY",
        ):
            env.pop(key, None)

        env["PYTHONDONTWRITEBYTECODE"] = "1"

        proc = subprocess.run(
            [
                sys.executable,
                str(RUNNER_PATH),
                "--preflight-only",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        combined = proc.stdout + proc.stderr

        self.assertEqual(
            proc.returncode,
            2,
            f"missing credentials must fail closed; output={combined!r}",
        )
        self.assertIn("MISSING_RUNTIME_CREDENTIALS", combined)

    def test_whitespace_runtime_credentials_abort_before_work(self) -> None:
        """Whitespace-only credentials are not valid runtime credentials."""

        cases = [
            ("   ", "password-sentinel"),
            ("user-sentinel", "\t  \n"),
            ("   ", "\t"),
        ]

        for user, password in cases:
            with self.subTest(user=user, password=password):
                env = os.environ.copy()

                for key in (
                    "http_proxy",
                    "https_proxy",
                    "HTTP_PROXY",
                    "HTTPS_PROXY",
                    "all_proxy",
                    "ALL_PROXY",
                ):
                    env.pop(key, None)

                env["ALFRESCO_USER"] = user
                env["ALFRESCO_PASS"] = password
                env["PYTHONDONTWRITEBYTECODE"] = "1"

                proc = subprocess.run(
                    [
                        sys.executable,
                        str(RUNNER_PATH),
                        "--preflight-only",
                    ],
                    cwd=REPO_ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )

                combined = proc.stdout + proc.stderr

                self.assertEqual(
                    proc.returncode,
                    2,
                    f"whitespace credential must fail closed; output={combined!r}",
                )
                self.assertIn("MISSING_RUNTIME_CREDENTIALS", combined)

                # Error reporting must never echo the supplied values.
                self.assertNotIn("password-sentinel", combined)
                self.assertNotIn("user-sentinel", combined)
    def test_nonblank_runtime_credentials_preserve_exact_bytes_as_text(self) -> None:
        """Valid credentials are checked for blankness but are not stripped."""

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bounded_runner",
            RUNNER_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        original_user = os.environ.get("ALFRESCO_USER")
        original_pass = os.environ.get("ALFRESCO_PASS")

        try:
            os.environ["ALFRESCO_USER"] = " user-with-spaces "
            os.environ["ALFRESCO_PASS"] = " pass-with-spaces "

            user, password = module.runtime_credentials()

            self.assertEqual(user, " user-with-spaces ")
            self.assertEqual(password, " pass-with-spaces ")
        finally:
            if original_user is None:
                os.environ.pop("ALFRESCO_USER", None)
            else:
                os.environ["ALFRESCO_USER"] = original_user

            if original_pass is None:
                os.environ.pop("ALFRESCO_PASS", None)
            else:
                os.environ["ALFRESCO_PASS"] = original_pass


class BoundedRunnerOrchestrationTest(unittest.TestCase):
    """main() must wire a real, bounded-run orchestration.

    These tests drive the missing main() behaviour.  Every side effect that
    would contact real Alfresco or spawn real afl-fuzz is replaced with an
    injectable module-level collaborator (build_alfresco_client /
    perform_preflight / launch_bounded_afl), so the suite stays fully offline.
    """

    _CRED_USER = " u "
    _CRED_PASS = " p "

    def _load(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bounded_runner_orchestration_test", RUNNER_PATH
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _set_creds(self):
        original = (
            os.environ.get("ALFRESCO_USER"),
            os.environ.get("ALFRESCO_PASS"),
        )
        os.environ["ALFRESCO_USER"] = self._CRED_USER
        os.environ["ALFRESCO_PASS"] = self._CRED_PASS
        return original

    def _restore_creds(self, original):
        u, p = original
        if u is None:
            os.environ.pop("ALFRESCO_USER", None)
        else:
            os.environ["ALFRESCO_USER"] = u
        if p is None:
            os.environ.pop("ALFRESCO_PASS", None)
        else:
            os.environ["ALFRESCO_PASS"] = p

    # -- preflight-only path -------------------------------------------------
    def test_preflight_only_calls_preflight_and_returns_zero_on_success(self) -> None:
        import contextlib
        import io

        module = self._load()

        calls: dict = {}

        def fake_build(base, credentials):
            calls["build"] = (base, tuple(credentials))
            return "CLIENT_SENTINEL"

        def fake_preflight(client):
            calls["preflight"] = client
            return {"authenticated_root": 200}

        module.build_alfresco_client = fake_build
        module.perform_preflight = fake_preflight

        orig = self._set_creds()
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = module.main(["--preflight-only"])
        finally:
            self._restore_creds(orig)

        self.assertEqual(
            rc,
            0,
            f"preflight success must return 0; stderr={err.getvalue()!r}",
        )
        self.assertEqual(
            calls.get("build"),
            ("http://127.0.0.1:8080", (self._CRED_USER, self._CRED_PASS)),
        )
        self.assertEqual(calls.get("preflight"), "CLIENT_SENTINEL")

    def test_preflight_only_returns_distinct_code_on_preflight_failure(self) -> None:
        import contextlib
        import io

        module = self._load()

        def fake_preflight(client):
            raise RuntimeError("PREFLIGHT_GATE_FAILED")

        module.build_alfresco_client = lambda base, credentials: "CLIENT_SENTINEL"
        module.perform_preflight = fake_preflight

        orig = self._set_creds()
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = module.main(["--preflight-only"])
        finally:
            self._restore_creds(orig)

        # Distinct from the credential-failure code (2): a service/preflight
        # failure is its own class of blocker.
        self.assertEqual(rc, 3, f"preflight failure must return 3; stderr={err.getvalue()!r}")
        self.assertIn("PREFLIGHT_GATE_FAILED", err.getvalue())

    def test_missing_credentials_short_circuits_before_client_or_preflight(self) -> None:
        import contextlib
        import io

        module = self._load()

        def must_not_build(base, credentials):
            raise AssertionError("client must not be built when credentials are missing")

        def must_not_preflight(client):
            raise AssertionError("preflight must not run when credentials are missing")

        module.build_alfresco_client = must_not_build
        module.perform_preflight = must_not_preflight

        env = os.environ.copy()
        env.pop("ALFRESCO_USER", None)
        env.pop("ALFRESCO_PASS", None)

        original_user = os.environ.get("ALFRESCO_USER")
        original_pass = os.environ.get("ALFRESCO_PASS")
        os.environ.pop("ALFRESCO_USER", None)
        os.environ.pop("ALFRESCO_PASS", None)
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = module.main(["--preflight-only"])
        finally:
            if original_user is None:
                os.environ.pop("ALFRESCO_USER", None)
            else:
                os.environ["ALFRESCO_USER"] = original_user
            if original_pass is None:
                os.environ.pop("ALFRESCO_PASS", None)
            else:
                os.environ["ALFRESCO_PASS"] = original_pass

        self.assertEqual(rc, 2)
        self.assertIn("MISSING_RUNTIME_CREDENTIALS", err.getvalue())

    # -- full bounded-run path ----------------------------------------------
    def test_multipart_bounded_run_binds_parent_and_writes_multipart_task(self) -> None:
        import contextlib
        import io

        module = self._load()
        folder_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        client_calls = []
        launch = {}

        class FakeClient:
            def list_children(self, parent_id):
                client_calls.append(("list", parent_id))
                if parent_id == "-my-":
                    return [{
                        "id": folder_id,
                        "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                        "parentId": "-my-",
                        "isFolder": True,
                        "isFile": False,
                    }]
                raise AssertionError(parent_id)

            def get_node(self, node_id):
                if node_id == folder_id:
                    return {
                        "id": folder_id,
                        "parentId": "-my-",
                        "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                    }
                if node_id == "node-1":
                    return {
                        "id": "node-1",
                        "parentId": folder_id,
                        "name": "sample.txt",
                    }
                raise AssertionError(node_id)

            def get_content_bytes(self, node_id):
                if node_id != "node-1":
                    raise AssertionError(node_id)
                return b"hello\n"

        def fake_launch(layout, config_path, child_env, *, max_test_cases, time_budget):
            launch["child_env"] = dict(child_env)
            payload = json.loads(Path(layout["task"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["scenario"], "multipart_upload")
            self.assertEqual(payload["parent_node_id"], folder_id)
            self.assertEqual(payload["target_endpoint"], "multipart_upload")
            self.assertEqual(launch["child_env"]["NV_MULTIPART_MODE"], "1")
            self.assertEqual(json.loads(Path(config_path).read_text(encoding="utf-8"))["parent_node_id"], folder_id)
            _materialize_execution_artifacts(layout)
            stats_path = Path(layout["afl_output"]) / "fuzzer_stats"
            stats_text = stats_path.read_text(encoding="utf-8")
            stats_text = stats_text.replace("ss_selected_sum : 0", "ss_selected_sum : 2")
            stats_text = stats_text.replace("seed_audit_record_count : 0", "seed_audit_record_count : 2")
            stats_text = stats_text.replace("seed_audit_expected_selection_count : 0", "seed_audit_expected_selection_count : 2")
            stats_text += "ss_selected_queue_0 : 1\nss_selected_queue_1 : 1\n"
            stats_path.write_text(stats_text, encoding="utf-8")
            Path(layout["multipart_uploads"]).write_text(
                json.dumps({
                    "target_invoked": True,
                    "status_observed": True,
                    "http_status": 201,
                    "exec_seq": 1,
                    "response_node_id": "node-1",
                    "parent_node_id": folder_id,
                    "uploaded_name": "sample.txt",
                    "file_size": 6,
                    "file_sha256": "sha256:" + hashlib.sha256(b"hello\n").hexdigest(),
                }) + "\n", encoding="utf-8"
            )
            Path(layout["seed_selection_audit"]).write_text(
                json.dumps({"queue_id": 0, "depth": 0, "ss_cov_cnt": 1, "ss_selected_cnt": 1, "ss_prob": 1.0}) + "\n"
                + json.dumps({"queue_id": 1, "depth": 0, "ss_cov_cnt": 1, "ss_selected_cnt": 1, "ss_prob": 1.0}) + "\n",
                encoding="utf-8",
            )
            return 0

        module.build_alfresco_client = lambda base, credentials: FakeClient()
        module.perform_preflight = lambda client: {"ok": True}
        module.launch_bounded_afl = fake_launch
        original = self._set_creds()
        try:
            with tempfile.TemporaryDirectory(prefix="multipart-main-") as tmp:
                source = Path(tmp) / "source"
                source.mkdir()
                seed_body = MultipartParserTest.VALID_SEED
                for name in ("seed-a.http", "seed-b.http", "seed-c.http"):
                    (source / name).write_bytes(seed_body)
                manifest = Path(tmp) / "manifest.txt"
                manifest.write_text("seed-a.http\nseed-b.http\nseed-c.http\n", encoding="utf-8")
                run_root = Path(tmp) / "run"
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main([
                        "--scenario", "multipart_upload",
                        "--run-root", str(run_root),
                        "--seed-manifest", str(manifest),
                        "--seed-source-dir", str(source),
                    ])
                if rc != 0:
                    report_path = run_root / "evidence" / "artifact_report.json"
                    report_text = report_path.read_text(encoding="utf-8") if report_path.is_file() else "<missing report>"
                    self.fail(f"rc={rc}; stderr={err.getvalue()!r}; report={report_text}")
                self.assertEqual(client_calls, [("list", "-my-")])
                task = json.loads((run_root / "task.json").read_text(encoding="utf-8"))
                self.assertEqual(task["scenario"], "multipart_upload")
                self.assertEqual(task["parent_node_id"], folder_id)
        finally:
            self._restore_creds(original)

    def test_bounded_run_wires_resolve_render_env_and_launch(self) -> None:
        import contextlib
        import io
        import tempfile

        module = self._load()

        folder_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        file_id = "11111111-2222-3333-4444-555555555555"

        class FakeClient:
            def __init__(self) -> None:
                self.list_calls = []
                self.create_calls = 0

            def list_children(self, parent_id):
                self.list_calls.append(parent_id)
                if parent_id == "-my-":
                    return [
                        {
                            "id": folder_id,
                            "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                            "isFolder": True,
                            "isFile": False,
                        }
                    ]
                if parent_id == folder_id:
                    return [
                        {
                            "id": file_id,
                            "parentId": folder_id,
                            "name": "nv-afl-levelc-metadata.txt",
                            "isFolder": False,
                            "isFile": True,
                            "aspectNames": ["cm:auditable"],
                        }
                    ]
                raise AssertionError(f"unexpected parent lookup: {parent_id}")

            def create_child(self, *args, **kwargs):
                self.create_calls += 1
                raise AssertionError("bounded resolver must never create nodes")

        client = FakeClient()
        launch: dict = {}

        def fake_launch(layout, config_path, child_env, *, max_test_cases, time_budget):
            launch["layout"] = layout
            launch["config_path"] = config_path
            launch["child_env"] = dict(child_env)
            launch["max_test_cases"] = max_test_cases
            launch["time_budget"] = time_budget
            _materialize_execution_artifacts(layout)
            return 0

        module.build_alfresco_client = lambda base, credentials: client
        module.perform_preflight = lambda client: {"ok": True}
        module.read_only_target_identity = lambda client, node_id: {
            "id": node_id,
            "parentId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "nv-afl-levelc-metadata.txt",
        }
        module.launch_bounded_afl = fake_launch

        orig = self._set_creds()
        try:
            with tempfile.TemporaryDirectory(
                prefix="alfresco-bounded-main-"
            ) as tmp:
                run_root = Path(tmp).resolve()
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(
                        [
                            "--run-root",
                            str(run_root),
                            "--max-test-cases",
                            "5",
                            "--time-budget",
                            "20",
                        ]
                    )

                self.assertEqual(
                    rc,
                    0,
                    f"bounded run must return 0 on success; stderr={err.getvalue()!r}",
                )

                # resolve_existing_dedicated_node was driven through the client.
                self.assertEqual(client.list_calls, ["-my-", folder_id])
                self.assertEqual(client.create_calls, 0)

                # render_runtime_target_config wrote a run-scoped config.
                target_path = run_root / "target.json"
                self.assertTrue(target_path.is_file())
                rendered_text = target_path.read_text(encoding="utf-8")
                self.assertNotIn("__ALFRESCO_NODE_ID__", rendered_text)
                self.assertIn(file_id, rendered_text)

                # Seed input directory exists with one initial seed.
                seed_input = run_root / "seed_input"
                self.assertTrue(seed_input.is_dir())
                seed_files = list(seed_input.iterdir())
                self.assertEqual(len(seed_files), 1, f"expected one seed, got {seed_files}")

                # Bounded task.json carries the small budget.
                task = json.loads((run_root / "task.json").read_text(encoding="utf-8"))
                self.assertEqual(task["max_test_cases"], 5)
                self.assertEqual(task["time_budget"], 20)

                # launch_bounded_afl was invoked with the prepared layout/env.
                self.assertEqual(launch.get("max_test_cases"), 5)
                self.assertEqual(launch.get("time_budget"), 20)
                self.assertEqual(
                    Path(launch["config_path"]).resolve(),
                    target_path.resolve(),
                )

                report = json.loads(
                    (run_root / "evidence" / "artifact_report.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertTrue(report["ok"])
                self.assertEqual(report["final_result"], "pass")
                self.assertEqual(report["missing_required"], [])
                self.assertEqual(report["launch_returncode"], 0)
                self.assertEqual(report["feedback_source"], "real_alfresco_feedback")

                env = launch["child_env"]
                self.assertEqual(env["NV_STATUS_PATH"], str(run_root / "nv_http_status.json"))
                self.assertEqual(env["NV_TARGET_CONFIG"], str(target_path))
                self.assertEqual(env["NV_ENDPOINT_NAME"], "metadata_update")
                self.assertTrue(env["NV_BODY_RULES"].endswith("alfresco_metadata_update_rules.json"))
                self.assertEqual(env["NV_TASK_PATH"], str(run_root / "task.json"))
                self.assertEqual(env["AFL_FAST_CAL"], "1")
                self.assertNotIn("AFL_NO_STARTUP_CALIBRATION", env)
                self.assertEqual(env["ALFRESCO_USER"], self._CRED_USER)
                self.assertEqual(env["ALFRESCO_PASS"], self._CRED_PASS)

                # Proxy isolation survived into the child environment.
                for key in (
                    "http_proxy", "https_proxy", "HTTP_PROXY",
                    "HTTPS_PROXY", "all_proxy", "ALL_PROXY",
                ):
                    self.assertNotIn(key, env)
                self.assertEqual(env["no_proxy"], "127.0.0.1,localhost")

                # No credential value leaked into the rendered config.
                self.assertNotIn("Basic ", rendered_text)
                self.assertNotIn(self._CRED_PASS, rendered_text)
        finally:
            self._restore_creds(orig)

    def test_incomplete_prelaunch_api_identity_fails_closed_before_launch(self) -> None:
        import contextlib
        import io
        import tempfile

        folder_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        file_id = "11111111-2222-3333-4444-555555555555"
        complete = {
            "id": file_id,
            "parentId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "nv-afl-levelc-metadata.txt",
        }

        for missing_field in ("id", "parentId", "name"):
            with self.subTest(missing_field=missing_field):
                module = self._load()
                launch_calls = []
                module.build_alfresco_client = lambda base, credentials: object()
                module.perform_preflight = lambda client: {"ok": True}
                module.resolve_existing_dedicated_node = lambda client: {
                    "folder_id": folder_id,
                    "file_id": file_id,
                    "parent_id": folder_id,
                    "target_name": complete["name"],
                }
                api_identity = dict(complete)
                del api_identity[missing_field]
                module.read_only_target_identity = lambda client, node_id, value=api_identity: value
                module.launch_bounded_afl = lambda *args, **kwargs: launch_calls.append(True) or 0

                original = self._set_creds()
                try:
                    with tempfile.TemporaryDirectory(prefix="bounded-identity-incomplete-") as tmp:
                        err = io.StringIO()
                        with contextlib.redirect_stderr(err):
                            rc = module.main(["--run-root", tmp])
                finally:
                    self._restore_creds(original)

                self.assertEqual(rc, 3)
                self.assertEqual(launch_calls, [])
                self.assertIn("DEDICATED_TARGET_IDENTITY_INCOMPLETE", err.getvalue())

    def test_bounded_run_rejects_run_root_inside_git_worktree_without_client(self) -> None:
        import contextlib
        import io
        import tempfile

        module = self._load()

        def must_not_build(base, credentials):
            raise AssertionError("client must not be built before run-root validation")

        module.build_alfresco_client = must_not_build
        module.launch_bounded_afl = lambda *a, **k: 0

        orig = self._set_creds()
        try:
            for run_root in (REPO_ROOT.resolve(), REPO_ROOT.resolve() / "out"):
                with self.subTest(run_root=run_root):
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        rc = module.main(
                            [
                                "--run-root",
                                str(run_root),
                                "--max-test-cases",
                                "3",
                            ]
                        )
                    self.assertEqual(rc, 2)
                    self.assertIn("RUN_ROOT_INSIDE_GIT_WORKTREE", err.getvalue())
        finally:
            self._restore_creds(orig)

    def test_bounded_run_node_resolution_failure_returns_service_error_without_launch(self) -> None:
        import contextlib
        import io
        import tempfile

        module = self._load()

        class MissingFolderClient:
            def __init__(self) -> None:
                self.list_calls = []

            def list_children(self, parent_id):
                self.list_calls.append(parent_id)
                if parent_id == "-my-":
                    return []
                raise AssertionError(f"resolver must stop after missing folder: {parent_id}")

            def create_child(self, *args, **kwargs):
                raise AssertionError("bounded resolver must never create nodes")

        client = MissingFolderClient()

        def must_not_launch(*a, **k):
            raise AssertionError("launch must not run when node resolution failed")

        module.build_alfresco_client = lambda base, credentials: client
        module.perform_preflight = lambda client: {"ok": True}
        module.read_only_target_identity = lambda client, node_id: {
            "id": node_id,
            "parentId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "nv-afl-levelc-metadata.txt",
        }
        module.launch_bounded_afl = must_not_launch

        orig = self._set_creds()
        try:
            with tempfile.TemporaryDirectory(prefix="alfresco-bounded-miss-") as tmp:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(
                        [
                            "--run-root",
                            str(Path(tmp).resolve()),
                            "--max-test-cases",
                            "3",
                        ]
                    )
        finally:
            self._restore_creds(orig)

        self.assertEqual(rc, 3)
        self.assertIn("BOUNDED_DEDICATED_FOLDER_MISSING", err.getvalue())
        self.assertEqual(client.list_calls, ["-my-"])

    def test_bounded_run_default_max_test_cases_is_small_single_digit(self) -> None:
        import contextlib
        import io
        import tempfile

        module = self._load()

        class FakeClient:
            def __init__(self) -> None:
                self.list_calls = []

            def list_children(self, parent_id):
                self.list_calls.append(parent_id)
                if parent_id == "-my-":
                    return [
                        {
                            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                            "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                            "isFolder": True,
                            "isFile": False,
                        }
                    ]
                if parent_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee":
                    return [
                        {
                            "id": "11111111-2222-3333-4444-555555555555",
                            "parentId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                            "name": "nv-afl-levelc-metadata.txt",
                            "isFolder": False,
                            "isFile": True,
                            "aspectNames": ["cm:auditable"],
                        }
                    ]
                raise AssertionError(f"unexpected parent lookup: {parent_id}")

            def create_child(self, *args, **kwargs):
                raise AssertionError("bounded resolver must never create nodes")

        client = FakeClient()
        launch: dict = {}

        module.build_alfresco_client = lambda base, credentials: client
        module.perform_preflight = lambda client: {"ok": True}
        module.read_only_target_identity = lambda client, node_id: {
            "id": node_id,
            "parentId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "nv-afl-levelc-metadata.txt",
        }
        def fake_launch(layout, config_path, child_env, **kw):
            launch.update(kw)
            _materialize_execution_artifacts(layout)
            return 0

        module.launch_bounded_afl = fake_launch

        orig = self._set_creds()
        try:
            with tempfile.TemporaryDirectory(prefix="alfresco-bounded-default-") as tmp:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(["--run-root", str(Path(tmp).resolve())])
        finally:
            self._restore_creds(orig)

        self.assertEqual(rc, 0, f"stderr={err.getvalue()!r}")
        self.assertLessEqual(
            launch.get("max_test_cases"), 9, "bounded default must stay single-digit"
        )
        self.assertGreaterEqual(launch.get("max_test_cases"), 1)

    def test_bounded_run_launch_returncode_propagates(self) -> None:
        import contextlib
        import io
        import tempfile

        module = self._load()

        class FakeClient:
            def list_children(self, parent_id):
                if parent_id == "-my-":
                    return [
                        {
                            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                            "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                            "isFolder": True,
                            "isFile": False,
                        }
                    ]
                if parent_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee":
                    return [
                        {
                            "id": "11111111-2222-3333-4444-555555555555",
                            "parentId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                            "name": "nv-afl-levelc-metadata.txt",
                            "isFolder": False,
                            "isFile": True,
                            "aspectNames": ["cm:auditable"],
                        }
                    ]
                raise AssertionError(f"unexpected parent lookup: {parent_id}")

            def create_child(self, *args, **kwargs):
                raise AssertionError("bounded resolver must never create nodes")

        module.build_alfresco_client = lambda base, credentials: FakeClient()
        module.perform_preflight = lambda client: {"ok": True}
        module.read_only_target_identity = lambda client, node_id: {
            "id": node_id,
            "parentId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "nv-afl-levelc-metadata.txt",
        }
        module.launch_bounded_afl = lambda *a, **k: 7

        orig = self._set_creds()
        try:
            with tempfile.TemporaryDirectory(prefix="alfresco-bounded-rc-") as tmp:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(
                        ["--run-root", str(Path(tmp).resolve()), "--max-test-cases", "3"]
                    )
                report = json.loads(
                    (Path(tmp).resolve() / "evidence" / "artifact_report.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(report["launch_returncode"], 7)
                self.assertEqual(report["final_result"], "launch_failed")
        finally:
            self._restore_creds(orig)

        self.assertEqual(rc, 7)

    def test_default_run_root_is_outside_the_git_worktree(self) -> None:
        module = self._load()
        self.assertTrue(hasattr(module, "default_run_root"))
        default = module.default_run_root()
        repo_root = REPO_ROOT.resolve()
        self.assertNotEqual(default.resolve(), repo_root)
        self.assertFalse(
            default.resolve().is_relative_to(repo_root),
            f"default run root must not live inside the worktree: {default}",
        )


class CB2RunnerContractTest(unittest.TestCase):
    """Offline CB-2 contract tests; every service/process collaborator is fake."""

    def _load(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "cb2_bounded_runner_contract_test", RUNNER_PATH
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_initial_seed_is_full_http_and_matches_c_validation_contract(self) -> None:
        module = self._load()
        self.assertTrue(hasattr(module, "write_initial_seed"))

        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-seed-") as tmp:
            config = Path(tmp) / "target.json"
            seed_dir = Path(tmp) / "seed_input"
            config.write_text(
                json.dumps(
                    {
                        "body_only_mode": 1,
                        "endpoints": [
                            {
                                "name": "metadata_update",
                                "method": "PUT",
                                "path": "/alfresco/api/-default-/public/alfresco/versions/1/nodes/node-1",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            seed_path = module.write_initial_seed(config, seed_dir)
            seed = Path(seed_path).read_bytes()

            self.assertNotEqual(seed.lstrip()[:1], b"{")
            self.assertTrue(seed.startswith(b"PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/node-1 HTTP/1.1\r\n"))
            self.assertIn(b"Content-Type: application/json\r\n", seed)
            self.assertIn(b"\r\n\r\n", seed)

            from nv_http_body_adapter import extract_http_body

            body = extract_http_body(seed)
            self.assertEqual(
                json.loads(body),
                {"properties": {"cm:title": "seed title", "cm:description": "seed description"}},
            )
            self.assertEqual(module.seed_request_metadata(config), ("PUT", "/alfresco/api/-default-/public/alfresco/versions/1/nodes/node-1"))

    def test_seed_requires_named_metadata_endpoint(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-seed-endpoint-") as tmp:
            config = Path(tmp) / "target.json"
            config.write_text(
                json.dumps(
                    {
                        "endpoints": [
                            {"name": "other", "method": "POST", "path": "/other"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "^TARGET_CONFIG_ENDPOINT_MISSING$"):
                module.seed_request_metadata(config)

    def test_seed_rejects_http_control_characters(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-seed-control-") as tmp:
            config = Path(tmp) / "target.json"
            config.write_text(
                json.dumps(
                    {
                        "endpoints": [
                            {
                                "name": "metadata_update",
                                "method": "PUT",
                                "path": "/ok\r\nX-Injected: yes",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "^TARGET_CONFIG_ENDPOINT_INVALID$"):
                module.seed_request_metadata(config)

    def test_launch_uses_stdin_transport_and_run_scoped_io(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-launch-") as tmp:
            root = Path(tmp).resolve()
            layout = module.build_run_layout(root, REPO_ROOT)
            layout["seed_dir"].mkdir(parents=True)
            layout["afl_output"].mkdir(parents=True)
            fake_afl = root / "afl-fuzz"
            fake_afl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_afl.chmod(0o755)
            module.AFL_BINARY = fake_afl
            calls = {}

            def fake_run(cmd, **kwargs):
                calls["cmd"] = list(cmd)
                calls["kwargs"] = kwargs
                return subprocess.CompletedProcess(cmd, 0)

            original_run = module.subprocess.run
            module.subprocess.run = fake_run
            try:
                rc = module.launch_bounded_afl(
                    layout,
                    layout["target_config"],
                    {"NV_STATUS_PATH": str(layout["status"])},
                    max_test_cases=3,
                    time_budget=5,
                )
            finally:
                module.subprocess.run = original_run
            self.assertEqual(rc, 0)
            cmd = calls["cmd"]
            self.assertNotIn("@@", cmd)
            self.assertEqual(cmd[cmd.index("-i") + 1], str(layout["seed_dir"]))
            self.assertEqual(cmd[cmd.index("-o") + 1], str(layout["afl_output"]))
            self.assertEqual(cmd[-2:], [sys.executable, str(module.HARNESS_PATH)])
            self.assertEqual(calls["kwargs"]["timeout"], 65)
            self.assertEqual(calls["kwargs"]["cwd"], str(layout["run_root"]))
            self.assertEqual(
                calls["kwargs"]["env"]["NV_SEED_SELECTION_AUDIT_PATH"],
                str(layout["seed_selection_audit"]),
            )

    def test_manifest_launch_preserves_all_initial_seed_entries(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-manifest-preserve-") as tmp:
            root = Path(tmp).resolve()
            layout = module.build_run_layout(root, REPO_ROOT)
            layout["seed_dir"].mkdir(parents=True)
            layout["afl_output"].mkdir(parents=True)
            layout["task"].write_text(
                json.dumps({"seed_source": "manifest"}), encoding="utf-8"
            )
            fake_afl = root / "afl-fuzz"
            fake_afl.write_text("#!/bin/sh\\nexit 0\\n", encoding="utf-8")
            fake_afl.chmod(0o755)
            module.AFL_BINARY = fake_afl
            calls = {}

            def fake_run(cmd, **kwargs):
                calls["env"] = dict(kwargs["env"])
                return subprocess.CompletedProcess(cmd, 0)

            original_run = module.subprocess.run
            module.subprocess.run = fake_run
            try:
                rc = module.launch_bounded_afl(
                    layout,
                    layout["target_config"],
                    {},
                    max_test_cases=3,
                    time_budget=5,
                )
            finally:
                module.subprocess.run = original_run

            self.assertEqual(rc, 0)
            self.assertEqual(calls["env"]["NV_KEEP_INITIAL_SEEDS"], "1")

    def test_manifest_launch_uses_sequential_queue_selection(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-manifest-launch-") as tmp:
            root = Path(tmp).resolve()
            layout = module.build_run_layout(root, REPO_ROOT)
            layout["seed_dir"].mkdir(parents=True)
            layout["afl_output"].mkdir(parents=True)
            layout["task"].write_text(
                json.dumps({"seed_source": "manifest"}), encoding="utf-8"
            )
            fake_afl = root / "afl-fuzz"
            fake_afl.write_text("#!/bin/sh\\nexit 0\\n", encoding="utf-8")
            fake_afl.chmod(0o755)
            module.AFL_BINARY = fake_afl
            calls = {}

            def fake_run(cmd, **kwargs):
                calls["cmd"] = list(cmd)
                return subprocess.CompletedProcess(cmd, 0)

            original_run = module.subprocess.run
            module.subprocess.run = fake_run
            try:
                rc = module.launch_bounded_afl(
                    layout,
                    layout["target_config"],
                    {},
                    max_test_cases=3,
                    time_budget=5,
                )
            finally:
                module.subprocess.run = original_run

            self.assertEqual(rc, 0)
            self.assertIn("-Z", calls["cmd"])

    def test_sequential_seed_audit_increments_before_recording(self) -> None:
        source = (REPO_ROOT / "src" / "afl-fuzz.c").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            source.count("afl->queue_cur->ss_selected_cnt++;"),
            2,
        )
        self.assertGreaterEqual(
            source.count("nv_seed_selection_audit_record(afl, afl->queue_cur);"),
            2,
        )

    def test_runtime_environment_uses_fast_calibration(self) -> None:
        """FAST calibration keeps the normal forkserver path but trims cycles."""
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-fastcal-") as tmp:
            root = Path(tmp).resolve()
            layout = module.build_run_layout(root, REPO_ROOT)
            env = module.runtime_environment(
                layout,
                layout["target_config"],
                layout["task"],
                ("u", "p"),
            )
            self.assertEqual(env["AFL_FAST_CAL"], "1")
            self.assertNotIn("AFL_NO_STARTUP_CALIBRATION", env)

    def test_runtime_environment_does_not_skip_forkserver_initialization(self) -> None:
        """The child env must never bypass forkserver startup."""
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-forkserver-") as tmp:
            root = Path(tmp).resolve()
            layout = module.build_run_layout(root, REPO_ROOT)
            env = module.runtime_environment(
                layout,
                layout["target_config"],
                layout["task"],
                ("u", "p"),
            )
            self.assertNotIn("AFL_NO_STARTUP_CALIBRATION", env)
            self.assertEqual(env["AFL_FAST_CAL"], "1")

    def test_launch_preserves_normal_forkserver_startup(self) -> None:
        """Launch uses the bounded-tree afl-fuzz, stdin transport, FAST cal.

        A fake subprocess recorder stands in for afl-fuzz so no real AFL is
        started and no network is contacted.
        """
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-launch-fastcal-") as tmp:
            root = Path(tmp).resolve()
            layout = module.build_run_layout(root, REPO_ROOT)
            layout["seed_dir"].mkdir(parents=True)
            layout["afl_output"].mkdir(parents=True)
            child_env = module.runtime_environment(
                layout,
                layout["target_config"],
                layout["task"],
                ("u", "p"),
            )
            calls = {}

            def fake_run(cmd, **kwargs):
                calls["cmd"] = list(cmd)
                calls["kwargs"] = kwargs
                return subprocess.CompletedProcess(cmd, 0)

            original_run = module.subprocess.run
            module.subprocess.run = fake_run
            try:
                rc = module.launch_bounded_afl(
                    layout,
                    layout["target_config"],
                    child_env,
                    max_test_cases=1,
                    time_budget=10,
                )
            finally:
                module.subprocess.run = original_run
            self.assertEqual(rc, 0)
            cmd = calls["cmd"]
            # AFL binary is the bounded-tree afl-fuzz, never a system binary.
            self.assertEqual(cmd[0], str(module.AFL_BINARY))
            self.assertEqual(cmd[0], str(REPO_ROOT / "afl-fuzz"))
            # stdin transport: no @@ positional; harness is the target argv.
            self.assertNotIn("@@", cmd)
            self.assertEqual(cmd[-2:], [sys.executable, str(module.HARNESS_PATH)])
            env = calls["kwargs"]["env"]
            self.assertEqual(env["AFL_FAST_CAL"], "1")
            self.assertNotIn("AFL_NO_STARTUP_CALIBRATION", env)

    def test_full_run_calls_preflight_before_node_resolution(self) -> None:
        module = self._load()
        import contextlib
        import io
        import tempfile

        events = []
        node = {"folder_id": "folder", "file_id": "11111111-2222-3333-4444-555555555555", "aspect_names": []}

        class FakeClient:
            def get_node(self, node_id):
                events.append("identity")
                return {
                    "id": node_id,
                    "parentId": "folder",
                    "name": "nv-afl-levelc-metadata.txt",
                }

        client = FakeClient()
        module.runtime_credentials = lambda: events.append("credential") or ("sentinel-user", "sentinel-pass")
        module.validate_base_url = lambda value: events.append("base") or value
        module.build_alfresco_client = lambda base, credentials: events.append("client") or client
        module.perform_preflight = lambda c: events.append("preflight") or {"ok": True}
        module.resolve_existing_dedicated_node = lambda c: events.append("resolve") or node
        def fake_render(node_id, out):
            events.append("render")
            out.write_text(
                json.dumps({"body_only_mode": 1, "endpoints": [{"name": "metadata_update", "method": "PUT", "path": "/nodes/" + node_id}]}),
                encoding="utf-8",
            )
            return out

        module.render_runtime_target_config = fake_render
        def fake_launch(layout, config_path, child_env, **kwargs):
            events.append("launch")
            _materialize_execution_artifacts(layout)
            return 0

        module.launch_bounded_afl = fake_launch

        original = (os.environ.get("ALFRESCO_USER"), os.environ.get("ALFRESCO_PASS"))
        os.environ["ALFRESCO_USER"] = "sentinel-user"
        os.environ["ALFRESCO_PASS"] = "sentinel-pass"
        try:
            with tempfile.TemporaryDirectory(prefix="cb2-order-") as tmp:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(["--run-root", tmp, "--max-test-cases", "3", "--time-budget", "1"])
        finally:
            if original[0] is None:
                os.environ.pop("ALFRESCO_USER", None)
            else:
                os.environ["ALFRESCO_USER"] = original[0]
            if original[1] is None:
                os.environ.pop("ALFRESCO_PASS", None)
            else:
                os.environ["ALFRESCO_PASS"] = original[1]

        self.assertEqual(rc, 0, err.getvalue())
        self.assertEqual(events, ["credential", "base", "client", "preflight", "resolve", "identity", "render", "launch"])

    def test_preflight_failure_prevents_resolution_and_launch(self) -> None:
        module = self._load()
        import contextlib
        import io
        import tempfile

        calls = []
        module.build_alfresco_client = lambda base, credentials: calls.append("client") or object()
        module.runtime_credentials = lambda: ("sentinel-user", "sentinel-pass")
        module.validate_base_url = lambda value: value
        module.perform_preflight = lambda client: (_ for _ in ()).throw(RuntimeError("PREFLIGHT_GATE_FAILED"))
        module.resolve_existing_dedicated_node = lambda client: calls.append("resolve")
        module.render_runtime_target_config = lambda *a, **k: calls.append("render")
        module.launch_bounded_afl = lambda *a, **k: calls.append("launch") or 0
        original = (os.environ.get("ALFRESCO_USER"), os.environ.get("ALFRESCO_PASS"))
        os.environ["ALFRESCO_USER"] = "sentinel-user"
        os.environ["ALFRESCO_PASS"] = "sentinel-pass"
        try:
            with tempfile.TemporaryDirectory(prefix="cb2-preflight-fail-") as tmp:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(["--run-root", tmp])
        finally:
            if original[0] is None:
                os.environ.pop("ALFRESCO_USER", None)
            else:
                os.environ["ALFRESCO_USER"] = original[0]
            if original[1] is None:
                os.environ.pop("ALFRESCO_PASS", None)
            else:
                os.environ["ALFRESCO_PASS"] = original[1]

        self.assertEqual(rc, 3)
        self.assertIn("PREFLIGHT_GATE_FAILED", err.getvalue())
        self.assertEqual(calls, ["client"])

    def test_task_json_contains_complete_bounded_schema(self) -> None:
        module = self._load()
        self.assertTrue(hasattr(module, "build_task_payload"))
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-task-") as tmp:
            seed_dir = Path(tmp) / "seed_input"
            task = module.build_task_payload(seed_dir, max_test_cases=3, time_budget=30)
            self.assertEqual(
                set(task),
                {"target_type", "target_endpoint", "seed_source", "seed_location", "mutation_scope", "max_test_cases", "time_budget", "enable_validity"},
            )
            self.assertEqual(task["target_type"], "http_api")
            self.assertEqual(task["target_endpoint"], "metadata_update")
            self.assertEqual(task["seed_source"], "seed_file")
            self.assertEqual(task["seed_location"], str(seed_dir.resolve()))
            self.assertEqual(task["mutation_scope"], ["field_value"])
            self.assertGreater(task["max_test_cases"], 0)
            self.assertGreater(task["time_budget"], 0)
            self.assertEqual(task["enable_validity"], 1)

    def test_all_runtime_paths_are_run_scoped_and_unique(self) -> None:
        module = self._load()
        first = module.build_run_layout(module.default_run_root(), REPO_ROOT)
        second = module.build_run_layout(module.default_run_root(), REPO_ROOT)
        self.assertNotEqual(first["run_root"], second["run_root"])
        required = {"target_config", "task", "seed_dir", "seed", "status", "probe", "state_db", "ctx", "err_dir", "state_trace", "body_valid_stats", "afl_output", "evidence"}
        self.assertTrue(required.issubset(first))
        self.assertEqual(first["status_seq"], Path(str(first["status"]) + ".seq"))
        for name, path in first.items():
            if name == "run_root":
                continue
            self.assertTrue(Path(path).resolve().is_relative_to(first["run_root"]))
            self.assertFalse(Path(path).resolve().is_relative_to(REPO_ROOT.resolve()))

    def test_successful_launch_defines_expected_artifact_contract(self) -> None:
        module = self._load()
        self.assertTrue(hasattr(module, "artifact_contract"))
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-artifacts-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            contract = module.artifact_contract(layout)
            self.assertEqual(
                set(contract), {"setup_required", "execution_required", "conditional"}
            )
            self.assertEqual(contract["setup_required"]["target"], layout["target_config"])
            self.assertEqual(contract["setup_required"]["task"], layout["task"])
            self.assertEqual(contract["setup_required"]["seed"], layout["seed"])
            self.assertEqual(contract["execution_required"]["status_seq"], layout["status_seq"])
            self.assertEqual(contract["execution_required"]["state_trace"], layout["state_trace"])
            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertFalse(report["ok"])
            self.assertIn("target", report["missing_required"])
            self.assertIn("setup_required", report)
            self.assertIn("execution_required", report)
            self.assertIn("conditional", report)
            self.assertIn("present", report)
            self.assertIn("missing_conditional", report)
            self.assertIn("final_result", report)

    def test_setup_artifacts_exist_before_launch(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-setup-ok-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            layout["run_root"].mkdir(parents=True, exist_ok=True)
            layout["target_config"].write_text("{}", encoding="utf-8")
            layout["task"].write_text("{}", encoding="utf-8")
            layout["seed"].parent.mkdir(parents=True, exist_ok=True)
            layout["seed"].write_bytes(b"PUT /nodes/id HTTP/1.1\r\n\r\n{}")
            layout["afl_output"].mkdir()
            layout["evidence"].mkdir()
            layout["err_dir"].mkdir()

            report = module.inspect_artifacts(layout)
            self.assertEqual(report["missing_required"], [])
            self.assertTrue(report["ok"])

    def test_missing_setup_artifact_prevents_launch(self) -> None:
        module = self._load()
        import contextlib
        import io
        import tempfile

        folder_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        file_id = "11111111-2222-3333-4444-555555555555"

        class FakeClient:
            def list_children(self, parent_id):
                if parent_id == "-my-":
                    return [{"id": folder_id, "name": "NV_AFL_REAL_PLATFORM_CALIBRATION", "isFolder": True, "isFile": False}]
                if parent_id == folder_id:
                    return [{"id": file_id, "parentId": folder_id, "name": "nv-afl-levelc-metadata.txt", "isFolder": False, "isFile": True}]
                raise AssertionError(parent_id)

        launch_calls = []
        module.build_alfresco_client = lambda base, credentials: FakeClient()
        module.perform_preflight = lambda client: {"ok": True}
        module.read_only_target_identity = lambda client, node_id: {
            "id": node_id,
            "parentId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "nv-afl-levelc-metadata.txt",
        }

        def fake_render(node_id, out):
            out.write_text(
                json.dumps({"endpoints": [{"name": "metadata_update", "method": "PUT", "path": "/nodes/" + node_id}]}),
                encoding="utf-8",
            )
            return out

        module.render_runtime_target_config = fake_render
        module.write_initial_seed = lambda config, seed_dir: seed_dir / "seed.http"
        module.launch_bounded_afl = lambda *args, **kwargs: launch_calls.append(True) or 0

        original = (os.environ.get("ALFRESCO_USER"), os.environ.get("ALFRESCO_PASS"))
        os.environ["ALFRESCO_USER"] = "sentinel-user"
        os.environ["ALFRESCO_PASS"] = "sentinel-pass"
        try:
            with tempfile.TemporaryDirectory(prefix="cb2-setup-missing-") as tmp:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(["--run-root", tmp])
                self.assertEqual(rc, module.ARTIFACT_CONTRACT_FAILURE)
                self.assertEqual(launch_calls, [])
                self.assertIn("ARTIFACT_CONTRACT_FAILED", err.getvalue())
        finally:
            if original[0] is None:
                os.environ.pop("ALFRESCO_USER", None)
            else:
                os.environ["ALFRESCO_USER"] = original[0]
            if original[1] is None:
                os.environ.pop("ALFRESCO_PASS", None)
            else:
                os.environ["ALFRESCO_PASS"] = original[1]

    def test_successful_launch_with_complete_required_artifacts_returns_zero(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-artifacts-success-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            layout["run_root"].mkdir(parents=True, exist_ok=True)
            layout["target_config"].write_text("{}", encoding="utf-8")
            layout["task"].write_text("{}", encoding="utf-8")
            layout["seed"].parent.mkdir(parents=True, exist_ok=True)
            layout["seed"].write_bytes(b"PUT /nodes/id HTTP/1.1\r\n\r\n{}")
            layout["afl_output"].mkdir()
            layout["evidence"].mkdir()
            layout["err_dir"].mkdir()
            _materialize_execution_artifacts(layout)

            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertTrue(report["ok"])
            self.assertEqual(report["final_result"], "pass")
            self.assertEqual(report["missing_required"], [])

    def test_successful_launch_with_missing_required_artifact_fails_closed(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-artifacts-fail-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            layout["run_root"].mkdir(parents=True, exist_ok=True)
            layout["target_config"].write_text("{}", encoding="utf-8")
            layout["task"].write_text("{}", encoding="utf-8")
            layout["seed"].parent.mkdir(parents=True, exist_ok=True)
            layout["seed"].write_bytes(b"PUT /nodes/id HTTP/1.1\r\n\r\n{}")
            layout["afl_output"].mkdir()
            layout["evidence"].mkdir()
            layout["err_dir"].mkdir()
            _materialize_execution_artifacts(layout, include_fuzzer_stats=False)

            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertFalse(report["ok"])
            self.assertEqual(report["final_result"], "artifact_contract_failed")
            self.assertIn("afl_stats", report["missing_required"])
            self.assertFalse((layout["afl_output"] / "fuzzer_stats").exists())

    def test_main_returns_artifact_contract_failure_when_launch_succeeds_without_execution_artifacts(self) -> None:
        module = self._load()
        import contextlib
        import io
        import tempfile

        folder_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        file_id = "11111111-2222-3333-4444-555555555555"

        class FakeClient:
            def list_children(self, parent_id):
                if parent_id == "-my-":
                    return [{"id": folder_id, "name": "NV_AFL_REAL_PLATFORM_CALIBRATION", "isFolder": True, "isFile": False}]
                if parent_id == folder_id:
                    return [{"id": file_id, "parentId": folder_id, "name": "nv-afl-levelc-metadata.txt", "isFolder": False, "isFile": True}]
                raise AssertionError(parent_id)

        launch_calls = []
        module.build_alfresco_client = lambda base, credentials: FakeClient()
        module.perform_preflight = lambda client: {"ok": True}
        module.read_only_target_identity = lambda client, node_id: {
            "id": node_id,
            "parentId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "nv-afl-levelc-metadata.txt",
        }

        def fake_render(node_id, out):
            out.write_text(
                json.dumps({"endpoints": [{"name": "metadata_update", "method": "PUT", "path": "/nodes/" + node_id}]}),
                encoding="utf-8",
            )
            return out

        module.render_runtime_target_config = fake_render

        def fake_launch(*args, **kwargs):
            launch_calls.append(True)
            return 0

        module.launch_bounded_afl = fake_launch
        original = (os.environ.get("ALFRESCO_USER"), os.environ.get("ALFRESCO_PASS"))
        os.environ["ALFRESCO_USER"] = "sentinel-user"
        os.environ["ALFRESCO_PASS"] = "sentinel-pass"
        try:
            with tempfile.TemporaryDirectory(prefix="cb2-main-artifact-fail-") as tmp:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(["--run-root", tmp])
                self.assertEqual(rc, module.ARTIFACT_CONTRACT_FAILURE)
                self.assertEqual(launch_calls, [True])
                report = json.loads(
                    (Path(tmp) / "evidence" / "artifact_report.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(report["launch_returncode"], 0)
                self.assertEqual(report["final_result"], "artifact_contract_failed")
                self.assertIn("afl_stats", report["missing_required"])
                self.assertIn("ARTIFACT_CONTRACT_FAILED", err.getvalue())
        finally:
            if original[0] is None:
                os.environ.pop("ALFRESCO_USER", None)
            else:
                os.environ["ALFRESCO_USER"] = original[0]
            if original[1] is None:
                os.environ.pop("ALFRESCO_PASS", None)
            else:
                os.environ["ALFRESCO_PASS"] = original[1]

    def test_missing_conditional_artifact_does_not_mask_required_contract(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-artifacts-conditional-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            layout["run_root"].mkdir(parents=True, exist_ok=True)
            layout["target_config"].write_text("{}", encoding="utf-8")
            layout["task"].write_text("{}", encoding="utf-8")
            layout["seed"].parent.mkdir(parents=True, exist_ok=True)
            layout["seed"].write_bytes(b"PUT /nodes/id HTTP/1.1\r\n\r\n{}")
            layout["afl_output"].mkdir()
            layout["evidence"].mkdir()
            layout["err_dir"].mkdir()
            _materialize_execution_artifacts(layout)

            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertTrue(report["ok"])
            self.assertIn("ctx", report["missing_conditional"])
            self.assertNotIn("ctx", report["missing_required"])

    def test_nonzero_launch_return_preserves_launch_failure_semantics(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-artifacts-launch-fail-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            layout["run_root"].mkdir(parents=True, exist_ok=True)
            layout["target_config"].write_text("{}", encoding="utf-8")
            layout["task"].write_text("{}", encoding="utf-8")
            layout["seed"].parent.mkdir(parents=True, exist_ok=True)
            layout["seed"].write_bytes(b"PUT /nodes/id HTTP/1.1\r\n\r\n{}")
            layout["afl_output"].mkdir()
            layout["evidence"].mkdir()
            layout["err_dir"].mkdir()

            report = module.inspect_artifacts(layout, launch_returncode=7)
            self.assertFalse(report["ok"])
            self.assertEqual(report["launch_returncode"], 7)
            self.assertEqual(report["final_result"], "launch_failed")
            self.assertEqual(report["launch_returncode"], 7)

    def test_launch_timeout_is_bounded_and_binary_missing_fails_closed(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-gate-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            module.AFL_BINARY = Path(tmp) / "missing-afl-fuzz"
            with self.assertRaisesRegex(RuntimeError, "^AFL_BINARY_MISSING$"):
                module.launch_bounded_afl(layout, layout["target_config"], {}, max_test_cases=1, time_budget=1)
            fake = Path(tmp) / "afl-fuzz"
            fake.write_text("binary", encoding="utf-8")
            fake.chmod(0o755)
            module.AFL_BINARY = fake
            original_run = module.subprocess.run
            module.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired(a[0], k["timeout"]))
            try:
                self.assertEqual(module.launch_bounded_afl(layout, layout["target_config"], {}, max_test_cases=1, time_budget=1), 124)
            finally:
                module.subprocess.run = original_run

    def test_non_executable_afl_binary_fails_closed(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cb2-gate-perm-") as tmp:
            layout = module.build_run_layout(Path(tmp) / "run", REPO_ROOT)
            layout["run_root"].mkdir(parents=True, exist_ok=True)
            fake = Path(tmp) / "afl-fuzz"
            fake.write_text("binary", encoding="utf-8")
            fake.chmod(0o644)
            module.AFL_BINARY = fake
            with self.assertRaisesRegex(RuntimeError, "^AFL_BINARY_NOT_EXECUTABLE$"):
                module.launch_bounded_afl(layout, layout["target_config"], {}, max_test_cases=1, time_budget=1)


class SeedSelectionAuditRunnerContractTest(unittest.TestCase):
    """Offline contract for the bounded run's seed-selection evidence."""

    def _load(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "seed_selection_audit_runner_test", RUNNER_PATH
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_runner_sets_run_scoped_seed_selection_audit_path(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="seed-audit-run-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            env = module.runtime_environment(
                layout, layout["target_config"], layout["task"], ("u", "p")
            )
            self.assertEqual(
                env["NV_SEED_SELECTION_AUDIT_PATH"],
                str(Path(tmp) / "evidence" / "seed_selection.jsonl"),
            )

    def test_seed_audit_path_is_inside_current_run_root(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="seed-audit-inside-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            path = layout["seed_selection_audit"]
            self.assertTrue(path.is_relative_to(layout["run_root"]))
            self.assertEqual(path, layout["evidence"] / "seed_selection.jsonl")

    def test_seed_audit_path_is_outside_git_worktree(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="seed-audit-outside-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            self.assertFalse(layout["seed_selection_audit"].is_relative_to(REPO_ROOT))

    def test_seed_audit_path_is_not_external_override(self) -> None:
        module = self._load()
        import tempfile

        prior = os.environ.get("NV_SEED_SELECTION_AUDIT_PATH")
        os.environ["NV_SEED_SELECTION_AUDIT_PATH"] = "/tmp/untrusted-audit.jsonl"
        try:
            with tempfile.TemporaryDirectory(prefix="seed-audit-override-") as tmp:
                layout = module.build_run_layout(Path(tmp), REPO_ROOT)
                env = module.runtime_environment(
                    layout, layout["target_config"], layout["task"], ("u", "p")
                )
                self.assertEqual(
                    env["NV_SEED_SELECTION_AUDIT_PATH"],
                    str(layout["seed_selection_audit"]),
                )
        finally:
            if prior is None:
                os.environ.pop("NV_SEED_SELECTION_AUDIT_PATH", None)
            else:
                os.environ["NV_SEED_SELECTION_AUDIT_PATH"] = prior

    def test_seed_audit_artifact_is_run_scoped(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="seed-audit-artifact-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            contract = module.artifact_contract(layout)
            self.assertEqual(
                contract["execution_required"]["seed_selection_audit"],
                layout["seed_selection_audit"],
            )

    def test_missing_seed_audit_is_reported_when_enabled(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="seed-audit-missing-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            layout["run_root"].mkdir(parents=True, exist_ok=True)
            layout["target_config"].write_text("{}", encoding="utf-8")
            layout["task"].write_text("{}", encoding="utf-8")
            layout["seed"].parent.mkdir()
            layout["seed"].write_bytes(b"PUT /offline HTTP/1.1\r\n\r\n{}")
            layout["afl_output"].mkdir()
            layout["evidence"].mkdir()
            layout["err_dir"].mkdir()
            _materialize_execution_artifacts(layout)
            layout["seed_selection_audit"].unlink()
            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertIn("seed_selection_audit", report["missing_required"])

    def test_seed_audit_artifact_has_strict_schema_and_no_secrets(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="seed-audit-schema-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            layout["seed_selection_audit"].parent.mkdir(parents=True)
            layout["seed_selection_audit"].write_text(
                json.dumps({
                    "queue_id": 2,
                    "depth": 1,
                    "ss_cov_cnt": 3,
                    "ss_selected_cnt": 4,
                    "ss_prob": 0.615571,
                }) + "\n",
                encoding="utf-8",
            )
            parsed = module.parse_seed_selection_audit(
                layout["seed_selection_audit"]
            )
            self.assertTrue(parsed["valid"], parsed)
            self.assertEqual(parsed["record_count"], 1)
            self.assertEqual(parsed["queue_ids"], [2])

    def test_seed_audit_artifact_rejects_extra_fields(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="seed-audit-extra-") as tmp:
            path = Path(tmp) / "seed_selection.jsonl"
            path.write_text(
                json.dumps({
                    "event": "seed_selected",
                    "queue_id": 0,
                    "depth": 1,
                    "ss_cov_cnt": 0,
                    "ss_selected_cnt": 1,
                    "ss_prob": 1.0,
                }) + "\n",
                encoding="utf-8",
            )
            parsed = module.parse_seed_selection_audit(path)
            self.assertFalse(parsed["valid"])
            self.assertIn("schema_violation:1", parsed["diagnostics"])

    def test_audit_writer_failure_is_reported_without_changing_scheduler_contract(self) -> None:
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="seed-audit-write-failure-") as tmp:
            layout = module.build_run_layout(Path(tmp), REPO_ROOT)
            for name in ("run_root", "seed_dir", "afl_output", "evidence", "err_dir"):
                Path(layout[name]).mkdir(parents=True, exist_ok=True)
            layout["target_config"].write_text("{}", encoding="utf-8")
            layout["task"].write_text("{}", encoding="utf-8")
            layout["seed"].write_bytes(b"PUT /offline HTTP/1.1\r\n\r\n{}")
            for name in ("status", "probe", "state_db", "body_valid_stats"):
                Path(layout[name]).write_text("{}", encoding="utf-8")
            layout["status_seq"].write_text("1", encoding="utf-8")
            layout["state_trace"].write_text("{}\n", encoding="utf-8")
            (layout["afl_output"] / "fuzzer_stats").write_text(
                "ss_selected_sum : 1\n"
                "nv_mab_total_pulls : 0\n"
                "security_state_reward_src_seq : 0\n"
                "nv_mab_journal_error_count : 0\n"
                "nv_mab_journal_audit_invalid : 0\n"
                "nv_mab_arm0_pulls : 0\n"
                "nv_mab_arm1_pulls : 0\n"
                "nv_mab_arm2_pulls : 0\n"
                "nv_mab_arm0_sum : 0\n"
                "nv_mab_arm1_sum : 0\n"
                "nv_mab_arm2_sum : 0\n"
                "nv_mab_arm0_pos : 0\n"
                "nv_mab_arm1_pos : 0\n"
                "nv_mab_arm2_pos : 0\n"
                "seed_audit_enabled : 1\n"
                "seed_audit_error_count : 0\n"
                "seed_audit_invalid : 0\n"
                "seed_audit_record_count : 0\n"
                "seed_audit_expected_selection_count : 1\n",
                encoding="utf-8",
            )
            layout["mab_journal"].touch()
            layout["seed_selection_audit"].touch()
            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertFalse(report["ok"])
            self.assertIn("seed_selection_audit_integrity", report["missing_required"])
            self.assertIn(
                "selected_seeds_missing_audit_records",
                report["seed_selection_audit"]["diagnostics"],
            )

    def _seed_audit_case(self, module, tmp, audit_text: str, selected_sum: int,
                         queue_counts: dict[int, int]):
        layout = module.build_run_layout(Path(tmp), REPO_ROOT)
        layout["run_root"].mkdir(parents=True, exist_ok=True)
        layout["target_config"].write_text("{}", encoding="utf-8")
        layout["task"].write_text("{}", encoding="utf-8")
        layout["seed"].parent.mkdir(parents=True, exist_ok=True)
        layout["seed"].write_bytes(b"PUT /offline HTTP/1.1\r\n\r\n{}")
        layout["afl_output"].mkdir()
        layout["evidence"].mkdir()
        layout["err_dir"].mkdir()
        _materialize_execution_artifacts(layout)
        layout["seed_selection_audit"].write_text(audit_text, encoding="utf-8")
        stats = layout["afl_output"] / "fuzzer_stats"
        with stats.open("a", encoding="utf-8") as fh:
            fh.write(f"ss_selected_sum : {selected_sum}\n")
            fh.write("seed_audit_enabled : 1\n")
            fh.write("seed_audit_error_count : 0\n")
            fh.write("seed_audit_invalid : 0\n")
            fh.write(f"seed_audit_record_count : {selected_sum}\n")
            fh.write(f"seed_audit_expected_selection_count : {selected_sum}\n")
            for queue_id, count in queue_counts.items():
                fh.write(f"ss_selected_queue_{queue_id} : {count}\n")
        return layout

    def test_missing_seed_selection_record_fails_closed(self) -> None:
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="seed-audit-missing-record-") as tmp:
            records = (
                '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":1,"ss_prob":1}\n'
                '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":2,"ss_prob":1}\n'
            )
            layout = self._seed_audit_case(module, tmp, records, 3, {0: 3})
            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertFalse(report["ok"])
            self.assertNotEqual(report["final_result"], "pass")
            self.assertIn("missing_selection_records", report["seed_selection_audit"]["diagnostics"])

    def test_extra_seed_selection_record_fails_closed(self) -> None:
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="seed-audit-extra-record-") as tmp:
            records = "".join(
                f'{{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":{n},"ss_prob":1}}\n'
                for n in range(1, 5)
            )
            layout = self._seed_audit_case(module, tmp, records, 3, {0: 3})
            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertFalse(report["ok"])
            self.assertIn("extra_selection_records", report["seed_selection_audit"]["diagnostics"])

    def test_seed_selection_record_count_reconciles(self) -> None:
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="seed-audit-reconcile-") as tmp:
            records = (
                '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":1,"ss_prob":1}\n'
                '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":2,"ss_prob":1}\n'
                '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":3,"ss_prob":1}\n'
            )
            layout = self._seed_audit_case(module, tmp, records, 3, {0: 3})
            report = module.inspect_artifacts(layout, launch_returncode=0)
            audit = report["seed_selection_audit"]
            self.assertTrue(report["ok"], report)
            self.assertEqual(audit["expected_records"], 3)
            self.assertEqual(audit["actual_records"], 3)
            self.assertEqual(audit["error_count"], 0)
            self.assertFalse(audit["audit_invalid"])
            self.assertTrue(audit["reconciled"])

    def test_seed_selection_per_queue_counts_reconcile(self) -> None:
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="seed-audit-per-queue-") as tmp:
            records = (
                '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":1,"ss_prob":1}\n'
                '{"queue_id":1,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":1,"ss_prob":1}\n'
                '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":2,"ss_prob":1}\n'
            )
            layout = self._seed_audit_case(module, tmp, records, 3, {0: 2, 1: 1})
            (layout["seed_dir"] / "second.http").write_bytes(b"PUT /offline HTTP/1.1\r\n\r\n{}")
            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertTrue(report["ok"], report)
            self.assertEqual(
                report["seed_selection_audit"]["per_queue"],
                {"0": {"expected": 2, "observed": 2},
                 "1": {"expected": 1, "observed": 1}},
            )

    def test_malformed_seed_selection_record_fails_closed(self) -> None:
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="seed-audit-malformed-") as tmp:
            records = (
                '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":1,"ss_prob":1}\n'
                '{not-json}\n'
            )
            layout = self._seed_audit_case(module, tmp, records, 2, {0: 2})
            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertFalse(report["ok"])
            self.assertTrue(report["seed_selection_audit"]["malformed_count"] > 0)
            self.assertFalse(report["seed_selection_audit"]["reconciled"])

    def test_partial_seed_selection_record_fails_closed(self) -> None:
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="seed-audit-partial-") as tmp:
            records = (
                '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":1,"ss_prob":1}\n'
                '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":2'
            )
            layout = self._seed_audit_case(module, tmp, records, 2, {0: 2})
            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertFalse(report["ok"])
            self.assertTrue(report["seed_selection_audit"]["partial_final_line"])
            self.assertFalse(report["seed_selection_audit"]["reconciled"])

    def test_seed_selection_per_queue_sequence_mismatch_fails_closed(self) -> None:
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="seed-audit-sequence-") as tmp:
            records = (
                '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":1,"ss_prob":1}\n'
                '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":3,"ss_prob":1}\n'
            )
            layout = self._seed_audit_case(module, tmp, records, 2, {0: 2})
            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertFalse(report["ok"])
            self.assertGreater(
                report["seed_selection_audit"]["duplicate_or_out_of_order_count"],
                0,
            )

    def test_run_scoped_seed_audit_is_written_by_production_picker(self) -> None:
        """Close runner path, bounded AFL, C picker/writer, and reconciliation."""
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="seed-audit-production-") as tmp:
            run_root = Path(tmp) / "run"
            layout = module.build_run_layout(run_root, REPO_ROOT)
            layout["run_root"].mkdir(parents=True)
            layout["afl_output"].mkdir()
            layout["evidence"].mkdir()
            layout["err_dir"].mkdir()
            module.initialize_mab_journal(layout)
            module.initialize_seed_selection_audit(layout)

            config = layout["target_config"]
            config.write_text(
                json.dumps(
                    {
                        "base": "http://offline.invalid",
                        "body_only_mode": 1,
                        "endpoints": [
                            {
                                "name": "metadata_update",
                                "method": "PUT",
                                "path": "/offline/metadata",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            task = layout["task"]
            task.write_text(
                json.dumps(
                    {
                        "target_type": "http_api",
                        "target_endpoint": "metadata_update",
                        "seed_source": "seed_file",
                        "seed_location": str(layout["seed_dir"]),
                        "mutation_scope": ["field_value"],
                        "max_test_cases": 30,
                        "time_budget": 3,
                        "enable_validity": 1,
                    }
                ),
                encoding="utf-8",
            )
            seed_dir = layout["seed_dir"]
            seed_dir.mkdir()
            bodies = (
                b'{"name":"seed-a","properties":{"cm:title":"A"}}',
                b'{"name":"seed-b","properties":{"cm:title":"B"}}',
                b'{"name":"seed-c","properties":{"cm:title":"C"}}',
            )
            for name, body in zip(("seed", "seed_b", "seed_c"), bodies):
                (seed_dir / f"{name}.http").write_bytes(
                    b"PUT /offline/metadata HTTP/1.1\r\n"
                    b"Host: offline.invalid\r\n"
                    b"Content-Type: application/json\r\n"
                    + f"Content-Length: {len(body)}\r\n".encode("ascii")
                    + b"\r\n"
                    + body
                )
            _materialize_execution_artifacts(layout, include_fuzzer_stats=False)

            child_env = module.runtime_environment(
                layout, config, task, ("offline-user", "offline-pass")
            )
            child_env.update(
                {
                    "NV_P0_PROFILE": "alfresco_metadata_update",
                    "AFL_NO_UI": "1",
                    "AFL_SKIP_CPUFREQ": "1",
                    "AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES": "1",
                }
            )
            original_harness = module.HARNESS_PATH
            original_rules = module.BODY_RULES_PATH
            module.HARNESS_PATH = REPO_ROOT / "targets" / "nv_p0_deterministic_target.py"
            module.BODY_RULES_PATH = REPO_ROOT / "validity" / "alfresco_metadata_update_rules.json"
            try:
                return_code = module.launch_bounded_afl(
                    layout,
                    config,
                    child_env,
                    max_test_cases=30,
                    time_budget=3,
                )
            finally:
                module.HARNESS_PATH = original_harness
                module.BODY_RULES_PATH = original_rules

            self.assertEqual(return_code, 0)
            report = module.inspect_artifacts(layout, launch_returncode=return_code)
            module.write_artifact_report(layout, report)
            artifact_report = json.loads(
                (layout["evidence"] / "artifact_report.json").read_text(
                    encoding="utf-8"
                )
            )
            audit = report["seed_selection_audit"]
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["final_result"], "pass")
            self.assertTrue(artifact_report["ok"], artifact_report)
            self.assertEqual(artifact_report["final_result"], "pass")
            self.assertTrue(audit["enabled"])
            self.assertEqual(audit["path"], str(run_root / "evidence" / "seed_selection.jsonl"))
            self.assertTrue(audit["present"])
            self.assertEqual(audit["expected_records"], audit["actual_records"])
            self.assertEqual(audit["error_count"], 0)
            self.assertFalse(audit["audit_invalid"])
            self.assertTrue(audit["reconciled"])

            records = [
                json.loads(line)
                for line in layout["seed_selection_audit"].read_text(encoding="utf-8").splitlines()
            ]
            stats = module.parse_fuzzer_stats(layout["afl_output"] / "fuzzer_stats")
            self.assertEqual(int(stats["corpus_count"]), 3)
            self.assertGreaterEqual(len(records), 1)
            for record in records:
                self.assertEqual(
                    set(record),
                    {"queue_id", "depth", "ss_cov_cnt", "ss_selected_cnt", "ss_prob"},
                )
                self.assertFalse(
                    any(
                        forbidden in json.dumps(record).lower()
                        for forbidden in (
                            "event", "seed", "request", "body", "authorization",
                            "token", "credential", "target", "content",
                        )
                    )
                )

    def test_identical_duplicate_seed_audit_record_fails_closed(self) -> None:
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="seed-audit-duplicate-") as tmp:
            record = '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":1,"ss_prob":1}\n'
            layout = self._seed_audit_case(module, tmp, record + record, 2, {0: 2})
            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertFalse(report["ok"])
            self.assertNotEqual(report["final_result"], "pass")
            self.assertEqual(report["seed_selection_audit"]["expected_records"], 2)
            self.assertEqual(report["seed_selection_audit"]["actual_records"], 2)
            self.assertTrue(report["seed_selection_audit"]["reconciled"] is False)
            self.assertTrue(
                any(
                    diagnostic.startswith("duplicate_record:")
                    for diagnostic in report["seed_selection_audit"]["diagnostics"]
                )
            )

    def test_seed_audit_missing_required_field_fails_closed(self) -> None:
        module = self._load()
        fields = ("queue_id", "depth", "ss_cov_cnt", "ss_selected_cnt", "ss_prob")
        for field in fields:
            with self.subTest(field=field):
                with __import__("tempfile").TemporaryDirectory(prefix="seed-audit-field-") as tmp:
                    record = {
                        "queue_id": 0,
                        "depth": 1,
                        "ss_cov_cnt": 0,
                        "ss_selected_cnt": 1,
                        "ss_prob": 1,
                    }
                    del record[field]
                    layout = self._seed_audit_case(
                        module, tmp, json.dumps(record) + "\n", 1, {0: 1}
                    )
                    report = module.inspect_artifacts(layout, launch_returncode=0)
                    self.assertFalse(report["ok"])
                    self.assertNotEqual(report["final_result"], "pass")
                    self.assertFalse(report["seed_selection_audit"]["reconciled"])

    def test_seed_audit_non_finite_probability_fails_closed(self) -> None:
        module = self._load()
        for probability in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(probability=probability):
                with __import__("tempfile").TemporaryDirectory(prefix="seed-audit-nonfinite-") as tmp:
                    record = (
                        '{"queue_id":0,"depth":1,"ss_cov_cnt":0,'
                        f'"ss_selected_cnt":1,"ss_prob":{probability}'
                        '}\n'
                    )
                    layout = self._seed_audit_case(module, tmp, record, 1, {0: 1})
                    report = module.inspect_artifacts(layout, launch_returncode=0)
                    self.assertFalse(report["ok"])
                    self.assertNotEqual(report["final_result"], "pass")
                    self.assertIn(
                        "probability_nonfinite:1",
                        report["seed_selection_audit"]["diagnostics"],
                    )

    def test_seed_audit_negative_counter_fails_closed(self) -> None:
        module = self._load()
        for field, value in (
            ("queue_id", -1),
            ("ss_cov_cnt", -1),
            ("ss_selected_cnt", 0),
        ):
            with self.subTest(field=field):
                with __import__("tempfile").TemporaryDirectory(prefix="seed-audit-negative-") as tmp:
                    record = {
                        "queue_id": 0,
                        "depth": 1,
                        "ss_cov_cnt": 0,
                        "ss_selected_cnt": 1,
                        "ss_prob": 1,
                    }
                    record[field] = value
                    layout = self._seed_audit_case(
                        module, tmp, json.dumps(record) + "\n", 1, {0: 1}
                    )
                    report = module.inspect_artifacts(layout, launch_returncode=0)
                    self.assertFalse(report["ok"])
                    self.assertNotEqual(report["final_result"], "pass")
                    self.assertIn(
                        "integer_range:1",
                        report["seed_selection_audit"]["diagnostics"],
                    )

    def test_seed_audit_writer_error_state_fails_closed(self) -> None:
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="seed-audit-writer-state-") as tmp:
            record = '{"queue_id":0,"depth":1,"ss_cov_cnt":0,"ss_selected_cnt":1,"ss_prob":1}\n'
            layout = self._seed_audit_case(module, tmp, record, 1, {0: 1})
            stats = layout["afl_output"] / "fuzzer_stats"
            with stats.open("a", encoding="utf-8") as fh:
                fh.write("seed_audit_error_count : 1\nseed_audit_invalid : 1\n")
            report = module.inspect_artifacts(layout, launch_returncode=0)
            self.assertFalse(report["ok"])
            self.assertEqual(report["seed_selection_audit"]["error_count"], 1)
            self.assertTrue(report["seed_selection_audit"]["audit_invalid"])


class PostExecutionReadbackContractTest(unittest.TestCase):
    """Offline contract for the final, run-scoped Alfresco read-back."""

    def _load(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "post_execution_readback_runner_test", RUNNER_PATH
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _layout(self, module, tmp):
        layout = module.build_run_layout(Path(tmp) / "run", REPO_ROOT)
        layout["run_root"].mkdir(parents=True)
        layout["evidence"].mkdir()
        layout["afl_output"].mkdir()
        return layout

    def _execution(self, module, layout, *, valid_count=3, exec_seq=6):
        layout["probe"].write_text(json.dumps({"ncov_total": 1}), encoding="utf-8")
        layout["state_db"].write_text("[]", encoding="utf-8")
        layout["body_valid_stats"].write_text(
            json.dumps({"body_rule_pass": 1}), encoding="utf-8"
        )
        layout["status"].write_text(
            json.dumps({"exec_seq": exec_seq, "http_code": 200, "ts_ms": 123}),
            encoding="utf-8",
        )
        layout["status_seq"].write_text(str(exec_seq), encoding="utf-8")
        layout["state_trace"].write_text(
            json.dumps({"exec_seq": exec_seq, "state": "PUT /nodes|2xx", "state_id": "1", "new": 1}) + "\n",
            encoding="utf-8",
        )
        (layout["afl_output"] / "fuzzer_stats").write_text(
            f"nv_total_valid_exec : {valid_count}\n"
            "nv_mab_total_pulls : 0\n"
            "nv_mab_arm0_pulls : 0\n"
            "nv_mab_arm1_pulls : 0\n"
            "nv_mab_arm2_pulls : 0\n"
            "nv_mab_arm0_sum : 0\n"
            "nv_mab_arm1_sum : 0\n"
            "nv_mab_arm2_sum : 0\n"
            "nv_mab_arm0_pos : 0\n"
            "nv_mab_arm1_pos : 0\n"
            "nv_mab_arm2_pos : 0\n"
            "security_state_reward_src_seq : 0\n"
            "nv_mab_journal_error_count : 0\n"
            "nv_mab_journal_audit_invalid : 0\n"
            "ss_selected_sum : 0\n"
            "seed_audit_enabled : 1\n"
            "seed_audit_error_count : 0\n"
            "seed_audit_invalid : 0\n"
            "seed_audit_record_count : 0\n"
            "seed_audit_expected_selection_count : 0\n",
            encoding="utf-8",
        )
        layout["mab_journal"].touch()
        layout["evidence"].joinpath("executions.jsonl").touch()
        layout["seed_selection_audit"].touch()

    def _identity(self, module):
        return {
            "node_id": "11111111-2222-3333-4444-555555555555",
            "parent_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "nv-afl-levelc-metadata.txt",
        }

    def _client(self, module, *, code=200, payload=None, calls=None):
        identity = self._identity(module)

        class FakeClient:
            def get_node(self, node_id):
                if calls is not None:
                    calls.append(("GET", "preflight:" + node_id, None, True))
                return {
                    "id": identity["node_id"],
                    "parentId": identity["parent_id"],
                    "name": identity["name"],
                }

            def request(self, method, path, body=None, authenticated=True):
                if calls is not None:
                    calls.append((method, path, body, authenticated))
                return code, payload if payload is not None else {
                    "entry": {
                        "id": identity["node_id"],
                        "parentId": identity["parent_id"],
                        "name": identity["name"],
                        "properties": {
                            "cm:title": "secret title",
                            "cm:description": "secret description",
                        },
                    }
                }

        return FakeClient()

    def test_successful_post_run_readback_writes_run_scoped_artifact(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="readback-success-") as tmp:
            layout = self._layout(module, tmp)
            self._execution(module, layout)
            calls = []
            result = module.post_execution_readback(
                self._client(module, calls=calls),
                self._identity(module),
                layout,
            )
            path = layout["evidence"] / "readback.json"
            self.assertTrue(path.is_file())
            self.assertEqual(path.parent, layout["evidence"])
            self.assertEqual(calls[0][0], "GET")
            self.assertEqual(result["verdict"], "pass")
            self.assertTrue(result["identity_match"])
            self.assertTrue(result["parent_match"])
            artifact = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["schema_version"], 1)
            self.assertEqual(artifact["event"], "post_execution_readback")
            self.assertEqual(artifact["correlation"]["last_exec_seq"], 6)
            self.assertEqual(artifact["correlation"]["valid_execution_count"], 3)
            self.assertEqual(artifact["request"], {"method": "GET", "status": 200})
            self.assertTrue(artifact["privacy"]["raw_body_included"] is False)
            artifact_text = path.read_text(encoding="utf-8")
            self.assertNotIn(self._identity(module)["node_id"], artifact_text)
            self.assertNotIn("secret title", artifact_text)
            self.assertNotIn("secret description", artifact_text)
            self.assertNotIn("Authorization", artifact_text)

    def test_post_run_readback_occurs_after_launch_and_snapshot(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="readback-order-") as tmp:
            layout = self._layout(module, tmp)
            self._execution(module, layout)
            events = []
            original_parse = module.parse_final_execution_snapshot
            original_write = module.write_readback_artifact
            try:
                module.parse_final_execution_snapshot = lambda l: events.append("snapshot") or original_parse(l)
                module.write_readback_artifact = lambda l, p: events.append("write") or original_write(l, p)
                client = self._client(module, calls=[])
                result = module.post_execution_readback(
                    client, self._identity(module), layout, event_log=events
                )
            finally:
                module.parse_final_execution_snapshot = original_parse
                module.write_readback_artifact = original_write
            self.assertEqual(result["verdict"], "pass")
            self.assertEqual(events, ["snapshot", "readback_get", "write"])

    def test_zero_valid_execution_does_not_require_readback(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="readback-zero-") as tmp:
            layout = self._layout(module, tmp)
            self._execution(module, layout, valid_count=0)
            client = self._client(module)
            result = module.post_execution_readback(client, self._identity(module), layout)
            self.assertFalse(result["applicable"])
            self.assertFalse(result["attempted"])
            self.assertFalse(result["present"])
            self.assertEqual(result["verdict"], "not_applicable")
            self.assertFalse((layout["evidence"] / "readback.json").exists())

    def test_missing_or_invalid_final_valid_stats_are_snapshot_invalid(self):
        module = self._load()
        import tempfile

        cases = {
            "missing_file": None,
            "missing_field": "execs_done : 1\n",
            "non_integer": "nv_total_valid_exec : not-an-integer\n",
            "negative": "nv_total_valid_exec : -1\n",
        }
        for case, stats_text in cases.items():
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory(prefix="readback-final-stats-") as tmp:
                    layout = self._layout(module, tmp)
                    if stats_text is not None:
                        (layout["afl_output"] / "fuzzer_stats").write_text(
                            stats_text, encoding="utf-8"
                        )
                    calls = []
                    result = module.post_execution_readback(
                        self._client(module, calls=calls), self._identity(module), layout
                    )
                    self.assertTrue(result["applicable"])
                    self.assertFalse(result["attempted"])
                    self.assertEqual(result["verdict"], "final_snapshot_invalid")
                    self.assertFalse(result["reconciled"])
                    self.assertEqual(calls, [])

    def test_inspect_rejects_malformed_readback_artifact_content(self):
        module = self._load()
        import copy
        import tempfile

        mutators = {
            "damaged_json": None,
            "missing_required": lambda artifact: artifact.pop("ordering"),
            "unknown_field": lambda artifact: artifact.update({"unexpected": True}),
            "wrong_type": lambda artifact: artifact["request"].update({"status": "200"}),
            "invalid_schema": lambda artifact: artifact.update({"schema_version": 999}),
            "invalid_event": lambda artifact: artifact.update({"event": "wrong"}),
            "identity_mismatch": lambda artifact: artifact["target"].update(
                {"node_identity": "sha256:node:different"}
            ),
            "correlation_mismatch": lambda artifact: artifact["correlation"].update(
                {"last_exec_seq": 999}
            ),
        }
        for case, mutate in mutators.items():
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory(prefix="readback-artifact-invalid-") as tmp:
                    layout = self._layout(module, tmp)
                    layout["target_config"].write_text("{}", encoding="utf-8")
                    layout["task"].write_text("{}", encoding="utf-8")
                    layout["seed_dir"].mkdir()
                    layout["seed"].write_text("{}", encoding="utf-8")
                    layout["err_dir"].mkdir()
                    self._execution(module, layout)
                    readback = module.post_execution_readback(
                        self._client(module), self._identity(module), layout
                    )
                    artifact_path = layout["readback"]
                    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
                    if mutate is None:
                        artifact_path.write_text("{not-json", encoding="utf-8")
                    else:
                        changed = copy.deepcopy(artifact)
                        mutate(changed)
                        artifact_path.write_text(json.dumps(changed), encoding="utf-8")

                    report = module.inspect_artifacts(
                        layout, launch_returncode=0, readback=readback
                    )
                    self.assertFalse(report["ok"])
                    self.assertEqual(report["final_result"], "artifact_contract_failed")
                    self.assertIn("readback", report["missing_required"])
                    self.assertFalse(report["readback"]["artifact_valid"])
                    self.assertEqual(
                        report["readback"]["artifact_diagnostic"],
                        "readback_artifact_invalid",
                    )

    def test_preflight_identity_get_is_not_post_run_readback(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="readback-preflight-") as tmp:
            layout = self._layout(module, tmp)
            calls = []
            client = self._client(module, calls=calls)
            identity = self._identity(module)
            module.read_only_target_identity(client, identity["node_id"])
            self._execution(module, layout)
            module.post_execution_readback(client, identity, layout)
            self.assertEqual(calls[0][0], "GET")
            self.assertEqual(calls[1][0], "GET")
            self.assertNotEqual(calls[0][1], calls[1][1])

    def test_readback_failure_mapping_fails_closed(self):
        module = self._load()
        import tempfile

        cases = (
            (401, None, "auth_failed"),
            (403, None, "auth_failed"),
            (404, None, "target_not_found"),
            (500, None, "readback_service_error"),
            (503, None, "readback_service_error"),
            (200, {"entry": {"id": "wrong", "parentId": self._identity(module)["parent_id"], "name": self._identity(module)["name"]}}, "identity_mismatch"),
            (200, {"entry": {"id": self._identity(module)["node_id"], "parentId": self._identity(module)["parent_id"], "name": "wrong"}}, "identity_mismatch"),
            (200, {"entry": {"id": self._identity(module)["node_id"], "parentId": "wrong", "name": self._identity(module)["name"]}}, "parent_mismatch"),
            (200, {"entry": {"id": self._identity(module)["node_id"], "parentId": self._identity(module)["parent_id"]}}, "identity_unavailable"),
            (200, {"not_entry": True}, "malformed_response"),
        )
        for code, payload, verdict in cases:
            with self.subTest(code=code, verdict=verdict):
                with tempfile.TemporaryDirectory(prefix="readback-map-") as tmp:
                    layout = self._layout(module, tmp)
                    self._execution(module, layout)
                    result = module.post_execution_readback(
                        self._client(module, code=code, payload=payload),
                        self._identity(module),
                        layout,
                    )
                    self.assertEqual(result["verdict"], verdict)
                    self.assertFalse(result["reconciled"])

    def test_readback_timeout_and_unreachable_are_distinct(self):
        module = self._load()
        import tempfile

        for error, verdict in ((TimeoutError("late"), "readback_timeout"), (ConnectionError("down"), "readback_unreachable")):
            with self.subTest(verdict=verdict):
                with tempfile.TemporaryDirectory(prefix="readback-network-") as tmp:
                    layout = self._layout(module, tmp)
                    self._execution(module, layout)

                    class FailingClient:
                        def request(self, *args, **kwargs):
                            raise error

                    result = module.post_execution_readback(
                        FailingClient(), self._identity(module), layout
                    )
                    self.assertEqual(result["verdict"], verdict)

    def test_attempted_readback_failure_writes_valid_failure_artifact(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="readback-failure-artifact-") as tmp:
            layout = self._layout(module, tmp)
            self._execution(module, layout)

            class FailingClient:
                def request(self, *args, **kwargs):
                    raise ConnectionError("down")

            result = module.post_execution_readback(
                FailingClient(), self._identity(module), layout
            )
            artifact_path = layout["readback"]
            self.assertTrue(result["attempted"])
            self.assertEqual(result["verdict"], "readback_unreachable")
            self.assertTrue(artifact_path.is_file())
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertTrue(module.validate_readback_artifact(artifact))
            self.assertTrue(module.reconcile_readback_artifact(artifact))
            self.assertNotEqual(result["verdict"], "pass")
            self.assertFalse(result["reconciled"])

    def test_readback_artifact_write_failure_fails_closed(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="readback-write-fail-") as tmp:
            layout = self._layout(module, tmp)
            self._execution(module, layout)
            original = module.os.replace
            module.os.replace = lambda *args: (_ for _ in ()).throw(OSError("disk"))
            try:
                result = module.post_execution_readback(
                    self._client(module), self._identity(module), layout
                )
            finally:
                module.os.replace = original
            self.assertEqual(result["verdict"], "artifact_write_failed")
            self.assertFalse(result["present"])

    def test_readback_artifact_is_atomic_and_never_uses_shared_tmp(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="readback-atomic-") as tmp:
            layout = self._layout(module, tmp)
            self._execution(module, layout)
            module.post_execution_readback(self._client(module), self._identity(module), layout)
            self.assertTrue((layout["evidence"] / "readback.json").is_file())
            self.assertFalse(Path("/tmp/readback.json").exists())
            self.assertFalse(Path("/tmp/nv_readback.json").exists())
            self.assertEqual(list(layout["evidence"].glob(".readback-*.tmp")), [])

    def test_readback_does_not_change_exec_seq_or_feedback_counters(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="readback-budget-") as tmp:
            layout = self._layout(module, tmp)
            self._execution(module, layout)
            before_status = layout["status"].read_text(encoding="utf-8")
            before_stats = (layout["afl_output"] / "fuzzer_stats").read_text(encoding="utf-8")
            before_journal = layout["mab_journal"].read_bytes()
            before_seed_audit = layout["seed_selection_audit"].read_bytes()
            module.post_execution_readback(self._client(module), self._identity(module), layout)
            self.assertEqual(layout["status"].read_text(encoding="utf-8"), before_status)
            self.assertEqual((layout["afl_output"] / "fuzzer_stats").read_text(encoding="utf-8"), before_stats)
            self.assertEqual(layout["mab_journal"].read_bytes(), before_journal)
            self.assertEqual(layout["seed_selection_audit"].read_bytes(), before_seed_audit)

    def test_readback_schema_parser_rejects_unknown_and_missing_fields(self):
        module = self._load()
        valid = {
            "schema_version": 1,
            "event": "post_execution_readback",
            "correlation": {"mode": "final_run_state", "last_exec_seq": 6, "valid_execution_count": 3},
            "target": {"node_identity": "sha256:node:x", "parent_identity": "sha256:parent:y", "name": "target"},
            "request": {"method": "GET", "status": 200},
            "result": {"metadata_hash": None, "field_presence": [], "version_label": None},
            "ordering": {"run_completed": True, "timestamp_ms": 1},
            "privacy": {"credentials_included": False, "authorization_included": False, "raw_body_included": False},
        }
        self.assertTrue(module.validate_readback_artifact(valid))
        unknown = dict(valid)
        unknown["unexpected"] = True
        self.assertFalse(module.validate_readback_artifact(unknown))
        missing = dict(valid)
        del missing["ordering"]
        self.assertFalse(module.validate_readback_artifact(missing))
        self.assertTrue(module.reconcile_readback_artifact(valid))

    def test_artifact_report_keeps_readback_and_audits_independent(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="readback-report-") as tmp:
            layout = self._layout(module, tmp)
            self._execution(module, layout)
            readback = module.post_execution_readback(
                self._client(module, code=500), self._identity(module), layout
            )
            report = module.inspect_artifacts(layout, launch_returncode=0, readback=readback)
            self.assertIn("readback", report)
            self.assertEqual(report["readback"]["verdict"], "readback_service_error")
            self.assertIn("mab_journal", report)
            self.assertIn("seed_selection_audit", report)
            self.assertEqual(report["launch_returncode"], 0)
            self.assertEqual(report["final_result"], "artifact_contract_failed")

    def test_readback_failure_does_not_override_launch_failure(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="readback-precedence-") as tmp:
            layout = self._layout(module, tmp)
            self._execution(module, layout)
            readback = module.post_execution_readback(
                self._client(module, code=500), self._identity(module), layout
            )
            report = module.inspect_artifacts(layout, launch_returncode=124, readback=readback)
            self.assertEqual(report["final_result"], "timeout")
            self.assertEqual(report["launch_returncode"], 124)
            self.assertEqual(report["readback"]["verdict"], "readback_service_error")

    def test_main_runs_final_readback_after_launch_and_snapshot(self):
        module = self._load()
        import contextlib
        import io
        import tempfile

        identity = self._identity(module)
        events = []

        class FakeClient:
            def list_children(self, parent_id):
                if parent_id == "-my-":
                    return [{
                        "id": identity["parent_id"],
                        "name": "NV_AFL_REAL_PLATFORM_CALIBRATION",
                        "isFolder": True,
                        "isFile": False,
                    }]
                if parent_id == identity["parent_id"]:
                    return [{
                        "id": identity["node_id"],
                        "parentId": identity["parent_id"],
                        "name": identity["name"],
                        "isFolder": False,
                        "isFile": True,
                    }]
                raise AssertionError(parent_id)

            def get_node(self, node_id):
                events.append("preflight_get")
                return {
                    "id": node_id,
                    "parentId": identity["parent_id"],
                    "name": identity["name"],
                }

            def request(self, method, path, body=None, authenticated=True):
                events.append("readback_get")
                self.assertions.append((method, path, body, authenticated))
                return 200, {"entry": {
                    "id": identity["node_id"],
                    "parentId": identity["parent_id"],
                    "name": identity["name"],
                    "properties": {"cm:title": "private", "cm:description": "private"},
                }}

            assertions = []

        client = FakeClient()
        module.build_alfresco_client = lambda base, credentials: client
        module.perform_preflight = lambda current: events.append("preflight") or {"ok": True}

        def fake_render(node_id, output):
            output.write_text(json.dumps({
                "endpoints": [{"name": "metadata_update", "method": "PUT", "path": "/nodes/" + node_id}],
            }), encoding="utf-8")
            return output

        module.render_runtime_target_config = fake_render

        def fake_launch(layout, config_path, child_env, **kwargs):
            events.append("launch")
            self._execution(module, layout, valid_count=3, exec_seq=6)
            return 0

        module.launch_bounded_afl = fake_launch
        original = (os.environ.get("ALFRESCO_USER"), os.environ.get("ALFRESCO_PASS"))
        os.environ["ALFRESCO_USER"] = "offline-user"
        os.environ["ALFRESCO_PASS"] = "offline-pass"
        try:
            with tempfile.TemporaryDirectory(prefix="readback-main-") as tmp:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = module.main(["--run-root", tmp])
                report = json.loads(
                    (Path(tmp) / "evidence" / "artifact_report.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(rc, 0, f"{err.getvalue()} report={report!r}")
                self.assertEqual(events, ["preflight", "preflight_get", "launch", "readback_get"])
                self.assertEqual(report["readback"]["verdict"], "pass")
                self.assertTrue(report["readback"]["reconciled"])
                self.assertEqual(report["runner"]["exit_code"], 0)
                self.assertEqual(report["runner"]["exit_status"], "success")
                self.assertTrue(report["runner"]["recorded"])
                self.assertEqual(report["launch_returncode"], 0)
                self.assertEqual(report["readback_verdict"], "pass")
                self.assertEqual(report["artifact_final_result"], "pass")
                self.assertTrue((Path(tmp) / "evidence" / "readback.json").is_file())
                self.assertEqual(client.assertions[0][0], "GET")
                self.assertIn(identity["node_id"], client.assertions[0][1])
        finally:
            if original[0] is None:
                os.environ.pop("ALFRESCO_USER", None)
            else:
                os.environ["ALFRESCO_USER"] = original[0]
            if original[1] is None:
                os.environ.pop("ALFRESCO_PASS", None)
            else:
                os.environ["ALFRESCO_PASS"] = original[1]


class RunnerExitEvidenceContractTest(unittest.TestCase):
    """Offline contracts for the bounded runner's own process result."""

    def _load(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("runner_exit_evidence_test", RUNNER_PATH)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _configure_main(self, module, *, launch_returncode=0, materialize=True,
                        readback=None, readback_exception=None):
        identity = {
            "node_id": "11111111-2222-3333-4444-555555555555",
            "parent_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "nv-afl-levelc-metadata.txt",
        }

        class FakeClient:
            def list_children(self, parent_id):
                if parent_id == "-my-":
                    return [{"id": identity["parent_id"], "name": "NV_AFL_REAL_PLATFORM_CALIBRATION", "isFolder": True, "isFile": False}]
                if parent_id == identity["parent_id"]:
                    return [{"id": identity["node_id"], "parentId": identity["parent_id"], "name": identity["name"], "isFolder": False, "isFile": True}]
                raise AssertionError(parent_id)

        module.build_alfresco_client = lambda base, credentials: FakeClient()
        module.perform_preflight = lambda client: {"ok": True}
        module.read_only_target_identity = lambda client, node_id: {
            "id": identity["node_id"], "parentId": identity["parent_id"], "name": identity["name"],
        }

        def fake_render(node_id, output):
            output.write_text(json.dumps({"endpoints": [{"name": "metadata_update", "method": "PUT", "path": "/nodes/" + node_id}]}), encoding="utf-8")
            return output

        def fake_launch(layout, config_path, child_env, **kwargs):
            if materialize:
                _materialize_execution_artifacts(layout)
            return launch_returncode

        module.render_runtime_target_config = fake_render
        module.launch_bounded_afl = fake_launch
        if readback_exception is not None:
            def failing_readback(*args, **kwargs):
                raise readback_exception
            module.post_execution_readback = failing_readback
        elif readback is not None:
            module.post_execution_readback = lambda *args, **kwargs: readback

    def _run(self, module, tmp):
        import contextlib
        import io

        original = (os.environ.get("ALFRESCO_USER"), os.environ.get("ALFRESCO_PASS"))
        os.environ["ALFRESCO_USER"] = "offline-user"
        os.environ["ALFRESCO_PASS"] = "offline-pass"
        try:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                return module.main(["--run-root", str(Path(tmp).resolve())]), stderr.getvalue()
        finally:
            for key, value in zip(("ALFRESCO_USER", "ALFRESCO_PASS"), original):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    @staticmethod
    def _readback_failure(verdict="readback_service_error"):
        return {
            "enabled": True, "applicable": True, "attempted": True,
            "present": False, "correlation": "moderate", "status": 500,
            "identity_match": False, "parent_match": False, "verdict": verdict,
            "reconciled": False, "valid_execution_count": 1,
        }

    def test_successful_runner_records_runner_exit_code(self):
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="runner-success-") as tmp:
            self._configure_main(module)
            rc, stderr = self._run(module, tmp)
            report = json.loads((Path(tmp) / "evidence" / "artifact_report.json").read_text())
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(report["runner"], {"exit_code": 0, "exit_status": "success", "recorded": True})
            self.assertEqual(report["launch_returncode"], 0)
            self.assertEqual(report["readback_verdict"], "not_applicable")
            self.assertEqual(report["artifact_final_result"], "pass")

    def test_launch_returncode_is_not_runner_exit_code(self):
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="runner-launch-") as tmp:
            self._configure_main(module, launch_returncode=7, materialize=False)
            rc, stderr = self._run(module, tmp)
            report = json.loads((Path(tmp) / "evidence" / "artifact_report.json").read_text())
            self.assertEqual(rc, 7, stderr)
            self.assertEqual(report["launch_returncode"], 7)
            self.assertEqual(report["runner"]["exit_code"], 7)
            self.assertEqual(report["runner"]["exit_status"], "launch_failed")

    def test_runner_exit_preserves_launch_failure(self):
        self.test_launch_returncode_is_not_runner_exit_code()

    def test_readback_failure_records_nonzero_runner_result(self):
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="runner-readback-") as tmp:
            self._configure_main(module, readback=self._readback_failure())
            rc, stderr = self._run(module, tmp)
            report = json.loads((Path(tmp) / "evidence" / "artifact_report.json").read_text())
            self.assertEqual(rc, module.READBACK_CONTRACT_FAILURE, stderr)
            self.assertEqual(report["launch_returncode"], 0)
            self.assertEqual(report["readback_verdict"], "readback_service_error")
            self.assertEqual(report["runner"]["exit_code"], module.READBACK_CONTRACT_FAILURE)
            self.assertEqual(report["runner"]["exit_status"], "readback_failed")
            self.assertNotEqual(report["artifact_final_result"], "pass")

    def test_artifact_failure_records_nonzero_runner_result(self):
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="runner-artifact-") as tmp:
            self._configure_main(module, materialize=False)
            rc, stderr = self._run(module, tmp)
            report = json.loads((Path(tmp) / "evidence" / "artifact_report.json").read_text())
            self.assertEqual(rc, module.ARTIFACT_CONTRACT_FAILURE, stderr)
            self.assertEqual(report["launch_returncode"], 0)
            self.assertEqual(report["runner"]["exit_status"], "artifact_contract_failed")
            self.assertEqual(report["artifact_final_result"], "artifact_contract_failed")

    def test_timeout_records_runner_result(self):
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="runner-timeout-") as tmp:
            self._configure_main(module, launch_returncode=124, materialize=False)
            rc, stderr = self._run(module, tmp)
            report = json.loads((Path(tmp) / "evidence" / "artifact_report.json").read_text())
            self.assertEqual(rc, 124, stderr)
            self.assertEqual(report["launch_returncode"], 124)
            self.assertEqual(report["runner"]["exit_code"], 124)
            self.assertEqual(report["runner"]["exit_status"], "timeout")

    def test_missing_final_stats_records_artifact_failure(self):
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="runner-missing-stats-") as tmp:
            self._configure_main(module)
            # Keep this path entirely fake: the launch collaborator is replaced
            # and does not invoke the production process launcher.
            module.launch_bounded_afl = lambda layout, config_path, child_env, **kwargs: (
                _materialize_execution_artifacts(layout, include_fuzzer_stats=False) or 0
            )
            rc, stderr = self._run(module, tmp)
            report = json.loads((Path(tmp) / "evidence" / "artifact_report.json").read_text())
            self.assertNotEqual(rc, 0, stderr)
            self.assertEqual(report["launch_returncode"], 0, stderr)
            self.assertEqual(report["runner"]["exit_code"], module.ARTIFACT_CONTRACT_FAILURE)
            self.assertEqual(report["artifact_final_result"], "artifact_contract_failed")

    def test_malformed_final_stats_records_artifact_failure(self):
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="runner-malformed-stats-") as tmp:
            self._configure_main(module)

            def launch_with_bad_stats(layout, config_path, child_env, **kwargs):
                _materialize_execution_artifacts(layout)
                (layout["afl_output"] / "fuzzer_stats").write_text(
                    "nv_total_valid_exec : malformed\n", encoding="utf-8"
                )
                return 0

            module.launch_bounded_afl = launch_with_bad_stats
            rc, stderr = self._run(module, tmp)
            report = json.loads((Path(tmp) / "evidence" / "artifact_report.json").read_text())
            self.assertNotEqual(rc, 0, stderr)
            self.assertEqual(report["launch_returncode"], 0)
            self.assertEqual(report["runner"]["exit_code"], module.ARTIFACT_CONTRACT_FAILURE)
            self.assertEqual(report["artifact_final_result"], "artifact_contract_failed")

    def test_runner_result_is_run_scoped(self):
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="runner-scope-") as tmp:
            layout = module.build_run_layout(Path(tmp) / "run", REPO_ROOT)
            self.assertTrue(module.runner_result_path(layout).is_relative_to(layout["run_root"]))
            self.assertEqual(module.runner_result_path(layout), layout["evidence"] / "artifact_report.json")

    def test_runner_result_is_atomic(self):
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="runner-atomic-") as tmp:
            layout = module.build_run_layout(Path(tmp) / "run", REPO_ROOT)
            layout["evidence"].mkdir(parents=True)
            report = {"runner": {"exit_code": 0, "exit_status": "success", "recorded": True}}
            module.write_artifact_report(layout, report)
            self.assertEqual(list(layout["evidence"].glob(".artifact-report-*.tmp")), [])
            self.assertEqual(json.loads(module.runner_result_path(layout).read_text()), report)

    def test_runner_result_contains_no_secrets(self):
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="runner-privacy-") as tmp:
            self._configure_main(module)
            rc, stderr = self._run(module, tmp)
            self.assertEqual(rc, 0, stderr)
            text = (Path(tmp) / "evidence" / "artifact_report.json").read_text()
            for secret in (
                "offline-user", "offline-pass", "password", "Authorization",
                "Basic ", "Bearer ", "raw_body", "response_body",
            ):
                self.assertNotIn(secret, text)

    def test_missing_runner_result_is_not_treated_as_success(self):
        module = self._load()
        self.assertFalse(module.validate_runner_result({}))
        self.assertFalse(module.validate_runner_result({"runner": {"exit_code": 0, "exit_status": "success"}}))
        self.assertFalse(module.validate_runner_result({"runner": {"exit_code": 0, "exit_status": "runner_failed", "recorded": True}}))

    def test_handled_exception_records_runner_result(self):
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="runner-exception-") as tmp:
            self._configure_main(module, readback_exception=RuntimeError("HANDLED_FAILURE"))
            rc, stderr = self._run(module, tmp)
            report = json.loads((Path(tmp) / "evidence" / "artifact_report.json").read_text())
            self.assertEqual(rc, module.READBACK_CONTRACT_FAILURE, stderr)
            self.assertTrue(report["runner"]["recorded"])
            self.assertEqual(report["runner"]["exit_code"], module.READBACK_CONTRACT_FAILURE)
            self.assertEqual(report["runner"]["exit_status"], "readback_failed")
            self.assertEqual(report["launch_returncode"], 0)

    def test_runner_result_write_failure_is_not_claimed_recorded(self):
        module = self._load()
        with __import__("tempfile").TemporaryDirectory(prefix="runner-write-failure-") as tmp:
            self._configure_main(module)
            original = module.write_artifact_report
            writes = 0

            def fail_final_write(*args, **kwargs):
                nonlocal writes
                writes += 1
                if writes > 1:
                    raise OSError("disk")
                return original(*args, **kwargs)

            module.write_artifact_report = fail_final_write
            try:
                rc, stderr = self._run(module, tmp)
            finally:
                module.write_artifact_report = original
            self.assertNotEqual(rc, 0)
            self.assertIn("NOT_RECORDED", stderr)
            report = json.loads(
                (Path(tmp) / "evidence" / "artifact_report.json").read_text()
            )
            self.assertEqual(report["runner"]["exit_code"], None)
            self.assertFalse(report["runner"]["recorded"])
            self.assertEqual(report["runner"]["exit_status"], "evidence_unavailable")


class ManifestControlledMultiSeedTest(unittest.TestCase):
    def _load(self):
        return _load_runner_module("alfresco_manifest_multi_seed_test")

    def _write_seed_set(self, root, names=("seed-a.http", "seed-b.http", "seed-c.http")):
        source = Path(root) / "source"
        manifest = Path(root) / "manifest.txt"
        source.mkdir()
        manifest.write_text("".join(f"{name}\n" for name in names), encoding="utf-8")
        payloads = {}
        for index, name in enumerate(names):
            body = json.dumps(
                {
                    "properties": {
                        "cm:title": f"seed-{index}",
                        "cm:description": f"desc-{index}",
                    }
                },
                separators=(",", ":"),
            ).encode("ascii")
            header = (
                f"PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/node-{index} HTTP/1.1\\r\\n"
                "Host: 127.0.0.1\\r\\n"
                "Content-Type: application/json\\r\\n"
                f"Content-Length: {len(body)}\\r\\n"
                "\\r\\n"
            ).encode("ascii")
            payload = header + body
            (source / name).write_bytes(payload)
            payloads[name] = payload
        return source, manifest, payloads

    def test_manifest_materialization_preserves_exact_bytes_and_excludes_extras(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="alfresco-manifest-seeds-") as tmp:
            source, manifest, payloads = self._write_seed_set(tmp)
            (source / "extra.http").write_bytes(b"extra")
            destination = Path(tmp) / "run" / "seed_input"
            materialized = module.materialize_manifest_seed_dir(
                manifest, source, destination
            )
            self.assertEqual(
                sorted(path.name for path in materialized.iterdir()),
                sorted(payloads),
            )
            for name, payload in payloads.items():
                self.assertEqual((materialized / name).read_bytes(), payload)
                self.assertTrue((materialized / name).is_file())
                self.assertFalse((materialized / name).is_symlink())

    def test_manifest_requires_at_least_three_regular_files(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="alfresco-manifest-min-") as tmp:
            source, manifest, _ = self._write_seed_set(
                tmp, ("seed-a.http", "seed-b.http")
            )
            with self.assertRaisesRegex(ValueError, "^MANIFEST_TOO_FEW_SEEDS$"):
                module.materialize_manifest_seed_dir(
                    manifest, source, Path(tmp) / "run" / "seed_input"
                )

    def test_manifest_rejects_symlink_source(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="alfresco-manifest-link-") as tmp:
            source, manifest, _ = self._write_seed_set(tmp)
            outside = Path(tmp) / "outside.http"
            outside.write_bytes(b"outside")
            (source / "seed-b.http").unlink()
            (source / "seed-b.http").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "^MANIFEST_SEED_NOT_REGULAR$"):
                module.materialize_manifest_seed_dir(
                    manifest, source, Path(tmp) / "run" / "seed_input"
                )

    def test_manifest_task_payload_records_authority(self):
        module = self._load()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="alfresco-manifest-task-") as tmp:
            task = module.build_task_payload(
                Path(tmp) / "seed_input",
                max_test_cases=3,
                time_budget=30,
                seed_source="manifest",
                seed_manifest=Path(tmp) / "manifest.txt",
            )
            self.assertEqual(task["seed_source"], "manifest")
            self.assertEqual(task["seed_manifest"], str(Path(tmp, "manifest.txt").resolve()))


if __name__ == "__main__":
    unittest.main()
