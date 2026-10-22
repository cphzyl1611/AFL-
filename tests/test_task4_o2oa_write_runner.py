"""Safety and live-schema contracts for the explicit O2OA write runner."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location("write_runner", Path(__file__).resolve().parents[1] / "scripts/run_task4_o2oa_write_experiment.py")
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)


class WriteRunnerSafety(unittest.TestCase):
    def setUp(self):
        self.manifest = {"category": "fixture-category", "identity": "fixture@unique@I", "title": "run-marker"}
        self.doc = {"id": "receipt", "categoryId": "fixture-category", "creatorIdentity": "fixture@unique@I",
            "creatorPerson": "fixture@unique@P", "docStatus": "draft", "title": "run-marker",
            "readPersonList": ["fixture@unique@P"], "readUnitList": [], "readGroupList": [],
            "authorPersonList": ["fixture@unique@P"], "managerList": ["fixture@unique@P"]}
        self.payload = {"type": "success", "data": {"data": {"document": self.doc, "nvMarker": "expected"}}}

    def test_952_nested_readback_checks_actual_content_and_creator_only_acl(self):
        self.assertTrue(r.document_check(self.payload, self.manifest, "receipt", {"nvMarker": "expected"}))
        self.assertFalse(r.document_check(self.payload, self.manifest, "receipt", {"nvMarker": "wrong"}))
        self.doc["readPersonList"].append("所有人")
        self.assertFalse(r.document_check(self.payload, self.manifest, "receipt"))

    def test_cleanup_refuses_foreign_owner_category_or_run_marker(self):
        for field in ("creatorIdentity", "categoryId", "title"):
            with self.subTest(field=field):
                value = self.doc[field]
                self.doc[field] = "foreign"
                with mock.patch.object(r, "request", return_value=(200, self.payload)) as request:
                    with self.assertRaisesRegex(RuntimeError, "OWNERSHIP"):
                        r.cleanup(self.manifest, "receipt")
                    self.assertEqual(request.call_count, 1)
                self.doc[field] = value

    def test_cleanup_does_not_treat_auth_or_generic_server_error_as_absence(self):
        for code, payload in [(401, {}), (500, {"type": "error", "prompt": "database failed"})]:
            with mock.patch.object(r, "request", return_value=(code, payload)) as request:
                self.assertFalse(r.cleanup(self.manifest, "receipt")["ok"])
                request.assert_called_once()

    def test_cleanup_recognizes_actual_952_missing_document_error(self):
        missing = {"type": "error", "prompt": "ExceptionDocumentNotExists"}
        with mock.patch.object(r, "request", side_effect=[(200, self.payload), (200, {"type": "success"}), (500, missing)]) as request:
            self.assertTrue(r.cleanup(self.manifest, "receipt")["ok"])
            self.assertEqual([x.args[0] for x in request.call_args_list], ["GET", "DELETE", "GET"])

    def test_worker_hard_cap_stops_before_business_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            phase = root / "create_save"
            phase.mkdir()
            r.put(root / "runtime.json", {"invocation_cap": 1})
            r.put(phase / "invocations.json", 1)
            with mock.patch.object(r.h, "main") as harness:
                with self.assertRaisesRegex(RuntimeError, "CAP_REACHED"):
                    r.worker(phase, root / "unused.http")
                harness.assert_not_called()

    def test_reject_admin_even_with_fixture_identity(self):
        env = {"NV_TOKEN": "offline", "NV_O2OA_CATEGORY_ID": "fixture", "NV_O2OA_CURRENT_USER_IDENTITY": "fixture@unique@I"}
        with mock.patch.dict(r.os.environ, env, clear=True):
            with mock.patch.object(r, "request", return_value=(200, {"type": "success", "data": {"name": "Task4TestUser", "tokenType": "manager"}})):
                with self.assertRaisesRegex(RuntimeError, "NONADMIN"):
                    r.fixture()

    def test_reject_test_user_with_broad_role(self):
        env = {"NV_TOKEN": "offline", "NV_O2OA_CATEGORY_ID": "fixture", "NV_O2OA_CURRENT_USER_IDENTITY": "fixture@unique@I"}
        with mock.patch.dict(r.os.environ, env, clear=True):
            with mock.patch.object(r, "request", return_value=(200, {"type": "success", "data": {"name": "Task4TestUser", "roleList": ["CMSCreator@unique@R"]}})):
                with self.assertRaisesRegex(RuntimeError, "GLOBAL_CMS_ROLES"):
                    r.fixture()


if __name__ == "__main__":
    unittest.main()
