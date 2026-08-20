"""Env-only, fail-closed Basic credential contract.

Scope note: this covers credential *containment* only.  Flowable stays
deprioritised; nothing here starts or resumes a Flowable fuzzing chain.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "nv_http_harness_under_test", REPO_ROOT / "nv_http_harness.py"
)
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)

USER_ENV = "FLOWABLE_USER"
PASS_ENV = "FLOWABLE_PASS"
BASIC_CFG = {
    "auth": {
        "type": "basic",
        "username_env": USER_ENV,
        "password_env": PASS_ENV,
    }
}


class BasicAuthEnvOnlyTest(unittest.TestCase):
    def apply(self, env: dict) -> dict:
        with mock.patch.dict(os.environ, env, clear=True):
            return harness.apply_auth_headers(BASIC_CFG, {})

    def test_credentials_are_assembled_in_process_from_environment(self) -> None:
        user, pw = "svc-user", "sv" + "cpass"
        headers = self.apply({USER_ENV: user, PASS_ENV: pw})
        expected = base64.b64encode(f"{user}:{pw}".encode("utf-8")).decode("ascii")
        self.assertEqual(headers["Authorization"], "Basic " + expected)

    def test_missing_password_env_aborts(self) -> None:
        with self.assertRaises(RuntimeError):
            self.apply({USER_ENV: "svc-user"})

    def test_missing_username_env_aborts(self) -> None:
        with self.assertRaises(RuntimeError):
            self.apply({PASS_ENV: "sv" + "cpass"})

    def test_empty_password_env_aborts(self) -> None:
        with self.assertRaises(RuntimeError):
            self.apply({USER_ENV: "svc-user", PASS_ENV: ""})

    def test_whitespace_only_password_env_aborts(self) -> None:
        with self.assertRaises(RuntimeError):
            self.apply({USER_ENV: "svc-user", PASS_ENV: "   \t "})

    def test_whitespace_only_username_env_aborts(self) -> None:
        with self.assertRaises(RuntimeError):
            self.apply({USER_ENV: "  ", PASS_ENV: "sv" + "cpass"})

    def test_no_fallback_credential_is_ever_used(self) -> None:
        """An abort, never a silent default or an unauthenticated pass-through."""
        with self.assertRaises(RuntimeError) as ctx:
            self.apply({})
        self.assertNotIn("Authorization", str(ctx.exception))

    def test_abort_message_never_carries_the_credential(self) -> None:
        pw = "sv" + "cpass"
        with mock.patch.dict(os.environ, {PASS_ENV: pw}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                harness.apply_auth_headers(BASIC_CFG, {})
        message = str(ctx.exception)
        self.assertNotIn(pw, message)
        self.assertIn(USER_ENV, message)

    def test_config_may_not_carry_inline_basic_credentials(self) -> None:
        cfg = {"auth": {"type": "basic", "username": "u", "password": "p"}}
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                harness.apply_auth_headers(cfg, {})

    def test_credential_like_unknown_keys_abort_case_insensitively(self) -> None:
        for key in (
            "username", "password", "USERNAME", "PASSWORD", "user", "pass",
            "passwd", "pwd", "credentials", "credential", "api_key", "apikey",
            "auth_token", "access_token", "token", "secret",
        ):
            with self.subTest(key=key):
                cfg = {
                    "auth": {
                        "type": "basic",
                        "username_env": USER_ENV,
                        "password_env": PASS_ENV,
                        key: "fixture-value",
                    }
                }
                with mock.patch.dict(
                    os.environ, {USER_ENV: "svc-user", PASS_ENV: "fixture-pass"}, clear=True
                ), self.assertRaises(RuntimeError):
                    harness.apply_auth_headers(cfg, {})

    def test_basic_unknown_structural_key_aborts(self) -> None:
        cfg = {
            "auth": {
                "type": "basic",
                "username_env": USER_ENV,
                "password_env": PASS_ENV,
                "unexpected": "fixture",
            }
        }
        with mock.patch.dict(
            os.environ, {USER_ENV: "svc-user", PASS_ENV: "fixture-pass"}, clear=True
        ), self.assertRaises(RuntimeError):
            harness.apply_auth_headers(cfg, {})


class FlowableConfigContainmentTest(unittest.TestCase):
    CONFIG = REPO_ROOT / "flowable_query.json"

    def test_config_declares_env_backed_basic_auth(self) -> None:
        auth = json.loads(self.CONFIG.read_text(encoding="utf-8"))["auth"]
        self.assertEqual(auth.get("type"), "basic")
        self.assertEqual(auth.get("username_env"), USER_ENV)
        self.assertEqual(auth.get("password_env"), PASS_ENV)

    def test_config_carries_no_credential_literal(self) -> None:
        auth = json.loads(self.CONFIG.read_text(encoding="utf-8"))["auth"]
        for banned in ("username", "password", "user", "pass", "secret", "token"):
            self.assertNotIn(banned, auth, f"inline credential key survived: {banned}")

    def test_secret_scanner_reports_config_clean(self) -> None:
        from scripts.secret_scan import scan_paths

        result = scan_paths([self.CONFIG], required=True)
        self.assertEqual(result["real_secret_findings"], 0, result["findings"])
        self.assertEqual(result["status"], "PASS")


class NonBasicAuthFailClosedTest(unittest.TestCase):
    def test_missing_raw_token_aborts(self) -> None:
        cfg = {"auth": {"type": "raw_token", "token_env": "NV_TOKEN"}}
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            harness.apply_auth_headers(cfg, {})

    def test_empty_raw_token_aborts(self) -> None:
        cfg = {"auth": {"type": "bearer", "token_env": "NV_TOKEN"}}
        with mock.patch.dict(os.environ, {"NV_TOKEN": "   "}, clear=True), self.assertRaises(RuntimeError):
            harness.apply_auth_headers(cfg, {})


class NoneAuthLegacyCompatibilityTest(unittest.TestCase):
    """``auth.type == "none"`` must stay backward compatible AND strict.

    Tracked configs predate the env-only hardening and still carry the inert
    bearer-shaped keys (header/prefix/token_env) beside ``"type": "none"``.
    They describe nothing that is ever read while auth is off, so they must not
    abort the harness -- while a genuinely unknown or credential-like key still
    must.
    """

    LEGACY_NONE_AUTH = {
        "type": "none",
        "header": "Authorization",
        "prefix": "Bearer ",
        "token_env": "NV_TOKEN",
    }

    def test_legacy_inert_keys_are_accepted_and_headers_are_unchanged(self) -> None:
        headers = {"Content-Type": "application/json"}
        with mock.patch.dict(os.environ, {"NV_TOKEN": "fixture-token"}, clear=True):
            result = harness.apply_auth_headers({"auth": dict(self.LEGACY_NONE_AUTH)}, headers)
        self.assertEqual(result, {"Content-Type": "application/json"})
        self.assertNotIn("Authorization", result)

    def test_none_auth_never_reads_the_declared_token_env(self) -> None:
        with mock.patch.dict(os.environ, {"NV_TOKEN": "fixture-token"}, clear=True):
            with mock.patch.object(
                harness, "_require_runtime_credential",
                side_effect=AssertionError("credential env read while auth is off"),
            ):
                result = harness.apply_auth_headers({"auth": dict(self.LEGACY_NONE_AUTH)}, {})
        self.assertEqual(result, {})

    def test_none_auth_does_not_require_the_token_env_to_exist(self) -> None:
        headers = {"Accept": "application/json"}
        with mock.patch.dict(os.environ, {}, clear=True):
            result = harness.apply_auth_headers({"auth": dict(self.LEGACY_NONE_AUTH)}, headers)
        self.assertEqual(result, {"Accept": "application/json"})

    def test_none_auth_still_rejects_credential_like_and_unknown_keys(self) -> None:
        for key in (
            "password", "username", "user", "pass", "passwd", "pwd",
            "credential", "credentials", "api_key", "apikey", "secret",
            "auth_token", "access_token", "unexpected",
        ):
            with self.subTest(key=key):
                auth = dict(self.LEGACY_NONE_AUTH)
                auth[key] = "synthetic-fixture"
                with mock.patch.dict(os.environ, {}, clear=True):
                    with self.assertRaises(RuntimeError):
                        harness.apply_auth_headers({"auth": auth}, {})

    def test_none_auth_rejection_message_never_carries_the_value(self) -> None:
        fixture = "synthetic-fixture-value"
        auth = dict(self.LEGACY_NONE_AUTH)
        auth["password"] = fixture
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                harness.apply_auth_headers({"auth": auth}, {})
        self.assertNotIn(fixture, str(ctx.exception))


class TrackedNvTargetConfigCompatibilityTest(unittest.TestCase):
    """The regression the abstract auth contract missed: the real tracked file.

    Testing only synthetic dicts is what let a tracked config that aborts the
    production harness ship green last round.
    """

    CONFIG = REPO_ROOT / "nv_target.json"

    def load(self) -> dict:
        return json.loads(self.CONFIG.read_text(encoding="utf-8"))

    def test_tracked_config_declares_no_auth(self) -> None:
        self.assertEqual(self.load()["auth"].get("type"), "none")

    def test_tracked_config_passes_through_production_apply_auth_headers(self) -> None:
        cfg = self.load()
        headers = {"Content-Type": "application/json"}
        with mock.patch.dict(os.environ, {}, clear=True):
            result = harness.apply_auth_headers(cfg, headers)
        self.assertEqual(result, {"Content-Type": "application/json"})

    def test_tracked_config_needs_no_runtime_credential_env(self) -> None:
        cfg = self.load()
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(
                harness, "_require_runtime_credential",
                side_effect=AssertionError("credential env read while auth is off"),
            ):
                result = harness.apply_auth_headers(cfg, {})
        self.assertEqual(result, {})

    def test_tracked_config_carries_no_credential_literal(self) -> None:
        auth = self.load()["auth"]
        for banned in ("username", "password", "user", "pass", "secret", "token"):
            self.assertNotIn(banned, auth, f"inline credential key survived: {banned}")


if __name__ == "__main__":
    unittest.main()
