#!/usr/bin/env python3
import json
import random
from pathlib import Path
import os

ROOT = Path.home() / "AFLplusplus"
DATA_DIR = ROOT / "model_stage" / "data"

IN_FILE = DATA_DIR / "sefanogan_dataset.jsonl"
TRAIN_FILE = DATA_DIR / "sefanogan_train.jsonl"
VAL_FILE = DATA_DIR / "sefanogan_val.jsonl"

RANDOM_SEED = int(os.getenv("SEFANOGAN_SPLIT_SEED", "20260319"))


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    random.seed(RANDOM_SEED)
    rows = load_jsonl(IN_FILE)

    normal = [r for r in rows if r.get("tag") == "normal"]
    border = [r for r in rows if r.get("tag") == "border"]
    abnormal = [r for r in rows if r.get("tag") == "abnormal"]

    random.shuffle(normal)

    n_train = max(1, int(len(normal) * 0.7))
    train_rows = normal[:n_train]

    val_rows = normal[n_train:] + border + abnormal

    write_jsonl(TRAIN_FILE, train_rows)
    write_jsonl(VAL_FILE, val_rows)

    print(f"[OK] wrote {TRAIN_FILE} ({len(train_rows)} rows)")
    print(f"[OK] wrote {VAL_FILE} ({len(val_rows)} rows)")
    print(f"train_normal={len(train_rows)}")
    print(f"val_normal={len([r for r in val_rows if r['tag']=='normal'])}")
    print(f"val_border={len([r for r in val_rows if r['tag']=='border'])}")
    print(f"val_abnormal={len([r for r in val_rows if r['tag']=='abnormal'])}")


if __name__ == "__main__":
    main()