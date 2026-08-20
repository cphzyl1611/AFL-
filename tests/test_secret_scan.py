from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.secret_scan import (
    SecretSerializationError,
    assert_no_secrets,
    canonical_serialize,
    guarded_report_bytes,
    main,
    runtime_secret_values,
    safe_write_report,
    scan_file,
    scan_paths,
)


class SecretScanTest(unittest.TestCase):
    def write(self, root: Path, name: str, data: str | bytes) -> Path:
        path = root / name
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def test_ascii_secret_redaction(self) -> None:
        fixture_value = "Ascii" + "Secret_123!"
        assignment = "ALFRESCO_" + "PASS"
        with tempfile.TemporaryDirectory() as td:
            path = self.write(Path(td), "x.py", f'{assignment} = "{fixture_value}"\n')
            findings, skipped = scan_file(path)
            self.assertIsNone(skipped)
            self.assertTrue(any(f.classification == "REAL_SECRET" for f in findings))
            report = {"findings": [f.__dict__ for f in findings]}
            encoded = canonical_serialize(report)
            self.assertNotIn(fixture_value.encode("utf-8"), encoded)

    def test_unicode_secret_redaction_uses_same_serialization(self) -> None:
        fixture_value = "密钥值-Δ-秘密"
        assignment = "ALFRESCO_" + "PASS"
        with tempfile.TemporaryDirectory() as td:
            path = self.write(Path(td), "x.py", f'{assignment} = "{fixture_value}"\n')
            findings, skipped = scan_file(path)
            self.assertIsNone(skipped)
            self.assertTrue(findings)
            report = {"findings": [f.__dict__ for f in findings], "note": "已脱敏"}
            out = Path(td) / "report.json"
            safe_write_report(out, report, [fixture_value])
            self.assertNotIn(fixture_value.encode("utf-8"), out.read_bytes())
            self.assertIn("已脱敏", out.read_text(encoding="utf-8"))

    def test_basic_authorization(self) -> None:
        blob = base64.b64encode(b"svc:" + b"S" * 20).decode("ascii")
        with tempfile.TemporaryDirectory() as td:
            findings, _ = scan_file(self.write(Path(td), "x.txt", f"Authorization: Basic {blob}\n"))
            self.assertTrue(any(f.category == "AUTHORIZATION_BASIC" for f in findings))

    def test_bearer_authorization(self) -> None:
        token = "A" * 24
        with tempfile.TemporaryDirectory() as td:
            findings, _ = scan_file(self.write(Path(td), "x.txt", f"Authorization: Bearer {token}\n"))
            self.assertTrue(any(f.category == "AUTHORIZATION_BEARER" for f in findings))

    def test_logger_false_positive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            findings, _ = scan_file(self.write(Path(td), "x.log", "logger=alfresco.repo.admin\n"))
            self.assertFalse(findings)

    def test_account_password_context_is_not_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            password_value = "Abc" + "123!xyz"
            text = 'account="service" password="' + password_value + '"\n'
            findings, _ = scan_file(self.write(Path(td), "x.conf", text))
            self.assertTrue(any(f.category == "ACCOUNT_PASSWORD_CONTEXT" for f in findings))

    def test_fail_closed_serialization_guard(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "report.json"
            with self.assertRaises(SecretSerializationError):
                safe_write_report(out, {"detail": "secret-value"}, ["secret-value"])
            self.assertFalse(out.exists())

    def test_nul_binary_is_accounted_for(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = self.write(Path(td), "binary.bin", b"prefix\x00BinarySecret_123!")
            result = scan_paths([path], required=True)
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(result["files_scanned"], 0)
            self.assertEqual(result["files_skipped"][0]["path"], str(path))
            self.assertIn("binary_or_nul", result["files_skipped"][0]["reason"])

    def test_oversized_file_is_accounted_for(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = self.write(Path(td), "large.txt", b"x" * 32)
            result = scan_paths([path], required=True, max_bytes=16)
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertIn("oversized", result["files_skipped"][0]["reason"])

    def test_clean_scan(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = scan_paths([self.write(Path(td), "clean.txt", "hello\n")])
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["real_secret_findings"], 0)
            self.assertEqual(result["files_skipped"], [])


class SimpleCredentialDetectionTest(unittest.TestCase):
    """W3: credential-context fields are sensitive regardless of complexity."""

    def write(self, root: Path, name: str, data: str | bytes) -> Path:
        path = root / name
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def assert_real_secret(self, text: str, suffix: str = ".conf") -> None:
        with tempfile.TemporaryDirectory() as td:
            path = self.write(Path(td), "candidate" + suffix, text)
            findings, skipped = scan_file(path)
            self.assertIsNone(skipped)
            self.assertTrue(
                any(f.classification == "REAL_SECRET" for f in findings),
                f"expected a REAL_SECRET finding for: {text!r}",
            )

    def test_a_simple_password_test_is_detected(self) -> None:
        self.assert_real_secret('password="' + "te" + 'st"\n')

    def test_b_simple_password_admin_is_detected(self) -> None:
        self.assert_real_secret('password="' + "adm" + 'in"\n')

    def test_b2_simple_password_hunter2_is_detected(self) -> None:
        self.assert_real_secret('password="' + "hunter" + '2"\n')

    def test_c_multiline_json_auth_block_is_detected(self) -> None:
        text = (
            "{\n"
            '  "auth": {\n'
            '    "type": "basic",\n'
            '    "username": "user",\n'
            '    "password": "' + "simple" + 'pass"\n'
            "  }\n"
            "}\n"
        )
        self.assert_real_secret(text, suffix=".json")

    def test_c2_flowable_shaped_config_does_not_pass(self) -> None:
        text = (
            "{\n"
            '  "base": "http://127.0.0.1:8080",\n'
            '  "auth": {\n'
            '    "type": "basic",\n'
            '    "username": "rest-' + "adm" + 'in",\n'
            '    "password": "' + "te" + 'st"\n'
            "  }\n"
            "}\n"
        )
        with tempfile.TemporaryDirectory() as td:
            path = self.write(Path(td), "flowable_shaped.json", text)
            result = scan_paths([path], required=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertGreater(result["real_secret_findings"], 0)

    def test_other_credential_field_names_are_detected(self) -> None:
        for field in ("passwd", "pwd", "secret", "token", "authorization"):
            with self.subTest(field=field):
                self.assert_real_secret(field + '="' + "ab" + 'c"\n')

    def test_empty_and_placeholder_credential_values_are_not_findings(self) -> None:
        for text in (
            'password=""\n',
            'password="${FLOWABLE_PASS}"\n',
            'password="$FLOWABLE_PASS"\n',
            'password="%FLOWABLE_PASS%"\n',
            'password="<REDACTED>"\n',
            'password="REDACTED"\n',
            'password=None\n',
            'password=null\n',
            'password="CHANGE_ME"\n',
            "password=os.getenv(\"FLOWABLE_PASS\")\n",
        ):
            with self.subTest(text=text):
                with tempfile.TemporaryDirectory() as td:
                    path = self.write(Path(td), "x.conf", text)
                    findings, _ = scan_file(path)
                    self.assertFalse(
                        [f for f in findings if f.classification == "REAL_SECRET"],
                        f"unexpected REAL_SECRET for: {text!r}",
                    )

    def test_known_variable_assignment_placeholders_are_not_findings(self) -> None:
        for text in (
            'ALFRESCO_PASS="%ALFRESCO_PASS%"\n',
            "FLOWABLE_" + "PASS=None\n",
            "TOKEN == NULL\n",
        ):
            with self.subTest(text=text):
                with tempfile.TemporaryDirectory() as td:
                    findings, _ = scan_file(self.write(Path(td), "x.py", text))
                    self.assertFalse(
                        [f for f in findings if f.classification == "REAL_SECRET"],
                        f"unexpected REAL_SECRET for: {text!r}",
                    )

    def test_logger_suppression_stays_narrow(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = self.write(Path(td), "log4j.properties", "logger=alfresco.repo.admin\n")
            findings, _ = scan_file(path)
            self.assertFalse([f for f in findings if f.classification == "REAL_SECRET"])
        # "admin" is not globally suppressed: it is a real secret in a credential context.
        self.assert_real_secret('password="' + "adm" + 'in"\n')

    def test_d_unicode_credential_detected_and_never_serialized(self) -> None:
        secret = "\u5bc6\u7801-\u03b4"  # low-complexity, non-ASCII
        with tempfile.TemporaryDirectory() as td:
            path = self.write(Path(td), "x.conf", 'password="' + secret + '"\n')
            findings, skipped = scan_file(path)
            self.assertIsNone(skipped)
            self.assertTrue(any(f.classification == "REAL_SECRET" for f in findings))
            out = Path(td) / "report.json"
            report = {"findings": [f.__dict__ for f in findings]}
            safe_write_report(out, report, [secret])
            self.assertNotIn(secret.encode("utf-8"), out.read_bytes())


class SkipAccountingPrecedenceTest(unittest.TestCase):
    def write(self, root: Path, name: str, data: str | bytes) -> Path:
        path = root / name
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def test_e_real_finding_plus_skipped_file_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write(root, "creds.conf", 'password="' + "te" + 'st"\n')
            self.write(root, "blob.bin", b"prefix\x00tail")
            result = scan_paths([root], required=True)
            self.assertGreater(result["real_secret_findings"], 0)
            self.assertTrue(result["files_skipped"])
            self.assertEqual(result["status"], "FAIL")

    def test_f_no_findings_plus_required_skip_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write(root, "clean.txt", "nothing to see\n")
            self.write(root, "blob.bin", b"prefix\x00tail")
            result = scan_paths([root], required=True)
            self.assertEqual(result["real_secret_findings"], 0)
            self.assertTrue(result["files_skipped"])
            self.assertEqual(result["status"], "INCOMPLETE")

    def test_findings_only_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write(root, "creds.conf", 'password="' + "te" + 'st"\n')
            result = scan_paths([root], required=True)
            self.assertEqual(result["status"], "FAIL")


class ReportFailClosedIntegrationTest(unittest.TestCase):
    """G: the production CLI must feed loaded secret values into the guard."""

    def test_runtime_secret_values_collects_credential_env(self) -> None:
        secret = "Rt" + "SecretVal99"
        with mock.patch.dict(
            os.environ,
            {"ALFRESCO_PASS": secret, "PATH": os.environ.get("PATH", "")},
            clear=True,
        ):
            values = runtime_secret_values()
        self.assertIn(secret, values)

    def test_runtime_secret_values_uses_project_allowlist(self) -> None:
        allowed = "Allowed" + "Secret42"
        unrelated = "Unrelated" + "Token99"
        with mock.patch.dict(
            os.environ,
            {"ALFRESCO_PASS": allowed, "RANDOM_TOKEN": unrelated},
            clear=True,
        ):
            values = runtime_secret_values()
        self.assertIn(allowed, values)
        self.assertNotIn(unrelated, values)

    def test_runtime_secret_values_deduplicates_and_ignores_blank(self) -> None:
        duplicate = "Duplicate" + "Secret42"
        with mock.patch.dict(
            os.environ,
            {
                "ALFRESCO_PASS": duplicate,
                "FLOWABLE_PASS": duplicate,
                "FLOWABLE_USER": "   ",
                "NV_TOKEN": "",
            },
            clear=True,
        ):
            values = runtime_secret_values()
        self.assertEqual(values, [duplicate])

    def test_runtime_secret_values_ignores_blank_and_placeholder(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"ALFRESCO_PASS": "   ", "FLOWABLE_PASS": "", "NV_TOKEN": "${NV_TOKEN}"},
            clear=True,
        ):
            values = runtime_secret_values()
        self.assertEqual(values, [])

    def test_g_main_refuses_report_containing_loaded_secret(self) -> None:
        secret = "Rt" + "SecretVal99"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # The secret reaches the report only through the recorded finding path.
            (root / ("note_" + secret + ".conf")).write_text(
                'password="' + "oth" + 'er"\n', encoding="utf-8"
            )
            out = root / "reports" / "report.json"
            with mock.patch.dict(os.environ, {"ALFRESCO_PASS": secret}, clear=False):
                with self.assertRaises(SecretSerializationError):
                    main(["--root", str(root), "--report", str(out)])
            self.assertFalse(out.exists())

    def test_g_main_writes_report_free_of_loaded_secrets(self) -> None:
        secret = "Rt" + "SecretVal99"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "clean.txt").write_text("nothing\n", encoding="utf-8")
            out = root / "reports" / "report.json"
            with mock.patch.dict(os.environ, {"ALFRESCO_PASS": secret}, clear=False):
                with contextlib.redirect_stdout(io.StringIO()):
                    rc = main(["--root", str(root), "--report", str(out)])
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            self.assertNotIn(secret.encode("utf-8"), out.read_bytes())

    def test_main_stdout_and_file_use_identical_guarded_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "clean.txt").write_text("nothing\n", encoding="utf-8")
            out = root / "reports" / "report.json"
            stdout = io.BytesIO()

            class BinaryStdout:
                def __init__(self, stream: io.BytesIO) -> None:
                    self.buffer = stream

            with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
                "sys.stdout", BinaryStdout(stdout)
            ):
                rc = main(["--root", str(root), "--report", str(out)])
            self.assertEqual(rc, 0)
            self.assertEqual(stdout.getvalue(), out.read_bytes())

    def test_main_unicode_secret_fails_before_either_sink(self) -> None:
        runtime_value = "密钥-δ"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "clean.txt").write_text("nothing\n", encoding="utf-8")
            out = root / "reports" / "report.json"
            stdout = io.BytesIO()

            class BinaryStdout:
                def __init__(self, stream: io.BytesIO) -> None:
                    self.buffer = stream

            with mock.patch.dict(os.environ, {"ALFRESCO_PASS": runtime_value}, clear=True), mock.patch(
                "sys.stdout", BinaryStdout(stdout)
            ):
                rc = main(["--root", str(root), "--report", str(out)])
            self.assertEqual(rc, 0)
            self.assertEqual(stdout.getvalue(), out.read_bytes())
            self.assertNotIn(runtime_value.encode("utf-8"), stdout.getvalue())

    def test_loaded_secret_fails_before_stdout_or_file(self) -> None:
        runtime_value = "Runtime" + "SecretValue42"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ("note_" + runtime_value + ".conf")).write_text(
                'pass' + 'word="other' + 'pass"\n', encoding="utf-8"
            )
            out = root / "reports" / "report.json"
            stdout = io.BytesIO()

            class BinaryStdout:
                def __init__(self, stream: io.BytesIO) -> None:
                    self.buffer = stream

            with mock.patch.dict(os.environ, {"ALFRESCO_PASS": runtime_value}, clear=True), mock.patch(
                "sys.stdout", BinaryStdout(stdout)
            ):
                with self.assertRaises(SecretSerializationError) as ctx:
                    main(["--root", str(root), "--report", str(out)])
            self.assertNotIn(runtime_value, str(ctx.exception))
            self.assertEqual(stdout.getvalue(), b"")
            self.assertFalse(out.exists())


# Synthetic fixtures only -- never a runtime secret.  Every entry but "plain"
# carries a character the canonical JSON serializer escapes, so the value's raw
# UTF-8 bytes do not survive verbatim into the emitted report even though a
# consumer calling json.loads() on those exact bytes recovers it in full.
ESCAPING_FIXTURES = {
    "plain": "fixture" + "PlainValue7",
    "quote": 'fixture"' + "quote7",
    "backslash": "fixture\\" + "slash7",
    "tab": "fixture\t" + "tab7",
    "newline": "fixture\n" + "newline7",
    "unicode_quote": '\u6d4b\u8bd5"' + "fixture7",
}


class SerializationGuardJsonEscapeTest(unittest.TestCase):
    """The guard must judge values recoverable from the exact emitted bytes.

    Raw-UTF-8 containment silently misses every value the serializer escapes.
    Decoding the same bytes the sinks receive is the only containment question
    that matches what a JSON consumer can actually read back.
    """

    @staticmethod
    def decoded_strings(value) -> list:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            out = []
            for key, item in value.items():
                if isinstance(key, str):
                    out.append(key)
                out.extend(SerializationGuardJsonEscapeTest.decoded_strings(item))
            return out
        if isinstance(value, list):
            out = []
            for item in value:
                out.extend(SerializationGuardJsonEscapeTest.decoded_strings(item))
            return out
        return []

    def assert_recoverable(self, serialized: bytes, protected: str) -> None:
        """A consumer of these exact bytes really does get the value back."""
        decoded = json.loads(serialized.decode("utf-8"))
        self.assertTrue(
            any(protected in text for text in self.decoded_strings(decoded)),
            "fixture is not recoverable from the emitted JSON; the test is wrong",
        )

    def assert_guard_blocks(self, report: dict, protected: str) -> None:
        self.assert_recoverable(canonical_serialize(report), protected)
        with self.assertRaises(SecretSerializationError) as ctx:
            guarded_report_bytes(report, [protected])
        self.assertNotIn(protected, str(ctx.exception))

    def test_escaped_value_in_a_report_value_is_blocked(self) -> None:
        for name, value in ESCAPING_FIXTURES.items():
            with self.subTest(fixture=name):
                self.assert_guard_blocks({"detail": value}, value)

    def test_escaped_value_nested_in_lists_and_mappings_is_blocked(self) -> None:
        for name, value in ESCAPING_FIXTURES.items():
            with self.subTest(fixture=name):
                report = {"findings": [{"path": value, "line": 1}], "files_scanned": 1}
                self.assert_guard_blocks(report, value)

    def test_escaped_value_used_as_a_json_key_is_blocked(self) -> None:
        for name, value in ESCAPING_FIXTURES.items():
            with self.subTest(fixture=name):
                self.assert_guard_blocks({"by_path": {value: 1}}, value)

    def test_escaped_value_on_the_finding_path_is_blocked(self) -> None:
        for name, value in ESCAPING_FIXTURES.items():
            with self.subTest(fixture=name):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    (root / ("note_" + value + ".conf")).write_text(
                        "pass" + 'word="othe' + 'rpass"\n', encoding="utf-8"
                    )
                    report = scan_paths([root], required=True)
                    self.assertTrue(report["findings"], report)
                    self.assert_guard_blocks(report, value)

    def test_escaped_value_on_the_skipped_file_path_is_blocked(self) -> None:
        for name, value in ESCAPING_FIXTURES.items():
            with self.subTest(fixture=name):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    (root / ("blob_" + value + ".bin")).write_bytes(b"\x00\x01\x02")
                    report = scan_paths([root], required=True)
                    self.assertTrue(report["files_skipped"], report)
                    self.assert_guard_blocks(report, value)

    def test_safe_write_report_creates_no_file_when_the_guard_trips(self) -> None:
        for name, value in ESCAPING_FIXTURES.items():
            with self.subTest(fixture=name):
                with tempfile.TemporaryDirectory() as td:
                    out = Path(td) / "reports" / "report.json"
                    with self.assertRaises(SecretSerializationError):
                        safe_write_report(out, {"detail": value}, [value])
                    self.assertFalse(out.exists())

    def test_guard_fails_closed_when_output_is_not_decodable_json(self) -> None:
        with self.assertRaises(SecretSerializationError):
            assert_no_secrets(b"\xff\xfe not json at all", ["fixture" + "Absent7"])

    def test_guard_allows_a_report_that_does_not_carry_the_value(self) -> None:
        report = {"note": 'escapes " and \\ and \t stay legible', "findings": [{"a": "b"}]}
        data = guarded_report_bytes(report, ["fixture" + "Absent7"])
        self.assertEqual(json.loads(data.decode("utf-8")), report)

    def test_blank_and_whitespace_only_protected_values_do_not_block(self) -> None:
        report = {"findings": [{"a": "b"}], "files_skipped": []}
        data = guarded_report_bytes(report, ["", "   ", "\t", "\n"])
        self.assertEqual(json.loads(data.decode("utf-8")), report)

    def test_cli_sink_emits_nothing_when_an_escaped_value_would_survive(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        for name, value in ESCAPING_FIXTURES.items():
            with self.subTest(fixture=name):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td) / "scan_root"
                    root.mkdir()
                    (root / ("blob_" + value + ".bin")).write_bytes(b"\x00\x01")
                    report_path = Path(td) / "reports" / "report.json"
                    env = dict(os.environ)
                    for stale in (
                        "ALFRESCO_USER", "ALFRESCO_PASS",
                        "FLOWABLE_USER", "FLOWABLE_PASS",
                    ):
                        env.pop(stale, None)
                    env["NV_TOKEN"] = value
                    proc = subprocess.run(
                        [
                            sys.executable, "scripts/secret_scan.py",
                            "--root", str(root),
                            "--report", str(report_path),
                        ],
                        cwd=str(repo_root), env=env, capture_output=True,
                    )
                    self.assertNotEqual(proc.returncode, 0)
                    self.assertEqual(proc.stdout, b"")
                    self.assertFalse(report_path.exists())
                    self.assertIn(b"SecretSerializationError", proc.stderr)
                    self.assertNotIn(value.encode("utf-8"), proc.stderr)


# Synthetic fixtures only -- never a real runtime value.  Assembled by
# concatenation so no credential-shaped literal is committed to the tree.
WS_CORE = "AUDIT" + "VALUE"
WS_LEADING = "  " + WS_CORE
WS_TRAILING = WS_CORE + "  "
WS_BOTH = "  " + WS_CORE + "  "
WS_BLANKS = ("", " ", "\t", "\n", "   \t   ")


class RuntimeSecretWhitespacePreservationTest(unittest.TestCase):
    """Runtime values must reach the guard byte-exact.

    ``strip()`` may decide only whether a value is whitespace-only.  Using the
    stripped result as the monitored value is wrong in both directions: it
    misses the padded value that a report can actually carry, and it invents a
    match for a value the report never carried.
    """

    @staticmethod
    def collect(env: dict) -> list[str]:
        # A mapping, not keyword arguments: ``NAME=value`` in source is the
        # very shape the scanner reports as a committed credential.
        with mock.patch.dict(os.environ, env, clear=True):
            return runtime_secret_values()

    def test_leading_whitespace_is_preserved(self) -> None:
        self.assertEqual(self.collect({"NV_TOKEN": WS_LEADING}), [WS_LEADING])

    def test_trailing_whitespace_is_preserved(self) -> None:
        self.assertEqual(self.collect({"NV_TOKEN": WS_TRAILING}), [WS_TRAILING])

    def test_whitespace_on_both_sides_is_preserved(self) -> None:
        self.assertEqual(self.collect({"NV_TOKEN": WS_BOTH}), [WS_BOTH])

    def test_tab_and_newline_padding_is_preserved(self) -> None:
        padded = "\t" + WS_CORE + "\n"
        self.assertEqual(self.collect({"NV_TOKEN": padded}), [padded])

    def test_whitespace_only_values_are_excluded(self) -> None:
        for blank in WS_BLANKS:
            with self.subTest(blank=repr(blank)):
                self.assertEqual(self.collect({"NV_TOKEN": blank}), [])

    def test_padded_placeholder_values_are_still_excluded(self) -> None:
        self.assertEqual(self.collect({"NV_TOKEN": "  ${NV_TOKEN}  "}), [])

    def test_identical_raw_values_are_deduplicated(self) -> None:
        self.assertEqual(
            self.collect({"NV_TOKEN": WS_BOTH, "ALFRESCO_PASS": WS_BOTH}), [WS_BOTH]
        )

    def test_distinct_raw_values_are_not_collapsed(self) -> None:
        padded = " " + WS_CORE + " "
        values = self.collect({"NV_TOKEN": WS_CORE, "ALFRESCO_PASS": padded})
        self.assertEqual(len(values), 2)
        self.assertEqual(sorted(values), sorted([WS_CORE, padded]))


class RuntimeSecretWhitespaceGuardIntegrationTest(unittest.TestCase):
    """The production CLI must guard on the exact raw runtime value."""

    ENV_KEYS = ("ALFRESCO_USER", "ALFRESCO_PASS", "FLOWABLE_USER", "FLOWABLE_PASS", "NV_TOKEN")

    def run_cli(self, *, token: str, marker: str, optional: bool) -> tuple:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "scan_root"
            root.mkdir()
            # A NUL-bearing file is recorded by path alone, so the marker
            # reaches the report without inventing a credential finding.
            (root / ("blob_" + marker + ".bin")).write_bytes(b"\x00\x01")
            report_path = Path(td) / "reports" / "report.json"
            env = dict(os.environ)
            for stale in self.ENV_KEYS:
                env.pop(stale, None)
            env["NV_TOKEN"] = token
            argv = [sys.executable, "scripts/secret_scan.py", "--root", str(root),
                    "--report", str(report_path)]
            if optional:
                argv.append("--optional")
            proc = subprocess.run(argv, cwd=str(repo_root), env=env, capture_output=True)
            return proc, report_path, report_path.exists(), report_path.read_bytes() if report_path.exists() else b""

    def test_raw_padded_runtime_value_in_the_report_is_blocked(self) -> None:
        proc, report_path, existed, _ = self.run_cli(token=WS_BOTH, marker=WS_BOTH, optional=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, b"")
        self.assertFalse(existed)
        self.assertIn(b"SecretSerializationError", proc.stderr)
        self.assertNotIn(WS_BOTH.encode("utf-8"), proc.stderr)

    def test_stripped_form_alone_is_not_a_false_match(self) -> None:
        proc, report_path, existed, written = self.run_cli(
            token=WS_BOTH, marker=WS_CORE, optional=True
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertTrue(existed)
        # The report really does carry the stripped form, so a guard that
        # compared against the stripped value would have blocked here.
        self.assertIn(WS_CORE.encode("utf-8"), written)
        self.assertNotIn(WS_BOTH.encode("utf-8"), written)
        self.assertEqual(proc.stdout, written)


if __name__ == "__main__":
    unittest.main()
