"""Offline contract tests for independent O2OA readiness URL resolution."""

from __future__ import annotations

import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import URLError

import nv_http_harness as harness


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def getcode(self) -> int:
        return 200

    def read(self, limit: int) -> bytes:
        del limit
        return b"{}"


class O2OAHealthContractTest(unittest.TestCase):
    def test_o2oa_target_declares_independent_health_url(self) -> None:
        config = json.loads(
            (Path(__file__).parents[1] / "targets" / "o2oa_query.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(config["base"], "http://127.0.0.1:20020")
        self.assertEqual(config["health_url"], "http://127.0.0.1:80/")
        self.assertNotIn("health", config)

    def test_o2oa_health_url_takes_precedence_over_legacy_health(self) -> None:
        cfg = {
            "base": "http://127.0.0.1:20020",
            "health": "/x_desktop/index.html",
            "health_url": "http://127.0.0.1:80/",
        }

        resolved_health_url = harness.resolve_health_url(cfg)

        self.assertEqual(resolved_health_url, "http://127.0.0.1:80/")
        self.assertNotEqual(
            resolved_health_url,
            "http://127.0.0.1:20020/x_desktop/index.html",
        )

    def test_legacy_base_plus_health_fallback(self) -> None:
        cfg = {"base": "http://127.0.0.1:8080", "health": "/health"}

        self.assertEqual(
            harness.resolve_health_url(cfg),
            "http://127.0.0.1:8080/health",
        )

    def test_health_url_does_not_change_business_base_or_endpoint(self) -> None:
        cfg = {
            "base": "http://127.0.0.1:20020",
            "health": "/x_desktop/index.html",
            "health_url": "http://127.0.0.1:80/",
        }
        endpoint_path = "/x_cms_assemble_control/jaxrs/document/filter/list/1/size/5"

        self.assertEqual(cfg["base"], "http://127.0.0.1:20020")
        self.assertEqual(
            cfg["base"].rstrip("/") + endpoint_path,
            "http://127.0.0.1:20020" + endpoint_path,
        )
        self.assertEqual(harness.resolve_health_url(cfg), "http://127.0.0.1:80/")

    def test_recovery_uses_resolved_health_url(self) -> None:
        with tempfile.TemporaryDirectory(prefix="o2oa_health_contract_") as directory:
            tmp = Path(directory)
            config = tmp / "target.json"
            status = tmp / "status.json"
            config.write_text(
                json.dumps(
                    {
                        "base": "http://127.0.0.1:20020",
                        "health": "/x_desktop/index.html",
                        "health_url": "http://127.0.0.1:80/",
                        "auth": {"type": "none"},
                        "endpoints": [{"method": "GET", "path": "/probe"}],
                    }
                ),
                encoding="utf-8",
            )
            stdin = types.SimpleNamespace(buffer=io.BytesIO(b"GET /probe\n\n"))
            with (
                mock.patch.dict(
                    harness.os.environ,
                    {
                        "NV_TARGET_CONFIG": str(config),
                        "NV_STATUS_LEDGER_PATH": str(tmp / "ledger.jsonl"),
                    },
                    clear=True,
                ),
                mock.patch.object(harness, "STATUS_PATH", str(status)),
                mock.patch.object(harness.sys, "stdin", stdin),
                mock.patch.object(
                    harness.urllib.request,
                    "urlopen",
                    side_effect=URLError("offline synthetic failure"),
                ),
                mock.patch.object(harness, "update_state", return_value={}),
                mock.patch.object(harness, "save_err_case"),
                mock.patch.object(harness, "health_check", return_value=True) as health_check,
            ):
                harness.main()

        health_check.assert_called_once_with("http://127.0.0.1:80/", timeout_sec=1.0)


if __name__ == "__main__":
    unittest.main()
