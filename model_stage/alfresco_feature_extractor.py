#!/usr/bin/env python3
"""Feature extraction for Alfresco document-interface validity scoring.

The extractor intentionally uses only the Python standard library. All public
extractors return the same fixed-length vector so metadata update, text content
update, and multipart upload samples can share one AE-like statistical scorer.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


_FEATURE_NAMES = [
    "scenario_metadata_update",
    "scenario_text_content_update",
    "scenario_multipart_upload",
    "total_fields",
    "has_name",
    "name_length",
    "has_properties",
    "title_length",
    "description_length",
    "property_count",
    "invalid_type_count",
    "string_field_count",
    "numeric_field_count",
    "byte_length",
    "char_length",
    "line_count",
    "max_line_length",
    "avg_line_length",
    "printable_ratio",
    "chinese_char_ratio",
    "digit_ratio",
    "whitespace_ratio",
    "entropy",
    "has_nul_byte",
    "utf8_valid",
    "filename_length",
    "filename_has_txt_suffix",
    "content_size",
    "nodeType_is_cm_content",
    "autoRename_present",
    "autoRename_true",
    "filedata_present",
]


def feature_names() -> list[str]:
    return list(_FEATURE_NAMES)


def _empty_feature_map() -> dict[str, float]:
    return {name: 0.0 for name in _FEATURE_NAMES}


def _count_fields(value: Any) -> int:
    if isinstance(value, dict):
        return len(value) + sum(_count_fields(item) for item in value.values())
    if isinstance(value, list):
        return sum(_count_fields(item) for item in value)
    return 0


def _count_value_types(value: Any) -> tuple[int, int]:
    string_count = 0
    numeric_count = 0

    def walk(item: Any) -> None:
        nonlocal string_count, numeric_count
        if isinstance(item, dict):
            for key, sub_value in item.items():
                if isinstance(key, str):
                    string_count += 1
                walk(sub_value)
        elif isinstance(item, list):
            for sub_value in item:
                walk(sub_value)
        elif isinstance(item, str):
            string_count += 1
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            numeric_count += 1

    walk(value)
    return string_count, numeric_count


def _invalid_metadata_type_count(payload: Mapping[str, Any]) -> int:
    invalid = 0
    if "name" not in payload or not isinstance(payload.get("name"), str):
        invalid += 1
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        invalid += 1
        return invalid + 2
    if "cm:title" not in properties or not isinstance(properties.get("cm:title"), str):
        invalid += 1
    if "cm:description" in properties and not isinstance(properties.get("cm:description"), str):
        invalid += 1
    return invalid


def _vector_from_map(values: dict[str, float]) -> list[float]:
    return [float(values[name]) for name in _FEATURE_NAMES]


def extract_metadata_features(payload: dict) -> list[float]:
    values = _empty_feature_map()
    values["scenario_metadata_update"] = 1.0

    if not isinstance(payload, dict):
        values["invalid_type_count"] = 4.0
        return _vector_from_map(values)

    properties = payload.get("properties")
    title = properties.get("cm:title") if isinstance(properties, dict) else None
    description = properties.get("cm:description") if isinstance(properties, dict) else None
    name = payload.get("name")
    string_count, numeric_count = _count_value_types(payload)

    values["total_fields"] = float(_count_fields(payload))
    values["has_name"] = 1.0 if isinstance(name, str) else 0.0
    values["name_length"] = float(len(name)) if isinstance(name, str) else 0.0
    values["has_properties"] = 1.0 if isinstance(properties, dict) else 0.0
    values["title_length"] = float(len(title)) if isinstance(title, str) else 0.0
    values["description_length"] = float(len(description)) if isinstance(description, str) else 0.0
    values["property_count"] = float(len(properties)) if isinstance(properties, dict) else 0.0
    values["invalid_type_count"] = float(_invalid_metadata_type_count(payload))
    values["string_field_count"] = float(string_count)
    values["numeric_field_count"] = float(numeric_count)
    return _vector_from_map(values)


def _text_stats(text: str | bytes) -> tuple[str, bytes, bool]:
    if isinstance(text, bytes):
        raw = text
        try:
            decoded = raw.decode("utf-8")
            utf8_valid = True
        except UnicodeDecodeError:
            decoded = raw.decode("utf-8", errors="replace")
            utf8_valid = False
        return decoded, raw, utf8_valid

    decoded = str(text)
    raw = decoded.encode("utf-8")
    return decoded, raw, True


def _entropy(raw: bytes) -> float:
    if not raw:
        return 0.0
    counts: dict[int, int] = {}
    for byte in raw:
        counts[byte] = counts.get(byte, 0) + 1
    total = float(len(raw))
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _fill_text_features(values: dict[str, float], text: str | bytes) -> None:
    decoded, raw, utf8_valid = _text_stats(text)
    lines = decoded.splitlines() or ([decoded] if decoded else [])
    line_lengths = [len(line) for line in lines]
    char_count = len(decoded)
    printable_count = sum(1 for char in decoded if char.isprintable() or char in "\r\n\t")
    chinese_count = sum(1 for char in decoded if "\u4e00" <= char <= "\u9fff")
    digit_count = sum(1 for char in decoded if char.isdigit())
    whitespace_count = sum(1 for char in decoded if char.isspace())
    denominator = float(char_count) if char_count else 1.0

    values["byte_length"] = float(len(raw))
    values["char_length"] = float(char_count)
    values["line_count"] = float(len(lines))
    values["max_line_length"] = float(max(line_lengths) if line_lengths else 0)
    values["avg_line_length"] = float(sum(line_lengths) / len(line_lengths)) if line_lengths else 0.0
    values["printable_ratio"] = printable_count / denominator
    values["chinese_char_ratio"] = chinese_count / denominator
    values["digit_ratio"] = digit_count / denominator
    values["whitespace_ratio"] = whitespace_count / denominator
    values["entropy"] = _entropy(raw)
    values["has_nul_byte"] = 1.0 if b"\x00" in raw else 0.0
    values["utf8_valid"] = 1.0 if utf8_valid else 0.0


def extract_text_content_features(text: str | bytes) -> list[float]:
    values = _empty_feature_map()
    values["scenario_text_content_update"] = 1.0
    _fill_text_features(values, text)
    return _vector_from_map(values)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def extract_multipart_upload_features(filename: str, content: bytes, fields: dict) -> list[float]:
    values = _empty_feature_map()
    values["scenario_multipart_upload"] = 1.0
    _fill_text_features(values, content)

    fields = fields if isinstance(fields, dict) else {}
    node_type = fields.get("nodeType")
    auto_rename = fields.get("autoRename")

    values["filename_length"] = float(len(filename or ""))
    values["filename_has_txt_suffix"] = 1.0 if str(filename or "").endswith(".txt") else 0.0
    values["content_size"] = float(len(content or b""))
    values["nodeType_is_cm_content"] = 1.0 if node_type == "cm:content" else 0.0
    values["autoRename_present"] = 1.0 if "autoRename" in fields else 0.0
    values["autoRename_true"] = 1.0 if _truthy(auto_rename) else 0.0
    values["filedata_present"] = 1.0 if content is not None else 0.0
    return _vector_from_map(values)
