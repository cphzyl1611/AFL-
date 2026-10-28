from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class _Handler(BaseHTTPRequestHandler):
    server_version = "Deep2FuzzMock/1"

    def log_message(self, *_args: Any) -> None:
        return

    @property
    def state(self):
        return self.server.state  # type: ignore[attr-defined]

    def _send(self, code: int, payload: Any) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            return value if isinstance(value, dict) else None
        except (ValueError, TypeError, json.JSONDecodeError):
            return None

    def _count(self) -> None:
        self.state["request_count"] += 1

    def do_GET(self) -> None:  # noqa: N802
        self._count()
        if self.path == "/health":
            self._send(200, {"status": "ok"})
            return
        if self.path.startswith("/api/items/"):
            item_id = self.path.rsplit("/", 1)[-1]
            item = self.state["items"].get(item_id)
            if item is not None and (
                item.get("force_readback_mismatch")
                or self.state.get("scenario") == "semantic_failure"
                and not item.get("semantic_mismatch_triggered")
            ):
                item = dict(item)
                item["force_readback_mismatch"] = False
                item["semantic_mismatch_triggered"] = True
                self.state["items"][item_id] = item
                item = {**item, "id": "mismatch-" + item_id}
            self._send(200 if item is not None else 404, item if item is not None else {"error": "not_found"})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        self._count()
        if self.path != "/api/items":
            self._send(404, {"error": "not_found"})
            return
        body = self._json()
        if body is None:
            self._send(400, {"error": "malformed_json"})
            return
        if self.state.get("scenario") == "expected_rejection" or body.get("reject") or body.get("reject_before_target"):
            self._send(422, {"error": "validation_rejection"})
            return
        item_id = f"item-{self.state['next_id']}"
        self.state["next_id"] += 1
        self.state["object_creation_count"] += 1
        item = {"id": item_id, **body}
        self.state["items"][item_id] = item
        self._send(201, item)

    def do_PUT(self) -> None:  # noqa: N802
        self._count()
        if not self.path.startswith("/api/items/"):
            self._send(404, {"error": "not_found"})
            return
        item_id = self.path.rsplit("/", 1)[-1]
        if item_id not in self.state["items"]:
            self._send(404, {"error": "not_found"})
            return
        body = self._json()
        if body is None:
            self._send(400, {"error": "malformed_json"})
            return
        if body.get("reject"):
            self._send(422, {"error": "validation_rejection"})
            return
        self.state["items"][item_id] = {"id": item_id, **body}
        self._send(200, self.state["items"][item_id])

    def do_DELETE(self) -> None:  # noqa: N802
        self._count()
        if not self.path.startswith("/api/items/"):
            self._send(404, {"error": "not_found"})
            return
        item_id = self.path.rsplit("/", 1)[-1]
        if item_id not in self.state["items"]:
            self._send(404, {"error": "not_found"})
            return
        if self.state.get("scenario") == "cleanup_failure" and self.state["object_creation_count"] >= 9:
            self._send(503, {"error": "cleanup_unavailable"})
            return
        del self.state["items"][item_id]
        self._send(204, {})


class MockRestService:
    """Context manager for an in-memory loopback service."""

    def __init__(self, scenario: str = "success") -> None:
        if scenario not in {"success", "expected_rejection", "semantic_failure", "validity_rejection", "cleanup_failure"}:
            raise ValueError(f"unsupported mock service scenario: {scenario}")
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.state = {"items": {}, "next_id": 1, "request_count": 0, "object_creation_count": 0, "scenario": scenario}  # type: ignore[attr-defined]
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def request_count(self) -> int:
        return int(self._server.state["request_count"])  # type: ignore[attr-defined]

    @property
    def object_creation_count(self) -> int:
        return int(self._server.state["object_creation_count"])  # type: ignore[attr-defined]

    def __enter__(self) -> "MockRestService":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
