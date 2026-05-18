#!/usr/bin/env python3
"""Build Alfresco AE v1 engineering scorer metadata from local seeds.

This creates an AE-like statistical baseline using feature mean/std from valid
and boundary Alfresco seeds. It does not train a GAN/fAnoGAN model.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_stage.alfresco_feature_extractor import (  # noqa: E402
    extract_metadata_features,
    extract_multipart_upload_features,
    extract_text_content_features,
    feature_names,
)


METADATA_DIR = ROOT / "in" / "alfresco_metadata_update_dataset"
CONTENT_DIR = ROOT / "in" / "alfresco_content_update_dataset"
UPLOAD_DIR = ROOT / "in" / "alfresco_multipart_upload_dataset"
OUT_META = ROOT / "model_stage" / "models" / "alfresco_ae_v1_meta.json"


def is_bad_seed(path: Path) -> bool:
    return "bad" in path.stem


def load_training_vectors() -> tuple[list[list[float]], dict[str, int]]:
    vectors: list[list[float]] = []
    coverage = {
        "metadata_update": 0,
        "content_update": 0,
        "multipart_upload": 0,
    }

    for path in sorted(METADATA_DIR.glob("*.json")):
        if is_bad_seed(path):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        vectors.append(extract_metadata_features(payload))
        coverage["metadata_update"] += 1

    for path in sorted(CONTENT_DIR.glob("*.txt")):
        if is_bad_seed(path):
            continue
        vectors.append(extract_text_content_features(path.read_bytes()))
        coverage["content_update"] += 1

    for path in sorted(UPLOAD_DIR.glob("*.txt")):
        if is_bad_seed(path):
            continue
        body = path.read_bytes()
        fields = {"nodeType": "cm:content", "autoRename": "true"}
        vectors.append(extract_multipart_upload_features(f"train_{path.name}", body, fields))
        coverage["multipart_upload"] += 1

    return vectors, coverage


def column_stats(vectors: list[list[float]]) -> tuple[list[float], list[float]]:
    if not vectors:
        raise RuntimeError("no valid Alfresco AE v1 training vectors found")

    width = len(vectors[0])
    for vector in vectors:
        if len(vector) != width:
            raise RuntimeError("inconsistent feature vector width")

    means: list[float] = []
    stds: list[float] = []
    for column in range(width):
        values = [vector[column] for vector in vectors]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = math.sqrt(variance)
        means.append(mean)
        stds.append(std if std > 1e-6 else 1.0)
    return means, stds


def score_vector(vector: list[float], mean: list[float], std: list[float]) -> float:
    z_values = [(value - mu) / sigma for value, mu, sigma in zip(vector, mean, std)]
    return math.sqrt(sum(value * value for value in z_values) / len(z_values))


def build_meta() -> dict[str, Any]:
    vectors, coverage = load_training_vectors()
    names = feature_names()
    mean, std = column_stats(vectors)
    train_scores = [score_vector(vector, mean, std) for vector in vectors]
    max_score = max(train_scores) if train_scores else 0.0
    score_median = median(train_scores) if train_scores else 0.0
    score_mean = sum(train_scores) / len(train_scores) if train_scores else 0.0
    score_std = math.sqrt(sum((score - score_mean) ** 2 for score in train_scores) / len(train_scores)) if train_scores else 0.0
    threshold_low = round(max(score_median, 0.05), 6)
    threshold_high = round(max(max_score + max(score_std, 0.5), 1.0), 6)

    return {
        "model_name": "alfresco_ae_v1",
        "model_type": "ae_like_statistical_baseline",
        "feature_names": names,
        "mean": [round(value, 8) for value in mean],
        "std": [round(value, 8) for value in std],
        "threshold_low": threshold_low,
        "threshold_high": threshold_high,
        "train_sample_count": len(vectors),
        "scenario_coverage": coverage,
        "train_score_stats": {
            "min": round(min(train_scores), 6) if train_scores else 0.0,
            "median": round(score_median, 6),
            "max": round(max_score, 6),
            "mean": round(score_mean, 6),
            "std": round(score_std, 6),
        },
        "score_formula": "root_mean_square_z_distance",
        "notes": [
            "Engineering AE v1 scorer for Alfresco validity scoring.",
            "Uses feature mean/std from valid and boundary local seeds.",
            "Not GAN or fAnoGAN.",
            "Not native O2OA document API coverage.",
        ],
    }


def main() -> int:
    meta = build_meta()
    OUT_META.parent.mkdir(parents=True, exist_ok=True)
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] Wrote {OUT_META}")
    print(f"[OK] train_sample_count={meta['train_sample_count']}")
    print(f"[OK] threshold_high={meta['threshold_high']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
