#!/usr/bin/env python3
import json
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim

from feature_extract import FEATURE_ORDER, extract_features_from_obj


ROOT = Path.home() / "AFLplusplus"
DATA_DIR = ROOT / "model_stage" / "data"
MODEL_DIR = ROOT / "model_stage" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

TRAIN_JSONL = DATA_DIR / "sefanogan_train.jsonl"
VAL_JSONL = DATA_DIR / "sefanogan_val.jsonl"

OUT_MODEL = MODEL_DIR / "sefanogan_ae_model.pt"
OUT_META = MODEL_DIR / "sefanogan_ae_meta.json"


class SmallAE(nn.Module):
    def __init__(self, input_dim: int, latent_dim: int = 8):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 24),
            nn.ReLU(),
            nn.Linear(24, latent_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 24),
            nn.ReLU(),
            nn.Linear(24, input_dim),
        )

    def forward(self, x):
        z = self.encoder(x)
        out = self.decoder(z)
        return out


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def row_to_feature_dict(row):
    body = row["body"]
    body_bytes = len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    return extract_features_from_obj(body, body_bytes=body_bytes)


def vectorize_feature_dict(feat):
    return [float(feat.get(k, 0.0)) for k in FEATURE_ORDER]


def compute_mean_std(vectors):
    dim = len(vectors[0])
    means = []
    stds = []
    for j in range(dim):
        col = [v[j] for v in vectors]
        mean = sum(col) / len(col)
        var = sum((x - mean) ** 2 for x in col) / len(col)
        std = var ** 0.5
        if std < 1e-6:
            std = 1.0
        means.append(mean)
        stds.append(std)
    return means, stds


def normalize_vectors(vectors, means, stds):
    out = []
    for v in vectors:
        z = [(v[i] - means[i]) / stds[i] for i in range(len(v))]
        out.append(z)
    return out


def train_ae(train_x, input_dim, latent_dim=8, epochs=400, lr=1e-3):
    device = torch.device("cpu")
    model = SmallAE(input_dim=input_dim, latent_dim=latent_dim).to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    x = torch.tensor(train_x, dtype=torch.float32, device=device)

    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        recon = model(x)
        loss = criterion(recon, x)
        loss.backward()
        optimizer.step()

        if epoch % 50 == 0 or epoch == epochs - 1:
            print(f"[AE] epoch={epoch:03d} loss={loss.item():.6f}")

    return model


def reconstruction_errors(model, xs):
    device = torch.device("cpu")
    x = torch.tensor(xs, dtype=torch.float32, device=device)
    model.eval()
    with torch.no_grad():
        recon = model(x)
        errs = torch.mean((recon - x) ** 2, dim=1)
    return errs.cpu().tolist()


def summarize(xs):
    if not xs:
        return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": len(xs),
        "mean": sum(xs) / len(xs),
        "min": min(xs),
        "max": max(xs),
    }


def main():
    train_rows = load_jsonl(TRAIN_JSONL)
    val_rows = load_jsonl(VAL_JSONL)

    train_normal_rows = [r for r in train_rows if r.get("tag") == "normal"]
    if not train_normal_rows:
        raise ValueError("no normal rows found in train set")

    train_feats = [row_to_feature_dict(r) for r in train_normal_rows]
    train_vecs = [vectorize_feature_dict(f) for f in train_feats]

    means, stds = compute_mean_std(train_vecs)
    train_z = normalize_vectors(train_vecs, means, stds)

    input_dim = len(FEATURE_ORDER)
    latent_dim = 8

    model = train_ae(train_z, input_dim=input_dim, latent_dim=latent_dim)

    train_errs = reconstruction_errors(model, train_z)

    val_by_tag = {"normal": [], "border": [], "abnormal": []}
    for row in val_rows:
        tag = row.get("tag")
        if tag not in val_by_tag:
            continue
        feat = row_to_feature_dict(row)
        vec = vectorize_feature_dict(feat)
        z = normalize_vectors([vec], means, stds)[0]
        err = reconstruction_errors(model, [z])[0]
        val_by_tag[tag].append(err)

    torch.save(model.state_dict(), OUT_MODEL)

    meta = {
        "model_type": "small_autoencoder",
        "feature_order": FEATURE_ORDER,
        "input_dim": input_dim,
        "latent_dim": latent_dim,
        "train_count": len(train_rows),
        "train_normal_count": len(train_normal_rows),
        "val_count": len(val_rows),
        "means": means,
        "stds": stds,
        "train_normal_recon": summarize(train_errs),
        "val_normal_recon": summarize(val_by_tag["normal"]),
        "val_border_recon": summarize(val_by_tag["border"]),
        "val_abnormal_recon": summarize(val_by_tag["abnormal"]),
    }

    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[OK] wrote {OUT_MODEL}")
    print(f"[OK] wrote {OUT_META}")
    print(f"train_count={meta['train_count']}")
    print(f"train_normal_count={meta['train_normal_count']}")
    print(f"val_count={meta['val_count']}")
    print(f"train_normal_recon_mean={meta['train_normal_recon']['mean']:.6f}")
    print(f"val_normal_recon_mean={meta['val_normal_recon']['mean']:.6f}")
    print(f"val_border_recon_mean={meta['val_border_recon']['mean']:.6f}")
    print(f"val_abnormal_recon_mean={meta['val_abnormal_recon']['mean']:.6f}")


if __name__ == "__main__":
    main()