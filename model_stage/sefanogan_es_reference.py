#!/usr/bin/env python3
"""Project-canonical SE-fAnoGAN-ES reference contract.

This is a reproducible project reference, not a claim to exactly reproduce the
underspecified original design documents. G and D are the existing prototype
implementations; E adds attention over semantic feature channels.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from model_stage.sefanogan_train_gan import Discriminator, Generator

# The existing discriminator has no output activation; expose that invariant
# explicitly in the canonical API without creating a second critic family.
if not hasattr(Discriminator, "output_activation"):
    Discriminator.output_activation = None


MODEL_FAMILY = "se_fanogan_es_reference"
SCHEMA_VERSION = 1
INPUT_DIM = 32
LATENT_DIM = 8
HIDDEN_DIM = 64
LAMBDA_GP = 10.0
N_CRITIC = 5
ALPHA = 0.75
BETA = 0.25


class ChannelAttentionEncoder(nn.Module):
    """Encode a fixed semantic feature vector with channel-wise gating."""

    def __init__(self, input_dim: int, latent_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.attention = nn.Sequential(
            nn.Linear(input_dim, max(1, input_dim // 4)),
            nn.ReLU(),
            nn.Linear(max(1, input_dim // 4), input_dim),
            nn.Sigmoid(),
        )
        self.projection = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, latent_dim),
        )

    def forward(self, x: torch.Tensor, return_attention: bool = False) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        weights = self.attention(x)
        latent = self.projection(x * weights)
        return (latent, weights) if return_attention else latent


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def _critic_value(critic: nn.Module, x: torch.Tensor) -> torch.Tensor:
    result = critic(x)
    return result[0] if isinstance(result, tuple) else result


def gradient_penalty(critic: nn.Module, real: torch.Tensor, fake: torch.Tensor) -> torch.Tensor:
    epsilon = torch.rand(real.size(0), 1, device=real.device)
    epsilon = epsilon.expand_as(real)
    interpolated = (epsilon * real + (1.0 - epsilon) * fake).requires_grad_(True)
    values = _critic_value(critic, interpolated)
    gradients = torch.autograd.grad(
        outputs=values,
        inputs=interpolated,
        grad_outputs=torch.ones_like(values),
        create_graph=True,
        retain_graph=True,
        only_inputs=True,
    )[0]
    norms = gradients.reshape(gradients.size(0), -1).norm(2, dim=1)
    return ((norms - 1.0) ** 2).mean()


def train_wgan_step(
    generator: Generator,
    critic: Discriminator,
    generator_optimizer: torch.optim.Optimizer,
    critic_optimizer: torch.optim.Optimizer,
    real: torch.Tensor,
    n_critic: int = N_CRITIC,
    latent_dim: int = LATENT_DIM,
    lambda_gp: float = LAMBDA_GP,
) -> dict[str, float]:
    critic_loss_value = 0.0
    for _ in range(n_critic):
        z = torch.randn(real.size(0), latent_dim, device=real.device)
        fake = generator(z).detach()
        critic_loss = (
            _critic_value(critic, fake).mean()
            - _critic_value(critic, real).mean()
            + lambda_gp * gradient_penalty(critic, real, fake)
        )
        critic_optimizer.zero_grad(set_to_none=True)
        critic_loss.backward()
        critic_optimizer.step()
        critic_loss_value = float(critic_loss.detach())

    z = torch.randn(real.size(0), latent_dim, device=real.device)
    generator_loss = -_critic_value(critic, generator(z)).mean()
    generator_optimizer.zero_grad(set_to_none=True)
    generator_loss.backward()
    generator_optimizer.step()
    values = {"critic_loss": critic_loss_value, "generator_loss": float(generator_loss.detach())}
    if not all(np.isfinite(value) for value in values.values()):
        raise FloatingPointError("non-finite WGAN training step")
    return values


@torch.no_grad()
def anomaly_score(encoder: ChannelAttentionEncoder, generator: Generator, critic: Discriminator, x: torch.Tensor) -> torch.Tensor:
    latent = encoder(x)
    reconstruction = generator(latent)
    _, real_features = critic(x)
    _, reconstruction_features = critic(reconstruction)
    reconstruction_error = ((x - reconstruction) ** 2).mean(dim=1)
    feature_error = ((real_features - reconstruction_features) ** 2).mean(dim=1)
    score = ALPHA * torch.sqrt(reconstruction_error + 1e-8) + BETA * torch.sqrt(feature_error + 1e-8)
    if not torch.isfinite(score).all():
        raise FloatingPointError("non-finite anomaly score")
    return score


def _checkpoint_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_checkpoint(
    checkpoint_path: Path,
    metadata_path: Path,
    generator: Generator,
    critic: Discriminator,
    encoder: ChannelAttentionEncoder,
    metadata_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"generator": generator.state_dict(), "discriminator": critic.state_dict(), "encoder": encoder.state_dict()},
        checkpoint_path,
    )
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "model_family": MODEL_FAMILY,
        "input_dim": int(generator.net[-1].out_features),
        "latent_dim": int(generator.net[0].in_features),
        "hidden_dims": [int(generator.net[0].out_features)],
        "attention_type": "feature_channel_squeeze_gating",
        "wgan_mode": "wgan_gp",
        "lambda_gp": LAMBDA_GP,
        "n_critic": N_CRITIC,
        "gan_epochs": 0,
        "encoder_epochs": 0,
        "seed": 0,
        "feature_contract": {"name": "alfresco_fixed_32", "representation": "fixed_32_dimensional_feature_vector"},
        "training_manifest_sha256": "",
        "checkpoint_sha256": _checkpoint_hash(checkpoint_path),
        "created_for": "reference_evaluation",
        "production_primary": False,
    }
    metadata.update(metadata_extra or {})
    metadata["checkpoint_sha256"] = _checkpoint_hash(checkpoint_path)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata


def _validate_metadata(metadata: dict[str, Any], checkpoint_path: Path) -> None:
    required = {
        "schema_version", "model_family", "input_dim", "latent_dim", "hidden_dims",
        "attention_type", "wgan_mode", "lambda_gp", "n_critic", "gan_epochs",
        "encoder_epochs", "seed", "feature_contract", "training_manifest_sha256",
        "checkpoint_sha256", "created_for", "production_primary",
    }
    missing = sorted(required - metadata.keys())
    if missing:
        raise ValueError(f"reference metadata missing keys: {missing}")
    if metadata["model_family"] != MODEL_FAMILY or int(metadata["input_dim"]) != INPUT_DIM:
        raise ValueError("unsupported reference model metadata")
    if metadata["checkpoint_sha256"] != _checkpoint_hash(checkpoint_path):
        raise ValueError("checkpoint hash mismatch")


class ReferenceScorer:
    def __init__(self, checkpoint_path: str | Path, metadata_path: str | Path) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.metadata_path = Path(metadata_path)
        if not self.checkpoint_path.is_file() or not self.metadata_path.is_file():
            raise FileNotFoundError("reference checkpoint or metadata is missing")
        self.metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        _validate_metadata(self.metadata, self.checkpoint_path)
        self.input_dim = int(self.metadata["input_dim"])
        hidden_dim = int(self.metadata["hidden_dims"][0])
        self.generator = Generator(int(self.metadata["latent_dim"]), self.input_dim, hidden_dim)
        self.discriminator = Discriminator(self.input_dim, hidden_dim)
        self.encoder = ChannelAttentionEncoder(self.input_dim, int(self.metadata["latent_dim"]), hidden_dim)
        state = torch.load(self.checkpoint_path, map_location="cpu", weights_only=True)
        try:
            self.generator.load_state_dict(state["generator"])
            self.discriminator.load_state_dict(state["discriminator"])
            self.encoder.load_state_dict(state["encoder"])
        except (KeyError, RuntimeError) as exc:
            raise ValueError("invalid reference checkpoint") from exc
        self.generator.eval()
        self.discriminator.eval()
        self.encoder.eval()
        self.mean = [float(value) for value in self.metadata.get("normalization_mean", [0.0] * self.input_dim)]
        self.std = [max(abs(float(value)), 1e-8) for value in self.metadata.get("normalization_std", [1.0] * self.input_dim)]
        if len(self.mean) != self.input_dim or len(self.std) != self.input_dim:
            raise ValueError("reference normalization dimension mismatch")

    def score(self, vector: list[float]) -> float:
        if len(vector) != self.input_dim:
            raise ValueError("reference feature dimension mismatch")
        normalized = [(float(value) - mu) / sigma for value, mu, sigma in zip(vector, self.mean, self.std)]
        value = float(anomaly_score(self.encoder, self.generator, self.discriminator, torch.tensor([normalized], dtype=torch.float32))[0])
        if not np.isfinite(value):
            raise FloatingPointError("non-finite reference score")
        return value
