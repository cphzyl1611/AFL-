"""Offline tests for body-only harness input representation bridging."""

from __future__ import annotations

import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import nv_http_harness as harness
from nv_body_valid import body_validate as real_body_validate


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def getcode(self) -> int:
        return 200

    def read(self, limit: int) -> bytes:
        del limit
        return b'{"status":"ok"}'


class BodyOnlyRepresentationBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nv_http_bridge_")
        self.tmp = Path(self._tmp.name)
        self.status = self.tmp / "status.json"
        self.stats = self.tmp / "body-valid-stats.json"
        self.config = self.tmp / "target.json"
        self.rules = self.tmp / "rules.json"
        self.config.write_text(
            json.dumps(
                {
                    "base": "http://offline.invalid",
                    "health": "/health",
                    "auth": {"type": "none"},
                    "body_only_mode": 1,
                    "default_endpoint": "metadata_update",
                    "endpoints": [
                        {
                            "name": "metadata_update",
                            "method": "PUT",
                            "path": "/alfresco/node/test-only",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.rules.write_text("{}", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_harness(self, testcase: bytes):
        validation_inputs: list[bytes] = []

        def recording_body_validate(**kwargs):
            validation_inputs.append(kwargs["raw_body"])
            return real_body_validate(**kwargs)

        stdin = types.SimpleNamespace(buffer=io.BytesIO(testcase))
        env = {
            "NV_TARGET_CONFIG": str(self.config),
            "NV_BODY_RULES": str(self.rules),
            "NV_BODY_VALID_STATS": str(self.stats),
        }
        with (
            mock.patch.dict(harness.os.environ, env, clear=True),
            mock.patch.object(harness, "STATUS_PATH", str(self.status)),
            mock.patch.object(harness.sys, "stdin", stdin),
            mock.patch.object(harness, "body_validate", recording_body_validate),
            mock.patch.object(
                harness,
                "update_state",
                return_value={"ncov_delta": 0, "ncov_total": 0, "nall": 1},
            ),
            mock.patch.object(
                harness.urllib.request,
                "urlopen",
                return_value=_Response(),
            ) as urlopen,
        ):
            return_code = harness.main()

        return return_code, validation_inputs, urlopen

    def test_full_http_is_accepted_and_its_body_reaches_validation_byte_exact(self) -> None:
        body = b'{\n  "properties": {"cm:title": "CB-1"}\n}\n'
        testcase = (
            b"PUT /alfresco/node/test-only HTTP/1.1\r\n"
            b"Content-Type: application/json\r\n"
            b"X-Representation: full-http\r\n"
            b"\r\n"
            + body
        )

        return_code, validation_inputs, urlopen = self.run_harness(testcase)

        self.assertEqual(return_code, 0)
        self.assertEqual(validation_inputs, [body])
        urlopen.assert_called_once()
        status = json.loads(self.status.read_text(encoding="utf-8"))
        self.assertGreater(status["exec_seq"], 0)

    def test_mutator_lf_full_http_reaches_validation_byte_exact(self) -> None:
        body = b'{"properties":{"cm:title":"LF-PRODUCER"}}'
        testcase = (
            b"PUT /alfresco/node/test-only\n"
            b"Content-Type: application/json\n"
            b"\n"
            + body
        )

        return_code, validation_inputs, urlopen = self.run_harness(testcase)

        self.assertEqual(return_code, 0)
        self.assertEqual(validation_inputs, [body])
        urlopen.assert_called_once()
        self.assertTrue(self.status.exists())
        status = json.loads(self.status.read_text(encoding="utf-8"))
        self.assertGreater(status["exec_seq"], 0)

    def test_plain_body_only_json_keeps_existing_validation_path(self) -> None:
        body = b'{\n  "properties": {"cm:title": "Level-C"}\n}\n'

        return_code, validation_inputs, urlopen = self.run_harness(body)

        self.assertEqual(return_code, 0)
        self.assertEqual(validation_inputs, [body])
        urlopen.assert_called_once()
        status = json.loads(self.status.read_text(encoding="utf-8"))
        self.assertGreater(status["exec_seq"], 0)

    def test_status_is_written_when_state_accounting_raises_after_http_response(self) -> None:
        testcase = (
            b"PUT /alfresco/node/test-only HTTP/1.1\r\n"
            b"Content-Type: application/json\r\n\r\n"
            b'{"properties":{"cm:title":"state-error"}}'
        )
        validation_inputs: list[bytes] = []

        def recording_body_validate(**kwargs):
            validation_inputs.append(kwargs["raw_body"])
            return real_body_validate(**kwargs)

        stdin = types.SimpleNamespace(buffer=io.BytesIO(testcase))
        env = {
            "NV_TARGET_CONFIG": str(self.config),
            "NV_BODY_RULES": str(self.rules),
            "NV_BODY_VALID_STATS": str(self.stats),
        }
        with (
            mock.patch.dict(harness.os.environ, env, clear=True),
            mock.patch.object(harness, "STATUS_PATH", str(self.status)),
            mock.patch.object(harness.sys, "stdin", stdin),
            mock.patch.object(harness, "body_validate", recording_body_validate),
            mock.patch.object(
                harness,
                "update_state",
                side_effect=RuntimeError("state accounting failed"),
            ),
            mock.patch.object(harness.urllib.request, "urlopen", return_value=_Response()),
        ):
            return_code = harness.main()

        self.assertEqual(return_code, 0)
        self.assertEqual(len(validation_inputs), 1)
        self.assertTrue(self.status.is_file())
        status = json.loads(self.status.read_text(encoding="utf-8"))
        self.assertGreater(status["exec_seq"], 0)
        self.assertEqual(status["http_code"], 200)

    def test_body_validation_reject_writes_non_target_terminal_status(self) -> None:
        body = b'{"properties":{"cm:title":"reject-me"}}'
        validation = {
            "ok": False,
            "reason": "score_reject",
            "score": 2.0,
            "score_rpc_ok": True,
            "norm_body": body,
        }
        stdin = types.SimpleNamespace(buffer=io.BytesIO(body))
        env = {
            "NV_TARGET_CONFIG": str(self.config),
            "NV_BODY_RULES": str(self.rules),
            "NV_BODY_VALID_STATS": str(self.stats),
            "NV_BODY_SCORE_ENDPOINT": "unix:///offline/not-used.sock",
            "NV_BODY_SCORE_THRESHOLD": "1.0",
        }
        with (
            mock.patch.dict(harness.os.environ, env, clear=True),
            mock.patch.object(harness, "STATUS_PATH", str(self.status)),
            mock.patch.object(harness.sys, "stdin", stdin),
            mock.patch.object(harness, "body_validate", return_value=validation),
            mock.patch.object(harness.urllib.request, "urlopen") as urlopen,
        ):
            return_code = harness.main()

        self.assertEqual(return_code, 0)
        urlopen.assert_not_called()
        status = json.loads(self.status.read_text(encoding="utf-8"))
        self.assertEqual(status["validation_reject"], 1)
        self.assertGreater(status["exec_seq"], 0)
        self.assertEqual(status["http_code"], 0)

    def test_malformed_http_envelope_fails_closed_before_body_validation(self) -> None:
        malformed = (
            b"PUT /alfresco/node/test-only HTTP/1.1\r\n"
            b"Content-Type: application/json\r\n"
            b'{"properties":{"cm:title":"missing blank line"}}'
        )

        return_code, validation_inputs, urlopen = self.run_harness(malformed)

        self.assertEqual(return_code, 0)
        self.assertEqual(validation_inputs, [])
        urlopen.assert_not_called()
        self.assertFalse(self.status.exists())
        self.assertFalse(Path(str(self.status) + ".seq").exists())

    def test_malformed_body_only_input_writes_non_target_validation_reject(self) -> None:
        return_code, validation_inputs, urlopen = self.run_harness(b"not-json")

        self.assertEqual(return_code, 0)
        self.assertEqual(validation_inputs, [b"not-json"])
        urlopen.assert_not_called()
        status = json.loads(self.status.read_text(encoding="utf-8"))
        self.assertEqual(status["validation_reject"], 1)
        self.assertGreater(status["exec_seq"], 0)
        self.assertEqual(status["http_code"], 0)


if __name__ == "__main__":
    unittest.main()
