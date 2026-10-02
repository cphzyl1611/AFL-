#!/usr/bin/env python3
"""Offline SE threshold calibration for real Alfresco metadata AE-vs-SE experiment.

Policy: MATCHED_OPERATING_CRITERION
Criterion: NORMAL_FALSE_REJECT_RATE

This script derives an SE threshold that matches the existing AE legacy threshold's
false-reject rate on a common frozen offline calibration population. It is fully
offline: no network, no real Alfresco, no AFL++, no model training.

The calibration population and threshold selection rule are frozen before any
real-service pilot run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from model_stage.alfresco_ae_v1_scorer import AlfrescoAEV1Scorer  # noqa: E402
from model_stage.sefanogan_es_reference import ReferenceScorer  # noqa: E402
from model_stage.alfresco_feature_extractor import extract_metadata_features  # noqa: E402


# Frozen policy constants
AE_LEGACY_THRESHOLD_HIGH = 1.623614
EXPECTED_CALIBRATION_MANIFEST_HASH = "66f030011b79c05fa73e4f397d1524ae81f5b70a48814130eb4a44ba2c9ac5b8"
SCHEMA_VERSION = 1


def validate_calibration_source(source_path: str) -> None:
    """Refuse any real_run/pilot/A-B evidence directory as calibration source."""
    forbidden = ["real_run", "pilot", "a_b_test", "ab_test", "production", "live"]
    lower_path = source_path.lower()
    for pattern in forbidden:
        if pattern in lower_path:
            raise ValueError(f"calibration source must not use real/pilot/A-B evidence: {source_path}")


def calibrate_threshold(
    ae_scores: list[float],
    se_scores: list[float],
    sample_ids: list[str],
    ae_threshold: float,
) -> dict[str, Any]:
    """Core threshold calibration logic.

    Selects SE threshold to match AE's false-reject rate on normal samples.

    Args:
        ae_scores: AE scores for normal calibration samples
        se_scores: SE scores for the exact same samples (same order)
        sample_ids: Sample identifiers (for verification)
        ae_threshold: The AE legacy threshold (1.623614)

    Returns:
        Calibration result with selected SE threshold and achieved FRRs
    """
    # Validation: empty population
    if not ae_scores or not se_scores or not sample_ids:
        raise ValueError("calibration population cannot be empty")

    # Validation: length mismatch
    if not (len(ae_scores) == len(se_scores) == len(sample_ids)):
        raise ValueError(f"sample count mismatch: AE={len(ae_scores)}, SE={len(se_scores)}, IDs={len(sample_ids)}")

    # Validation: duplicate sample IDs
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("duplicate sample IDs in calibration population")

    # Validation: non-finite scores
    if not all(math.isfinite(score) for score in ae_scores):
        raise ValueError("non-finite AE scores in calibration population")
    if not all(math.isfinite(score) for score in se_scores):
        raise ValueError("non-finite SE scores in calibration population")

    # Compute AE false-reject rate
    ae_rejects = sum(1 for score in ae_scores if score >= ae_threshold)
    ae_frr = ae_rejects / len(ae_scores)

    # Find SE threshold that minimizes |SE_FRR - AE_FRR|
    # Candidate thresholds: all unique SE scores plus min-epsilon and max+epsilon
    unique_se = sorted(set(se_scores))
    candidates = [min(se_scores) - 0.001] + unique_se + [max(se_scores) + 0.001]

    best_threshold = None
    best_frr = None
    best_mismatch = float('inf')

    for candidate in candidates:
        se_rejects = sum(1 for score in se_scores if score >= candidate)
        se_frr = se_rejects / len(se_scores)
        mismatch = abs(se_frr - ae_frr)

        if mismatch < best_mismatch:
            best_mismatch = mismatch
            best_threshold = candidate
            best_frr = se_frr
        elif mismatch == best_mismatch:
            # Tie-break: prefer MORE CONSERVATIVE threshold (higher = more restrictive)
            # Higher score means more anomalous for both AE and SE
            if candidate > best_threshold:
                best_threshold = candidate
                best_frr = se_frr

    return {
        "ae_threshold": ae_threshold,
        "ae_frr": ae_frr,
        "se_threshold": best_threshold,
        "se_frr": best_frr,
        "frr_absolute_mismatch": best_mismatch,
        "calibration_sample_count": len(sample_ids),
    }


def load_calibration_population(
    manifest_path: Path,
    ae_scorer: AlfrescoAEV1Scorer,
    se_scorer: ReferenceScorer,
) -> tuple[list[float], list[float], list[str], str]:
    """Load and score the frozen calibration population.

    Returns:
        (ae_scores, se_scores, sample_ids, manifest_hash)
    """
    if not manifest_path.is_file():
        raise FileNotFoundError(f"calibration manifest not found: {manifest_path}")

    # Verify manifest hash
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if manifest_hash != EXPECTED_CALIBRATION_MANIFEST_HASH:
        raise ValueError(
            f"calibration manifest hash mismatch: expected {EXPECTED_CALIBRATION_MANIFEST_HASH}, "
            f"got {manifest_hash}"
        )

    # Load manifest entries
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Filter to metadata_update valid/normal samples only
    metadata_normal = [
        e for e in entries
        if e["scenario"] == "metadata_update"
        and e["sample_type"] == "valid"
        and e["expected_valid"]
    ]

    if len(metadata_normal) < 10:
        raise ValueError(f"insufficient normal metadata samples: {len(metadata_normal)} < 10")

    # Score all samples with both backends
    ae_scores = []
    se_scores = []
    sample_ids = []

    dataset_dir = manifest_path.parent

    for entry in metadata_normal:
        sample_path = dataset_dir / entry["file"]
        if not sample_path.is_file():
            raise FileNotFoundError(f"calibration sample missing: {sample_path}")

        # Load and extract features
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
        features = extract_metadata_features(payload)

        # Score with AE
        ae_score = ae_scorer.score_vector(features)

        # Score with SE
        se_score = se_scorer.score(features)

        ae_scores.append(ae_score)
        se_scores.append(se_score)
        sample_ids.append(entry["file"])

    return ae_scores, se_scores, sample_ids, manifest_hash


def generate_threshold_artifact(
    result: dict[str, Any],
    manifest_hash: str,
    sample_ids: list[str],
    ae_backend: str,
    se_backend: str,
    se_checkpoint_path: Path,
    se_metadata_path: Path,
) -> dict[str, Any]:
    """Generate the immutable threshold artifact JSON."""

    # Compute SE checkpoint and metadata hashes
    se_checkpoint_hash = hashlib.sha256(se_checkpoint_path.read_bytes()).hexdigest()
    se_metadata_hash = hashlib.sha256(se_metadata_path.read_bytes()).hexdigest()

    # Compute sample commitment hash
    sample_commitment = "\n".join(sorted(sample_ids)).encode("utf-8")
    sample_id_commitment_hash = hashlib.sha256(sample_commitment).hexdigest()

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "offline_threshold_calibration_for_real_alfresco_metadata_ae_vs_se",
        "policy": "MATCHED_OPERATING_CRITERION",
        "criterion": "NORMAL_FALSE_REJECT_RATE",
        "calibration_manifest_hash": manifest_hash,
        "calibration_sample_count": result["calibration_sample_count"],
        "sample_id_commitment": sample_id_commitment_hash,
        "ae_backend": ae_backend,
        "ae_threshold_source": "alfresco_ae_v1_meta.json::threshold_high",
        "ae_threshold": result["ae_threshold"],
        "ae_frr": result["ae_frr"],
        "se_backend": se_backend,
        "se_checkpoint_hash": se_checkpoint_hash,
        "se_metadata_hash": se_metadata_hash,
        "se_threshold": result["se_threshold"],
        "se_frr": result["se_frr"],
        "frr_absolute_mismatch": result["frr_absolute_mismatch"],
        "score_direction": "higher_score_means_more_anomalous_for_both_backends",
        "selection_rule": "minimize_abs_diff_between_ae_frr_and_se_frr",
        "tie_break_rule": "prefer_higher_threshold_more_conservative",
        "created_by": "scripts/calibrate_se_realrun_threshold.py",
        "frozen_before_real_pilot": True,
        "network_used": False,
        "real_alfresco_used": False,
        "afl_run_executed": False,
    }

    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calibrate SE threshold to match AE FRR on frozen offline population"
    )
    parser.add_argument(
        "--calibration-manifest",
        type=Path,
        default=ROOT / "in/alfresco_extended_eval_dataset/manifest.json",
        help="Path to frozen calibration manifest",
    )
    parser.add_argument(
        "--se-checkpoint",
        type=Path,
        default=Path("/home/dministrator/alfresco-audit-artifacts/sefanogan-es-round3-20260901-/training_runs/seed-20260519/sefanogan_es_reference.pt"),
        help="Path to frozen SE reference checkpoint",
    )
    parser.add_argument(
        "--se-metadata",
        type=Path,
        default=Path("/home/dministrator/alfresco-audit-artifacts/sefanogan-es-round3-20260901-/training_runs/seed-20260519/sefanogan_es_reference.json"),
        help="Path to frozen SE reference metadata",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "model_stage/models/sefanogan_es_realrun_threshold.json",
        help="Output path for threshold artifact",
    )
    args = parser.parse_args()

    # Validate sources
    validate_calibration_source(str(args.calibration_manifest))

    # Load scorers
    print("Loading AE scorer...", file=sys.stderr)
    ae_scorer = AlfrescoAEV1Scorer()

    print("Loading SE reference scorer...", file=sys.stderr)
    if not args.se_checkpoint.is_file() or not args.se_metadata.is_file():
        raise FileNotFoundError(f"SE reference artifacts unavailable: {args.se_checkpoint}, {args.se_metadata}")
    se_scorer = ReferenceScorer(args.se_checkpoint, args.se_metadata)

    # Load and score calibration population
    print("Loading calibration population...", file=sys.stderr)
    ae_scores, se_scores, sample_ids, manifest_hash = load_calibration_population(
        args.calibration_manifest, ae_scorer, se_scorer
    )

    print(f"Calibration population: {len(sample_ids)} metadata normal samples", file=sys.stderr)

    # Calibrate threshold
    print("Calibrating SE threshold to match AE FRR...", file=sys.stderr)
    result = calibrate_threshold(ae_scores, se_scores, sample_ids, AE_LEGACY_THRESHOLD_HIGH)

    print(f"AE FRR: {result['ae_frr']:.4f}", file=sys.stderr)
    print(f"SE threshold: {result['se_threshold']:.6f}", file=sys.stderr)
    print(f"SE FRR: {result['se_frr']:.4f}", file=sys.stderr)
    print(f"FRR mismatch: {result['frr_absolute_mismatch']:.4f}", file=sys.stderr)

    # Generate artifact
    artifact = generate_threshold_artifact(
        result,
        manifest_hash,
        sample_ids,
        "alfresco_ae_v1",
        "sefanogan_es_reference",
        args.se_checkpoint,
        args.se_metadata,
    )

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    artifact_hash = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(f"\nThreshold artifact written: {args.output}", file=sys.stderr)
    print(f"Artifact SHA256: {artifact_hash}", file=sys.stderr)

    # Print summary to stdout (for capture)
    print(json.dumps({
        "se_threshold": result["se_threshold"],
        "ae_frr": result["ae_frr"],
        "se_frr": result["se_frr"],
        "artifact_path": str(args.output),
        "artifact_hash": artifact_hash,
    }))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
