"""Explicit Phase-1 platform registry; no discovery or module loading."""
from __future__ import annotations

from typing import Any, Callable, Mapping

from .base import AdapterRegistryError, PlatformAdapter, SECRET_FIELD_NAMES
from .mock_rest.adapter import MockRestAdapter


_FACTORIES: dict[str, Callable[[Mapping[str, Any]], PlatformAdapter]] = {
    "mock_rest": MockRestAdapter,
}


def list_adapters() -> list[str]:
    return sorted(_FACTORIES)


def _validate_config(config: Mapping[str, Any]) -> None:
    allowed_env_names = {"username_env", "password_env", "token_env"}
    allowed_keys = {"base_url", "timeout_sec", *allowed_env_names}
    for key in config:
        normalized = str(key).lower().replace("-", "_")
        if normalized not in allowed_keys:
            raise AdapterRegistryError(f"unknown adapter config field: {key}")
        if normalized in allowed_env_names:
            continue
        if normalized in SECRET_FIELD_NAMES or any(
            part in normalized for part in ("authorization", "password", "cookie", "token")
        ):
            raise AdapterRegistryError(f"secret-bearing config field is not allowed: {key}")
    for key, value in config.items():
        if str(key).lower().replace("-", "_") in allowed_env_names:
            if not isinstance(value, str) or not value or not value.replace("_", "").isalnum() or not value[0].isalpha():
                raise AdapterRegistryError(f"credential configuration must name an environment variable: {key}")
            continue
        if isinstance(value, str) and any(
            marker in value.lower() for marker in ("bearer ", "basic ", "set-cookie")
        ):
            raise AdapterRegistryError(f"secret-bearing config value is not allowed: {key}")


def validate_adapter(adapter: object) -> list[str]:
    required = ("build_request", "interpret_response", "business_verdict", "extract_object_id", "create", "update", "readback", "cleanup", "update_runtime_context")
    missing = []
    for name in required:
        implementation = getattr(type(adapter), name, None)
        base_implementation = getattr(PlatformAdapter, name, None)
        if not callable(getattr(adapter, name, None)) or implementation is base_implementation:
            missing.append(name)
    return missing


def get_adapter(name: str, config: Mapping[str, Any] | None = None) -> PlatformAdapter:
    key = str(name).strip()
    if key not in _FACTORIES:
        raise AdapterRegistryError(f"unknown adapter: {key or '<empty>'}")
    supplied = dict(config or {})
    _validate_config(supplied)
    adapter = _FACTORIES[key](supplied)
    missing = validate_adapter(adapter)
    if missing:
        raise AdapterRegistryError(f"adapter {key} is missing: {', '.join(missing)}")
    return adapter
