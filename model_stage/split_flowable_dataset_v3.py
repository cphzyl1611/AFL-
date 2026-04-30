#!/usr/bin/env python3
import json
import random
from pathlib import Path

random.seed(1234)

ROOT = Path.home() / "AFLplusplus"
DATA_DIR = ROOT / "model_stage" / "data"
IN_FILE = DATA_DIR / "flowable_dataset_v3.jsonl"
TRAIN_FILE = DATA_DIR / "flowable_train_v3.jsonl"
VAL_FILE = DATA_DIR / "flowable_val_v3.jsonl"

rows = [json.loads(x) for x in IN_FILE.read_text(encoding="utf-8").splitlines() if x.strip()]

normal = [r for r in rows if r["tag"] == "normal"]
border = [r for r in rows if r["tag"] == "border"]
abnormal = [r for r in rows if r["tag"] == "abnormal"]

random.shuffle(normal)
n_train = int(len(normal) * 0.7)
train_rows = normal[:n_train]
val_rows = normal[n_train:] + border + abnormal

with TRAIN_FILE.open("w", encoding="utf-8") as f:
    for r in train_rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

with VAL_FILE.open("w", encoding="utf-8") as f:
    for r in val_rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"[OK] wrote {TRAIN_FILE} ({len(train_rows)} rows)")
print(f"[OK] wrote {VAL_FILE} ({len(val_rows)} rows)")
print(f"train_normal={len(train_rows)}")
print(f"val_normal={sum(1 for r in val_rows if r['tag']=='normal')}")
print(f"val_border={sum(1 for r in val_rows if r['tag']=='border')}")
print(f"val_abnormal={sum(1 for r in val_rows if r['tag']=='abnormal')}")
