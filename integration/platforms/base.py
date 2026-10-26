"""Small, explicit platform adapter contract.

The core creates execution identities and owns validity, accounting, state, and
reporting.  Adapters only describe platform requests and business outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


SECRET_FIELD_NAMES = {
    "authorization", "cookie", "password", "passwd", "secret", "token",
    "private_key", "client_secret", "access_token", "refresh_token",
}


class SecretFieldError(ValueError):
    """Raised when a structured contract object would carry a secret."""


class AdapterRegistryError(ValueError):
    """Raised for unknown or invalid adapters."""


def _check_safe(value: Any, path: str = "result") -> None:
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in (
            "bearer ", "basic ", "set-cookie:", "authorization:",
            "password=", "token=", "secret=",
        )):
            raise SecretFieldError(f"secret-bearing text is not allowed: {path}")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in SECRET_FIELD_NAMES or any(
                part in normalized for part in ("authorization", "password", "cookie", "token")
            ):
                raise SecretFieldError(f"secret field is not allowed: {path}.{key}")
            _check_safe(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _check_safe(child, f"{path}[{index}]")


@dataclass(frozen=True)
class ExecutionIdentity:
    task_id: str
    run_id: str
    exec_seq: int
    seed_id: str
    mutation_arm: str

    def __post_init__(self) -> None:
        for name in ("task_id", "run_id", "seed_id", "mutation_arm"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"missing execution identity field: {name}")
        if isinstance(self.exec_seq, bool) or not isinstance(self.exec_seq, int) or self.exec_seq <= 0:
            raise ValueError("exec_seq must be a positive integer")


@dataclass(frozen=True)
class RequestSpec:
    method: str
    path: str
    body: Any = None
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.method or not self.path.startswith("/"):
            raise ValueError("request method/path is invalid")
        _check_safe(dict(self.headers), "headers")


@dataclass(frozen=True)
class BusinessVerdict:
    business_success: bool
    expected_rejection: bool = False
    semantic_failure: bool = False
    error_kind: str | None = None
    safe_message: str = ""

    def __post_init__(self) -> None:
        _check_safe(self.safe_message)


@dataclass(frozen=True)
class AdapterExecutionResult:
    identity: ExecutionIdentity
    http_code: int
    response_class: str
    business_success: bool = False
    expected_rejection: bool = False
    semantic_failure: bool = False
    object_id: str | None = None
    error_kind: str | None = None
    latency_ms: int = 0
    safe_message: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.http_code < -2:
            raise ValueError("invalid HTTP code")
        _check_safe(self.metadata)
        _check_safe(self.safe_message)

    @classmethod
    def for_identity(cls, identity: ExecutionIdentity, **kwargs: Any) -> "AdapterExecutionResult":
        return cls(identity=identity, **kwargs)


@dataclass(frozen=True)
class ReadbackResult:
    identity: ExecutionIdentity
    success: bool
    payload: Mapping[str, Any] = field(default_factory=dict)
    object_id: str | None = None
    absent: bool = False
    semantic_failure: bool = False
    error_kind: str | None = None
    latency_ms: int = 0
    safe_message: str = ""

    def __post_init__(self) -> None:
        _check_safe(self.payload)
        _check_safe(self.safe_message)


@dataclass(frozen=True)
class CleanupResult:
    identity: ExecutionIdentity
    success: bool
    absent: bool = False
    object_id: str | None = None
    error_kind: str | None = None
    safe_message: str = ""

    def __post_init__(self) -> None:
        _check_safe(self.safe_message)


@dataclass(frozen=True)
class HealthResult:
    identity: ExecutionIdentity
    success: bool
    business_recovery: bool = False
    http_code: int = 0
    safe_message: str = ""

    def __post_init__(self) -> None:
        _check_safe(self.safe_message)


class PlatformAdapter:
    """Structural contract implemented by a platform adapter."""

    name = ""

    def build_request(self, operation: str, payload: Any, identity: ExecutionIdentity, object_id: str | None = None) -> RequestSpec:
        raise NotImplementedError

    def interpret_response(self, operation: str, http_code: int, payload: Any, identity: ExecutionIdentity, object_id: str | None = None) -> AdapterExecutionResult:
        raise NotImplementedError

    def business_verdict(self, operation: str, http_code: int, payload: Any, identity: ExecutionIdentity, object_id: str | None = None) -> BusinessVerdict:
        raise NotImplementedError

    def extract_object_id(self, payload: Any) -> str | None:
        raise NotImplementedError

    def create(self, payload: Mapping[str, Any], identity: ExecutionIdentity) -> AdapterExecutionResult:
        raise NotImplementedError

    def update(self, object_id: str, payload: Mapping[str, Any], identity: ExecutionIdentity) -> AdapterExecutionResult:
        raise NotImplementedError

    def readback(self, object_id: str, identity: ExecutionIdentity) -> ReadbackResult:
        raise NotImplementedError

    def cleanup(self, object_id: str, identity: ExecutionIdentity) -> CleanupResult:
        raise NotImplementedError

    def health_check(self, identity: ExecutionIdentity) -> HealthResult:
        raise NotImplementedError

    def runtime_context(self) -> Mapping[str, str]:
        return {}

    def update_runtime_context(self, context: Mapping[str, str]) -> Mapping[str, str]:
        raise NotImplementedError
