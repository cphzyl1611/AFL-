#!/usr/bin/env python3
"""Isolated strict input adapter for the O2OA v2 research contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from model_stage.feature_extract import FEATURE_ORDER, extract_features_from_bytes, vectorize_feature_dict


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "model_stage" / "contracts" / "o2oa_cms_doc_list_fixed_38.json"
RULE_PATH = ROOT / "validity" / "o2oa_query_rules.json"


class O2OAV2InputError(ValueError):
    """Raised when input cannot satisfy the strict O2OA v2 contract."""


class _DuplicateKey(ValueError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_contract() -> dict[str, Any]:
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise O2OAV2InputError("invalid O2OA v2 contract artifact") from exc
    if contract.get("contract_id") != "o2oa_cms_doc_list_fixed_38":
        raise O2OAV2InputError("unexpected O2OA v2 contract ID")
    if contract.get("input_dim") != 38 or contract.get("feature_order") != FEATURE_ORDER:
        raise O2OAV2InputError("O2OA v2 feature contract mismatch")
    for path_key, expected in (
        ("extractor_path", "model_stage/feature_extract.py"),
        ("rule_contract_path", "validity/o2oa_query_rules.json"),
    ):
        if contract.get(path_key) != expected:
            raise O2OAV2InputError(f"unexpected {path_key}")
    for path_key, hash_key in (
        ("parser_contract_path", "parser_contract_sha256"),
        ("extractor_path", "extractor_sha256"),
        ("rule_contract_path", "rule_contract_sha256"),
    ):
        path = ROOT / contract[path_key].split(":", 1)[0]
        try:
            artifact_hash = _sha256(path.read_bytes())
        except OSError as exc:
            # Translate any I/O failure (missing file, permission denied, etc.)
            # reading a bound artifact into the adapter's exception contract.
            raise O2OAV2InputError(f"{path_key} artifact unreadable") from exc
        if artifact_hash != contract[hash_key]:
            raise O2OAV2InputError(f"{path_key} hash mismatch")
    return contract


def _validate_rules(obj: Any) -> None:
    try:
        rules = json.loads(RULE_PATH.read_text(encoding="utf-8"))
        endpoint = rules["endpoints"]["cms_doc_list"]
        common = rules["common"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise O2OAV2InputError("invalid O2OA rule contract") from exc

    if not isinstance(obj, dict):
        raise O2OAV2InputError("cms_doc_list root must be an object")
    def depth(value: Any, current: int = 0) -> int:
        if isinstance(value, dict):
            return current + 1 if not value else max(depth(child, current + 1) for child in value.values())
        if isinstance(value, list):
            return current + 1 if not value else max(depth(child, current + 1) for child in value)
        return current + 1

    def key_count(value: Any) -> int:
        if isinstance(value, dict):
            return len(value) + sum(key_count(child) for child in value.values())
        if isinstance(value, list):
            return sum(key_count(child) for child in value)
        return 0

    def max_string_length(value: Any) -> int:
        if isinstance(value, dict):
            return max([max_string_length(key) for key in value] + [max_string_length(child) for child in value.values()] or [0])
        if isinstance(value, list):
            return max([max_string_length(child) for child in value] or [0])
        return len(value) if isinstance(value, str) else 0

    if len(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) > common["max_bytes"]:
        raise O2OAV2InputError("body exceeds O2OA byte limit")
    if depth(obj) > common["max_depth"]:
        raise O2OAV2InputError("body exceeds O2OA depth limit")
    if key_count(obj) > common["max_keys"]:
        raise O2OAV2InputError("body exceeds O2OA key limit")
    if max_string_length(obj) > common["max_string"]:
        raise O2OAV2InputError("body contains an oversized string")
    for key in endpoint["required"]:
        if key not in obj:
            raise O2OAV2InputError(f"missing required field: {key}")
    if not isinstance(obj["docStatusList"], list):
        raise O2OAV2InputError("docStatusList must be an array")
    if not isinstance(obj["categoryIdList"], list):
        raise O2OAV2InputError("categoryIdList must be an array")
    if not isinstance(obj["key"], str):
        raise O2OAV2InputError("key must be a string")
    if len(obj["docStatusList"]) > endpoint["properties"]["docStatusList"]["maxItems"]:
        raise O2OAV2InputError("docStatusList exceeds maxItems")
    if len(obj["categoryIdList"]) > endpoint["properties"]["categoryIdList"]["maxItems"]:
        raise O2OAV2InputError("categoryIdList exceeds maxItems")
    if len(obj["key"]) > endpoint["properties"]["key"]["maxLength"]:
        raise O2OAV2InputError("key exceeds maxLength")


@dataclass(frozen=True)
class O2OAV2Input:
    raw_body: bytes
    raw_body_sha256: str
    parsed_object: Any
    canonical_json_bytes: bytes
    canonical_json_sha256: str
    feature_vector: tuple[float, ...]
    feature_vector_sha256: str
    feature_names: tuple[str, ...]
    contract_id: str


def prepare_o2oa_v2_input(raw_body: bytes) -> O2OAV2Input:
    if not isinstance(raw_body, bytes) or not raw_body:
        raise O2OAV2InputError("raw body must be non-empty bytes")
    try:
        text = raw_body.decode("utf-8", errors="strict")
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_nonfinite,
        )
        canonical = json.dumps(
            parsed,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, _DuplicateKey) as exc:
        raise O2OAV2InputError("strict O2OA v2 JSON parsing failed") from exc

    contract = _load_contract()
    _validate_rules(parsed)
    features = extract_features_from_bytes(canonical)
    vector = tuple(vectorize_feature_dict(features))
    if len(vector) != contract["input_dim"] or not all(map(lambda value: value == value and abs(value) != float("inf"), vector)):
        raise O2OAV2InputError("invalid O2OA v2 feature vector")
    vector_bytes = json.dumps(list(vector), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return O2OAV2Input(
        raw_body=raw_body,
        raw_body_sha256=_sha256(raw_body),
        parsed_object=parsed,
        canonical_json_bytes=canonical,
        canonical_json_sha256=_sha256(canonical),
        feature_vector=vector,
        feature_vector_sha256=_sha256(vector_bytes),
        feature_names=tuple(FEATURE_ORDER),
        contract_id=contract["contract_id"],
    )
