"""Offline contracts for the bounded Alfresco real-feedback orchestrator."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
import hashlib
import json




REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py"


class ExistingDedicatedResourceResolutionTest(unittest.TestCase):
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
                "run_root",
                "target_config",
                "seed",
                "status",
                "afl_output",
                "evidence",
            }
            self.assertEqual(set(layout), expected_keys)

            self.assertEqual(layout["run_root"], run_root)
            self.assertEqual(layout["target_config"], run_root / "target.json")
            self.assertEqual(layout["seed"], run_root / "seed.http")
            self.assertEqual(layout["status"], run_root / "nv_http_status.json")
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


if __name__ == "__main__":
    unittest.main()
