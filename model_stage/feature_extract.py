#!/usr/bin/env python3
import json
import math
from typing import Any, Dict, List


FEATURE_ORDER = [
    "body_bytes",
    "json_depth",
    "total_keys",
    "total_nodes",
    "dict_count",
    "list_count",
    "string_count",
    "number_count",
    "bool_count",
    "null_count",
    "max_string_len",
    "avg_string_len",
    "max_list_len",
    "avg_list_len",
    "max_run_length_any_string",
    "avg_run_length_strings",
    "max_special_ratio",
    "avg_special_ratio",
    "max_space_ratio",
    "avg_space_ratio",
    "max_case_flip_ratio",
    "avg_case_flip_ratio",
    "min_unique_char_ratio",
    "avg_unique_char_ratio",
    "max_list_repeat_ratio",
    "avg_list_repeat_ratio",
    "repeated_list_count",
    "large_list_count",
    "long_item_list_count",
    "has_key_field",
    "key_len",
    "key_run_length",
    "key_special_ratio",
    "key_unique_char_ratio",
    "docStatusList_len",
    "docStatusList_repeat_ratio",
    "categoryIdList_len",
    "categoryIdList_repeat_ratio",
]


SPECIAL_CHARS = set("!@#$%^&*?~|\\/`'\";:<>,+=")


def json_depth(x: Any, d: int = 0) -> int:
    if isinstance(x, dict):
        if not x:
            return d + 1
        return max(json_depth(v, d + 1) for v in x.values())
    if isinstance(x, list):
        if not x:
            return d + 1
        return max(json_depth(v, d + 1) for v in x)
    return d + 1


def _max_run_length(s: str) -> int:
    if not s:
        return 0
    best = 1
    cur = 1
    for i in range(1, len(s)):
        if s[i] == s[i - 1]:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def _special_ratio(s: str) -> float:
    if not s:
        return 0.0
    return sum(1 for ch in s if ch in SPECIAL_CHARS) / max(1, len(s))


def _space_ratio(s: str) -> float:
    if not s:
        return 0.0
    return sum(1 for ch in s if ch.isspace()) / max(1, len(s))


def _case_flip_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 2:
        return 0.0
    flips = 0
    for i in range(1, len(letters)):
        if letters[i].islower() != letters[i - 1].islower():
            flips += 1
    return flips / max(1, len(letters) - 1)


def _unique_char_ratio(s: str) -> float:
    if not s:
        return 1.0
    return len(set(s)) / max(1, len(s))


def _normalize_scalar(v: Any) -> str:
    if isinstance(v, str):
        return f"s:{v}"
    if isinstance(v, bool):
        return f"b:{v}"
    if isinstance(v, (int, float)):
        return f"n:{v}"
    if v is None:
        return "null"
    return f"t:{type(v).__name__}"


def _list_repeat_ratio(arr: list) -> float:
    if not arr:
        return 0.0
    vals = [_normalize_scalar(v) if not isinstance(v, (dict, list)) else type(v).__name__ for v in arr]
    uniq = set(vals)
    max_dup = max(vals.count(v) for v in uniq)
    return max_dup / max(1, len(vals))


def _safe_avg(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def extract_features_from_obj(obj: Any, body_bytes: int = 0) -> Dict[str, float]:
    feat: Dict[str, float] = {k: 0.0 for k in FEATURE_ORDER}
    feat["body_bytes"] = float(body_bytes)
    feat["json_depth"] = float(json_depth(obj))

    total_nodes = 0
    total_keys = 0
    dict_count = 0
    list_count = 0
    string_count = 0
    number_count = 0
    bool_count = 0
    null_count = 0

    string_lens: List[float] = []
    list_lens: List[float] = []
    run_lengths: List[float] = []
    special_ratios: List[float] = []
    space_ratios: List[float] = []
    case_flip_ratios: List[float] = []
    unique_char_ratios: List[float] = []
    list_repeat_ratios: List[float] = []

    repeated_list_count = 0
    large_list_count = 0
    long_item_list_count = 0

    def walk(x: Any):
        nonlocal total_nodes, total_keys, dict_count, list_count
        nonlocal string_count, number_count, bool_count, null_count
        nonlocal repeated_list_count, large_list_count, long_item_list_count

        total_nodes += 1

        if isinstance(x, dict):
            dict_count += 1
            total_keys += len(x)
            for _, v in x.items():
                walk(v)

        elif isinstance(x, list):
            list_count += 1
            list_lens.append(float(len(x)))
            rr = _list_repeat_ratio(x)
            list_repeat_ratios.append(rr)

            if rr >= 0.7:
                repeated_list_count += 1
            if len(x) >= 10:
                large_list_count += 1
            if any(isinstance(v, str) and len(v) > 32 for v in x):
                long_item_list_count += 1

            for v in x:
                walk(v)

        elif isinstance(x, str):
            string_count += 1
            string_lens.append(float(len(x)))
            run_lengths.append(float(_max_run_length(x)))
            special_ratios.append(_special_ratio(x))
            space_ratios.append(_space_ratio(x))
            case_flip_ratios.append(_case_flip_ratio(x))
            unique_char_ratios.append(_unique_char_ratio(x))

        elif isinstance(x, bool):
            bool_count += 1

        elif x is None:
            null_count += 1

        elif isinstance(x, (int, float)):
            number_count += 1

    walk(obj)

    feat["total_keys"] = float(total_keys)
    feat["total_nodes"] = float(total_nodes)
    feat["dict_count"] = float(dict_count)
    feat["list_count"] = float(list_count)
    feat["string_count"] = float(string_count)
    feat["number_count"] = float(number_count)
    feat["bool_count"] = float(bool_count)
    feat["null_count"] = float(null_count)

    feat["max_string_len"] = max(string_lens) if string_lens else 0.0
    feat["avg_string_len"] = _safe_avg(string_lens)
    feat["max_list_len"] = max(list_lens) if list_lens else 0.0
    feat["avg_list_len"] = _safe_avg(list_lens)

    feat["max_run_length_any_string"] = max(run_lengths) if run_lengths else 0.0
    feat["avg_run_length_strings"] = _safe_avg(run_lengths)
    feat["max_special_ratio"] = max(special_ratios) if special_ratios else 0.0
    feat["avg_special_ratio"] = _safe_avg(special_ratios)
    feat["max_space_ratio"] = max(space_ratios) if space_ratios else 0.0
    feat["avg_space_ratio"] = _safe_avg(space_ratios)
    feat["max_case_flip_ratio"] = max(case_flip_ratios) if case_flip_ratios else 0.0
    feat["avg_case_flip_ratio"] = _safe_avg(case_flip_ratios)
    feat["min_unique_char_ratio"] = min(unique_char_ratios) if unique_char_ratios else 1.0
    feat["avg_unique_char_ratio"] = _safe_avg(unique_char_ratios)

    feat["max_list_repeat_ratio"] = max(list_repeat_ratios) if list_repeat_ratios else 0.0
    feat["avg_list_repeat_ratio"] = _safe_avg(list_repeat_ratios)
    feat["repeated_list_count"] = float(repeated_list_count)
    feat["large_list_count"] = float(large_list_count)
    feat["long_item_list_count"] = float(long_item_list_count)

    # endpoint-related light features
    if isinstance(obj, dict):
        key_val = obj.get("key")
        if isinstance(key_val, str):
            feat["has_key_field"] = 1.0
            feat["key_len"] = float(len(key_val))
            feat["key_run_length"] = float(_max_run_length(key_val))
            feat["key_special_ratio"] = _special_ratio(key_val)
            feat["key_unique_char_ratio"] = _unique_char_ratio(key_val)

        dsl = obj.get("docStatusList")
        if isinstance(dsl, list):
            feat["docStatusList_len"] = float(len(dsl))
            feat["docStatusList_repeat_ratio"] = _list_repeat_ratio(dsl)

        cidl = obj.get("categoryIdList")
        if isinstance(cidl, list):
            feat["categoryIdList_len"] = float(len(cidl))
            feat["categoryIdList_repeat_ratio"] = _list_repeat_ratio(cidl)

    return feat


def extract_features_from_bytes(body: bytes) -> Dict[str, float]:
    obj = json.loads(body.decode("utf-8"))
    return extract_features_from_obj(obj, body_bytes=len(body))


def vectorize_feature_dict(feat: Dict[str, float]) -> List[float]:
    return [float(feat.get(k, 0.0)) for k in FEATURE_ORDER]


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("usage: python3 feature_extract.py <json_file>")
        raise SystemExit(1)

    with open(sys.argv[1], "rb") as f:
        body = f.read()

    feat = extract_features_from_bytes(body)
    print(json.dumps(feat, ensure_ascii=False, indent=2))
    print("VECTOR =", vectorize_feature_dict(feat))