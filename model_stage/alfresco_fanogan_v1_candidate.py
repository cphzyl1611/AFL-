#!/usr/bin/env python3
"""Alfresco fAnoGAN v1 candidate training helpers.

This module intentionally keeps the fAnoGAN work at candidate level. If PyTorch
is unavailable, it builds a dependency-free GAN-style statistical candidate.
That fallback is useful for offline comparison with AE v1, but it is not a
production GAN/fAnoGAN or SE-fAnoGAN-ES implementation.
"""

from __future__ import annotations

import importlib.util
import json
import math
import random
import sys
from dataclasses import dataclass
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


DEFAULT_META_PATH = ROOT / "model_stage" / "models" / "alfresco_fanogan_v1_candidate_meta.json"
DEFAULT_WEIGHT_PATH = ROOT / "model_stage" / "models" / "alfresco_fanogan_v1_candidate.pt"
LATENT_DIM = 8


@dataclass(frozen=True)
class CandidateVectorSet:
    vectors: list[list[float]]
    scenario_coverage: dict[str, int]


def torch_available() -> bool:
    return importlib.util.find_spec("torch") is not None


def feature_vector_for_sample(sample: Any) -> list[float]:
    scenario = getattr(sample, "scenario")
    if scenario == "metadata_update":
        payload = getattr(sample, "payload")
        return extract_metadata_features(payload if isinstance(payload, dict) else {})
    if scenario == "content_update":
        return extract_text_content_features(getattr(sample, "content"))
    if scenario == "multipart_upload":
        content = getattr(sample, "content")
        filename = getattr(sample, "filename")
        fields = getattr(sample, "fields")
        return extract_multipart_upload_features(filename, content, fields)
    raise ValueError(f"unsupported scenario: {scenario}")


def load_valid_training_vectors() -> CandidateVectorSet:
    from scripts.run_alfresco_ae_v1_threshold_sweep import all_samples

    coverage = {
        "metadata_update": 0,
        "content_update": 0,
        "multipart_upload": 0,
    }
    vectors: list[list[float]] = []
    for sample in all_samples():
        if getattr(sample, "sample_origin") != "seed" or not getattr(sample, "expected_valid"):
            continue
        vector = feature_vector_for_sample(sample)
        vectors.append(vector)
        coverage[getattr(sample, "scenario")] += 1
    if not vectors:
        raise RuntimeError("no valid Alfresco training vectors found")
    return CandidateVectorSet(vectors=vectors, scenario_coverage=coverage)


def augment_vectors(vectors: list[list[float]], factor: int = 3, jitter_ratio: float = 0.025) -> list[list[float]]:
    """Create deterministic light jitter around normal vectors.

    The source seed set is intentionally small. This augmentation only helps
    estimate candidate score thresholds; it is not used as evidence of a full
    GAN training corpus.
    """

    rng = random.Random(20260519)
    augmented: list[list[float]] = []
    for vector in vectors:
        for _ in range(max(0, factor - 1)):
            jittered: list[float] = []
            for value in vector:
                scale = max(abs(float(value)), 1.0)
                jittered.append(float(value) + rng.uniform(-jitter_ratio, jitter_ratio) * scale)
            augmented.append(jittered)
    return augmented


def column_stats(vectors: list[list[float]]) -> tuple[list[float], list[float]]:
    if not vectors:
        raise RuntimeError("no vectors for column stats")
    width = len(vectors[0])
    for vector in vectors:
        if len(vector) != width:
            raise RuntimeError("inconsistent feature vector width")

    means: list[float] = []
    stds: list[float] = []
    for column in range(width):
        values = [float(vector[column]) for vector in vectors]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = math.sqrt(variance)
        means.append(mean)
        stds.append(std if std > 1e-6 else 1.0)
    return means, stds


def rms_z_distance(vector: list[float], mean: list[float], std: list[float]) -> float:
    z_values = [(float(value) - mu) / sigma for value, mu, sigma in zip(vector, mean, std)]
    return math.sqrt(sum(value * value for value in z_values) / len(z_values))


def nearest_normal_distance(vector: list[float], normal_vectors: list[list[float]], std: list[float]) -> float:
    best = float("inf")
    for normal in normal_vectors:
        total = 0.0
        for value, baseline, sigma in zip(vector, normal, std):
            delta = (float(value) - float(baseline)) / sigma
            total += delta * delta
        best = min(best, math.sqrt(total / len(vector)))
    return best if math.isfinite(best) else 0.0


def entropy_penalty(vector: list[float], entropy_baseline: float, entropy_scale: float) -> float:
    names = feature_names()
    try:
        entropy_value = float(vector[names.index("entropy")])
    except (ValueError, IndexError):
        return 0.0
    if entropy_value <= entropy_baseline:
        return 0.0
    return (entropy_value - entropy_baseline) / max(entropy_scale, 1.0)


def candidate_score(
    vector: list[float],
    mean: list[float],
    std: list[float],
    normal_vectors: list[list[float]],
    entropy_baseline: float,
    entropy_scale: float,
) -> float:
    reconstruction_like = rms_z_distance(vector, mean, std)
    density_like = nearest_normal_distance(vector, normal_vectors, std)
    entropy_like = entropy_penalty(vector, entropy_baseline, entropy_scale)
    return 0.55 * reconstruction_like + 0.35 * density_like + 0.10 * entropy_like


def build_statistical_candidate_meta() -> dict[str, Any]:
    vector_set = load_valid_training_vectors()
    base_vectors = vector_set.vectors
    augmented = augment_vectors(base_vectors)
    training_cloud = base_vectors + augmented
    names = feature_names()
    mean, std = column_stats(training_cloud)

    entropy_index = names.index("entropy")
    train_entropy_values = sorted(float(vector[entropy_index]) for vector in base_vectors)
    entropy_baseline = train_entropy_values[-1] if train_entropy_values else 0.0
    entropy_scale = max(entropy_baseline, 1.0)

    train_scores = [
        candidate_score(vector, mean, std, base_vectors, entropy_baseline, entropy_scale)
        for vector in training_cloud
    ]
    score_mean = sum(train_scores) / len(train_scores)
    score_std = math.sqrt(sum((score - score_mean) ** 2 for score in train_scores) / len(train_scores))
    max_score = max(train_scores)
    score_median = median(train_scores)
    threshold_low = round(max(score_median, 0.05), 6)
    threshold_high = round(max(max_score + max(score_std, 0.45), 1.0), 6)

    return {
        "model_name": "alfresco_fanogan_v1_candidate",
        "model_type": "gan_style_statistical_candidate",
        "torch_available": torch_available(),
        "feature_names": names,
        "feature_dim": len(names),
        "latent_dim": LATENT_DIM,
        "mean": [round(value, 8) for value in mean],
        "std": [round(value, 8) for value in std],
        "normal_vectors": [[round(float(value), 8) for value in vector] for vector in base_vectors],
        "entropy_baseline": round(entropy_baseline, 8),
        "entropy_scale": round(entropy_scale, 8),
        "train_sample_count": len(base_vectors),
        "augmentation_count": len(augmented),
        "threshold_low": threshold_low,
        "threshold_high": threshold_high,
        "train_score_stats": {
            "min": round(min(train_scores), 6),
            "median": round(score_median, 6),
            "max": round(max_score, 6),
            "mean": round(score_mean, 6),
            "std": round(score_std, 6),
        },
        "score_formula": "0.55*rms_z_distance + 0.35*nearest_normal_distance + 0.10*entropy_penalty",
        "scenario_coverage": vector_set.scenario_coverage,
        "boundary": [
            "candidate only",
            "not full SE-fAnoGAN-ES",
            "not production GAN model",
            "not a replacement for Alfresco AE v1",
        ],
        "notes": [
            "PyTorch is unavailable in this environment; built dependency-free GAN-style statistical candidate.",
            "Uses existing Alfresco fixed-length feature extractor and valid/border seed vectors.",
            "Synthetic invalid samples are used for comparison only, not for training.",
        ],
    }


def build_candidate_meta() -> dict[str, Any]:
    # Torch is intentionally not required. The current local environment does
    # not provide it, so the reliable path is the documented statistical
    # candidate fallback.
    return build_statistical_candidate_meta()


def write_candidate_meta(path: Path = DEFAULT_META_PATH) -> dict[str, Any]:
    meta = build_candidate_meta()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def main() -> int:
    meta = write_candidate_meta()
    print(f"[OK] Wrote {DEFAULT_META_PATH}")
    print(f"[OK] model_type={meta['model_type']}")
    print(f"[OK] train_sample_count={meta['train_sample_count']}")
    print(f"[OK] augmentation_count={meta['augmentation_count']}")
    print(f"[OK] threshold_high={meta['threshold_high']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
