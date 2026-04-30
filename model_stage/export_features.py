#!/usr/bin/env python3
import csv
import json
from pathlib import Path
from collections import defaultdict
from statistics import mean

from feature_extract import extract_features_from_obj, FEATURE_ORDER


ROOT = Path.home() / "AFLplusplus"
DATA_DIR = ROOT / "model_stage" / "data"
IN_FILE = DATA_DIR / "sefanogan_dataset.jsonl"
OUT_CSV = DATA_DIR / "sefanogan_features.csv"
OUT_SUMMARY = DATA_DIR / "sefanogan_features_summary.json"


def main():
    rows = []
    grouped = defaultdict(list)

    with open(IN_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)

            endpoint = rec["endpoint"]
            source_file = rec["source_file"]
            tag = rec["tag"]
            body = rec["body"]

            body_bytes = len(
                json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            )
            feat = extract_features_from_obj(body, body_bytes=body_bytes)

            row = {
                "endpoint": endpoint,
                "source_file": source_file,
                "tag": tag,
            }
            for k in FEATURE_ORDER:
                row[k] = feat.get(k, 0.0)

            rows.append(row)
            grouped[tag].append(feat)

    # 写 CSV
    fieldnames = ["endpoint", "source_file", "tag"] + FEATURE_ORDER
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)

    # 写 summary
    summary = {}
    for tag, feats in grouped.items():
        tag_summary = {}
        for k in FEATURE_ORDER:
            vals = [float(feat.get(k, 0.0)) for feat in feats]
            tag_summary[k] = {
                "mean": mean(vals) if vals else 0.0,
                "min": min(vals) if vals else 0.0,
                "max": max(vals) if vals else 0.0,
            }
        summary[tag] = {
            "count": len(feats),
            "features": tag_summary,
        }

    with open(OUT_SUMMARY, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[OK] wrote {OUT_CSV} ({len(rows)} rows)")
    print(f"[OK] wrote {OUT_SUMMARY}")


if __name__ == "__main__":
    main()