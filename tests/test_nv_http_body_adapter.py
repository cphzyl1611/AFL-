"""Offline contract tests for the full-HTTP to exact-body adapter."""

from __future__ import annotations

import unittest
from unittest import mock

from nv_http_body_adapter import HttpBodyAdapterError, extract_http_body


class HttpBodyAdapterTest(unittest.TestCase):
    def test_request_line_is_excluded_from_output_body(self) -> None:
        actual = extract_http_body(b"PUT /nodes/id\n\n{\"name\":\"report\"}")

        self.assertEqual(actual, b'{"name":"report"}')

    def test_headers_are_excluded_from_output_body(self) -> None:
        testcase = (
            b"POST /documents\n"
            b"Host: example.invalid\n"
            b"Content-Type: application/json\n"
            b"X-Trace: local-only\n"
            b"\n"
            b'{"title":"draft"}'
        )

        actual = extract_http_body(testcase)

        self.assertEqual(actual, b'{"title":"draft"}')

    def test_first_envelope_delimiter_separates_the_complete_body(self) -> None:
        body = b"first body line\n\nsecond body line"
        testcase = b"POST /documents\nContent-Type: text/plain\n\n" + body

        actual = extract_http_body(testcase)

        self.assertEqual(actual, body)

    def test_body_bytes_are_preserved_exactly(self) -> None:
        body = b" \t{\x00\xff\x80}\r\ntrailing-space \n"
        testcase = b"PUT /nodes/id\nContent-Type: application/octet-stream\n\n" + body

        actual = extract_http_body(testcase)

        self.assertEqual(actual, body)

    def test_lf_envelope_delimiter_is_accepted(self) -> None:
        actual = extract_http_body(b"PATCH /item\nX-Mode: lf\n\nlf-body")

        self.assertEqual(actual, b"lf-body")

    def test_crlf_envelope_delimiter_is_accepted(self) -> None:
        actual = extract_http_body(
            b"PATCH /item HTTP/1.1\r\nX-Mode: crlf\r\n\r\ncrlf-body\r\n"
        )

        self.assertEqual(actual, b"crlf-body\r\n")

    def test_malformed_envelope_without_delimiter_fails_closed(self) -> None:
        malformed = b"POST /documents\nContent-Type: application/json\n{\"x\":1}"

        with self.assertRaises(HttpBodyAdapterError):
            extract_http_body(malformed)

    def test_malformed_request_line_fails_closed(self) -> None:
        malformed_cases = (
            b"not an HTTP request\n\nbody",
            b"\nHeader: value\n\nbody",
            b"\r\nHeader: value\r\n\r\nbody",
        )

        for testcase in malformed_cases:
            with self.subTest(testcase=testcase):
                with self.assertRaises(HttpBodyAdapterError):
                    extract_http_body(testcase)

    def test_empty_body_fails_closed(self) -> None:
        with self.assertRaises(HttpBodyAdapterError):
            extract_http_body(b"POST /documents\nContent-Type: application/json\n\n")

    def test_conversion_performs_no_network_activity(self) -> None:
        with (
            mock.patch("socket.socket") as socket_ctor,
            mock.patch("socket.create_connection") as create_connection,
            mock.patch("urllib.request.urlopen") as urlopen,
        ):
            actual = extract_http_body(b"POST /offline\n\n{\"offline\":true}")

        self.assertEqual(actual, b'{"offline":true}')
        socket_ctor.assert_not_called()
        create_connection.assert_not_called()
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
