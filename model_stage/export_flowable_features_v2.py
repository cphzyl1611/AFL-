#!/usr/bin/env python3
import csv
import json
from pathlib import Path
import sys

ROOT = Path.home() / "AFLplusplus"
DATA_DIR = ROOT / "model_stage" / "data"
IN_FILE = DATA_DIR / "flowable_dataset_v2.jsonl"
OUT_FILE = DATA_DIR / "flowable_features_v2.csv"
SUMMARY_FILE = DATA_DIR / "flowable_features_v2_summary.json"

sys.path.insert(0, str(ROOT / "model_stage"))
from feature_extract import extract_features_from_bytes

rows = []
with IN_FILE.open("r", encoding="utf-8") as f:
    for raw in f:
        row = json.loads(raw)
        body_bytes = json.dumps(row["body"], ensure_ascii=False).encode("utf-8")
        feat = extract_features_from_bytes(body_bytes)
        feat["endpoint"] = row["endpoint"]
        feat["source_file"] = row["source_file"]
        feat["tag"] = row["tag"]
        rows.append(feat)

fieldnames = list(rows[0].keys())
with OUT_FILE.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

summary = {"rows": len(rows), "tags": {}}
for r in rows:
    summary["tags"][r["tag"]] = summary["tags"].get(r["tag"], 0) + 1

SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"[OK] wrote {OUT_FILE} ({len(rows)} rows)")
print(f"[OK] wrote {SUMMARY_FILE}")
