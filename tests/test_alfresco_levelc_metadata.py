"""Alfresco Level-C metadata-update path: committed template + runtime launcher.

Scope note.  These are *offline* contract tests over synthetic fixtures.  They
prove the containment and resolution contract of the Level-C launcher; they do
not talk to a real Alfresco, and nothing here is a fuzzing campaign.

The real-service part of Level-C (authenticated preflight, production-harness
smoke, metadata read-back) is driven by the launcher itself and recorded as
evidence -- deliberately not as a unit test, so the suite stays hermetic.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from tests.test_v071_exec_seq import LocalServer, free_port

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "targets" / "alfresco_metadata_update.json"

_spec = importlib.util.spec_from_file_location(
    "alfresco_levelc_launcher_under_test",
    REPO_ROOT / "scripts" / "run_alfresco_levelc_metadata.py",
)
launcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(launcher)

_hspec = importlib.util.spec_from_file_location(
    "nv_http_harness_for_levelc", REPO_ROOT / "nv_http_harness.py"
)
harness = importlib.util.module_from_spec(_hspec)
_hspec.loader.exec_module(harness)

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

FOLDER = launcher.DEDICATED_FOLDER_NAME
FILENAME = launcher.DEDICATED_FILE_NAME
FOLDER_ID = "11111111-2222-3333-4444-555555555555"
FILE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FOREIGN_ID = "99999999-8888-7777-6666-555555555555"


def entry(node_id: str, name: str, *, is_folder: bool, parent_id: str = "",
          aspects=None) -> dict:
    return {
        "id": node_id,
        "name": name,
        "isFolder": is_folder,
        "isFile": not is_folder,
        "nodeType": "cm:folder" if is_folder else "cm:content",
        "parentId": parent_id,
        "aspectNames": list(aspects or []),
        "properties": {},
    }


class FakeClient:
    """Duck-typed stand-in for the launcher's Alfresco client.

    Children are keyed by parent id, so a node that lives somewhere else is
    simply not reachable through the dedicated folder -- the same containment
    the real API gives us.
    """

    def __init__(self, children: dict | None = None):
        self.children = {k: list(v) for k, v in (children or {}).items()}
        self.created: list[tuple[str, str, str]] = []
        self.updates: list[tuple[str, dict]] = []

    def list_children(self, parent_id: str) -> list:
        return list(self.children.get(parent_id, []))

    def create_child(self, parent_id: str, name: str, node_type: str) -> dict:
        self.created.append((parent_id, name, node_type))
        new_id = "cccccccc-0000-0000-0000-%012d" % len(self.created)
        made = entry(new_id, name, is_folder=(node_type == "cm:folder"),
                     parent_id=parent_id)
        self.children.setdefault(parent_id, []).append(made)
        return made

    def get_node(self, node_id: str) -> dict:
        for kids in self.children.values():
            for item in kids:
                if item["id"] == node_id:
                    return item
        raise launcher.LevelCAbort(f"node not found: {node_id}")

    def update_node(self, node_id: str, body: dict) -> dict:
        self.updates.append((node_id, body))
        return self.get_node(node_id)


_DEFAULT = object()


def populated(*, folders=_DEFAULT, files=_DEFAULT) -> FakeClient:
    """The happy-path listing, with either level overridable -- including to []."""
    root = ([entry(FOLDER_ID, FOLDER, is_folder=True,
                   parent_id=launcher.DEDICATED_PARENT)]
            if folders is _DEFAULT else list(folders))
    kids = ([entry(FILE_ID, FILENAME, is_folder=False, parent_id=FOLDER_ID)]
            if files is _DEFAULT else list(files))
    return FakeClient({launcher.DEDICATED_PARENT: root, FOLDER_ID: kids})


# --------------------------------------------------------------------------
# TEST 1-3: the committed target template
# --------------------------------------------------------------------------
class CommittedTemplateTest(unittest.TestCase):
    def load(self) -> dict:
        return json.loads(TEMPLATE.read_text(encoding="utf-8"))

    def test_template_exists_and_parses(self) -> None:
        self.assertTrue(TEMPLATE.is_file(), f"missing committed template: {TEMPLATE}")
        self.assertIsInstance(self.load(), dict)

    def test_template_lives_in_the_committed_tree_and_is_not_ignored(self) -> None:
        """It is a committed artifact, not a run-scoped one.

        Asserted as "inside the tree and not git-ignored" rather than
        "already tracked": this round deliberately ends with COMMIT = NO, so
        requiring an index entry would test the round's git policy instead of
        the template's contract.
        """
        import subprocess
        rel = TEMPLATE.relative_to(REPO_ROOT)
        self.assertEqual(rel.parts[0], "targets")
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(rel)],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertNotEqual(ignored.returncode, 0, "template is git-ignored")

    def test_template_carries_no_concrete_node_uuid(self) -> None:
        found = UUID_RE.findall(TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(found, [], f"concrete node UUID committed: {found}")

    def test_template_carries_no_credential_or_authorization_literal(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        lowered = text.lower()
        for banned in ("basic ", "bearer ", "authorization\":", "password\":",
                       "username\":", "\"secret\"", "admin:"):
            self.assertNotIn(banned, lowered, f"credential-shaped literal: {banned}")

    def test_template_is_clean_under_the_active_secret_scanner(self) -> None:
        from scripts.secret_scan import scan_paths

        result = scan_paths([TEMPLATE], required=True)
        self.assertEqual(result["real_secret_findings"], 0, result["findings"])
        self.assertEqual(result["status"], "PASS")

    def test_auth_contract_references_only_the_two_env_names(self) -> None:
        auth = self.load()["auth"]
        self.assertEqual(auth.get("type"), "basic")
        self.assertEqual(auth.get("username_env"), "ALFRESCO_USER")
        self.assertEqual(auth.get("password_env"), "ALFRESCO_PASS")
        self.assertEqual(set(auth) - {"type", "header"},
                         {"username_env", "password_env"})

    def test_template_auth_block_is_accepted_by_the_production_harness(self) -> None:
        cfg = self.load()
        with mock.patch.dict(os.environ,
                             {"ALFRESCO_USER": "fixture-user",
                              "ALFRESCO_PASS": "fixture-" + "credential"},
                             clear=True):
            headers = harness.apply_auth_headers(cfg, {})
        self.assertTrue(headers["Authorization"].startswith("Basic "))

    def test_template_auth_is_fail_closed_without_runtime_credentials(self) -> None:
        cfg = self.load()
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                harness.apply_auth_headers(cfg, {})

    def test_template_declares_the_metadata_update_put_endpoint(self) -> None:
        cfg = self.load()
        self.assertEqual(cfg.get("body_only_mode"), 1)
        self.assertEqual(cfg.get("default_endpoint"), "metadata_update")
        with mock.patch.dict(os.environ, {"NV_TARGET_CONFIG": str(TEMPLATE)}, clear=True):
            loaded = harness.load_target_config()
        method, path = harness.get_named_endpoint(loaded, "metadata_update")
        self.assertEqual(method, "PUT")
        self.assertTrue(
            path.startswith("/alfresco/api/-default-/public/alfresco/versions/1/nodes/"),
            f"unexpected Alfresco node path: {path}",
        )
        self.assertTrue(path.endswith(launcher.NODE_ID_PLACEHOLDER),
                        "template must end in the node-id placeholder")


# --------------------------------------------------------------------------
# TEST 4-6: credential contract
# --------------------------------------------------------------------------
class CredentialGateTest(unittest.TestCase):
    def test_both_credentials_present_is_accepted(self) -> None:
        user, password = launcher.require_credentials(
            {"ALFRESCO_USER": "u", "ALFRESCO_PASS": "p"}
        )
        self.assertEqual((user, password), ("u", "p"))

    def test_missing_user_aborts(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.require_credentials({"ALFRESCO_PASS": "p"})

    def test_missing_password_aborts(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.require_credentials({"ALFRESCO_USER": "u"})

    def test_whitespace_only_user_aborts(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.require_credentials({"ALFRESCO_USER": "  \t ", "ALFRESCO_PASS": "p"})

    def test_whitespace_only_password_aborts(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.require_credentials({"ALFRESCO_USER": "u", "ALFRESCO_PASS": " \n "})

    def test_abort_message_never_carries_the_credential_value(self) -> None:
        # Deliberately not named "secret": the fail-closed scanner treats an
        # assignment to a credential-named variable as a real finding, and it
        # is right to -- the fixture value is what matters, not the name.
        fixture_value = "fixture-" + "credential"
        with self.assertRaises(launcher.LevelCAbort) as ctx:
            launcher.require_credentials(
                {"ALFRESCO_USER": "  ", "ALFRESCO_PASS": fixture_value})
        self.assertNotIn(fixture_value, str(ctx.exception))
        self.assertIn("ALFRESCO_USER", str(ctx.exception))


# --------------------------------------------------------------------------
# TEST 7: proxy sanitation
# --------------------------------------------------------------------------
class ProxySanitationTest(unittest.TestCase):
    AMBIENT = {
        "http_proxy": "http://proxy.invalid:7890",
        "https_proxy": "http://proxy.invalid:7890",
        "HTTP_PROXY": "http://proxy.invalid:7890",
        "HTTPS_PROXY": "http://proxy.invalid:7890",
        "all_proxy": "socks5://proxy.invalid:7891",
        "ALL_PROXY": "socks5://proxy.invalid:7891",
        "no_proxy": "127.*",
        "NO_PROXY": "127.*",
        "PATH": "/usr/bin",
    }

    def test_every_proxy_variable_is_removed_from_the_child_env(self) -> None:
        child = launcher.sanitize_child_env(dict(self.AMBIENT))
        for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                     "all_proxy", "ALL_PROXY"):
            self.assertNotIn(name, child, f"proxy variable survived: {name}")

    def test_no_proxy_is_set_to_explicit_hosts_not_a_glob(self) -> None:
        child = launcher.sanitize_child_env(dict(self.AMBIENT))
        for name in ("no_proxy", "NO_PROXY"):
            self.assertEqual(child[name], "127.0.0.1,localhost")
            self.assertNotIn("*", child[name], "glob form urllib does not honour")

    def test_unrelated_environment_is_preserved(self) -> None:
        child = launcher.sanitize_child_env(dict(self.AMBIENT))
        self.assertEqual(child["PATH"], "/usr/bin")

    def test_the_caller_environment_is_not_mutated(self) -> None:
        ambient = dict(self.AMBIENT)
        launcher.sanitize_child_env(ambient)
        self.assertEqual(ambient["http_proxy"], "http://proxy.invalid:7890")

    def test_sanitation_is_applied_even_with_no_ambient_proxy(self) -> None:
        child = launcher.sanitize_child_env({"PATH": "/usr/bin"})
        self.assertEqual(child["no_proxy"], "127.0.0.1,localhost")

    def test_launcher_own_requests_bypass_a_hostile_ambient_proxy(self) -> None:
        """Behaviour, not handler introspection: the request must arrive.

        The ambient proxy points at a dead port and no_proxy uses the ``127.*``
        glob urllib does not match -- exactly this machine's configuration.
        A plain urlopen therefore fails, which is the control that proves the
        hazard is real rather than hypothetical.
        """
        server = LocalServer()
        hostile = dict(self.AMBIENT)
        dead = f"http://127.0.0.1:{free_port()}"
        hostile["http_proxy"] = hostile["HTTP_PROXY"] = dead
        try:
            with mock.patch.dict(os.environ, hostile, clear=True):
                with self.assertRaises(urllib.error.URLError):
                    urllib.request.urlopen(server.base + "/probe", timeout=5)
                opener = launcher.build_direct_opener()
                with opener.open(server.base + "/probe", timeout=5) as resp:
                    self.assertEqual(resp.getcode(), 200)
        finally:
            server.stop()

    def test_production_harness_child_reaches_the_service_despite_the_proxy(self) -> None:
        """End to end: sanitize_child_env is what actually gets the request out.

        The production harness is launched exactly as the launcher launches
        it, with the same hostile ambient proxy, against a local stand-in for
        Alfresco.  If the sanitation were dropped, the harness would report a
        proxy failure instead of a 200 and the server would see no hit.
        """
        server = LocalServer()
        run_dir = launcher.run_scoped_dir(pid=os.getpid())
        try:
            cfg = json.loads(TEMPLATE.read_text(encoding="utf-8"))
            cfg["base"] = server.base
            cfg["endpoints"][0]["path"] = f"/nodes/{FILE_ID}"
            run_dir.mkdir(parents=True, exist_ok=True)
            cfg_path = run_dir / "proxy_probe_target.json"
            cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

            hostile = dict(os.environ)
            dead = f"http://127.0.0.1:{free_port()}"
            for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
                hostile[name] = dead
            hostile["no_proxy"] = hostile["NO_PROXY"] = "127.*"

            env = launcher.harness_env(
                ambient=hostile, config_path=cfg_path, run_dir=run_dir,
                credentials=("fixture-user", "fixture-" + "credential"),
            )
            proc = subprocess.Popen(
                launcher.harness_command(), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            proc.communicate(input=launcher.metadata_body("NV_LEVELC_SMOKE_1").encode(),
                             timeout=60)

            status = json.loads(
                launcher.status_path_for(run_dir).read_text(encoding="utf-8"))
            self.assertEqual(status["http_code"], 200, status)
            self.assertEqual(status["method"], "PUT")
            self.assertGreater(status["exec_seq"], 0)
            self.assertEqual(server.hit_count, 1, "request never reached the service")
        finally:
            server.stop()
            shutil.rmtree(run_dir, ignore_errors=True)


# --------------------------------------------------------------------------
# TEST 8 + 12: node-id rendering, outside the committed tree
# --------------------------------------------------------------------------
class RenderedConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.run_dir = launcher.run_scoped_dir()
        self.out = self.run_dir / "target.json"

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_placeholder_is_replaced_exactly_once(self) -> None:
        rendered = launcher.render_target_config(FILE_ID, self.out)
        text = rendered.read_text(encoding="utf-8")
        self.assertNotIn(launcher.NODE_ID_PLACEHOLDER, text)
        self.assertEqual(text.count(FILE_ID), 1)

    def test_rendered_path_targets_the_resolved_node(self) -> None:
        rendered = launcher.render_target_config(FILE_ID, self.out)
        cfg = json.loads(rendered.read_text(encoding="utf-8"))
        path = cfg["endpoints"][0]["path"]
        self.assertTrue(path.endswith("/nodes/" + FILE_ID))
        self.assertTrue(UUID_RE.fullmatch(path.rsplit("/", 1)[-1]))

    def test_non_uuid_node_id_is_rejected(self) -> None:
        for bad in ("", "   ", "-my-", "../etc/passwd", "not-a-uuid", FILE_ID + "/extra"):
            with self.subTest(bad=bad):
                with self.assertRaises(launcher.LevelCAbort):
                    launcher.render_target_config(bad, self.out)

    def test_template_without_the_placeholder_is_rejected(self) -> None:
        broken = self.run_dir / "broken_template.json"
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_text(json.dumps({"endpoints": [{"path": "/nodes/fixed"}]}), encoding="utf-8")
        with self.assertRaises(launcher.LevelCAbort):
            launcher.render_target_config(FILE_ID, self.out, template_path=broken)

    def test_template_with_a_duplicated_placeholder_is_rejected(self) -> None:
        broken = self.run_dir / "dup_template.json"
        broken.parent.mkdir(parents=True, exist_ok=True)
        ph = launcher.NODE_ID_PLACEHOLDER
        broken.write_text(json.dumps(
            {"endpoints": [{"path": f"/nodes/{ph}"}, {"path": f"/nodes/{ph}"}]}),
            encoding="utf-8")
        with self.assertRaises(launcher.LevelCAbort):
            launcher.render_target_config(FILE_ID, self.out, template_path=broken)

    def test_the_committed_template_is_never_written_to(self) -> None:
        before = TEMPLATE.read_bytes()
        launcher.render_target_config(FILE_ID, self.out)
        self.assertEqual(TEMPLATE.read_bytes(), before)

    def test_rendered_config_stays_outside_the_committed_tree(self) -> None:
        rendered = launcher.render_target_config(FILE_ID, self.out)
        self.assertFalse(
            str(rendered.resolve()).startswith(str(REPO_ROOT.resolve()) + os.sep),
            f"run-scoped config landed inside the repository: {rendered}",
        )

    def test_rendering_into_the_committed_tree_is_refused(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.render_target_config(FILE_ID, REPO_ROOT / "targets" / "rendered.json")


# --------------------------------------------------------------------------
# TEST 13: run-scoped status namespace
# --------------------------------------------------------------------------
class RunScopedNamespaceTest(unittest.TestCase):
    def test_run_dir_is_pid_scoped_and_outside_the_repo(self) -> None:
        run_dir = launcher.run_scoped_dir()
        self.assertIn(str(os.getpid()), run_dir.name)
        self.assertFalse(str(run_dir).startswith(str(REPO_ROOT)))

    def test_status_path_is_run_scoped_not_the_global_default(self) -> None:
        run_dir = launcher.run_scoped_dir()
        status = launcher.status_path_for(run_dir)
        self.assertEqual(status.parent, run_dir)
        self.assertNotEqual(str(status), "/tmp/nv_http_status.json")

    def test_two_runs_do_not_share_a_status_namespace(self) -> None:
        a = launcher.status_path_for(launcher.run_scoped_dir(pid=101))
        b = launcher.status_path_for(launcher.run_scoped_dir(pid=102))
        self.assertNotEqual(a, b)


# --------------------------------------------------------------------------
# TEST 9-11: dedicated node resolution
# --------------------------------------------------------------------------
class DedicatedNodeResolutionTest(unittest.TestCase):
    def test_existing_dedicated_folder_and_file_are_reused(self) -> None:
        client = populated()
        resolved = launcher.resolve_dedicated_node(client)
        self.assertEqual(resolved["folder_id"], FOLDER_ID)
        self.assertEqual(resolved["file_id"], FILE_ID)
        self.assertFalse(resolved["created_folder"])
        self.assertFalse(resolved["created_file"])
        self.assertEqual(client.created, [])

    def test_zero_folder_match_takes_the_controlled_create_path(self) -> None:
        client = FakeClient({launcher.DEDICATED_PARENT: []})
        resolved = launcher.resolve_dedicated_node(client)
        self.assertTrue(resolved["created_folder"])
        self.assertTrue(resolved["created_file"])
        self.assertEqual(
            client.created,
            [(launcher.DEDICATED_PARENT, FOLDER, "cm:folder"),
             (resolved["folder_id"], FILENAME, "cm:content")],
        )

    def test_zero_file_match_inside_an_existing_folder_creates_only_the_file(self) -> None:
        client = populated(files=[])
        resolved = launcher.resolve_dedicated_node(client)
        self.assertFalse(resolved["created_folder"])
        self.assertTrue(resolved["created_file"])
        self.assertEqual(client.created, [(FOLDER_ID, FILENAME, "cm:content")])

    def test_multiple_matching_folders_abort(self) -> None:
        client = FakeClient({launcher.DEDICATED_PARENT: [
            entry(FOLDER_ID, FOLDER, is_folder=True, parent_id=launcher.DEDICATED_PARENT),
            entry(FOREIGN_ID, FOLDER, is_folder=True, parent_id=launcher.DEDICATED_PARENT),
        ]})
        with self.assertRaises(launcher.LevelCAbort) as ctx:
            launcher.resolve_dedicated_node(client)
        self.assertIn("folder", str(ctx.exception).lower())

    def test_multiple_matching_files_abort(self) -> None:
        client = populated(files=[
            entry(FILE_ID, FILENAME, is_folder=False, parent_id=FOLDER_ID),
            entry(FOREIGN_ID, FILENAME, is_folder=False, parent_id=FOLDER_ID),
        ])
        with self.assertRaises(launcher.LevelCAbort) as ctx:
            launcher.resolve_dedicated_node(client)
        self.assertIn("file", str(ctx.exception).lower())

    def test_nothing_is_created_when_resolution_aborts(self) -> None:
        client = FakeClient({launcher.DEDICATED_PARENT: [
            entry(FOLDER_ID, FOLDER, is_folder=True, parent_id=launcher.DEDICATED_PARENT),
            entry(FOREIGN_ID, FOLDER, is_folder=True, parent_id=launcher.DEDICATED_PARENT),
        ]})
        with self.assertRaises(launcher.LevelCAbort):
            launcher.resolve_dedicated_node(client)
        self.assertEqual(client.created, [])

    def test_unknown_historical_sibling_folders_are_never_selected(self) -> None:
        client = FakeClient({
            launcher.DEDICATED_PARENT: [
                entry(FOREIGN_ID, "Some Real Business Folder", is_folder=True,
                      parent_id=launcher.DEDICATED_PARENT),
                entry(FOLDER_ID, FOLDER, is_folder=True,
                      parent_id=launcher.DEDICATED_PARENT),
            ],
            FOLDER_ID: [entry(FILE_ID, FILENAME, is_folder=False, parent_id=FOLDER_ID)],
        })
        resolved = launcher.resolve_dedicated_node(client)
        self.assertEqual(resolved["folder_id"], FOLDER_ID)

    def test_unknown_historical_files_in_the_dedicated_folder_are_never_selected(self) -> None:
        client = populated(files=[
            entry(FOREIGN_ID, "quarterly-report.docx", is_folder=False, parent_id=FOLDER_ID),
            entry(FILE_ID, FILENAME, is_folder=False, parent_id=FOLDER_ID),
        ])
        resolved = launcher.resolve_dedicated_node(client)
        self.assertEqual(resolved["file_id"], FILE_ID)

    def test_a_same_named_file_outside_the_dedicated_folder_is_never_selected(self) -> None:
        client = FakeClient({
            launcher.DEDICATED_PARENT: [
                entry(FOLDER_ID, FOLDER, is_folder=True, parent_id=launcher.DEDICATED_PARENT),
                entry(FOREIGN_ID, FILENAME, is_folder=False,
                      parent_id=launcher.DEDICATED_PARENT),
            ],
            FOLDER_ID: [entry(FILE_ID, FILENAME, is_folder=False, parent_id=FOLDER_ID)],
        })
        resolved = launcher.resolve_dedicated_node(client)
        self.assertEqual(resolved["file_id"], FILE_ID)

    def test_a_folder_shaped_match_is_not_accepted_as_the_target_file(self) -> None:
        client = populated(files=[
            entry(FILE_ID, FILENAME, is_folder=True, parent_id=FOLDER_ID),
        ])
        resolved = launcher.resolve_dedicated_node(client)
        self.assertTrue(resolved["created_file"])
        self.assertNotEqual(resolved["file_id"], FILE_ID)

    def test_a_file_whose_parent_is_not_the_dedicated_folder_is_refused(self) -> None:
        client = FakeClient({
            launcher.DEDICATED_PARENT: [
                entry(FOLDER_ID, FOLDER, is_folder=True, parent_id=launcher.DEDICATED_PARENT)],
            FOLDER_ID: [entry(FILE_ID, FILENAME, is_folder=False, parent_id=FOREIGN_ID)],
        })
        with self.assertRaises(launcher.LevelCAbort):
            launcher.resolve_dedicated_node(client)

    def test_resolution_never_touches_cm_name(self) -> None:
        client = populated()
        launcher.resolve_dedicated_node(client)
        self.assertEqual(client.updates, [])


# --------------------------------------------------------------------------
# TEST 14: it is the production harness that gets launched
# --------------------------------------------------------------------------
class ProductionHarnessTest(unittest.TestCase):
    def test_harness_command_points_at_the_committed_production_harness(self) -> None:
        import sys
        cmd = launcher.harness_command()
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(Path(cmd[1]), (REPO_ROOT / "nv_http_harness.py").resolve())
        self.assertTrue(Path(cmd[1]).is_file())

    def test_launcher_references_no_mock_or_replacement_target(self) -> None:
        source = (REPO_ROOT / "scripts" / "run_alfresco_levelc_metadata.py").read_text(
            encoding="utf-8")
        for banned in ("_mock.py", "mock_target", "fake_harness", "nv_http_harness_mock"):
            self.assertNotIn(banned, source, f"launcher references {banned}")

    def test_harness_env_is_proxy_sanitized_and_run_scoped(self) -> None:
        run_dir = launcher.run_scoped_dir(pid=4242)
        env = launcher.harness_env(
            ambient={"http_proxy": "http://proxy.invalid:7890", "PATH": "/usr/bin"},
            config_path=Path("/tmp/nv-alfresco-levelc-4242/target.json"),
            run_dir=run_dir,
            credentials=("u", "p"),
        )
        self.assertNotIn("http_proxy", env)
        self.assertEqual(env["no_proxy"], "127.0.0.1,localhost")
        self.assertEqual(env["NV_TARGET_CONFIG"], "/tmp/nv-alfresco-levelc-4242/target.json")
        self.assertEqual(env["NV_ENDPOINT_NAME"], "metadata_update")
        self.assertTrue(env["NV_STATUS_PATH"].startswith(str(run_dir)))
        self.assertEqual(env["ALFRESCO_USER"], "u")
        self.assertEqual(env["ALFRESCO_PASS"], "p")
        self.assertEqual(
            env["NV_BODY_RULES"],
            str(REPO_ROOT / "validity" / "alfresco_metadata_update_rules.json"),
        )


# --------------------------------------------------------------------------
# Request body contract: metadata only, never cm:name
# --------------------------------------------------------------------------
class MetadataBodyTest(unittest.TestCase):
    def test_marker_body_only_carries_title_and_description(self) -> None:
        body = json.loads(launcher.metadata_body("NV_LEVELC_SMOKE_1"))
        self.assertEqual(set(body), {"properties"})
        self.assertEqual(set(body["properties"]), {"cm:title", "cm:description"})
        self.assertNotIn("name", body)

    def test_marker_appears_in_the_updated_title(self) -> None:
        body = json.loads(launcher.metadata_body("NV_LEVELC_SMOKE_2"))
        self.assertIn("NV_LEVELC_SMOKE_2", body["properties"]["cm:title"])

    def test_each_round_produces_a_distinct_marker_body(self) -> None:
        bodies = {launcher.metadata_body(f"NV_LEVELC_SMOKE_{i}") for i in (1, 2, 3)}
        self.assertEqual(len(bodies), 3)

    def test_marker_body_passes_the_committed_validity_rules(self) -> None:
        from nv_body_valid import body_validate

        result = body_validate(
            endpoint_name="metadata_update",
            raw_body=launcher.metadata_body("NV_LEVELC_SMOKE_1").encode("utf-8"),
            rules_path=str(REPO_ROOT / "validity" / "alfresco_metadata_update_rules.json"),
        )
        self.assertTrue(result["ok"], result["reason"])

    def test_readback_matches_only_the_current_round_marker(self) -> None:
        node = {"properties": {"cm:title": "NV_LEVELC_SMOKE_3 title",
                               "cm:description": "NV_LEVELC_SMOKE_3 description"}}
        self.assertTrue(launcher.marker_matches(node, "NV_LEVELC_SMOKE_3"))
        self.assertFalse(launcher.marker_matches(node, "NV_LEVELC_SMOKE_2"))

    def test_readback_rejects_a_node_missing_the_marker_entirely(self) -> None:
        self.assertFalse(launcher.marker_matches({"properties": {}}, "NV_LEVELC_SMOKE_1"))


# --------------------------------------------------------------------------
# Evidence containment: nothing sensitive may reach the summary
# --------------------------------------------------------------------------
class EvidenceContainmentTest(unittest.TestCase):
    def test_summary_redacts_the_credentials(self) -> None:
        summary = launcher.sanitized_summary(
            credentials=("svc-user", "fixture-" + "credential"),
            node={"folder_id": FOLDER_ID, "file_id": FILE_ID},
            rounds=[{"marker": "NV_LEVELC_SMOKE_1", "http_code": 200, "exec_seq": 7,
                     "readback_match": True}],
        )
        blob = json.dumps(summary)
        self.assertNotIn("svc-user", blob)
        self.assertNotIn("fixture-credential", blob)
        self.assertEqual(summary["credentials"], "REDACTED")

    def test_summary_carries_no_authorization_header(self) -> None:
        summary = launcher.sanitized_summary(
            credentials=("svc-user", "pw"), node={}, rounds=[])
        self.assertNotIn("Authorization", json.dumps(summary))
        self.assertNotIn("Basic ", json.dumps(summary))


if __name__ == "__main__":
    unittest.main()
