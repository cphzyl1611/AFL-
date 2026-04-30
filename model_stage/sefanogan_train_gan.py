#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F


ROOT = Path.home() / "AFLplusplus"
DATA_DIR = ROOT / "model_stage" / "data"
MODEL_DIR = ROOT / "model_stage" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

FEATURES_CSV = DATA_DIR / "sefanogan_features.csv"
TRAIN_JSONL = DATA_DIR / "sefanogan_train.jsonl"
VAL_JSONL = DATA_DIR / "sefanogan_val.jsonl"

OUT_MODEL = MODEL_DIR / "sefanogan_gan_model.pt"
OUT_META = MODEL_DIR / "sefanogan_gan_meta.json"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
LATENT_DIM = 8
HIDDEN_DIM = 64
EPOCHS_GAN = 300
EPOCHS_E = 300
BATCH_SIZE = 16
LR = 1e-3
ALPHA = 0.90
BETA = 0.10


def load_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def load_feature_table(path: Path) -> Tuple[pd.DataFrame, List[str]]:
    df = pd.read_csv(path)

    exclude_cols = {"source_file", "tag", "endpoint"}

    candidate_cols = [c for c in df.columns if c not in exclude_cols]

    feature_order = []
    for c in candidate_cols:
        try:
            df[c].astype("float32")
            feature_order.append(c)
        except Exception:
            print(f"[WARN] skip non-numeric column: {c}")

    return df, feature_order


def build_split_matrix(
    split_rows: List[dict],
    feature_df: pd.DataFrame,
    feature_order: List[str],
) -> Tuple[np.ndarray, List[str], List[str]]:
    """
    返回:
    X: 特征矩阵
    tags: 每行标签
    files: 每行 source_file
    """
    use_files = [r["source_file"] for r in split_rows]
    use_tags = [r["tag"] for r in split_rows]

    sub = feature_df.set_index("source_file").loc[use_files].reset_index()
    X = sub[feature_order].to_numpy(dtype=np.float32)
    return X, use_tags, use_files


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


def standardize_fit(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    means = X.mean(axis=0)
    stds = X.std(axis=0)
    stds = np.where(stds < 1e-8, 1.0, stds)
    Xn = (X - means) / stds
    return Xn, means, stds


def standardize_apply(X: np.ndarray, means: np.ndarray, stds: np.ndarray) -> np.ndarray:
    return (X - means) / stds


def batches(X: torch.Tensor, batch_size: int):
    idx = torch.randperm(X.size(0))
    for i in range(0, X.size(0), batch_size):
        yield X[idx[i:i + batch_size]]


def train_gan(
    G: Generator,
    D: Discriminator,
    X_train: torch.Tensor,
):
    opt_g = torch.optim.Adam(G.parameters(), lr=LR)
    opt_d = torch.optim.Adam(D.parameters(), lr=LR)

    bce = nn.BCEWithLogitsLoss()

    for epoch in range(EPOCHS_GAN):
        g_loss_sum = 0.0
        d_loss_sum = 0.0
        n_steps = 0

        for xb in batches(X_train, BATCH_SIZE):
            n_steps += 1
            bs = xb.size(0)

            # ---- train D ----
            z = torch.randn(bs, LATENT_DIM, device=DEVICE)
            fake = G(z).detach()

            real_logits, _ = D(xb)
            fake_logits, _ = D(fake)

            real_y = torch.ones_like(real_logits)
            fake_y = torch.zeros_like(fake_logits)

            d_loss = bce(real_logits, real_y) + bce(fake_logits, fake_y)
            opt_d.zero_grad()
            d_loss.backward()
            opt_d.step()

            # ---- train G ----
            z = torch.randn(bs, LATENT_DIM, device=DEVICE)
            fake = G(z)
            fake_logits, _ = D(fake)
            g_loss = bce(fake_logits, torch.ones_like(fake_logits))

            opt_g.zero_grad()
            g_loss.backward()
            opt_g.step()

            g_loss_sum += float(g_loss.item())
            d_loss_sum += float(d_loss.item())

        if epoch % 50 == 0 or epoch == EPOCHS_GAN - 1:
            print(
                f"[GAN] epoch={epoch:03d} "
                f"d_loss={d_loss_sum/max(n_steps,1):.6f} "
                f"g_loss={g_loss_sum/max(n_steps,1):.6f}"
            )


def train_encoder(
    E: Encoder,
    G: Generator,
    D: Discriminator,
    X_train: torch.Tensor,
):
    opt_e = torch.optim.Adam(E.parameters(), lr=LR)

    for epoch in range(EPOCHS_E):
        loss_sum = 0.0
        n_steps = 0

        for xb in batches(X_train, BATCH_SIZE):
            n_steps += 1
            z = E(xb)
            recon = G(z)

            _, feat_real = D(xb)
            _, feat_recon = D(recon)

            recon_loss = F.mse_loss(recon, xb)
            feat_loss = F.mse_loss(feat_recon, feat_real)
            loss = ALPHA * recon_loss + BETA * feat_loss

            opt_e.zero_grad()
            loss.backward()
            opt_e.step()

            loss_sum += float(loss.item())

        if epoch % 50 == 0 or epoch == EPOCHS_E - 1:
            print(f"[ENC] epoch={epoch:03d} loss={loss_sum/max(n_steps,1):.6f}")


@torch.no_grad()
def score_samples(
    E: Encoder,
    G: Generator,
    D: Discriminator,
    X: torch.Tensor,
) -> np.ndarray:
    z = E(X)
    recon = G(z)

    _, feat_real = D(X)
    _, feat_recon = D(recon)

    recon_err = ((X - recon) ** 2).mean(dim=1)
    feat_err = ((feat_real - feat_recon) ** 2).mean(dim=1)
    score = ALPHA * recon_err + BETA * feat_err
    score = torch.log1p(score)
    return score.cpu().numpy()


def summarize_scores(scores: np.ndarray) -> Dict[str, float]:
    return {
        "count": int(len(scores)),
        "mean": float(scores.mean()) if len(scores) else 0.0,
        "min": float(scores.min()) if len(scores) else 0.0,
        "max": float(scores.max()) if len(scores) else 0.0,
    }


def main():
    feature_df, feature_order = load_feature_table(FEATURES_CSV)
    train_rows = load_jsonl(TRAIN_JSONL)
    val_rows = load_jsonl(VAL_JSONL)

    X_train_raw, train_tags, _ = build_split_matrix(train_rows, feature_df, feature_order)
    X_val_raw, val_tags, _ = build_split_matrix(val_rows, feature_df, feature_order)

    # 只用 normal 训练
    train_normal_mask = np.array([t == "normal" for t in train_tags], dtype=bool)
    X_train_normal_raw = X_train_raw[train_normal_mask]

    X_train_norm, means, stds = standardize_fit(X_train_normal_raw)
    X_train_all_norm = standardize_apply(X_train_raw, means, stds)
    X_val_all_norm = standardize_apply(X_val_raw, means, stds)

    X_train_tensor = torch.tensor(X_train_norm, dtype=torch.float32, device=DEVICE)
    X_train_all_tensor = torch.tensor(X_train_all_norm, dtype=torch.float32, device=DEVICE)
    X_val_all_tensor = torch.tensor(X_val_all_norm, dtype=torch.float32, device=DEVICE)

    input_dim = len(feature_order)

    G = Generator(LATENT_DIM, input_dim, HIDDEN_DIM).to(DEVICE)
    D = Discriminator(input_dim, HIDDEN_DIM).to(DEVICE)
    E = Encoder(input_dim, LATENT_DIM, HIDDEN_DIM).to(DEVICE)

    train_gan(G, D, X_train_tensor)
    train_encoder(E, G, D, X_train_tensor)

    train_scores = score_samples(E, G, D, X_train_all_tensor)
    val_scores = score_samples(E, G, D, X_val_all_tensor)

    train_normal_scores = train_scores[np.array([t == "normal" for t in train_tags])]
    val_normal_scores = val_scores[np.array([t == "normal" for t in val_tags])]
    val_border_scores = val_scores[np.array([t == "border" for t in val_tags])]
    val_abnormal_scores = val_scores[np.array([t == "abnormal" for t in val_tags])]

    torch.save(
        {
            "encoder": E.state_dict(),
            "generator": G.state_dict(),
            "discriminator": D.state_dict(),
        },
        OUT_MODEL,
    )

    meta = {
        "model_type": "sefanogan_es",
        "feature_order": feature_order,
        "input_dim": input_dim,
        "latent_dim": LATENT_DIM,
        "alpha": ALPHA,
        "beta": BETA,
        "train_count": int(len(train_tags)),
        "train_normal_count": int(train_normal_mask.sum()),
        "val_count": int(len(val_tags)),
        "means": means.tolist(),
        "stds": stds.tolist(),
        "train_normal_score": summarize_scores(train_normal_scores),
        "val_normal_score": summarize_scores(val_normal_scores),
        "val_border_score": summarize_scores(val_border_scores),
        "val_abnormal_score": summarize_scores(val_abnormal_scores),
    }

    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] wrote {OUT_MODEL}")
    print(f"[OK] wrote {OUT_META}")
    print(f"train_count={meta['train_count']}")
    print(f"train_normal_count={meta['train_normal_count']}")
    print(f"val_count={meta['val_count']}")
    print(f"train_normal_score_mean={meta['train_normal_score']['mean']:.6f}")
    print(f"val_normal_score_mean={meta['val_normal_score']['mean']:.6f}")
    print(f"val_border_score_mean={meta['val_border_score']['mean']:.6f}")
    print(f"val_abnormal_score_mean={meta['val_abnormal_score']['mean']:.6f}")


if __name__ == "__main__":
    main()