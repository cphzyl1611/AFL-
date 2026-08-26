"""Alfresco Level-C content-overwrite path: committed target + runtime launcher.

Scope note.  These are *offline* contract tests over synthetic fixtures and a
real loopback HTTP server.  They prove the containment, resolution and
byte-exactness contract of the Level-C content launcher; they do not talk to a
real Alfresco, and nothing here is a fuzzing campaign.

The real-service part (authenticated preflight, production-harness content
smoke, byte-exact read-back) is driven by the launcher itself and recorded as
evidence -- deliberately not as a unit test, so the suite stays hermetic.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "targets" / "alfresco_content_update.json"

_spec = importlib.util.spec_from_file_location(
    "alfresco_content_launcher_under_test",
    REPO_ROOT / "scripts" / "run_alfresco_levelc_content.py",
)
launcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(launcher)

_hspec = importlib.util.spec_from_file_location(
    "nv_http_harness_for_content", REPO_ROOT / "nv_http_harness.py")
harness = importlib.util.module_from_spec(_hspec)
_hspec.loader.exec_module(harness)

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
NODE_ID_PLACEHOLDER = "__ALFRESCO_NODE_ID__"
CONTENT_PATH_SUFFIX = "/content"


class CommittedContentTemplateTest(unittest.TestCase):
    """The committed target must describe the request and carry no secret."""

    def load(self) -> dict:
        return json.loads(TEMPLATE.read_text(encoding="utf-8"))

    def test_template_exists_and_parses(self) -> None:
        self.assertTrue(TEMPLATE.is_file(), f"missing committed target: {TEMPLATE}")
        self.assertIsInstance(self.load(), dict)

    def test_template_lives_in_the_committed_tree_and_is_not_ignored(self) -> None:
        proc = subprocess.run(
            ["git", "check-ignore", "-q", str(TEMPLATE)],
            cwd=REPO_ROOT, capture_output=True,
        )
        self.assertNotEqual(proc.returncode, 0,
                            "content target must not be gitignored")

    def test_template_carries_no_concrete_node_uuid(self) -> None:
        self.assertEqual(UUID_RE.findall(TEMPLATE.read_text(encoding="utf-8")), [])

    def test_template_carries_no_credential_or_authorization_literal(self) -> None:
        """`password_env` is the required contract; `"password":` would be a leak."""
        lowered = TEMPLATE.read_text(encoding="utf-8").lower()
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
        self.assertEqual(auth["type"], "basic")
        self.assertEqual(auth["username_env"], "ALFRESCO_USER")
        self.assertEqual(auth["password_env"], "ALFRESCO_PASS")
        self.assertNotIn("username", auth)
        self.assertNotIn("password", auth)

    def test_template_declares_exactly_one_put_content_endpoint(self) -> None:
        cfg = self.load()
        eps = cfg["endpoints"]
        self.assertEqual(len(eps), 1, "content target must expose one endpoint only")
        ep = eps[0]
        self.assertEqual(ep["method"], "PUT")
        self.assertTrue(ep["path"].endswith(CONTENT_PATH_SUFFIX),
                        f"endpoint must target the content path, got {ep['path']}")
        self.assertIn(NODE_ID_PLACEHOLDER, ep["path"])

    def test_template_carries_exactly_one_node_placeholder(self) -> None:
        self.assertEqual(
            TEMPLATE.read_text(encoding="utf-8").count(NODE_ID_PLACEHOLDER), 1)

    def test_template_does_not_use_json_body_only_mode(self) -> None:
        """Raw content cannot survive body_only_mode: it JSON-normalises the body."""
        self.assertNotEqual(int(self.load().get("body_only_mode", 0)), 1)

    def test_template_declares_no_metadata_or_versioning_behaviour(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        for forbidden in ("cm:name", "cm:title", "cm:description",
                          "cm:versionable", "majorVersion", "body_templates"):
            self.assertNotIn(forbidden, text,
                             f"content target must not carry {forbidden!r}")


class FakeContentClient:
    """Records calls so resolution/read-back contracts can be asserted."""

    def __init__(self, listings=None, raw=b"", node=None):
        self._listings = listings or {}
        self._raw = raw
        self._node = node or {}
        self.created: list[tuple] = []
        self.raw_gets: list[str] = []

    def list_children(self, parent_id):
        return self._listings.get(parent_id, [])

    def create_child(self, parent_id, name, node_type):
        self.created.append((parent_id, name, node_type))
        return {"id": f"created-{name}", "name": name,
                "isFolder": node_type == "cm:folder",
                "isFile": node_type == "cm:content", "parentId": parent_id}

    def get_node(self, node_id):
        return self._node

    def get_content_bytes(self, node_id):
        self.raw_gets.append(node_id)
        return 200, self._raw

    def version_count(self, node_id):
        return 0


def folder(name, nid="folder-1"):
    return {"id": nid, "name": name, "isFolder": True, "isFile": False}


def afile(name, nid="file-1", parent="folder-1"):
    return {"id": nid, "name": name, "isFolder": False, "isFile": True,
            "parentId": parent, "aspectNames": []}


class ContentCredentialGateTest(unittest.TestCase):
    """Reuses the independently verified metadata credential gate."""

    def test_both_credentials_present_is_accepted(self) -> None:
        user, password = launcher.require_credentials(
            {"ALFRESCO_USER": "u", "ALFRESCO_PASS": "p"})
        self.assertEqual((user, password), ("u", "p"))

    def test_missing_user_aborts(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.require_credentials({"ALFRESCO_PASS": "p"})

    def test_missing_password_aborts(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.require_credentials({"ALFRESCO_USER": "u"})

    def test_whitespace_only_password_aborts(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.require_credentials({"ALFRESCO_USER": "u", "ALFRESCO_PASS": "   "})

    def test_abort_message_never_carries_the_credential_value(self) -> None:
        sentinel = "ZZSENTINELVALUEZZ"
        with self.assertRaises(launcher.LevelCAbort) as ctx:
            launcher.require_credentials({"ALFRESCO_USER": sentinel})
        self.assertNotIn(sentinel, str(ctx.exception))


class ContentProxySanitationTest(unittest.TestCase):
    HOSTILE = {"http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
               "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
               "all_proxy": "socks5://127.0.0.1:9", "ALL_PROXY": "socks5://127.0.0.1:9",
               "no_proxy": "127.*", "NO_PROXY": "127.*"}

    def test_every_proxy_variable_is_removed_from_the_child_env(self) -> None:
        child = launcher.sanitize_child_env(dict(self.HOSTILE))
        for name in ("http_proxy", "https_proxy", "HTTP_PROXY",
                     "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
            self.assertNotIn(name, child, f"{name} survived sanitation")

    def test_loopback_bypass_uses_explicit_hosts_not_the_unmatched_glob(self) -> None:
        child = launcher.sanitize_child_env(dict(self.HOSTILE))
        self.assertEqual(child["no_proxy"], "127.0.0.1,localhost")
        self.assertEqual(child["NO_PROXY"], "127.0.0.1,localhost")
        self.assertNotIn("127.*", child["no_proxy"])

    def test_harness_env_is_proxy_sanitised(self) -> None:
        env = launcher.harness_env(dict(self.HOSTILE), Path("/tmp/x/target.json"),
                                   Path("/tmp/x"), ("u", "p"))
        for name in ("http_proxy", "HTTPS_PROXY", "ALL_PROXY"):
            self.assertNotIn(name, env)


class ContentNodeResolutionTest(unittest.TestCase):
    """Only the one dedicated file may ever be selected."""

    def test_unique_folder_and_file_resolve_without_creating_anything(self) -> None:
        client = FakeContentClient(listings={
            launcher.DEDICATED_PARENT: [folder(launcher.DEDICATED_FOLDER_NAME)],
            "folder-1": [afile(launcher.DEDICATED_FILE_NAME)],
        })
        node = launcher.resolve_dedicated_node(client)
        self.assertEqual(node["file_id"], "file-1")
        self.assertFalse(node["created_folder"])
        self.assertFalse(node["created_file"])
        self.assertEqual(client.created, [])

    def test_duplicate_dedicated_folder_aborts(self) -> None:
        client = FakeContentClient(listings={
            launcher.DEDICATED_PARENT: [folder(launcher.DEDICATED_FOLDER_NAME, "a"),
                                        folder(launcher.DEDICATED_FOLDER_NAME, "b")],
        })
        with self.assertRaises(launcher.LevelCAbort):
            launcher.resolve_dedicated_node(client)

    def test_duplicate_dedicated_file_aborts(self) -> None:
        client = FakeContentClient(listings={
            launcher.DEDICATED_PARENT: [folder(launcher.DEDICATED_FOLDER_NAME)],
            "folder-1": [afile(launcher.DEDICATED_FILE_NAME, "f1"),
                         afile(launcher.DEDICATED_FILE_NAME, "f2")],
        })
        with self.assertRaises(launcher.LevelCAbort):
            launcher.resolve_dedicated_node(client)

    def test_unknown_sibling_node_is_never_selected(self) -> None:
        client = FakeContentClient(listings={
            launcher.DEDICATED_PARENT: [folder(launcher.DEDICATED_FOLDER_NAME)],
            "folder-1": [afile("some-unrelated-historical-file.txt", "other"),
                         afile(launcher.DEDICATED_FILE_NAME, "file-1")],
        })
        node = launcher.resolve_dedicated_node(client)
        self.assertEqual(node["file_id"], "file-1")


class ContentRenderedConfigTest(unittest.TestCase):
    NODE = "11111111-2222-3333-4444-555555555555"

    def test_rendered_config_targets_the_content_path_of_the_resolved_node(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                out = launcher.render_target_config(self.NODE, Path(tmp) / "t.json")
                cfg = json.loads(out.read_text())
        self.assertEqual(
            cfg["endpoints"][0]["path"],
            f"{launcher.API_BASE}/nodes/{self.NODE}/content")

    def test_committed_template_is_not_modified_by_rendering(self) -> None:
        before = TEMPLATE.read_bytes()
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            launcher.render_target_config(self.NODE, Path(tmp) / "t.json")
        self.assertEqual(TEMPLATE.read_bytes(), before)
        self.assertIn(NODE_ID_PLACEHOLDER, before.decode())

    def test_rendering_into_the_committed_tree_is_refused(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.render_target_config(self.NODE, REPO_ROOT / "targets" / "leak.json")

    def test_non_uuid_node_id_is_refused(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for bad in ("../etc/passwd", "-root-", "abc", "", self.NODE + "/x"):
                with self.assertRaises(launcher.LevelCAbort):
                    launcher.render_target_config(bad, Path(tmp) / "t.json")


class ContentPayloadTest(unittest.TestCase):
    """Payloads must be synthetic, distinct, and differently sized."""

    def test_three_payloads_are_distinct(self) -> None:
        blobs = [launcher.payload_for(x) for x in ("A", "B", "C")]
        self.assertEqual(len(set(blobs)), 3)

    def test_lengths_differ_so_append_or_truncation_is_detectable(self) -> None:
        a, b, c = (len(launcher.payload_for(x)) for x in ("A", "B", "C"))
        self.assertLess(a, b, "B must be longer than A")
        self.assertLess(c, a, "C must be shorter than A, to catch truncation bugs")

    def test_no_payload_is_a_prefix_of_another(self) -> None:
        blobs = [launcher.payload_for(x) for x in ("A", "B", "C")]
        for one in blobs:
            for other in blobs:
                if one is not other:
                    self.assertFalse(other.startswith(one))

    def test_payloads_are_lf_only_with_no_trailing_newline(self) -> None:
        for label in ("A", "B", "C"):
            blob = launcher.payload_for(label)
            self.assertNotIn(b"\r", blob)
            self.assertFalse(blob.endswith(b"\n"))

    def test_payloads_are_deterministic(self) -> None:
        self.assertEqual(launcher.payload_for("B"), launcher.payload_for("B"))


class HarnessSeedRoundTripTest(unittest.TestCase):
    """The bytes we intend must be the bytes the production parser yields."""

    NODE = "11111111-2222-3333-4444-555555555555"

    def path(self) -> str:
        return launcher.content_path_for(self.NODE)

    def test_production_parser_recovers_method_path_and_exact_bytes(self) -> None:
        for label in ("A", "B", "C"):
            payload = launcher.payload_for(label)
            seed = launcher.build_http_seed(self.path(), payload)
            method, path, headers, body = harness.parse_http_seed(seed)
            self.assertEqual(method, "PUT")
            self.assertEqual(path, self.path())
            self.assertEqual(body, payload, f"round {label} bytes altered in transit")

    def test_seed_declares_a_non_json_content_type(self) -> None:
        seed = launcher.build_http_seed(self.path(), launcher.payload_for("A"))
        _, _, headers, _ = harness.parse_http_seed(seed)
        self.assertTrue(headers["Content-Type"].startswith("text/plain"))
        self.assertNotIn("json", headers["Content-Type"])

    def test_multiline_payload_internal_blank_lines_survive(self) -> None:
        payload = b"NV_LEVELC_CONTENT_SELFTEST_X\n\nafter blank\nend"
        seed = launcher.build_http_seed(self.path(), payload)
        _, _, _, body = harness.parse_http_seed(seed)
        self.assertEqual(body, payload)

    def test_rendered_config_whitelists_the_seed_path(self) -> None:
        """Otherwise the harness silently rewrites the path to the default."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = launcher.render_target_config(self.NODE, Path(tmp) / "t.json")
            with mock.patch.dict(os.environ, {"NV_TARGET_CONFIG": str(cfg_path)}):
                cfg = harness.load_target_config()
        self.assertIn(self.path(), cfg["_allowed_paths"])
        self.assertIn("PUT", cfg["_allowed_methods"])


class HarnessUnsafePayloadTest(unittest.TestCase):
    """Refuse payloads the seed parser would silently alter."""

    def test_crlf_payload_is_refused(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.harness_safe_payload(b"line-one\r\nline-two")

    def test_trailing_newline_payload_is_refused(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.harness_safe_payload(b"content\n")

    def test_non_utf8_payload_is_refused(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.harness_safe_payload(b"abc\xff\xfedef")

    def test_empty_payload_is_refused(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.harness_safe_payload(b"")

    def test_payload_beginning_with_a_blank_line_is_refused(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.build_http_seed("/p", b"\nstarts blank")

    def test_a_refused_payload_is_genuinely_altered_by_the_parser(self) -> None:
        """Proves the guard tracks real harness behaviour, not a guess."""
        payload = b"content\n"
        seed = b"PUT /p\nContent-Type: text/plain\n\n" + payload
        _, _, _, body = harness.parse_http_seed(seed)
        self.assertNotEqual(body, payload)
        self.assertEqual(body, b"content")

    def test_the_three_shipped_payloads_all_pass_the_guard(self) -> None:
        for label in ("A", "B", "C"):
            self.assertEqual(launcher.harness_safe_payload(launcher.payload_for(label)),
                             launcher.payload_for(label))


class ReadBackComparisonTest(unittest.TestCase):
    """Substring containment is never sufficient; bytes must be exact."""

    BASE = b"NV_LEVELC_CONTENT_SELFTEST_A\nline000-xxxx"

    def test_identical_bytes_pass_on_every_axis(self) -> None:
        r = launcher.compare_content(self.BASE, self.BASE)
        self.assertTrue(r["bytes_exact"])
        self.assertTrue(r["length_match"])
        self.assertTrue(r["sha256_match"])
        self.assertEqual(r["expected_len"], len(self.BASE))
        self.assertEqual(r["observed_len"], len(self.BASE))

    def test_same_marker_but_different_bytes_fails(self) -> None:
        observed = b"NV_LEVELC_CONTENT_SELFTEST_A\nline000-yyyy"
        r = launcher.compare_content(self.BASE, observed)
        self.assertFalse(r["bytes_exact"])
        self.assertFalse(r["sha256_match"])
        self.assertTrue(r["length_match"], "same length: only a hash catches this")

    def test_truncation_fails(self) -> None:
        r = launcher.compare_content(self.BASE, self.BASE[:-5])
        self.assertFalse(r["bytes_exact"])
        self.assertFalse(r["length_match"])
        self.assertFalse(r["sha256_match"])

    def test_append_fails(self) -> None:
        r = launcher.compare_content(self.BASE, self.BASE + b"residue")
        self.assertFalse(r["bytes_exact"])
        self.assertFalse(r["length_match"])

    def test_prefix_overwrite_leaving_old_tail_fails(self) -> None:
        """The classic partial-overwrite bug this round exists to catch."""
        old = launcher.payload_for("B")
        new = launcher.payload_for("C")
        partial = new + old[len(new):]
        r = launcher.compare_content(new, partial)
        self.assertFalse(r["bytes_exact"])
        self.assertFalse(r["length_match"])

    def test_empty_readback_fails(self) -> None:
        r = launcher.compare_content(self.BASE, b"")
        self.assertFalse(r["bytes_exact"])

    def test_reported_hashes_are_real_sha256_of_the_inputs(self) -> None:
        r = launcher.compare_content(self.BASE, b"other")
        self.assertEqual(r["expected_sha256"], hashlib.sha256(self.BASE).hexdigest())
        self.assertEqual(r["observed_sha256"], hashlib.sha256(b"other").hexdigest())


class ContentDownloadTest(unittest.TestCase):
    """The read-back must be an independent GET of the stored bytes."""

    NODE = "11111111-2222-3333-4444-555555555555"

    def setUp(self) -> None:
        import http.server, threading
        payload = b"stored-bytes\nsecond-line"
        node = self.NODE

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                if self.path == f"{launcher.API_BASE}/nodes/{node}/content":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()

            def log_message(self, *a):
                return

        self.payload = payload
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def client(self):
        return launcher.ContentClient(f"http://127.0.0.1:{self.port}", ("u", "p"))

    def test_download_returns_raw_bytes_not_parsed_json(self) -> None:
        code, data = self.client().get_content_bytes(self.NODE)
        self.assertEqual(code, 200)
        self.assertIsInstance(data, bytes)
        self.assertEqual(data, self.payload)

    def test_download_reports_non_200_without_raising(self) -> None:
        code, _ = self.client().get_content_bytes(
            "99999999-8888-7777-6666-555555555555")
        self.assertEqual(code, 404)

    def test_download_bypasses_an_ambient_proxy(self) -> None:
        hostile = {"http_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1",
                   "no_proxy": "127.*"}
        with mock.patch.dict(os.environ, hostile):
            code, data = self.client().get_content_bytes(self.NODE)
        self.assertEqual(code, 200)
        self.assertEqual(data, self.payload)


class FakeAlfresco:
    """A loopback stand-in that stores content, so overwrite semantics are real."""

    def __init__(self, node_id: str, initial: bytes = b"initial-content"):
        import http.server, threading
        self.node_id = node_id
        self.store = initial
        self.name = "nv-afl-levelc-metadata.txt"
        self.aspects = ["cm:auditable", "cm:titled"]
        self.puts = 0
        self.put_content_types: list[str] = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _send(self, code, payload, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_PUT(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                if self.path == f"{launcher.API_BASE}/nodes/{outer.node_id}/content":
                    outer.store = body            # full overwrite
                    outer.puts += 1
                    outer.put_content_types.append(self.headers.get("Content-Type", ""))
                    self._send(200, json.dumps({"entry": {"id": outer.node_id}}).encode())
                else:
                    self._send(404, b"{}")

            def do_GET(self):
                base = self.path.split("?", 1)[0]
                if base == f"{launcher.API_BASE}/nodes/{outer.node_id}/content":
                    self._send(200, outer.store, "text/plain")
                elif base == f"{launcher.API_BASE}/nodes/{outer.node_id}/versions":
                    self._send(200, json.dumps({"list": {"entries": []}}).encode())
                elif base == f"{launcher.API_BASE}/nodes/{outer.node_id}":
                    self._send(200, json.dumps({"entry": {
                        "id": outer.node_id, "name": outer.name,
                        "aspectNames": outer.aspects, "properties": {}}}).encode())
                else:
                    self._send(404, b"{}")

            def log_message(self, *a):
                return

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class ProductionHarnessContentRoundTest(unittest.TestCase):
    """End-to-end through the real nv_http_harness.py, over loopback."""

    NODE = "11111111-2222-3333-4444-555555555555"

    def setUp(self) -> None:
        import tempfile
        self.server = FakeAlfresco(self.NODE)
        self.addCleanup(self.server.stop)
        self.tmp = tempfile.mkdtemp(prefix="levelc-content-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.run_dir = Path(self.tmp) / "run"
        self.run_dir.mkdir()
        cfg_path = launcher.render_target_config(self.NODE, Path(self.tmp) / "target.json")
        cfg = json.loads(cfg_path.read_text())
        cfg["base"] = self.server.base
        cfg_path.write_text(json.dumps(cfg))
        self.cfg_path = cfg_path
        self.client = launcher.ContentClient(self.server.base, ("u", "p"))

    def round(self, label):
        return launcher.run_round(label, self.cfg_path, self.run_dir,
                                  ("u", "p"), self.client, self.NODE)

    def test_round_drives_the_production_harness_to_a_real_put(self) -> None:
        r = self.round("A")
        self.assertEqual(r["harness_returncode"], 0)
        self.assertEqual(r["http_code"], 200)
        self.assertEqual(r["method"], "PUT")
        self.assertEqual(self.server.puts, 1, "the harness must have issued the PUT")

    def test_round_sends_a_non_json_content_type(self) -> None:
        self.round("A")
        self.assertTrue(self.server.put_content_types[0].startswith("text/plain"))

    def test_stored_bytes_equal_the_payload_exactly(self) -> None:
        r = self.round("A")
        self.assertEqual(self.server.store, launcher.payload_for("A"))
        self.assertTrue(r["readback"]["bytes_exact"])
        self.assertTrue(r["readback"]["sha256_match"])
        self.assertTrue(r["readback"]["length_match"])

    def test_status_document_is_valid_json_with_a_positive_exec_seq(self) -> None:
        r = self.round("A")
        status = json.loads(launcher.status_path_for(self.run_dir).read_text())
        self.assertEqual(status["http_code"], 200)
        self.assertGreater(r["exec_seq"], 0)

    def test_three_rounds_produce_distinct_monotonic_exec_seq(self) -> None:
        seqs = [self.round(x)["exec_seq"] for x in ("A", "B", "C")]
        self.assertEqual(len(set(seqs)), 3, f"exec_seq collision: {seqs}")
        self.assertEqual(seqs, sorted(seqs), f"exec_seq not monotonic: {seqs}")
        self.assertTrue(all(v > 0 for v in seqs))

    def test_full_overwrite_leaves_no_residue_from_the_longer_run(self) -> None:
        """B is the longest; C must replace it entirely, not just its prefix."""
        self.round("B")
        self.round("C")
        self.assertEqual(self.server.store, launcher.payload_for("C"))
        self.assertEqual(len(self.server.store), len(launcher.payload_for("C")))
        self.assertNotIn(b"NV_LEVELC_CONTENT_SELFTEST_B", self.server.store)

    def test_readback_detects_a_server_that_appends_instead_of_overwriting(self) -> None:
        """A negative control: the comparison must fail on broken semantics."""
        self.round("A")
        self.server.store = launcher.payload_for("A") + b"-residue"
        code, data = self.client.get_content_bytes(self.NODE)
        result = launcher.compare_content(launcher.payload_for("A"), data)
        self.assertFalse(result["bytes_exact"])
        self.assertFalse(result["length_match"])

    def test_status_path_is_run_scoped(self) -> None:
        other = Path(self.tmp) / "run2"
        self.assertNotEqual(launcher.status_path_for(self.run_dir),
                            launcher.status_path_for(other))

    def test_round_reports_name_and_aspects_for_the_state_guard(self) -> None:
        r = self.round("A")
        self.assertEqual(r["node_name"], "nv-afl-levelc-metadata.txt")
        self.assertNotIn("cm:versionable", r["aspects"])
        self.assertEqual(r["version_count"], 0)

    def test_no_metadata_property_is_written_by_a_content_round(self) -> None:
        self.round("A")
        self.assertEqual(self.server.puts, 1)
        self.assertTrue(all(p.startswith("text/plain")
                            for p in self.server.put_content_types))


class StateGuardTest(unittest.TestCase):
    """Guards that must fire before any content byte is written."""

    def base_node(self, **over):
        node = {"folder_id": "f", "file_id": "n", "created_folder": False,
                "created_file": False, "aspect_names": ["cm:auditable"]}
        node.update(over)
        return node

    def test_reusing_the_existing_dedicated_node_is_accepted(self) -> None:
        launcher.assert_reused_existing_node(self.base_node())

    def test_a_newly_created_file_aborts_the_content_round(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.assert_reused_existing_node(self.base_node(created_file=True))

    def test_a_newly_created_folder_aborts_the_content_round(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.assert_reused_existing_node(self.base_node(created_folder=True))

    def test_versionable_node_aborts(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.assert_not_versionable(
                self.base_node(aspect_names=["cm:auditable", "cm:versionable"]))

    def test_non_versionable_node_is_accepted(self) -> None:
        launcher.assert_not_versionable(self.base_node())

    def test_name_mutation_is_detected(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.assert_name_unchanged("before.txt", "after.txt")

    def test_unchanged_name_is_accepted(self) -> None:
        launcher.assert_name_unchanged("same.txt", "same.txt")

    def test_version_growth_is_detected(self) -> None:
        with self.assertRaises(launcher.LevelCAbort):
            launcher.assert_no_version_growth(0, 3)

    def test_stable_version_count_is_accepted(self) -> None:
        launcher.assert_no_version_growth(0, 0)


class SanitizedSummaryTest(unittest.TestCase):
    # Not a credential: a sentinel string we assert never reaches the summary.
    # Named to avoid tripping the credential-context rule in scripts/secret_scan.py.
    FIXTURE_VALUE = "ZZSENTINELVALUEZZ"

    def summary(self):
        node = {"folder_id": "11111111-2222-3333-4444-555555555555",
                "file_id": "99999999-8888-7777-6666-555555555555",
                "created_folder": False, "created_file": False,
                "aspect_names": ["cm:auditable"]}
        return launcher.sanitized_summary(
            ("user", self.FIXTURE_VALUE), node,
            [{"label": "A", "http_code": 200, "exec_seq": 1}],
            base="http://127.0.0.1:8080")

    def test_credentials_are_redacted(self) -> None:
        blob = json.dumps(self.summary())
        self.assertNotIn(self.FIXTURE_VALUE, blob)
        self.assertEqual(self.summary()["credentials"], "REDACTED")

    def test_no_concrete_node_uuid_reaches_the_summary(self) -> None:
        blob = json.dumps(self.summary())
        self.assertEqual(UUID_RE.findall(blob), [])

    def test_rounds_and_extras_are_preserved(self) -> None:
        summary = self.summary()
        self.assertEqual(summary["rounds"][0]["exec_seq"], 1)
        self.assertEqual(summary["base"], "http://127.0.0.1:8080")


class LauncherEntryPointTest(unittest.TestCase):
    def test_main_fails_closed_before_any_network_call(self) -> None:
        import socket
        import tempfile

        class Blocked(RuntimeError):
            pass

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch.object(
                        socket, "socket",
                        side_effect=Blocked("network must not be touched")):
                    with self.assertRaises(launcher.LevelCAbort):
                        launcher.main(["--evidence-dir", tmp])

    def test_harness_command_points_at_the_production_harness(self) -> None:
        self.assertTrue(launcher.harness_command()[-1].endswith("nv_http_harness.py"))
        self.assertNotIn("mock", " ".join(launcher.harness_command()).lower())

    def test_launcher_carries_no_scheduler_mab_or_reward_logic(self) -> None:
        """Scan identifiers and literals, not prose: the docstring may *mention*
        afl-fuzz to say it is out of scope."""
        import ast

        src = (REPO_ROOT / "scripts" / "run_alfresco_levelc_content.py").read_text()
        tree = ast.parse(src)
        docstring_nodes = set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                first = (n.body or [None])[0]
                if (isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    docstring_nodes.add(id(first.value))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id.lower())
            elif isinstance(node, ast.Attribute):
                names.add(node.attr.lower())
            elif isinstance(node, ast.alias):
                names.add(node.name.lower())
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) not in docstring_nodes:
                    names.add(node.value.lower())
        joined = " ".join(sorted(names))
        for banned in ("afl-fuzz", "nv_mab", "ucb", "reward", "ss_prob", "mutate"):
            self.assertNotIn(banned, joined, f"out-of-scope logic: {banned}")

    def test_launcher_is_clean_under_the_active_secret_scanner(self) -> None:
        from scripts.secret_scan import scan_paths

        result = scan_paths(
            [REPO_ROOT / "scripts" / "run_alfresco_levelc_content.py"], required=True)
        self.assertEqual(result["real_secret_findings"], 0, result["findings"])

    def test_verified_metadata_assets_are_untouched_by_this_round(self) -> None:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--",
             "scripts/run_alfresco_levelc_metadata.py",
             "targets/alfresco_metadata_update.json"],
            cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(proc.stdout.strip(), "",
                         "the verified metadata assets must not change")


if __name__ == "__main__":
    unittest.main()
