#!/usr/bin/env python3
import json
from pathlib import Path

LOG_PATH = Path("/tmp/nv_score_log_ae_round2.jsonl")

def load_unique():
    uniq = {}
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            body = rec.get("body", "")
            score = float(rec.get("score", 0.0))
            if body not in uniq:
                uniq[body] = {
                    "score": score,
                    "body_len": rec.get("body_len", 0),
                    "body": body,
                }
    items = list(uniq.values())
    items.sort(key=lambda x: x["score"])
    return items

def show_bucket(title, items):
    print(f"=== {title} ===")
    for i, item in enumerate(items, 1):
        print(f"[{i}] score={item['score']:.6f} len={item['body_len']}")
        print(item["body"])
        print()

def main():
    items = load_unique()
    print(f"[OK] unique samples = {len(items)}")
    print()

    border_low = [x for x in items if 0.2 <= x["score"] < 2]
    abnormal_mid = [x for x in items if 2 <= x["score"] < 20]
    abnormal_high = [x for x in items if x["score"] >= 20]

    show_bucket("BORDER CANDIDATES (0.2 ~ 2)", border_low[:20])
    show_bucket("ABNORMAL MID (2 ~ 20)", abnormal_mid[:20])
    show_bucket("ABNORMAL HIGH (20+)", abnormal_high[:20])

if __name__ == "__main__":
    main()