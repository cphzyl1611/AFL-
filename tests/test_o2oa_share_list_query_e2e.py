"""Offline contract for the native O2OA share-list URL-query scenario."""

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
from nv_url_query import parse_seed


REPO_ROOT = Path(__file__).parents[1]
TARGET_CONFIG = REPO_ROOT / "targets" / "o2oa_query.json"
RULES = REPO_ROOT / "validity" / "o2oa_query_rules.json"
SEED = (
    REPO_ROOT
    / "in"
    / "o2oa_url_query"
    / "seed_file_share_list_my_query_0.json"
)
ENDPOINT_NAME = "file_share_list_my_query"
ENDPOINT_PATH = "/x_file_assemble_control/jaxrs/share/list/my"
ALLOWED_FILE_TYPES = {"attachment", "folder"}


class _Response:
    headers: dict[str, str] = {}

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def getcode(self) -> int:
        return 200

    def read(self, limit: int) -> bytes:
        return json.dumps(self.payload, separators=(",", ":")).encode("utf-8")[:limit]


def _endpoint(config: dict) -> dict:
    return next(
        endpoint
        for endpoint in config["endpoints"]
        if endpoint.get("name") == ENDPOINT_NAME
    )


def _mutate(seed: bytes) -> tuple[bytes, str | None]:
    env = {
        "NV_BODY_ONLY_MODE": "1",
        "NV_CUR_ARM": "0",
        "NV_ENDPOINT_NAME": ENDPOINT_NAME,
    }
    with mock.patch.dict(os.environ, env, clear=True):
        mutated = bytes(afl_custom_fuzz(None, seed, b"", 4096))
        used_arm = os.environ.get("NV_JSON_ARM_USED")
    return mutated, used_arm


class O2OAShareListQueryConfigSeedValidationTest(unittest.TestCase):
    def validate(self, raw: bytes) -> dict:
        return body_validate(
            scenario="metadata_update",
            endpoint_name=ENDPOINT_NAME,
            raw_body=raw,
            rules_path=str(RULES),
        )

    def test_native_endpoint_is_exact_bodyless_and_needs_no_runtime_id(self) -> None:
        config = json.loads(TARGET_CONFIG.read_text(encoding="utf-8"))
        endpoint = _endpoint(config)

        self.assertEqual(endpoint["method"], "GET")
        self.assertEqual(endpoint["path"], ENDPOINT_PATH)
        self.assertEqual(endpoint["transport"], "url_query")
        self.assertEqual(endpoint["request_body"], "none")
        self.assertNotIn("runtime_path_parameter", endpoint)
        self.assertNotIn("runtime_body_parameter", endpoint)

        method, path, resolved = harness.resolve_named_endpoint(
            config,
            ENDPOINT_NAME,
            environ={},
        )
        self.assertEqual((method, path), ("GET", ENDPOINT_PATH))
        self.assertEqual(resolved["name"], ENDPOINT_NAME)

    def test_canonical_seed_is_query_only_and_contains_no_identifier(self) -> None:
        raw = SEED.read_bytes()
        query, body = parse_seed(raw)

        self.assertEqual(query, {"fileType": "attachment"})
        self.assertIsNone(body)
        seed_text = raw.decode("utf-8")
        for forbidden in ("attachmentId", "documentId", "categoryId", "NV_TOKEN"):
            self.assertNotIn(forbidden, seed_text)

    def test_validation_accepts_only_the_authoritative_file_type_enum(self) -> None:
        for value in ("attachment", "folder"):
            result = self.validate(
                json.dumps({"query": {"fileType": value}}).encode("utf-8")
            )
            self.assertTrue(result["ok"], result)

        invalid_envelopes = (
            {"query": {"fileType": "attachment7"}},
            {"query": {"fileType": ""}},
            {"query": {"fileType": ["attachment", "folder"]}},
            {"query": {"fileType": "attachment", "unknown": "value"}},
            {"query": {"fileType": "attachment"}, "body": {}},
        )
        for envelope in invalid_envelopes:
            with self.subTest(envelope=envelope):
                result = self.validate(json.dumps(envelope).encode("utf-8"))
                self.assertFalse(result["ok"], result)


class O2OAShareListQueryMutationTest(unittest.TestCase):
    def test_field_value_arm_swaps_attachment_to_folder(self) -> None:
        mutated, used_arm = _mutate(b'{"query":{"fileType":"attachment"}}')
        query, body = parse_seed(mutated)

        self.assertEqual(used_arm, "0")
        self.assertEqual(query, {"fileType": "folder"})
        self.assertIsNone(body)
        self.assertIn(query["fileType"], ALLOWED_FILE_TYPES)

    def test_field_value_arm_swaps_folder_to_attachment(self) -> None:
        mutated, used_arm = _mutate(b'{"query":{"fileType":"folder"}}')
        query, body = parse_seed(mutated)

        self.assertEqual(used_arm, "0")
        self.assertEqual(query, {"fileType": "attachment"})
        self.assertIsNone(body)
        self.assertIn(query["fileType"], ALLOWED_FILE_TYPES)

    def test_attachment_endpoint_retains_generic_field_value_mutation(self) -> None:
        seed = b'{"query":{"fileName":"nv-query.txt"}}'
        env = {
            "NV_BODY_ONLY_MODE": "1",
            "NV_CUR_ARM": "0",
            "NV_ENDPOINT_NAME": "cms_attachment_download_query",
        }
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch(
                "nv_json_mutator.mutate_query_value",
                return_value={"fileName": "generic-mutated.txt"},
            ) as generic_mutator,
        ):
            mutated = bytes(afl_custom_fuzz(None, seed, b"", 4096))
            used_arm = os.environ.get("NV_JSON_ARM_USED")

        query, body = parse_seed(mutated)
        self.assertEqual(used_arm, "0")
        self.assertEqual(query, {"fileName": "generic-mutated.txt"})
        self.assertIsNone(body)
        generic_mutator.assert_called_once_with(
            {"fileName": "nv-query.txt"},
            "value",
        )


class O2OAShareListQueryHarnessTest(unittest.TestCase):
    def run_harness(self, response_payload: dict) -> tuple[int, object, dict, object]:
        mutated, used_arm = _mutate(SEED.read_bytes())
        self.assertEqual(used_arm, "0")
        query, body = parse_seed(mutated)
        self.assertEqual(query, {"fileType": "folder"})
        self.assertIsNone(body)

        temporary = tempfile.TemporaryDirectory(prefix="o2oa_share_query_offline_")
        self.addCleanup(temporary.cleanup)
        tmp = Path(temporary.name)
        status = tmp / "status.json"
        stdin = types.SimpleNamespace(buffer=io.BytesIO(mutated))
        env = {
            "NV_TARGET_CONFIG": str(TARGET_CONFIG),
            "NV_BODY_RULES": str(RULES),
            "NV_ENDPOINT_NAME": ENDPOINT_NAME,
            "NV_BODY_VALID_STATS": str(tmp / "body-valid.json"),
            "NV_STATUS_LEDGER_PATH": str(tmp / "status.jsonl"),
        }
        state_result = {"ncov_delta": 1, "ncov_total": 2, "nall": 3}
        with (
            mock.patch.dict(harness.os.environ, env, clear=True),
            mock.patch.object(harness, "STATUS_PATH", str(status)),
            mock.patch.object(harness.sys, "stdin", stdin),
            mock.patch.object(
                harness,
                "apply_auth_headers",
                side_effect=lambda cfg, headers: headers,
            ),
            mock.patch.object(
                harness,
                "open_direct",
                return_value=_Response(response_payload),
            ) as transport,
            mock.patch.object(
                harness,
                "update_state",
                return_value=state_result,
            ) as update_state,
        ):
            return_code = harness.main()

        return return_code, transport.call_args.args[0], json.loads(
            status.read_text(encoding="utf-8")
        ), update_state

    def test_transmitted_query_is_mutated_and_get_has_zero_body(self) -> None:
        return_code, request, observed, update_state = self.run_harness({"data": []})
        parsed = urlsplit(request.full_url)

        self.assertEqual(return_code, 0)
        self.assertEqual(request.method, "GET")
        self.assertEqual(parsed.path, ENDPOINT_PATH)
        self.assertEqual(
            parse_qs(parsed.query, keep_blank_values=True),
            {"fileType": ["folder"]},
        )
        self.assertNotEqual(parsed.query, "fileType=attachment")
        self.assertIsNone(request.data)
        self.assertIsNone(request.get_header("Content-length"))
        self.assertEqual(observed["http_code"], 200)
        self.assertEqual(observed["method"], "GET")
        self.assertEqual(observed["path"], ENDPOINT_PATH + "?fileType=folder")
        self.assertGreater(observed["exec_seq"], 0)
        self.assertEqual(observed["ncov_delta"], 1)
        update_state.assert_called_once_with(
            "GET",
            ENDPOINT_PATH + "?fileType=folder",
            "2xx",
            biz_code=mock.ANY,
        )

    def test_empty_and_nonempty_2xx_results_are_both_successful(self) -> None:
        for payload in ({"data": []}, {"data": [{"name": "offline-fixture"}]}):
            with self.subTest(payload=payload):
                return_code, _request, observed, _update_state = self.run_harness(payload)
                self.assertEqual(return_code, 0)
                self.assertEqual(observed["http_code"], 200)
                self.assertEqual(observed["class"], "2xx")


if __name__ == "__main__":
    unittest.main()
