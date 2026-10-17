"""Offline end-to-end contract for the native O2OA URL-query scenario."""

from __future__ import annotations

import io
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import nv_http_harness as harness
from nv_body_valid import body_validate
from nv_json_mutator import afl_custom_fuzz
from nv_url_query import build_query_string, mutate_query_value, parse_seed


REPO_ROOT = Path(__file__).parents[1]
TARGET_CONFIG = REPO_ROOT / "targets" / "o2oa_query.json"
RULES = REPO_ROOT / "validity" / "o2oa_query_rules.json"
SEED = (
    REPO_ROOT
    / "in"
    / "o2oa_url_query"
    / "seed_cms_attachment_download_query_0.json"
)
ENDPOINT_NAME = "cms_attachment_download_query"
PATH_TEMPLATE = (
    "/x_cms_assemble_control/jaxrs/fileinfo/download/document/{attachmentId}"
)


class _Response:
    headers = {"Content-Disposition": 'attachment; filename="mutated-name.txt"'}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def getcode(self) -> int:
        return 200

    def read(self, limit: int) -> bytes:
        del limit
        return b"offline-response"


def _endpoint(config: dict) -> dict:
    return next(
        endpoint
        for endpoint in config["endpoints"]
        if endpoint.get("name") == ENDPOINT_NAME
    )


class O2OAURLQueryConfigAndSeedTest(unittest.TestCase):
    def test_native_endpoint_config_is_exact_and_runtime_bound(self) -> None:
        config = json.loads(TARGET_CONFIG.read_text(encoding="utf-8"))
        endpoint = _endpoint(config)

        self.assertEqual(endpoint["method"], "GET")
        self.assertEqual(endpoint["path"], PATH_TEMPLATE)
        self.assertEqual(endpoint["transport"], "url_query")
        self.assertEqual(endpoint["request_body"], "none")
        self.assertEqual(
            endpoint["runtime_path_parameter"],
            {
                "placeholder": "{attachmentId}",
                "env": "NV_O2OA_ATTACHMENT_ID",
            },
        )
        self.assertEqual(config["auth"]["token_env"], "NV_TOKEN")
        self.assertNotIn("token", config["auth"])

    def test_runtime_attachment_id_is_required_and_fail_closed(self) -> None:
        config = json.loads(TARGET_CONFIG.read_text(encoding="utf-8"))

        with self.assertRaisesRegex(RuntimeError, "NV_O2OA_ATTACHMENT_ID"):
            harness.resolve_named_endpoint(config, ENDPOINT_NAME, environ={})
        with self.assertRaisesRegex(RuntimeError, "NV_O2OA_ATTACHMENT_ID"):
            harness.resolve_named_endpoint(
                config,
                ENDPOINT_NAME,
                environ={"NV_O2OA_ATTACHMENT_ID": "   "},
            )

        method, path, endpoint = harness.resolve_named_endpoint(
            config,
            ENDPOINT_NAME,
            environ={"NV_O2OA_ATTACHMENT_ID": "offline id/only"},
        )
        self.assertEqual(method, "GET")
        self.assertEqual(
            path,
            "/x_cms_assemble_control/jaxrs/fileinfo/download/document/"
            "offline%20id%2Fonly",
        )
        self.assertEqual(endpoint["name"], ENDPOINT_NAME)

    def test_dedicated_query_seed_uses_canonical_query_only_envelope(self) -> None:
        query, body = parse_seed(SEED.read_bytes())

        self.assertEqual(query, {"fileName": "nv-query.txt"})
        self.assertIsNone(body)
        self.assertNotIn("attachmentId", SEED.read_text(encoding="utf-8"))


class O2OAURLQueryMutationAndEncodingTest(unittest.TestCase):
    def test_query_only_seed_mutation_changes_value_and_preserves_attribution(self) -> None:
        seed = SEED.read_bytes()
        with mock.patch.dict(
            os.environ,
            {"NV_BODY_ONLY_MODE": "1", "NV_CUR_ARM": "0"},
            clear=True,
        ):
            mutated = bytes(afl_custom_fuzz(None, seed, b"", 4096))
            used_arm = os.environ.get("NV_JSON_ARM_USED")

        query, body = parse_seed(mutated)
        self.assertEqual(used_arm, "0")
        self.assertIsNone(body)
        self.assertIn("fileName", query)
        self.assertNotEqual(query["fileName"], "nv-query.txt")

    def test_value_boundary_and_structure_mutations_change_serialized_query(self) -> None:
        original = {"fileName": "nv-query.txt"}
        original_query = build_query_string(original)

        value = mutate_query_value(original, "value")
        with mock.patch("random.random", return_value=0.0):
            boundary = mutate_query_value(original, "boundary")
        structure = mutate_query_value(original, "structure")

        self.assertNotEqual(build_query_string(value), original_query)
        self.assertNotEqual(build_query_string(boundary), original_query)
        self.assertNotEqual(build_query_string(structure), original_query)
        self.assertIsInstance(structure["fileName"], list)

    def test_all_query_arms_preserve_query_only_envelope_and_attribution(self) -> None:
        seed = SEED.read_bytes()
        for arm in range(3):
            env = {"NV_BODY_ONLY_MODE": "1", "NV_CUR_ARM": str(arm)}
            random_patch = (
                mock.patch("random.random", return_value=0.0)
                if arm == 1
                else mock.patch("random.random", wraps=__import__("random").random)
            )
            with mock.patch.dict(os.environ, env, clear=True), random_patch:
                mutated = bytes(afl_custom_fuzz(None, seed, b"", 4096))
                used_arm = os.environ.get("NV_JSON_ARM_USED")

            query, body = parse_seed(mutated)
            self.assertEqual(used_arm, str(arm))
            self.assertIsInstance(query, dict)
            self.assertIsNone(body)
            self.assertNotEqual(build_query_string(query), "fileName=nv-query.txt")
            validation = body_validate(
                scenario="metadata_update",
                endpoint_name=ENDPOINT_NAME,
                raw_body=mutated,
                rules_path=str(RULES),
            )
            self.assertTrue(validation["ok"], validation)

    def test_percent_encoding_round_trips_semantically(self) -> None:
        semantic = {"fileName": "space + & = 文件.txt"}
        encoded = build_query_string(semantic)

        self.assertIn("space+", encoded)
        self.assertIn("%2B", encoded)
        self.assertIn("%26", encoded)
        self.assertIn("%3D", encoded)
        self.assertIn("%E6%96%87%E4%BB%B6", encoded)
        self.assertEqual(parse_qs(encoded, keep_blank_values=True), {
            "fileName": [semantic["fileName"]]
        })


class O2OAURLQueryValidationTest(unittest.TestCase):
    def validate(self, raw: bytes) -> dict:
        return body_validate(
            scenario="metadata_update",
            endpoint_name=ENDPOINT_NAME,
            raw_body=raw,
            rules_path=str(RULES),
        )

    def test_query_envelope_is_not_rejected_by_unrelated_body_required_rules(self) -> None:
        result = self.validate(SEED.read_bytes())

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["query"], {"fileName": "nv-query.txt"})
        self.assertIsNone(result["body"])

    def test_file_name_type_length_and_bodyless_contract_are_validated(self) -> None:
        self.assertFalse(self.validate(b'{"query":{"fileName":42}}')["ok"])
        self.assertFalse(
            self.validate(
                json.dumps({"query": {"fileName": "x" * 2049}}).encode("utf-8")
            )["ok"]
        )
        self.assertFalse(
            self.validate(
                b'{"query":{"fileName":"ok.txt"},"body":{"unexpected":true}}'
            )["ok"]
        )
        self.assertTrue(self.validate(b'{"query":{}}')["ok"])

    def test_existing_json_body_endpoint_rules_still_apply(self) -> None:
        result = body_validate(
            scenario="metadata_update",
            endpoint_name="cms_doc_list",
            raw_body=(REPO_ROOT / "in" / "o2oa_body" / "seed_cms_doc_list_0.json").read_bytes(),
            rules_path=str(RULES),
        )
        self.assertTrue(result["ok"], result)


class O2OAURLQueryHarnessTest(unittest.TestCase):
    def test_harness_never_reaches_transport_without_runtime_attachment_id(self) -> None:
        stdin = types.SimpleNamespace(buffer=io.BytesIO(SEED.read_bytes()))
        env = {
            "NV_TARGET_CONFIG": str(TARGET_CONFIG),
            "NV_BODY_RULES": str(RULES),
            "NV_ENDPOINT_NAME": ENDPOINT_NAME,
        }
        with (
            mock.patch.dict(harness.os.environ, env, clear=True),
            mock.patch.object(harness.sys, "stdin", stdin),
            mock.patch.object(harness, "open_direct") as transport,
        ):
            with self.assertRaisesRegex(RuntimeError, "NV_O2OA_ATTACHMENT_ID"):
                harness.main()

        transport.assert_not_called()

    def test_mock_transport_gets_mutated_query_zero_body_and_observes_response(self) -> None:
        seed = SEED.read_bytes()
        with mock.patch.dict(
            os.environ,
            {"NV_BODY_ONLY_MODE": "1", "NV_CUR_ARM": "0"},
            clear=True,
        ):
            mutated = bytes(afl_custom_fuzz(None, seed, b"", 4096))
        mutated_query, mutated_body = parse_seed(mutated)
        self.assertIsNone(mutated_body)

        with tempfile.TemporaryDirectory(prefix="o2oa_url_query_offline_") as directory:
            tmp = Path(directory)
            status = tmp / "status.json"
            stdin = types.SimpleNamespace(buffer=io.BytesIO(mutated))
            env = {
                "NV_TARGET_CONFIG": str(TARGET_CONFIG),
                "NV_BODY_RULES": str(RULES),
                "NV_ENDPOINT_NAME": ENDPOINT_NAME,
                "NV_O2OA_ATTACHMENT_ID": "offline-attachment-id",
                "NV_BODY_VALID_STATS": str(tmp / "body-valid.json"),
                "NV_STATUS_LEDGER_PATH": str(tmp / "status.jsonl"),
            }
            with (
                mock.patch.dict(harness.os.environ, env, clear=True),
                mock.patch.object(harness, "STATUS_PATH", str(status)),
                mock.patch.object(harness.sys, "stdin", stdin),
                mock.patch.object(harness, "apply_auth_headers", side_effect=lambda cfg, headers: headers) as auth,
                mock.patch.object(harness, "open_direct", return_value=_Response()) as transport,
                mock.patch.object(
                    harness,
                    "update_state",
                    return_value={"ncov_delta": 1, "ncov_total": 2, "nall": 3},
                ),
            ):
                return_code = harness.main()

            self.assertEqual(return_code, 0)
            auth.assert_called_once()
            transport.assert_called_once()
            request = transport.call_args.args[0]
            parsed = urlsplit(request.full_url)
            self.assertEqual(request.method, "GET")
            self.assertEqual(
                parsed.path,
                "/x_cms_assemble_control/jaxrs/fileinfo/download/document/"
                "offline-attachment-id",
            )
            self.assertEqual(
                parse_qs(parsed.query, keep_blank_values=True),
                {
                    "fileName": (
                        mutated_query["fileName"]
                        if isinstance(mutated_query["fileName"], list)
                        else [mutated_query["fileName"]]
                    )
                },
            )
            self.assertNotEqual(
                parse_qs(parsed.query)["fileName"],
                ["nv-query.txt"],
            )
            self.assertIsNone(request.data)
            self.assertEqual(request.get_header("Content-length"), None)

            observed = json.loads(status.read_text(encoding="utf-8"))
            self.assertEqual(observed["http_code"], 200)
            self.assertGreater(observed["exec_seq"], 0)
            self.assertEqual(observed["path"], parsed.path + "?" + parsed.query)
            self.assertEqual(observed["ncov_delta"], 1)
            self.assertEqual(
                observed["content_disposition"],
                'attachment; filename="mutated-name.txt"',
            )


if __name__ == "__main__":
    unittest.main()
