#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Dict, Any, List

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class SmallAE(nn.Module):
    def __init__(self, input_dim: int, latent_dim: int = 8, hidden_dim: int = 24):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, latent_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, input_dim),
        )

    def forward(self, x):
        z = self.encoder(x)
        out = self.decoder(z)
        return out


class Encoder(nn.Module):
    def __init__(self, input_dim: int, latent_dim: int, hidden_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, latent_dim),
        )

    def forward(self, x):
        return self.net(x)


class Generator(nn.Module):
    def __init__(self, latent_dim: int, output_dim: int, hidden_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, z):
        return self.net(z)


class Discriminator(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int):
        super().__init__()
        self.feat = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LeakyReLU(0.2),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LeakyReLU(0.2),
        )
        self.head = nn.Linear(hidden_dim, 1)

    def forward(self, x):
        feat = self.feat(x)
        logit = self.head(feat)
        return logit, feat


def vectorize_features(feature_order: List[str], means: List[float], stds: List[float], feature_map: Dict[str, Any]) -> torch.Tensor:
    vals = []
    for i, k in enumerate(feature_order):
        v = float(feature_map.get(k, 0.0))
        m = float(means[i])
        s = float(stds[i]) if float(stds[i]) > 1e-8 else 1.0
        vals.append((v - m) / s)
    x = torch.tensor([vals], dtype=torch.float32, device=DEVICE)
    return x


class AEInfer:
    def __init__(self, model_path: str, meta_path: str):
        self.meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        self.feature_order = self.meta["feature_order"]
        self.means = self.meta["means"]
        self.stds = self.meta["stds"]

        state = torch.load(model_path, map_location=DEVICE)

        # 兼容两种保存方式：
        # 1) 直接 save(state_dict)
        # 2) save({"state_dict": ...})
        if isinstance(state, dict) and "state_dict" in state:
            state_dict = state["state_dict"]
        else:
            state_dict = state

        # 从 checkpoint 自动推断结构
        # encoder.0.weight: [hidden_dim, input_dim]
        # encoder.2.weight: [latent_dim, hidden_dim]
        enc0_w = state_dict["encoder.0.weight"]
        enc2_w = state_dict["encoder.2.weight"]

        hidden_dim = int(enc0_w.shape[0])
        input_dim = int(enc0_w.shape[1])
        latent_dim = int(enc2_w.shape[0])

        self.model = SmallAE(
            input_dim=input_dim,
            latent_dim=latent_dim,
            hidden_dim=hidden_dim,
        ).to(DEVICE)

        self.model.load_state_dict(state_dict)
        self.model.eval()

    @torch.no_grad()
    def score(self, feature_map: Dict[str, Any]) -> Dict[str, Any]:
        x = vectorize_features(self.feature_order, self.means, self.stds, feature_map)
        recon = self.model(x)
        recon_err = ((x - recon) ** 2).mean().item()
        return {
            "mode": "ae",
            "score": float(recon_err),
            "recon_err": float(recon_err),
            "feat_err": 0.0,
        }


class GANInfer:
    def __init__(self, model_path: str, meta_path: str):
        self.meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        self.feature_order = self.meta["feature_order"]
        self.means = self.meta["means"]
        self.stds = self.meta["stds"]
        self.alpha = float(self.meta.get("alpha", 0.7))
        self.beta = float(self.meta.get("beta", 0.3))

        input_dim = self.meta["input_dim"]
        latent_dim = self.meta["latent_dim"]
        hidden_dim = 64

        self.E = Encoder(input_dim, latent_dim, hidden_dim).to(DEVICE)
        self.G = Generator(latent_dim, input_dim, hidden_dim).to(DEVICE)
        self.D = Discriminator(input_dim, hidden_dim).to(DEVICE)

        state = torch.load(model_path, map_location=DEVICE)
        self.E.load_state_dict(state["encoder"])
        self.G.load_state_dict(state["generator"])
        self.D.load_state_dict(state["discriminator"])

        self.E.eval()
        self.G.eval()
        self.D.eval()

    @torch.no_grad()
    def score(self, feature_map: Dict[str, Any]) -> Dict[str, Any]:
        x = vectorize_features(self.feature_order, self.means, self.stds, feature_map)

        z = self.E(x)
        recon = self.G(z)

        _, feat_real = self.D(x)
        _, feat_recon = self.D(recon)

        recon_err = ((x - recon) ** 2).mean().item()
        feat_err = ((feat_real - feat_recon) ** 2).mean().item()
        raw_score = self.alpha * recon_err + self.beta * feat_err
        score = float(np.log1p(raw_score))

        return {
            "mode": "sefanogan_es",
            "score": float(score),
            "raw_score": float(raw_score),
            "recon_err": float(recon_err),
            "feat_err": float(feat_err),
        }