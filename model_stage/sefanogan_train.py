#!/usr/bin/env python3
import csv
import json
import math
from pathlib import Path
from statistics import mean, pstdev

from feature_extract import FEATURE_ORDER


ROOT = Path.home() / "AFLplusplus"
DATA_DIR = ROOT / "model_stage" / "data"
MODEL_DIR = ROOT / "model_stage" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

IN_CSV = DATA_DIR / "sefanogan_features.csv"
OUT_MODEL = MODEL_DIR / "sefanogan_placeholder_model.json"


def load_rows():
    rows = []
    with open(IN_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item = {
                "endpoint": row["endpoint"],
                "source_file": row["source_file"],
                "tag": row["tag"],
            }
            for k in FEATURE_ORDER:
                item[k] = float(row[k])
            rows.append(item)
    return rows


def vectorize(row):
    return [float(row[k]) for k in FEATURE_ORDER]


def transpose(matrix):
    if not matrix:
        return []
    return list(map(list, zip(*matrix)))


def train_placeholder_model(rows):
    normal_rows = [r for r in rows if r["tag"] == "normal"]
    if not normal_rows:
        raise ValueError("no normal rows found in dataset")

    normal_vecs = [vectorize(r) for r in normal_rows]
    cols = transpose(normal_vecs)

    means = [mean(col) for col in cols]
    stds = []
    for col in cols:
        s = pstdev(col) if len(col) > 1 else 0.0
        if s < 1e-6:
            s = 1.0
        stds.append(s)

    norm_vecs = []
    for vec in normal_vecs:
        z = [(vec[i] - means[i]) / stds[i] for i in range(len(vec))]
        norm_vecs.append(z)

    center_cols = transpose(norm_vecs)
    center = [mean(col) for col in center_cols]

    # 训练集正常样本距离，用于给后续阈值感知
    normal_dists = []
    for z in norm_vecs:
        d = math.sqrt(sum((z[i] - center[i]) ** 2 for i in range(len(z))))
        normal_dists.append(d)

    model = {
        "model_type": "placeholder_center_distance",
        "feature_order": FEATURE_ORDER,
        "train_count": len(rows),
        "normal_count": len(normal_rows),
        "means": means,
        "stds": stds,
        "center": center,
        "normal_dist_mean": mean(normal_dists) if normal_dists else 0.0,
        "normal_dist_min": min(normal_dists) if normal_dists else 0.0,
        "normal_dist_max": max(normal_dists) if normal_dists else 0.0,
    }
    return model


def main():
    rows = load_rows()
    model = train_placeholder_model(rows)

    with open(OUT_MODEL, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)

    print(f"[OK] wrote {OUT_MODEL}")
    print(f"train_count={model['train_count']}")
    print(f"normal_count={model['normal_count']}")
    print(f"normal_dist_mean={model['normal_dist_mean']:.6f}")
    print(f"normal_dist_min={model['normal_dist_min']:.6f}")
    print(f"normal_dist_max={model['normal_dist_max']:.6f}")


if __name__ == "__main__":
    main()