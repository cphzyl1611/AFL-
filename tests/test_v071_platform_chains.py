"""v0.7.1 -- platform request shapes through the shared HTTP harness.

Every launcher in this repository runs the same target:

    afl-fuzz -n -i <in> -o <out> -- python3 nv_http_harness.py

so a platform "chain" is a *target config* plus a *request shape*, not a
separate harness.  These tests drive the real committed configs through the
real harness, with only ``base`` redirected to a local server, and assert that
each one now produces execution identity.

Scope: this proves the harness path a platform uses carries ``exec_seq``.  It
is not a fuzzing campaign against a real O2OA, Alfresco or Flowable service,
and nothing here should be read as one.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.test_v071_exec_seq import (
    LocalServer,
    run_harness,
    read_status,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def redirect(config_path: Path, base: str, out_path: Path) -> Path:
    """Take a committed target config and point it at the local server."""
    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["base"] = base
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)
    return out_path


class PlatformChainTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = LocalServer()
        cls.tmp = Path(tempfile.mkdtemp(prefix="v071_platform_"))
        cls.status = cls.tmp / "nv_http_status.json"

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _two_executions(self, cfg: Path, body: bytes, **extra):
        """Run the same request twice; return both status documents."""
        run_harness(self.status, cfg, body, **extra)
        first = read_status(self.status)
        run_harness(self.status, cfg, body, **extra)
        second = read_status(self.status)
        return first, second

    def _assert_chain_has_identity(self, first, second, label):
        self.assertIn("exec_seq", first, f"{label}: no exec_seq")
        self.assertGreater(first["exec_seq"], 0, f"{label}: exec_seq not allocated")
        self.assertNotEqual(
            first["exec_seq"], second["exec_seq"],
            f"{label}: two executions shared one identity",
        )
        # The legacy identity is still emitted alongside it.
        self.assertIn("ts_ms", first)
        self.assertIn("body_hash16", first)

    def test_o2oa_cms_doc_list_chain_has_exec_seq(self):
        """The real committed O2OA config, PUT cms_doc_list."""
        cfg = redirect(REPO_ROOT / "targets" / "o2oa_query.json",
                       self.server.base, self.tmp / "o2oa.json")
        body = json.dumps({
            "docStatusList": ["published"],
            "categoryIdList": ["c1"],
            "key": "kw",
        }).encode()

        first, second = self._two_executions(
            cfg, body,
            NV_ENDPOINT_NAME="cms_doc_list",
            NV_BODY_RULES=str(REPO_ROOT / "validity" / "o2oa_query_rules.json"),
            NV_TOKEN="audit-local-token",
        )
        self._assert_chain_has_identity(first, second, "o2oa")
        self.assertEqual(first["method"], "PUT")
        self.assertTrue(first["path"].startswith("/x_cms_assemble_control/"),
                        f"unexpected O2OA path: {first['path']}")

    def test_alfresco_metadata_update_chain_has_exec_seq(self):
        """The Alfresco metadata_update request shape.

        The repository commits no Alfresco HTTP target config -- the committed
        Alfresco AFL work uses mock/wrapper targets that write no NV status
        document at all.  A real Alfresco HTTP run is driven by
        scripts/run_main_baseline_rule_generic.sh with CFG pointed at an
        Alfresco config, which launches this same harness.  This test builds
        that config from the committed Alfresco seed shape and rules.
        """
        cfg_path = self.tmp / "alfresco.json"
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump({
                "target_type": "http_api",
                "base": self.server.base,
                "health": "/health",
                "body_only_mode": 1,
                "default_endpoint": "metadata_update",
                "endpoints": [{
                    "name": "metadata_update",
                    "method": "PUT",
                    "path": "/alfresco/api/-default-/public/alfresco/versions/1/nodes/n1",
                }],
            }, fh)

        seed = REPO_ROOT / "in" / "alfresco_afl_metadata_update_smoke" / "seed_ok_0.json"
        body = seed.read_bytes()

        first, second = self._two_executions(
            cfg_path, body,
            NV_ENDPOINT_NAME="metadata_update",
            NV_BODY_RULES=str(REPO_ROOT / "validity"
                              / "alfresco_metadata_update_rules.json"),
        )
        self._assert_chain_has_identity(first, second, "alfresco")
        self.assertEqual(first["method"], "PUT")

    def test_flowable_config_inherits_the_upgrade_if_it_is_ever_used(self):
        """flowable_query.json is harness-schema but no launcher references it.

        It is covered by construction: any config driven through this harness
        gets execution identity.  This does not add a Flowable AFL++ chain.

        Its Basic credential is env-only and fail-closed; see
        tests/test_flowable_credential_contract.py.
        """
        cfg = redirect(REPO_ROOT / "flowable_query.json",
                       self.server.base, self.tmp / "flowable.json")
        body = json.dumps({"processDefinitionKey": "documentProcess"}).encode()

        # The config is env-only fail-closed now: supply throwaway runtime
        # credentials for the local server, never a committed literal.
        first, second = self._two_executions(
            cfg, body,
            NV_ENDPOINT_NAME="process_start",
            NV_BODY_RULES=str(REPO_ROOT / "validity"
                              / "flowable_doc_create_rules.json"),
            FLOWABLE_USER="audit-local-user",
            FLOWABLE_PASS="audit-local-" + "credential",
        )
        self._assert_chain_has_identity(first, second, "flowable")

    def test_every_launcher_uses_the_single_shared_harness(self):
        """The inventory claim, asserted rather than described.

        If a new launcher ever introduces a second HTTP target, this fails and
        the exec_seq inventory has to be revisited.
        """
        launchers = sorted(
            p for p in REPO_ROOT.glob("**/*.sh")
            if "nv_http_harness.py" in p.read_text(errors="ignore")
        )
        self.assertGreaterEqual(len(launchers), 8,
                                "expected the known HTTP launcher scripts")
        for script in launchers:
            text = script.read_text(errors="ignore")
            targets = [
                line for line in text.splitlines()
                if "-- " in line and ".py" in line and "harness" not in line
            ]
            self.assertEqual(
                targets, [],
                f"{script.name} launches an HTTP target other than "
                f"nv_http_harness.py: {targets}",
            )


if __name__ == "__main__":
    unittest.main()
