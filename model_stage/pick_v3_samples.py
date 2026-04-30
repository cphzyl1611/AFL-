#!/usr/bin/env python3
import json
from pathlib import Path

LOG_PATH = Path("/tmp/nv_score_log.jsonl")

def main():
    uniq = {}
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            body = rec.get("body", "")
            score = float(rec.get("score", 0.0))

            # 同 body 只保留一个，默认保留最低 ts 的第一条即可
            if body not in uniq:
                uniq[body] = {
                    "score": score,
                    "body_len": rec.get("body_len", 0),
                    "body": body,
                }

    items = list(uniq.values())
    items.sort(key=lambda x: x["score"])

    print(f"[OK] unique samples = {len(items)}")
    print()

    print("=== LOW SCORE (first 15) ===")
    for i, item in enumerate(items[:15], 1):
        print(f"[{i}] score={item['score']:.6f} len={item['body_len']}")
        print(item["body"])
        print()

    print("=== MID SCORE (middle 15) ===")
    if items:
        mid = len(items) // 2
        seg = items[max(0, mid - 7): min(len(items), mid + 8)]
        for i, item in enumerate(seg, 1):
            print(f"[{i}] score={item['score']:.6f} len={item['body_len']}")
            print(item["body"])
            print()

    print("=== HIGH SCORE (last 15) ===")
    for i, item in enumerate(items[-15:], 1):
        print(f"[{i}] score={item['score']:.6f} len={item['body_len']}")
        print(item["body"])
        print()

if __name__ == "__main__":
    main()