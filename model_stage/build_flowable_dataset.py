#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path.home() / "AFLplusplus"
IN_DIR = ROOT / "in" / "flowable_process_start_dataset"
MANIFEST = ROOT / "model_stage" / "manifests" / "flowable_manifest_50.txt"
OUT_DIR = ROOT / "model_stage" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "flowable_dataset.jsonl"

rows = []
for line in MANIFEST.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    fname, tag = [x.strip() for x in line.split(",")]
    body = json.loads((IN_DIR / fname).read_text(encoding="utf-8"))
    rows.append({
        "endpoint": "process_start",
        "source_file": fname,
        "tag": tag,
        "body": body
    })

with OUT_FILE.open("w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print(f"[OK] wrote {OUT_FILE} ({len(rows)} rows)")
