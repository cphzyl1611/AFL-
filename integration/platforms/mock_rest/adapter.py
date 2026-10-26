from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

from ..base import (
    AdapterExecutionResult,
    BusinessVerdict,
    CleanupResult,
    ExecutionIdentity,
    HealthResult,
    PlatformAdapter,
    ReadbackResult,
    RequestSpec,
    _check_safe,
)


def _response_class(code: int) -> str:
    if code < 0:
        return "transport_error"
    return f"{code // 100}xx"


class MockRestAdapter(PlatformAdapter):
    name = "mock_rest"

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.base_url = str(config.get("base_url", "")).rstrip("/")
        parsed = urllib.parse.urlsplit(self.base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.port is None
            or parsed.path not in ("", "/")
        ):
            raise ValueError("mock_rest only accepts a 127.0.0.1 HTTP base_url")
        self.timeout = float(config.get("timeout_sec", 2.0))
        if self.timeout <= 0:
            raise ValueError("timeout_sec must be positive")
        self._context = {"platform": self.name, "base_url": self.base_url}

    @staticmethod
    def _check_identity(identity: ExecutionIdentity) -> None:
        if not isinstance(identity, ExecutionIdentity):
            raise ValueError("core execution identity is required")

    def runtime_context(self) -> Mapping[str, str]:
        return dict(self._context)

    def update_runtime_context(self, context: Mapping[str, str]) -> Mapping[str, str]:
        if not isinstance(context, Mapping):
            raise ValueError("runtime context must be a mapping")
        _check_safe(context, "runtime_context")
        self._context.update({str(key): str(value) for key, value in context.items()})
        return self.runtime_context()

    @staticmethod
    def _object_path(object_id: str | None) -> str:
        if not object_id or any(ord(ch) < 0x20 for ch in str(object_id)):
            raise ValueError("object_id is required")
        return "/api/items/" + urllib.parse.quote(str(object_id), safe="")

    def build_request(self, operation: str, payload: Any, identity: ExecutionIdentity, object_id: str | None = None) -> RequestSpec:
        self._check_identity(identity)
        if operation == "create":
            method, path = "POST", "/api/items"
        elif operation == "readback":
            method, path = "GET", self._object_path(object_id)
        elif operation == "update":
            method, path = "PUT", self._object_path(object_id)
        elif operation == "cleanup":
            method, path = "DELETE", self._object_path(object_id)
        elif operation == "health":
            method, path = "GET", "/health"
        else:
            raise ValueError(f"unsupported operation: {operation}")
        return RequestSpec(method, path, payload, {"Accept": "application/json", "Content-Type": "application/json"})

    def _request(self, spec: RequestSpec) -> tuple[int, Any, int, str | None]:
        body = None if spec.body is None or spec.method == "GET" or spec.method == "DELETE" else json.dumps(spec.body, separators=(",", ":")).encode()
        request = urllib.request.Request(self.base_url + spec.path, data=body, method=spec.method, headers=dict(spec.headers))
        started = time.monotonic()
        try:
            # The mock is loopback-only; bypass inherited proxy variables so a
            # developer proxy cannot turn an offline smoke into network traffic.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=self.timeout) as response:
                code = int(response.status)
                raw = response.read(256 * 1024)
        except urllib.error.HTTPError as exc:
            code, raw = int(exc.code), exc.read(256 * 1024)
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc).__class__.__name__.lower()
            return -2, {}, int((time.monotonic() - started) * 1000), "timeout" if "timeout" in reason else "connection"
        except TimeoutError:
            return -2, {}, int((time.monotonic() - started) * 1000), "timeout"
        latency = int((time.monotonic() - started) * 1000)
        if code == 204 or not raw:
            return code, {}, latency, None
        try:
            return code, json.loads(raw.decode("utf-8")), latency, None
        except (UnicodeDecodeError, json.JSONDecodeError):
            return code, raw, latency, "malformed_json"

    def extract_object_id(self, payload: Any) -> str | None:
        if isinstance(payload, Mapping) and isinstance(payload.get("id"), str) and payload["id"].strip():
            return payload["id"].strip()
        return None

    def business_verdict(self, operation: str, http_code: int, payload: Any, identity: ExecutionIdentity, object_id: str | None = None) -> BusinessVerdict:
        self._check_identity(identity)
        if http_code < 0:
            return BusinessVerdict(False, semantic_failure=True, error_kind="connection", safe_message="target connection failed")
        if 400 <= http_code < 500:
            return BusinessVerdict(False, expected_rejection=True, error_kind="expected_rejection", safe_message="target rejected the request")
        if not isinstance(payload, Mapping):
            return BusinessVerdict(False, semantic_failure=True, error_kind="malformed_json", safe_message="target response was not JSON")
        result_id = object_id or self.extract_object_id(payload)
        if operation == "readback" and (not result_id or self.extract_object_id(payload) != result_id):
            return BusinessVerdict(False, semantic_failure=True, error_kind="readback_mismatch", safe_message="readback did not match object id")
        if operation in {"create", "update"} and 200 <= http_code < 300 and not result_id:
            return BusinessVerdict(False, semantic_failure=True, error_kind="missing_object_id", safe_message="target response omitted object id")
        success = 200 <= http_code < 300
        return BusinessVerdict(success, semantic_failure=not success, error_kind=None if success else "unexpected_http", safe_message="business operation completed" if success else "target returned an unexpected response")

    def interpret_response(self, operation: str, http_code: int, payload: Any, identity: ExecutionIdentity, object_id: str | None = None) -> AdapterExecutionResult:
        self._check_identity(identity)
        result_id = object_id or self.extract_object_id(payload)
        verdict = self.business_verdict(operation, http_code, payload, identity, object_id)
        return AdapterExecutionResult.for_identity(identity, http_code=http_code, response_class="transport_error" if http_code < 0 else _response_class(http_code), business_success=verdict.business_success, expected_rejection=verdict.expected_rejection, semantic_failure=verdict.semantic_failure, object_id=result_id, error_kind=verdict.error_kind, safe_message=verdict.safe_message)

    def create(self, payload: Mapping[str, Any], identity: ExecutionIdentity) -> AdapterExecutionResult:
        self._check_identity(identity)
        started = time.monotonic()
        try:
            code, response, latency, error = self._request(self.build_request("create", dict(payload), identity))
        except (OSError, ValueError) as exc:
            return AdapterExecutionResult.for_identity(identity, http_code=-2, response_class="transport_error", semantic_failure=True, error_kind="connection", safe_message=str(exc))
        if error == "malformed_json":
            return AdapterExecutionResult.for_identity(identity, http_code=code, response_class=_response_class(code), semantic_failure=True, error_kind=error, latency_ms=latency, safe_message="target response was not JSON")
        if code < 0:
            return AdapterExecutionResult.for_identity(identity, http_code=code, response_class="transport_error", semantic_failure=True, error_kind=error or "connection", latency_ms=latency, safe_message="target connection failed")
        result = self.interpret_response("create", code, response, identity)
        return AdapterExecutionResult(**{**result.__dict__, "latency_ms": latency})

    def update(self, object_id: str, payload: Mapping[str, Any], identity: ExecutionIdentity) -> AdapterExecutionResult:
        self._check_identity(identity)
        code, response, latency, error = self._request(self.build_request("update", dict(payload), identity, object_id))
        if error == "malformed_json":
            return AdapterExecutionResult.for_identity(identity, http_code=code, response_class=_response_class(code), semantic_failure=True, error_kind=error, latency_ms=latency, safe_message="target response was not JSON")
        if code < 0:
            return AdapterExecutionResult.for_identity(identity, http_code=code, response_class="transport_error", semantic_failure=True, error_kind=error or "connection", latency_ms=latency, safe_message="target connection failed")
        result = self.interpret_response("update", code, response, identity, object_id)
        return AdapterExecutionResult(**{**result.__dict__, "latency_ms": latency})

    def readback(self, object_id: str, identity: ExecutionIdentity) -> ReadbackResult:
        self._check_identity(identity)
        code, payload, latency, error = self._request(self.build_request("readback", None, identity, object_id))
        if code == 404:
            return ReadbackResult(identity, False, object_id=object_id, absent=True, latency_ms=latency, error_kind="not_found", safe_message="object is absent")
        if error or not isinstance(payload, Mapping):
            return ReadbackResult(identity, False, object_id=object_id, semantic_failure=True, latency_ms=latency, error_kind=error or "malformed_json", safe_message="readback failed")
        if code < 200 or code >= 300 or payload.get("id") != object_id:
            return ReadbackResult(identity, False, payload if isinstance(payload, Mapping) else {}, object_id=object_id, semantic_failure=True, latency_ms=latency, error_kind="readback_mismatch", safe_message="readback did not match object id")
        return ReadbackResult(identity, True, payload, object_id=object_id, latency_ms=latency, safe_message="readback matched")

    def cleanup(self, object_id: str, identity: ExecutionIdentity) -> CleanupResult:
        self._check_identity(identity)
        current = self.readback(object_id, identity)
        if current.absent:
            return CleanupResult(identity, True, True, object_id=object_id, safe_message="already absent")
        if not current.success:
            return CleanupResult(identity, False, object_id=object_id, error_kind="ownership_or_readback_failure", safe_message="cleanup precondition failed")
        code, _payload, _latency, error = self._request(self.build_request("cleanup", None, identity, object_id))
        if error or code < 200 or code >= 300:
            return CleanupResult(identity, False, object_id=object_id, error_kind=error or "delete_failed", safe_message="cleanup delete failed")
        absent = self.readback(object_id, identity).absent
        return CleanupResult(identity, absent, absent, object_id=object_id, safe_message="cleanup verified" if absent else "cleanup absence check failed")

    def health_check(self, identity: ExecutionIdentity) -> HealthResult:
        self._check_identity(identity)
        code, payload, _latency, error = self._request(self.build_request("health", None, identity))
        return HealthResult(identity, not error and code == 200 and isinstance(payload, Mapping) and payload.get("status") == "ok", False, code, "health check completed" if not error else "health check failed")
