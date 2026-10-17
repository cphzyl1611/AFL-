"""Offline TDD contracts for native O2OA create/save and data update."""

from __future__ import annotations

import io
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

import nv_http_harness as harness
from nv_body_valid import body_validate
from nv_json_mutator import afl_custom_fuzz


REPO_ROOT = Path(__file__).parents[1]
TARGET_CONFIG = REPO_ROOT / "targets" / "o2oa_query.json"
RULES = REPO_ROOT / "validity" / "o2oa_query_rules.json"
CREATE_SEED = REPO_ROOT / "in" / "o2oa_document_create" / "seed_create_draft_0.json"
UPDATE_SEED = REPO_ROOT / "in" / "o2oa_document_data_update" / "seed_update_data_0.json"

CREATE = "cms_document_create_save"
DOCUMENT_GET = "cms_document_get"
UPDATE = "cms_document_data_update"
DATA_GET = "cms_document_data_get"
RUNTIME_CATEGORY_MARKER = "__NV_RUNTIME_CATEGORY_ID__"
RUNTIME_IDENTITY_MARKER = "__NV_RUNTIME_CURRENT_USER_IDENTITY__"
OFFLINE_CATEGORY = "offline-category-fixture"
OFFLINE_DOCUMENT = "offline-created-document-id"
OFFLINE_IDENTITY = "test-user@o2oa@I"
OFFLINE_PERSON = "test-user@o2oa@P"
ALL_PEOPLE = "所有人"
FORBIDDEN_CREATE_FIELDS = (
    "id",
    "identity",
    "authorList",
    "pictureList",
    "cloudPictures",
    "wf_jobId",
    "wf_workId",
    "wf_attachmentIds",
    "documentNotify",
    "publishTime",
    "dataPaths",
    "skipPermission",
)


def _config() -> dict:
    return json.loads(TARGET_CONFIG.read_text(encoding="utf-8"))


def _endpoint(config: dict, name: str) -> dict:
    return next(endpoint for endpoint in config["endpoints"] if endpoint.get("name") == name)


class _Response:
    headers: dict[str, str] = {}

    def __init__(self, payload: dict, code: int = 200):
        self.payload = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.code = code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def getcode(self) -> int:
        return self.code

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


class O2OACreateUpdateConfigSeedTest(unittest.TestCase):
    def test_native_endpoint_definitions_are_exact_and_bounded(self) -> None:
        config = _config()
        create = _endpoint(config, CREATE)
        document_get = _endpoint(config, DOCUMENT_GET)
        update = _endpoint(config, UPDATE)
        data_get = _endpoint(config, DATA_GET)

        self.assertEqual((create["method"], create["path"]), (
            "POST", "/x_cms_assemble_control/jaxrs/document"
        ))
        self.assertEqual(create["mutation_profile"], "o2oa_document_create")
        self.assertEqual(create["capture_document_id"], True)
        self.assertEqual(create["runtime_body_parameter"], {
            "field": "categoryId",
            "env": "NV_O2OA_CATEGORY_ID",
            "marker": RUNTIME_CATEGORY_MARKER,
        })
        self.assertEqual(create["runtime_body_path_parameters"], [{
            "path": ["readerList", 0, "permissionObjectCode"],
            "env": "NV_O2OA_CURRENT_USER_IDENTITY",
            "marker": RUNTIME_IDENTITY_MARKER,
        }])
        self.assertEqual(create["hotpicture_zero_check"], {
            "read_only_endpoint": "hotpic_list",
            "application": "CMS",
            "before_create_expected_count": 0,
            "after_create_expected_matching_count": 0,
            "after_create_context": "documentId",
        })
        self.assertEqual(config["body_templates"]["hotpic_list"], {
            "application": "CMS",
        })

        context_binding = {
            "placeholder": "{documentId}",
            "context": "documentId",
        }
        self.assertEqual((document_get["method"], document_get["path"]), (
            "GET", "/x_cms_assemble_control/jaxrs/document/{documentId}"
        ))
        self.assertEqual(document_get["runtime_path_parameter"], context_binding)
        self.assertEqual(document_get["request_body"], "none")
        self.assertEqual((update["method"], update["path"]), (
            "PUT", "/x_cms_assemble_control/jaxrs/data/document/{documentId}"
        ))
        self.assertEqual(update["runtime_path_parameter"], context_binding)
        self.assertEqual(update["mutation_profile"], "o2oa_document_data_update")
        self.assertEqual((data_get["method"], data_get["path"]), (
            "GET", "/x_cms_assemble_control/jaxrs/data/document/{documentId}"
        ))
        self.assertEqual(data_get["runtime_path_parameter"], context_binding)
        self.assertEqual(data_get["request_body"], "none")

        formal_paths = "\n".join(
            endpoint["path"] for endpoint in (create, document_get, update, data_get)
        )
        for forbidden in (
            "publish/content", "workflow", "attachment", "permission",
            "correlation", "notification", "event",
        ):
            self.assertNotIn(forbidden, formal_paths)

    def test_create_seed_is_draft_create_without_real_bindings(self) -> None:
        seed = json.loads(CREATE_SEED.read_text(encoding="utf-8"))
        self.assertEqual(seed, {
            "categoryId": RUNTIME_CATEGORY_MARKER,
            "title": "nv-formal-draft",
            "docStatus": "draft",
            "docData": {"nvMarker": "create-seed"},
            "readerList": [{
                "permissionObjectType": "人员",
                "permissionObjectCode": RUNTIME_IDENTITY_MARKER,
            }],
        })
        for field in FORBIDDEN_CREATE_FIELDS:
            self.assertNotIn(field, seed)

    def test_update_seed_is_nonempty_business_data_without_document_id(self) -> None:
        seed = json.loads(UPDATE_SEED.read_text(encoding="utf-8"))
        self.assertEqual(seed, {"nvMarker": "update-seed"})
        self.assertNotIn("documentId", seed)
        self.assertNotIn("id", seed)


class O2OACreateUpdateValidationTest(unittest.TestCase):
    def validate(self, endpoint: str, value) -> dict:
        return body_validate(
            scenario="metadata_update",
            endpoint_name=endpoint,
            raw_body=json.dumps(value).encode("utf-8"),
            rules_path=str(RULES),
        )

    def test_create_validation_enforces_formal_draft_create_contract(self) -> None:
        valid = {
            "categoryId": OFFLINE_CATEGORY,
            "title": "nv-formal-draft",
            "docStatus": "draft",
            "docData": {"nvMarker": "create-seed"},
            "readerList": [{
                "permissionObjectType": "人员",
                "permissionObjectCode": OFFLINE_IDENTITY,
            }],
        }
        self.assertTrue(self.validate(CREATE, valid)["ok"])
        for invalid in (
            {**valid, "categoryId": ""},
            {**valid, "title": 42},
            {**valid, "docStatus": "published"},
            {**valid, "docStatus": "waitPublish"},
            {**valid, "docData": []},
            {key: value for key, value in valid.items() if key != "readerList"},
            {**valid, "readerList": []},
            {**valid, "readerList": [valid["readerList"][0]] * 2},
            {**valid, "readerList": [{
                "permissionObjectType": "组织",
                "permissionObjectCode": OFFLINE_IDENTITY,
            }]},
            {**valid, "readerList": [{
                "permissionObjectType": "人员",
                "permissionObjectCode": "  ",
            }]},
        ):
            self.assertFalse(self.validate(CREATE, invalid)["ok"], invalid)

        for field in FORBIDDEN_CREATE_FIELDS:
            self.assertFalse(
                self.validate(CREATE, {**valid, field: "forbidden"})["ok"],
                field,
            )

    def test_update_validation_accepts_only_nonempty_json_objects(self) -> None:
        self.assertTrue(self.validate(UPDATE, {"nvMarker": "update-seed"})["ok"])
        for invalid in (None, [], "string", 123, True, {}):
            self.assertFalse(self.validate(UPDATE, invalid)["ok"], invalid)

    def test_readback_endpoints_accept_empty_control_seed(self) -> None:
        self.assertTrue(self.validate(DOCUMENT_GET, {})["ok"])
        self.assertTrue(self.validate(DATA_GET, {})["ok"])

    def test_existing_three_endpoint_seed_matrix_remains_valid(self) -> None:
        seeds = {
            "cms_doc_list": "seed_cms_doc_list_0.json",
            "review_count": "seed_review_count_0.json",
            "calendar_filter": "seed_calendar_filter_0.json",
        }
        for endpoint, filename in seeds.items():
            result = body_validate(
                scenario="metadata_update",
                endpoint_name=endpoint,
                raw_body=(REPO_ROOT / "in" / "o2oa_body" / filename).read_bytes(),
                rules_path=str(RULES),
            )
            self.assertTrue(result["ok"], (endpoint, result))


class O2OACreateUpdateMutationTest(unittest.TestCase):
    def mutate(self, endpoint: str, seed: bytes, arm: int) -> tuple[bytes, str | None]:
        with mock.patch.dict(
            os.environ,
            {
                "NV_BODY_ONLY_MODE": "1",
                "NV_ENDPOINT_NAME": endpoint,
                "NV_CUR_ARM": str(arm),
            },
            clear=True,
        ):
            mutated = bytes(afl_custom_fuzz(None, seed, b"", 4096))
            used_arm = os.environ.get("NV_JSON_ARM_USED")
        return mutated, used_arm

    def test_create_all_arms_mutate_content_and_protect_formal_invariants(self) -> None:
        seed = CREATE_SEED.read_bytes()
        original = json.loads(seed)
        for arm in range(3):
            mutated_bytes, used_arm = self.mutate(CREATE, seed, arm)
            mutated = json.loads(mutated_bytes)
            self.assertEqual(used_arm, str(arm))
            self.assertNotEqual(mutated, original)
            self.assertEqual(mutated["categoryId"], RUNTIME_CATEGORY_MARKER)
            self.assertEqual(mutated["docStatus"], "draft")
            self.assertEqual(mutated["readerList"], [{
                "permissionObjectType": "人员",
                "permissionObjectCode": RUNTIME_IDENTITY_MARKER,
            }])
            for field in FORBIDDEN_CREATE_FIELDS:
                self.assertNotIn(field, mutated)
            self.assertIsInstance(mutated["docData"], dict)
            effective = harness.bind_runtime_body_parameter(
                _endpoint(_config(), CREATE),
                mutated_bytes,
                environ={
                    "NV_O2OA_CATEGORY_ID": OFFLINE_CATEGORY,
                    "NV_O2OA_CURRENT_USER_IDENTITY": OFFLINE_IDENTITY,
                },
            )
            effective_obj = json.loads(effective)
            self.assertEqual(effective_obj["readerList"], [{
                "permissionObjectType": "人员",
                "permissionObjectCode": OFFLINE_IDENTITY,
            }])
            validation = body_validate(
                scenario="metadata_update",
                endpoint_name=CREATE,
                raw_body=effective,
                rules_path=str(RULES),
            )
            self.assertTrue(validation["ok"], validation)

    def test_update_mutation_changes_actual_body_and_preserves_attribution(self) -> None:
        seed = UPDATE_SEED.read_bytes()
        mutated, used_arm = self.mutate(UPDATE, seed, 0)
        self.assertEqual(used_arm, "0")
        self.assertNotEqual(mutated, seed)
        self.assertNotEqual(json.loads(mutated)["nvMarker"], "update-seed")
        validation = body_validate(
            scenario="metadata_update",
            endpoint_name=UPDATE,
            raw_body=mutated,
            rules_path=str(RULES),
        )
        self.assertTrue(validation["ok"], validation)


class O2OARuntimeBindingContextTest(unittest.TestCase):
    def test_runtime_category_binding_is_exact_and_fail_closed(self) -> None:
        create = _endpoint(_config(), CREATE)
        seed = CREATE_SEED.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "NV_O2OA_CATEGORY_ID"):
            harness.bind_runtime_body_parameter(
                create,
                seed,
                environ={"NV_O2OA_CURRENT_USER_IDENTITY": OFFLINE_IDENTITY},
            )
        with self.assertRaisesRegex(RuntimeError, "NV_O2OA_CATEGORY_ID"):
            harness.bind_runtime_body_parameter(
                create,
                seed,
                environ={
                    "NV_O2OA_CATEGORY_ID": "  ",
                    "NV_O2OA_CURRENT_USER_IDENTITY": OFFLINE_IDENTITY,
                },
            )

        effective = harness.bind_runtime_body_parameter(
            create,
            seed,
            environ={
                "NV_O2OA_CATEGORY_ID": OFFLINE_CATEGORY,
                "NV_O2OA_CURRENT_USER_IDENTITY": OFFLINE_IDENTITY,
            },
        )
        body = json.loads(effective)
        self.assertEqual(body["categoryId"], OFFLINE_CATEGORY)
        self.assertEqual(body["readerList"], [{
            "permissionObjectType": "人员",
            "permissionObjectCode": OFFLINE_IDENTITY,
        }])
        self.assertEqual(body["docStatus"], "draft")
        self.assertNotIn("id", body)

    def test_runtime_current_user_identity_binding_is_exact_and_fail_closed(self) -> None:
        create = _endpoint(_config(), CREATE)
        seed = CREATE_SEED.read_bytes()
        for environ in (
            {"NV_O2OA_CATEGORY_ID": OFFLINE_CATEGORY},
            {
                "NV_O2OA_CATEGORY_ID": OFFLINE_CATEGORY,
                "NV_O2OA_CURRENT_USER_IDENTITY": "  ",
            },
        ):
            with self.assertRaisesRegex(
                RuntimeError, "NV_O2OA_CURRENT_USER_IDENTITY"
            ):
                harness.bind_runtime_body_parameter(create, seed, environ=environ)

        effective = harness.bind_runtime_body_parameter(
            create,
            seed,
            environ={
                "NV_O2OA_CATEGORY_ID": OFFLINE_CATEGORY,
                "NV_O2OA_CURRENT_USER_IDENTITY": OFFLINE_IDENTITY,
            },
        )
        self.assertEqual(
            json.loads(effective)["readerList"][0]["permissionObjectCode"],
            OFFLINE_IDENTITY,
        )

    def test_create_harness_stops_before_transport_without_runtime_category(self) -> None:
        with tempfile.TemporaryDirectory(prefix="o2oa_category_fail_closed_") as directory:
            tmp = Path(directory)
            env = {
                "NV_TARGET_CONFIG": str(TARGET_CONFIG),
                "NV_BODY_RULES": str(RULES),
                "NV_ENDPOINT_NAME": CREATE,
                "NV_CTX_PATH": str(tmp / "nv_ctx.json"),
            }
            stdin = types.SimpleNamespace(buffer=io.BytesIO(CREATE_SEED.read_bytes()))
            with (
                mock.patch.dict(harness.os.environ, env, clear=True),
                mock.patch.object(harness.sys, "stdin", stdin),
                mock.patch.object(harness, "open_direct") as transport,
            ):
                with self.assertRaisesRegex(RuntimeError, "NV_O2OA_CATEGORY_ID"):
                    harness.main()
            transport.assert_not_called()

    def test_create_harness_stops_before_transport_without_runtime_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="o2oa_identity_fail_closed_") as directory:
            tmp = Path(directory)
            env = {
                "NV_TARGET_CONFIG": str(TARGET_CONFIG),
                "NV_BODY_RULES": str(RULES),
                "NV_ENDPOINT_NAME": CREATE,
                "NV_CTX_PATH": str(tmp / "nv_ctx.json"),
                "NV_O2OA_CATEGORY_ID": OFFLINE_CATEGORY,
            }
            stdin = types.SimpleNamespace(buffer=io.BytesIO(CREATE_SEED.read_bytes()))
            with (
                mock.patch.dict(harness.os.environ, env, clear=True),
                mock.patch.object(harness.sys, "stdin", stdin),
                mock.patch.object(harness, "open_direct") as transport,
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "NV_O2OA_CURRENT_USER_IDENTITY"
                ):
                    harness.main()
            transport.assert_not_called()

    def test_document_context_path_binding_is_exact_and_fail_closed(self) -> None:
        config = _config()
        for endpoint in (DOCUMENT_GET, UPDATE, DATA_GET):
            with self.assertRaisesRegex(RuntimeError, "documentId"):
                harness.resolve_named_endpoint(
                    config,
                    endpoint,
                    environ={},
                    context={},
                )

        method, path, _ = harness.resolve_named_endpoint(
            config,
            UPDATE,
            environ={},
            context={"documentId": OFFLINE_DOCUMENT},
        )
        self.assertEqual(method, "PUT")
        self.assertEqual(
            path,
            "/x_cms_assemble_control/jaxrs/data/document/" + OFFLINE_DOCUMENT,
        )

    def test_create_response_uses_o2oa_action_result_data_id(self) -> None:
        response = json.dumps({
            "type": "success",
            "data": {"id": OFFLINE_DOCUMENT},
        }).encode("utf-8")
        self.assertEqual(harness.extract_o2oa_document_id(response), OFFLINE_DOCUMENT)
        for invalid in (
            b"{}",
            b'{"data":{"documentId":"guessed-alias"}}',
            b'{"id":"wrong-level"}',
        ):
            self.assertIsNone(harness.extract_o2oa_document_id(invalid))

    def test_context_save_is_run_local_and_atomic_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="o2oa_ctx_offline_") as directory:
            path = Path(directory) / "run" / "nv_ctx.json"
            path.parent.mkdir()
            env = {"NV_CTX_PATH": str(path)}
            with mock.patch.dict(harness.os.environ, env, clear=True):
                harness.ctx_save({"documentId": OFFLINE_DOCUMENT}, require_explicit=True)
                self.assertEqual(
                    harness.ctx_load(require_explicit=True),
                    {"documentId": OFFLINE_DOCUMENT},
                )
            self.assertTrue(path.is_file())
            self.assertFalse(Path(str(path) + ".tmp").exists())

    def test_document_readback_requires_creator_only_acl_and_no_all_people(self) -> None:
        valid = json.dumps({
            "type": "success",
            "data": {
                "nvMarker": "create-seed",
                "document": {
                    "id": OFFLINE_DOCUMENT,
                    "categoryId": OFFLINE_CATEGORY,
                    "title": "nv-formal-draft",
                    "docStatus": "draft",
                    "creatorIdentity": OFFLINE_IDENTITY,
                    "creatorPerson": OFFLINE_PERSON,
                    "readPersonList": [OFFLINE_PERSON],
                    "readUnitList": [],
                    "readGroupList": [],
                    "authorPersonList": [OFFLINE_PERSON],
                    "managerList": [OFFLINE_PERSON],
                },
            },
        }).encode("utf-8")
        expected = {
            "document_id": OFFLINE_DOCUMENT,
            "category_id": OFFLINE_CATEGORY,
            "title": "nv-formal-draft",
            "doc_status": "draft",
            "reader_identity": OFFLINE_IDENTITY,
            "doc_data": {"nvMarker": "create-seed"},
        }
        self.assertTrue(harness.verify_o2oa_document_readback(valid, **expected))

        for document_patch in (
            {"readPersonList": [ALL_PEOPLE, OFFLINE_PERSON]},
            {"readPersonList": []},
            {"readPersonList": ["another-user@o2oa@P"]},
            {"readUnitList": ["all-unit"]},
            {"readGroupList": ["all-group"]},
            {"authorPersonList": ["another-user@o2oa@P"]},
            {"managerList": ["another-user@o2oa@P"]},
            {"creatorIdentity": "another-user@o2oa@I"},
        ):
            payload = json.loads(valid)
            payload["data"]["document"].update(document_patch)
            self.assertFalse(harness.verify_o2oa_document_readback(
                json.dumps(payload).encode("utf-8"), **expected
            ), document_patch)

        flat_payload = json.dumps({
            "type": "success",
            "data": {
                "id": OFFLINE_DOCUMENT,
                "categoryId": OFFLINE_CATEGORY,
                "title": "nv-formal-draft",
                "docStatus": "draft",
                "nvMarker": "create-seed",
                "readPersonList": [OFFLINE_PERSON],
            },
        }).encode("utf-8")
        self.assertFalse(harness.verify_o2oa_document_readback(
            flat_payload, **expected
        ))

    def test_hotpicture_pre_post_zero_check_contract(self) -> None:
        empty = b'{"type":"success","data":[]}'
        self.assertTrue(harness.verify_o2oa_hotpicture_zero(
            empty, application="CMS"
        ))
        self.assertTrue(harness.verify_o2oa_hotpicture_zero(
            empty, application="CMS", info_id=OFFLINE_DOCUMENT
        ))
        matching = json.dumps({
            "type": "success",
            "data": [{"application": "CMS", "infoId": OFFLINE_DOCUMENT}],
        }).encode("utf-8")
        self.assertFalse(harness.verify_o2oa_hotpicture_zero(
            matching, application="CMS"
        ))
        self.assertFalse(harness.verify_o2oa_hotpicture_zero(
            matching, application="CMS", info_id=OFFLINE_DOCUMENT
        ))


class O2OAFormalStateChainTest(unittest.TestCase):
    def test_mocked_create_readback_update_readback_uses_one_document(self) -> None:
        with tempfile.TemporaryDirectory(prefix="o2oa_state_chain_") as directory:
            tmp = Path(directory)
            ctx_path = tmp / "nv_ctx.json"
            status_path = tmp / "status.json"
            env = {
                "NV_TARGET_CONFIG": str(TARGET_CONFIG),
                "NV_BODY_RULES": str(RULES),
                "NV_BODY_VALID_STATS": str(tmp / "body-valid.json"),
                "NV_STATUS_LEDGER_PATH": str(tmp / "status.jsonl"),
                "NV_CTX_PATH": str(ctx_path),
                "NV_O2OA_CATEGORY_ID": OFFLINE_CATEGORY,
                "NV_O2OA_CURRENT_USER_IDENTITY": OFFLINE_IDENTITY,
                "NV_BODY_ONLY_MODE": "1",
            }
            requests = []

            def invoke(endpoint: str, seed: bytes, response: dict) -> bytes:
                os.environ["NV_ENDPOINT_NAME"] = endpoint
                stdin = types.SimpleNamespace(buffer=io.BytesIO(seed))

                def open_direct(request, timeout):
                    del timeout
                    requests.append(request)
                    return _Response(response)

                with (
                    mock.patch.object(harness.sys, "stdin", stdin),
                    mock.patch.object(harness, "open_direct", side_effect=open_direct),
                ):
                    self.assertEqual(harness.main(), 0)
                return json.dumps(response, separators=(",", ":")).encode("utf-8")

            with (
                mock.patch.dict(harness.os.environ, env, clear=True),
                mock.patch.object(harness, "STATUS_PATH", str(status_path)),
                mock.patch.object(harness, "_CTX_PATH", None),
                mock.patch.object(
                    harness, "apply_auth_headers", side_effect=lambda cfg, headers: headers
                ),
                mock.patch.object(
                    harness,
                    "update_state",
                    return_value={"ncov_delta": 1, "ncov_total": 1, "nall": 1},
                ),
            ):
                create_response = invoke(
                    CREATE,
                    CREATE_SEED.read_bytes(),
                    {"type": "success", "data": {"id": OFFLINE_DOCUMENT}},
                )
                self.assertEqual(
                    harness.extract_o2oa_document_id(create_response), OFFLINE_DOCUMENT
                )
                self.assertEqual(
                    harness.ctx_load(require_explicit=True)["documentId"],
                    OFFLINE_DOCUMENT,
                )

                document_response = invoke(
                    DOCUMENT_GET,
                    b"{}",
                    {
                        "type": "success",
                        "data": {
                            "nvMarker": "create-seed",
                            "document": {
                                "id": OFFLINE_DOCUMENT,
                                "categoryId": OFFLINE_CATEGORY,
                                "title": "nv-formal-draft",
                                "docStatus": "draft",
                                "creatorIdentity": OFFLINE_IDENTITY,
                                "creatorPerson": OFFLINE_PERSON,
                                "readPersonList": [OFFLINE_PERSON],
                                "readUnitList": [],
                                "readGroupList": [],
                                "authorPersonList": [OFFLINE_PERSON],
                                "managerList": [OFFLINE_PERSON],
                            },
                        },
                    },
                )
                self.assertTrue(harness.verify_o2oa_document_readback(
                    document_response,
                    document_id=OFFLINE_DOCUMENT,
                    category_id=OFFLINE_CATEGORY,
                    title="nv-formal-draft",
                    doc_status="draft",
                    reader_identity=OFFLINE_IDENTITY,
                    doc_data={"nvMarker": "create-seed"},
                ))

                with mock.patch.dict(
                    os.environ,
                    {
                        **env,
                        "NV_ENDPOINT_NAME": UPDATE,
                        "NV_CUR_ARM": "0",
                    },
                    clear=True,
                ):
                    mutated_update = bytes(
                        afl_custom_fuzz(None, UPDATE_SEED.read_bytes(), b"", 4096)
                    )
                    self.assertEqual(os.environ.get("NV_JSON_ARM_USED"), "0")
                updated_marker = json.loads(mutated_update)["nvMarker"]
                self.assertNotEqual(updated_marker, "update-seed")
                invoke(
                    UPDATE,
                    mutated_update,
                    {"type": "success", "data": {"id": OFFLINE_DOCUMENT}},
                )

                data_response = invoke(
                    DATA_GET,
                    b"{}",
                    {"type": "success", "data": {"nvMarker": updated_marker}},
                )
                self.assertTrue(harness.verify_o2oa_data_readback(
                    data_response, {"nvMarker": updated_marker}
                ))

            self.assertEqual([request.method for request in requests], [
                "POST", "GET", "PUT", "GET"
            ])
            self.assertEqual(urlsplit(requests[0].full_url).path,
                "/x_cms_assemble_control/jaxrs/document")
            for request in requests[1:]:
                self.assertIn(OFFLINE_DOCUMENT, urlsplit(request.full_url).path)
            create_body = json.loads(requests[0].data)
            self.assertEqual(create_body["categoryId"], OFFLINE_CATEGORY)
            self.assertEqual(create_body["docStatus"], "draft")
            self.assertEqual(create_body["readerList"], [{
                "permissionObjectType": "人员",
                "permissionObjectCode": OFFLINE_IDENTITY,
            }])
            for field in FORBIDDEN_CREATE_FIELDS:
                self.assertNotIn(field, create_body)
            self.assertIsNone(requests[1].data)
            self.assertEqual(json.loads(requests[2].data)["nvMarker"], updated_marker)
            self.assertIsNone(requests[3].data)

            records = [
                json.loads(line)
                for line in (tmp / "status.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(records), 4)
            self.assertEqual([record["method"] for record in records], [
                "POST", "GET", "PUT", "GET"
            ])
            exec_sequences = [record["exec_seq"] for record in records]
            self.assertTrue(all(sequence > 0 for sequence in exec_sequences))
            self.assertEqual(exec_sequences, sorted(set(exec_sequences)))
            self.assertTrue(all(record["ncov_delta"] == 1 for record in records))


if __name__ == "__main__":
    unittest.main()
