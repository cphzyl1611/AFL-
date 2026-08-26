"""Convert a full HTTP-like testcase to its byte-exact body."""

from __future__ import annotations


class HttpBodyAdapterError(ValueError):
    """The testcase has no usable HTTP envelope/body boundary."""


def extract_http_body(testcase: bytes) -> bytes:
    """Return bytes after the first LF or CRLF HTTP envelope delimiter."""
    delimiters = (b"\r\n\r\n", b"\n\n")
    matches = (
        (offset, len(delimiter))
        for delimiter in delimiters
        if (offset := testcase.find(delimiter)) >= 0
    )

    try:
        boundary, delimiter_length = min(matches)
    except ValueError as exc:
        raise HttpBodyAdapterError("missing HTTP envelope/body delimiter") from exc

    if boundary == 0:
        raise HttpBodyAdapterError("missing HTTP request envelope")

    request_line = testcase[:boundary].split(b"\n", 1)[0].removesuffix(b"\r")
    request_parts = request_line.split()
    if len(request_parts) < 2 or not request_parts[1].startswith(b"/"):
        raise HttpBodyAdapterError("malformed HTTP request line")

    body = testcase[boundary + delimiter_length :]
    if not body:
        raise HttpBodyAdapterError("empty HTTP body")

    return body
