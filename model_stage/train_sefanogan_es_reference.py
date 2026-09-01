#!/usr/bin/env python3
"""Reproducible offline trainer for the project SE-fAnoGAN-ES reference."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_stage.alfresco_fanogan_v1_candidate import load_valid_training_vectors
from model_stage.sefanogan_es_reference import (
    ALPHA,
    BETA,
    HIDDEN_DIM,
    INPUT_DIM,
    LAMBDA_GP,
    LATENT_DIM,
    N_CRITIC,
    ChannelAttentionEncoder,
    Discriminator,
    Generator,
    anomaly_score,
    save_checkpoint,
    seed_everything,
    train_wgan_step,
)


def manifest_for_training(sample_count: int, coverage: dict[str, int]) -> tuple[dict, str]:
    from scripts.run_alfresco_ae_v1_threshold_sweep import CONTENT_DIR, METADATA_DIR, UPLOAD_DIR

    source_dirs = [METADATA_DIR, CONTENT_DIR, UPLOAD_DIR]
    source_hashes = {}
    for directory in source_dirs:
        for path in sorted(directory.glob("*")):
            if path.is_file():
                source_hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "role": "normal_only_training",
        "source": "load_valid_training_vectors",
        "source_paths": [str(path) for path in source_dirs],
        "source_file_sha256": source_hashes,
        "sample_count": sample_count,
        "scenario_coverage": coverage,
        "representation": "alfresco_fixed_32",
        "raw_samples_in_manifest": False,
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return manifest, hashlib.sha256(encoded).hexdigest()


def train(args: argparse.Namespace) -> dict:
    seed_everything(args.seed)
    vectors = load_valid_training_vectors()
    if len(vectors.vectors[0]) != INPUT_DIM:
        raise ValueError("approved Alfresco feature contract is not 32-dimensional")
    x = torch.tensor(vectors.vectors, dtype=torch.float32)
    mean = x.mean(dim=0)
    std = x.std(dim=0, unbiased=False).clamp_min(1e-8)
    x = (x - mean) / std

    generator = Generator(LATENT_DIM, INPUT_DIM, HIDDEN_DIM)
    discriminator = Discriminator(INPUT_DIM, HIDDEN_DIM)
    encoder = ChannelAttentionEncoder(INPUT_DIM, LATENT_DIM, HIDDEN_DIM)
    g_optimizer = torch.optim.Adam(generator.parameters(), lr=args.learning_rate)
    d_optimizer = torch.optim.Adam(discriminator.parameters(), lr=args.learning_rate)

    for _ in range(args.epochs_gan):
        train_wgan_step(generator, discriminator, g_optimizer, d_optimizer, x, N_CRITIC, LATENT_DIM, LAMBDA_GP)
    for parameter in discriminator.parameters():
        parameter.requires_grad_(False)
    for parameter in generator.parameters():
        parameter.requires_grad_(False)
    e_optimizer = torch.optim.Adam(encoder.parameters(), lr=args.learning_rate)
    for _ in range(args.epochs_encoder):
        latent = encoder(x)
        reconstruction = generator(latent)
        _, real_features = discriminator(x)
        _, reconstruction_features = discriminator(reconstruction)
        loss = ALPHA * ((reconstruction - x) ** 2).mean() + BETA * ((reconstruction_features - real_features) ** 2).mean()
        e_optimizer.zero_grad(set_to_none=True)
        loss.backward()
        e_optimizer.step()

    manifest, manifest_hash = manifest_for_training(len(vectors.vectors), vectors.scenario_coverage)
    output_dir = Path(args.output_dir)
    checkpoint = output_dir / "sefanogan_es_reference.pt"
    metadata = output_dir / "sefanogan_es_reference.json"
    extra = {
        "gan_epochs": args.epochs_gan,
        "encoder_epochs": args.epochs_encoder,
        "seed": args.seed,
        "training_manifest_sha256": manifest_hash,
        "training_manifest": manifest,
        "normalization_mean": mean.tolist(),
        "normalization_std": std.tolist(),
        "score_formula": "0.75*sqrt(reconstruction_mse)+0.25*sqrt(discriminator_feature_mse)",
    }
    result = save_checkpoint(checkpoint, metadata, generator, discriminator, encoder, extra)
    result["checkpoint_path"] = str(checkpoint)
    result["metadata_path"] = str(metadata)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260519)
    parser.add_argument("--epochs-gan", type=int, default=20)
    parser.add_argument("--epochs-encoder", type=int, default=20)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    args = parser.parse_args()
    result = train(args)
    print(json.dumps({"model_family": result["model_family"], "checkpoint_path": result["checkpoint_path"], "metadata_path": result["metadata_path"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
