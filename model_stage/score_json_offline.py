#!/usr/bin/env python3
import json
import sys
from feature_extract import extract_features_from_bytes


def score_from_features(feat: dict) -> float:
    sc = 0.1

    # 1. key 字段异常
    key_len = feat.get("key_len", 0.0)
    key_run = feat.get("key_run_length", 0.0)
    key_ucr = feat.get("key_unique_char_ratio", 1.0)
    key_special = feat.get("key_special_ratio", 0.0)

    if key_len > 128:
        sc += 1.0
    elif key_len > 64:
        sc += 0.5

    if key_run > 40:
        sc += 2.0
    elif key_run > 20:
        sc += 1.0
    elif key_run > 10:
        sc += 0.4

    if key_ucr < 0.05:
        sc += 1.5
    elif key_ucr < 0.15:
        sc += 0.7

    if key_special > 0.2:
        sc += 0.8

    # 2. 列表规模与重复度
    dsl_len = feat.get("docStatusList_len", 0.0)
    dsl_rep = feat.get("docStatusList_repeat_ratio", 0.0)
    cidl_len = feat.get("categoryIdList_len", 0.0)
    cidl_rep = feat.get("categoryIdList_repeat_ratio", 0.0)

    if dsl_len >= 20:
        sc += 0.6
    elif dsl_len >= 10:
        sc += 0.2

    if cidl_len >= 20:
        sc += 0.6
    elif cidl_len >= 10:
        sc += 0.2

    if dsl_rep >= 0.95:
        sc += 1.2
    elif dsl_rep >= 0.7:
        sc += 0.5

    if cidl_rep >= 0.95:
        sc += 1.2
    elif cidl_rep >= 0.7:
        sc += 0.5

    # 3. 全局字符串异常
    max_run = feat.get("max_run_length_any_string", 0.0)
    min_ucr = feat.get("min_unique_char_ratio", 1.0)
    max_str_len = feat.get("max_string_len", 0.0)

    if max_run > 60:
        sc += 1.0
    elif max_run > 20:
        sc += 0.4

    if min_ucr < 0.05:
        sc += 0.8
    elif min_ucr < 0.15:
        sc += 0.3

    if max_str_len > 128:
        sc += 0.6
    elif max_str_len > 64:
        sc += 0.2

    # 4. 全局列表重复度
    max_list_rep = feat.get("max_list_repeat_ratio", 0.0)
    repeated_list_count = feat.get("repeated_list_count", 0.0)
    large_list_count = feat.get("large_list_count", 0.0)

    if max_list_rep >= 1.0:
        sc += 0.8
    elif max_list_rep >= 0.8:
        sc += 0.3

    if repeated_list_count >= 2:
        sc += 0.8
    elif repeated_list_count >= 1:
        sc += 0.3

    if large_list_count >= 2:
        sc += 0.4

    # 5. 组合异常
    if key_run > 20 and repeated_list_count >= 1:
        sc += 0.8
    if key_ucr < 0.05 and large_list_count >= 2:
        sc += 0.8

    return float(sc)


def main():
    if len(sys.argv) != 2:
        print("usage: python3 score_json_offline.py <json_file>")
        raise SystemExit(1)

    path = sys.argv[1]
    with open(path, "rb") as f:
        body = f.read()

    feat = extract_features_from_bytes(body)
    score = score_from_features(feat)

    print(json.dumps({
        "file": path,
        "score": score,
        "features": feat
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()